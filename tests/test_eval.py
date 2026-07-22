"""Unit tests for the positioning eval harness scorer (tools/bps_eval.py).

The scorer is pure Python (stdlib only) and is what every later
precision/jumpiness change will be judged against, so its metrics must be
correct on known synthetic input. The HTTP `record` path is not exercised here
(it needs a live HA); these cover the scoring maths.
"""
import json
import math
import sys
from pathlib import Path

# tools/ is not a package; put it on the path so `import bps_eval` resolves.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import bps_eval as ev  # noqa: E402


SCALE = 40.0  # px per metre, matches the positioning tests' convention


def _write(tmp_path, samples, scales=None):
    p = tmp_path / "rec.jsonl"
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "header", "started": 0.0,
                             "scales": scales if scales is not None else {"F": SCALE}}) + "\n")
        for s in samples:
            fh.write(json.dumps(s) + "\n")
    return str(p)


def _sample(t, x, y, raw=None, floor="F", zone="living"):
    return {"ent": "beacon", "updated": float(t), "cords": [x, y],
            "raw": list(raw) if raw else [x, y], "floor": floor, "zone": zone,
            "rms_m": 0.5, "conf": 0.8}


# --- percentile ------------------------------------------------------------
def test_percentile_interpolates():
    assert ev.percentile([0, 10], 50) == 5.0
    assert ev.percentile([0, 10, 20, 30, 40], 95) == 38.0
    assert ev.percentile([7], 95) == 7
    assert math.isnan(ev.percentile([], 50))


# --- stationary scatter (CEP) ----------------------------------------------
def test_stationary_cep_in_metres():
    # Four points 40 px (= 1 m) from a centroid at (100, 100): CEP is 1 m.
    pts = [(140, 100), (60, 100), (100, 140), (100, 60)]
    samples = [_sample(i, x, y) for i, (x, y) in enumerate(pts)]
    m = ev.score_entity(samples, {"F": SCALE})
    assert m["published"]["units"] == "m"
    assert abs(m["published"]["cep50"] - 1.0) < 1e-6
    assert abs(m["published"]["cep95"] - 1.0) < 1e-6


def test_bias_uses_truth_and_scale():
    # Centroid sits 80 px (= 2 m) from the declared truth.
    pts = [(180, 100), (180, 100)]
    samples = [_sample(i, x, y) for i, (x, y) in enumerate(pts)]
    m = ev.score_entity(samples, {"F": SCALE}, truth=(100.0, 100.0))
    assert abs(m["published"]["bias"] - 2.0) < 1e-6


def test_pixel_units_when_scale_unknown():
    # No scale for the sampled floor -> report in pixels, never divide by a guess.
    samples = [_sample(0, 100, 100), _sample(1, 140, 100)]
    m = ev.score_entity(samples, {})   # empty scale map
    assert m["published"]["units"] == "px"
    assert abs(m["published"]["step_median"] - 40.0) < 1e-6  # raw pixels, not /40


# --- jumpiness (step length) -----------------------------------------------
def test_step_length_and_cross_floor_skip():
    # Steps of 1 m, 1 m, then a floor change (must NOT count as a planar step).
    samples = [
        _sample(0, 100, 100),
        _sample(1, 140, 100),            # +1 m
        _sample(2, 180, 100),            # +1 m
        _sample(3, 500, 500, floor="G"),  # floor change: skipped
    ]
    m = ev.score_entity(samples, {"F": SCALE, "G": SCALE})
    assert abs(m["published"]["step_median"] - 1.0) < 1e-6
    assert abs(m["published"]["step_max"] - 1.0) < 1e-6   # the huge jump was skipped
    assert m["floor_flaps"] == 1


def test_raw_vs_published_are_scored_separately():
    # Published is pinned (filter did its job); raw is noisy. Both reported.
    samples = [
        _sample(0, 100, 100, raw=(100, 100)),
        _sample(1, 100, 100, raw=(140, 100)),
        _sample(2, 100, 100, raw=(60, 100)),
    ]
    m = ev.score_entity(samples, {"F": SCALE})
    assert m["published"]["step_p95"] == 0.0        # published never moved
    assert m["raw"]["step_p95"] > 0.0               # raw jumped around


# --- flap counts -----------------------------------------------------------
def test_zone_flap_count():
    samples = [
        _sample(0, 100, 100, zone="a"),
        _sample(1, 100, 100, zone="a"),
        _sample(2, 100, 100, zone="b"),   # flap
        _sample(3, 100, 100, zone="a"),   # flap
    ]
    m = ev.score_entity(samples, {"F": SCALE})
    assert m["zone_flaps"] == 2
    assert m["floor_flaps"] == 0


# --- walk cross-track ------------------------------------------------------
def test_crosstrack_against_polyline():
    # A straight path along y=100; samples sit 40 px (= 1 m) off it.
    waypoints = [(0.0, 100.0), (400.0, 100.0)]
    samples = [_sample(0, 100, 140), _sample(1, 200, 60)]  # ±1 m off the line
    m = ev.score_entity(samples, {"F": SCALE}, waypoints=waypoints)
    assert abs(m["published"]["crosstrack_rms"] - 1.0) < 1e-6
    assert abs(m["published"]["crosstrack_p95"] - 1.0) < 1e-2


# --- end to end via a file -------------------------------------------------
def test_load_and_score_roundtrip(tmp_path):
    path = _write(tmp_path, [_sample(0, 100, 100), _sample(1, 140, 100)])
    result = ev.score_recording(path)
    assert set(result) == {"beacon"}
    assert result["beacon"]["n"] == 2
    assert result["beacon"]["scale_px_per_m"] == SCALE


def test_samples_are_sorted_by_updated(tmp_path):
    # Out-of-order arrival must not inflate step length.
    path = _write(tmp_path, [_sample(2, 180, 100), _sample(0, 100, 100), _sample(1, 140, 100)])
    m = ev.score_recording(path)["beacon"]
    assert abs(m["published"]["step_max"] - 1.0) < 1e-6  # 1 m steps, not the 2 m out-of-order gap


# --- resilience to non-pristine recordings ---------------------------------
def test_truncated_final_line_is_skipped(tmp_path):
    # A recording killed mid-flush (the recorder appends line by line) leaves a
    # partial trailing line; it must be skipped, not abort the whole score.
    path = tmp_path / "rec.jsonl"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "header", "scales": {"F": SCALE}}) + "\n")
        fh.write(json.dumps(_sample(0, 100, 100)) + "\n")
        fh.write('{"ent":"beacon","updated":1.0,"cords":[140,10')  # truncated
    result = ev.score_recording(str(path))
    assert result["beacon"]["n"] == 1  # the good sample survives


def test_row_missing_ent_is_skipped(tmp_path):
    path = tmp_path / "rec.jsonl"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "header", "scales": {"F": SCALE}}) + "\n")
        fh.write(json.dumps({"updated": 0.0, "cords": [1, 2]}) + "\n")  # no 'ent'
        fh.write(json.dumps(_sample(1, 100, 100)) + "\n")
    result = ev.score_recording(str(path))
    assert set(result) == {"beacon"} and result["beacon"]["n"] == 1


def test_null_updated_does_not_crash_sort(tmp_path):
    # Mixed present/null `updated` must sort deterministically, not raise
    # TypeError comparing None to float.
    s_null = _sample(0, 100, 100)
    s_null["updated"] = None
    path = _write(tmp_path, [s_null, _sample(1, 140, 100)])
    m = ev.score_recording(path)["beacon"]
    assert m["n"] == 2
    assert isinstance(m["duration_s"], (int, float))
