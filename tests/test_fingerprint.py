"""Fingerprint positioning and truth marks (fingerprint.py, truth.py)."""
import math

from bps import fingerprint as fpm
from bps import truth

# Four receivers in a 10 m square (scale 10 px/m), plus one upstairs.
LAYOUT = {"floor": [
    {"name": "Ground", "scale": 10, "receivers": [
        {"entity_id": "a", "cords": {"x": 0, "y": 0}},
        {"entity_id": "b", "cords": {"x": 100, "y": 0}, "correction": 2.0},
        {"entity_id": "c", "cords": {"x": 0, "y": 100}},
        {"entity_id": "d", "cords": {"x": 100, "y": 100}},
    ]},
    {"name": "Upstairs", "scale": 10, "receivers": [{"entity_id": "u", "cords": {"x": 50, "y": 50}}]},
]}
POS = {r["entity_id"]: (r["cords"]["x"] / 10, r["cords"]["y"] / 10) for f in LAYOUT["floor"] for r in f["receivers"]}


def dist(p, q):
    return math.hypot(p[0] - q[0], p[1] - q[1])


def samples(wall=1.0):
    """Receiver pairs as the calibration samples them. ``wall`` stretches every
    range that crosses from the a/c side to the b/d side (a wall in the middle)."""
    out = {}
    for tx in "abcd":
        for rx in "abcd":
            if tx == rx:
                continue
            d = dist(POS[tx], POS[rx])
            if (tx in "ac") != (rx in "ac"):
                d *= wall
            out[f"{tx}|{rx}"] = [d / (2.0 if rx == "b" else 1.0)] * 5   # b reads short: corrected x2
    return out


def test_references_apply_corrections_and_skip_thin_pairs():
    s = samples()
    s["a|c"] = [10.0, 10.0]          # too few samples: not part of a's reference
    refs = fpm.references(LAYOUT, s)
    assert set(refs) == {"Ground"}    # nobody ranged the upstairs receiver
    a = next(r for r in refs["Ground"] if r["slug"] == "a")
    assert a["vector"]["a"] == fpm.SELF_DISTANCE_M
    assert abs(a["vector"]["b"] - 10.0) < 1e-9       # 5 m raw x correction 2
    assert "c" not in a["vector"]


def test_match_lands_near_the_receiver_whose_fingerprint_fits():
    refs = fpm.references(LAYOUT, samples(wall=2.0))
    # standing next to receiver a: the wall stretches b and d for the device too
    thing = {"a": 0.6, "b": 20.0, "c": 10.0, "d": 28.0}
    m = fpm.match(thing, refs["Ground"])
    assert dist((m["x"] / 10, m["y"] / 10), POS["a"]) < 2.0
    assert m["refs"][0][0] == "a" and m["conf"] > 0.5


def test_gain_learns_toward_the_devices_scale():
    g = fpm.Gain()
    for _ in range(200):
        g.learn(2.0, 1.0, entity="watch")
    assert g.get("watch") > 3.0 and g.get() > 1.5
    assert g.get() <= fpm.GAIN_MAX
    g.learn(float("nan"))
    g.learn(-1)


def test_blend():
    fp = {"x": 100.0, "y": 0.0, "conf": 0.9, "ratio": 1.0}
    assert fpm.blend((0.0, 0.0), fp, 0) == (0.0, 0.0)
    assert fpm.blend((0.0, 0.0), fp, 0.5) == (50.0, 0.0)
    assert fpm.blend((0.0, 0.0), {**fp, "ratio": 3.0}, 1.0) == (0.0, 0.0)    # nothing alike: no pull
    assert fpm.blend((0.0, 0.0), {**fp, "conf": 0.1}, 1.0) == (0.0, 0.0)


def test_truth_marks_measure_each_method():
    m = truth.new_mark("phone", "Ground", 10, 10, 10, now=0)
    assert truth.collecting([m], "phone", now=10) is m
    assert truth.collecting([m], "phone", now=100) is None
    for _ in range(6):
        # trilateration 3 m off, fingerprint 1 m off, both along x
        truth.add_cycle(m, "Ground", (40, 10), (20, 10), 1.0, {"a": 1.0, "b": 9.0}, 2.0)
    truth.add_cycle(m, "Upstairs", (10, 10), None, None, {}, 1.0)
    ev = truth.evaluate([m])
    assert ev["summary"]["tri"] == 3.0 and ev["summary"]["fp"] == 1.0
    assert ev["summary"]["w0.5"] == 2.0 and ev["best_weight"] == 1.0
    assert ev["marks"][0]["wrong_floor"] == 1
    ref = truth.reference(m)
    assert ref["vector"] == {"a": 0.5, "b": 4.5} and (ref["x"], ref["y"]) == (10, 10)
    # a mark becomes a reference where no receiver sits
    refs = fpm.references(LAYOUT, samples(), extra=[ref])
    assert any(r["slug"].startswith("mark:") for r in refs["Ground"])


def test_too_short_marks_tell_nothing_and_are_trimmed():
    m = truth.new_mark("phone", "Ground", 0, 0, 10, now=0)
    truth.add_cycle(m, "Ground", (0, 0), None, None, {}, 1.0)
    assert truth.evaluate([m])["usable"] == 0
    assert truth.trim([m], now=1000) == []
