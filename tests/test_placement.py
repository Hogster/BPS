"""Receiver placement advisor (pure numpy/shapely, no HA)."""
import numpy as np

from custom_components.bps.placement import (
    DEFAULT_A, analyze, analyze_floor, error_field, fit_noise_model, usage_from_history,
)

SCALE = 100.0  # px per metre


def _rect(name, x0, y0, x1, y1):
    return {"entity_id": name, "poly": True,
            "cords": [{"x": x0, "y": y0}, {"x": x1, "y": y0}, {"x": x1, "y": y1}, {"x": x0, "y": y1}]}


def _rx(name, x, y):
    return {"entity_id": name, "cords": {"x": x, "y": y}}


def _floor():
    # two 6 m x 4 m rooms side by side; all receivers in the left room
    return {"name": "F", "scale": SCALE,
            "zones": [_rect("Left", 0, 0, 600, 400), _rect("Right", 600, 0, 1200, 400)],
            "receivers": [_rx("r1", 50, 50), _rx("r2", 550, 50), _rx("r3", 300, 380)]}


def test_geometry_beats_distance():
    gx, gy = np.array([3.0, 3.0]), np.array([2.0, 2.0])
    around = [(0.0, 0.0, 1), (6.0, 0.0, 1), (3.0, 4.0, 1)]
    in_a_row = [(1.0, 2.0, 1), (0.5, 2.0, 1), (0.0, 2.0, 1)]   # all on one side, closer
    e_around = error_field(gx, gy, around, 0.5, 0.0)[0]
    e_row = error_field(gx, gy, in_a_row, 0.5, 0.0)[0]
    assert e_around < e_row


def test_out_of_range_is_capped():
    e = error_field(np.array([100.0]), np.array([100.0]), [(0.0, 0.0, 1)], 0.5, 0.0)
    assert e[0] == 8.0


def test_noise_model_defaults_without_calibration():
    a, b, factor, n = fit_noise_model([], {})
    assert (a, n, factor) == (DEFAULT_A, 0, {})


def test_noise_model_fit_and_receiver_factor():
    matrix, samples = [], {}
    rng = np.random.default_rng(1)
    for i in range(12):
        d = 2.0 + i
        bad = i % 3 == 0
        matrix.append({"tx": "bad" if bad else f"t{i}", "rx": f"r{i}", "true_m": d,
                       "measured_m": d * (2.0 if bad else 1.1), "corrected_m": d * (2.0 if bad else 1.1)})
        samples[f"{'bad' if bad else f't{i}'}|r{i}"] = list(d * np.exp(rng.normal(0, 0.2, 20)))
    a, b, factor, n = fit_noise_model(matrix, samples)
    assert n == 12 and a > 0
    assert factor["bad"] > 1.0


def test_usage_dwell_flaps_and_bounces():
    rows = [(0, "Kitchen"), (600, "Livingroom"), (630, "Kitchen"), (1800, "unavailable"), (1900, "Kitchen")]
    dwell, visits, flaps, bounces = usage_from_history({"sensor.x_bps_zone": rows}, 2000)
    assert dwell["Kitchen"] == 600 + 1170 + 100
    assert flaps["Livingroom"] == 1 and bounces[("Kitchen", "Livingroom")] == 1
    assert "unavailable" not in dwell


def test_pick_lands_in_the_uncovered_room():
    r = analyze_floor(_floor(), (0.5, 0.0, {}), ({}, {}, {}))
    assert r["ok"]
    worst = r["zones"][0]["zone"]
    assert worst == "Right"
    assert r["picks"][0]["zone"] == "Right"
    assert r["picks"][0]["gain_pct"] > 0
    g = r["grid"]
    assert len(g["err"]) == g["nx"] * g["ny"] == len(g["in_zone"])


def test_usage_weighting_moves_the_pick():
    floor = _floor()
    floor["receivers"] = [_rx("r1", 600, 200)]  # one receiver on the shared wall
    left = analyze_floor(floor, (0.5, 0.0, {}), ({"Left": 36000.0}, {}, {}))
    right = analyze_floor(floor, (0.5, 0.0, {}), ({"Right": 36000.0}, {}, {}))
    assert left["picks"][0]["zone"] == "Left"
    assert right["picks"][0]["zone"] == "Right"


def test_floor_without_scale_is_reported_not_crashing():
    floor = _floor()
    floor["scale"] = None
    r = analyze({"floor": [floor]}, None, {}, 0)
    assert r["floors"][0]["ok"] is False


def test_own_usage_stats_flaps_and_bounces():
    from custom_components.bps.usage import UsageStats
    u = UsageStats()
    t0 = 1_800_000_000
    u.feed("sensor.a_bps_zone", "Kitchen", t0)
    u.feed("sensor.a_bps_zone", "Livingroom", t0 + 600)
    u.feed("sensor.a_bps_zone", "Kitchen", t0 + 620)
    u.feed("sensor.a_bps_zone", "unavailable", t0 + 900)
    dwell, visits, flaps, bounces, days = u.summary()
    assert dwell["Kitchen"] == 600 + 280 and dwell["Livingroom"] == 20
    assert flaps["Livingroom"] == 1 and bounces[("Kitchen", "Livingroom")] == 1
    assert days == 1
    again = UsageStats(u.to_data())
    assert again.summary()[0]["Kitchen"] == 880


def test_own_usage_used_when_recorder_has_nothing():
    own = ({"Right": 36000.0}, {"Right": 3}, {}, {}, 2)
    floor = _floor()
    floor["receivers"] = [_rx("r1", 600, 200)]
    r = analyze({"floor": [floor]}, None, {}, 0, own)
    assert r["usage"]["source"] == "bps" and r["usage"]["days"] == 2
    assert r["floors"][0]["picks"][0]["zone"] == "Right"
