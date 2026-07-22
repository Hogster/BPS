"""Regression tests for the positioning maths, run against the real `bps`
module (Home Assistant stubbed by conftest). Covers the pieces most likely to
regress silently: the trilateration solver, receiver mount-height slant
correction, 3D calibration ground truth, and the floor hypothesis-competition
election helpers.
"""
import asyncio
import math

import bps
from bps import calibration as cal_mod

SCALE = 40.0  # px per metre


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# --------------------------------------------------------------------------- #
# Trilateration solver
# --------------------------------------------------------------------------- #
def test_trilaterate_recovers_known_point():
    d = math.hypot(5, 5)
    pts = [(0, 0, d), (10, 0, d), (0, 10, d)]
    x, y = bps.trilaterate(pts)
    assert abs(x - 5) < 0.05 and abs(y - 5) < 0.05


def test_trilaterate_zero_radius_survives():
    # Regression: a 0 radius must not divide-by-zero and abort the solve.
    res = bps.trilaterate([(0, 0, 0.0), (10, 0, 10.0), (0, 10, 10.0)])
    assert res is not None


def test_min_weight_radius_tames_a_spuriously_short_reading():
    truth = (140.0, 140.0)
    far = [
        (400.0, 140.0, 260.0),
        (140.0, 400.0, 260.0),
        (400.0, 400.0, math.hypot(260, 260)),
    ]
    liar = (100.0, 100.0, 0.01)          # claims the tracker is basically on it
    honest = (140.0, 140.0, 20.0)        # 0.5 m at 40 px/m, corroborated
    pts = far + [liar, honest]
    d_unclamped = math.dist(bps.trilaterate(pts), truth)
    d_clamped = math.dist(bps.trilaterate(pts, min_weight_radius=20.0), truth)
    assert d_clamped < d_unclamped - 15.0  # the clamp pulls the fit off the liar


# --------------------------------------------------------------------------- #
# Tracker height + slant correction
# --------------------------------------------------------------------------- #
def test_tracker_height_default_and_override():
    assert bps._tracker_height({}) == bps.TRACKER_HEIGHT_M
    assert bps._tracker_height({"tracker_height": 0.3}) == 0.3
    assert bps._tracker_height({"tracker_height": 99}) == bps.TRACKER_HEIGHT_M  # out of range


def _run_radii(state, unit="m", height=None, tracker_height=None):
    class St:
        def __init__(self):
            self.state = state
            self.attributes = {"unit_of_measurement": unit}

    class Hass:
        states = type("S", (), {"get": staticmethod(lambda _eid: St())})()

    rec = {"entity_id": "probe", "cords": {"x": 0, "y": 0}}
    if height is not None:
        rec["height"] = height
    data = {"floor": [{"name": "F", "scale": SCALE, "receivers": [rec]}]}
    if tracker_height is not None:
        data["tracker_height"] = tracker_height
    run(bps.update_receiver_radii(Hass(), {"entity": "phone", "data": data}))
    return rec


def test_no_height_leaves_distance_alone():
    r = _run_radii("2.3")
    assert abs(r["distance"] - 2.3) < 1e-9
    assert abs(r["cords"]["r"] - 92.0) < 1e-6


def test_height_removes_vertical_leg_from_radius_only():
    # dz = 1.2 -> horizontal sqrt(2.3^2 - 1.2^2) = 1.962 m into the radius;
    # the election "distance" stays the calibrated slant (cross-floor safe).
    r = _run_radii("2.3", height=2.2)
    assert abs(r["cords"]["r"] - 1.9621 * SCALE) < 0.1
    assert abs(r["distance"] - 2.3) < 1e-9


def test_height_underneath_clamps_radius_to_zero():
    r = _run_radii("1.0", height=2.2)  # slant < vertical leg
    assert r["cords"]["r"] == 0.0


def test_nan_and_out_of_range_height_ignored():
    assert abs(_run_radii("2.3", height=float("nan"))["cords"]["r"] - 92.0) < 1e-6
    assert abs(_run_radii("2.3", height=float("inf"))["cords"]["r"] - 92.0) < 1e-6
    assert abs(_run_radii("2.3", height=25)["cords"]["r"] - 92.0) < 1e-6


# --------------------------------------------------------------------------- #
# Calibration ground truth (2D vs 3D)
# --------------------------------------------------------------------------- #
def _cal(ha=None, hb=None):
    return {"receivers": {
        "a": {"x": 0.0, "y": 0.0, "scale": SCALE, "floor": "F", "height": ha},
        "b": {"x": 120.0, "y": 0.0, "scale": SCALE, "floor": "F", "height": hb},
    }}


def test_true_distance_2d_when_heights_absent_or_partial():
    assert abs(cal_mod._true_distance_m(_cal(), "a", "b") - 3.0) < 1e-9
    assert abs(cal_mod._true_distance_m(_cal(ha=2.2), "a", "b") - 3.0) < 1e-9


def test_true_distance_3d_when_both_heights_present():
    # 3 m apart on the map, 0.3 m vs 2.2 m high -> sqrt(9 + 1.9^2) = 3.551 m.
    assert abs(cal_mod._true_distance_m(_cal(ha=0.3, hb=2.2), "a", "b") - 3.5511) < 1e-3


# --------------------------------------------------------------------------- #
# Floor election helpers
# --------------------------------------------------------------------------- #
def test_score_rewards_agreement_and_coverage():
    good = [(x, y, math.hypot(x - 400, y - 400), 1.0)
            for (x, y) in [(0, 0), (800, 0), (0, 800), (800, 800), (400, 0)]]
    conf, rms, cov = bps._score_floor_fit((400.0, 400.0), good, SCALE)
    assert rms < 1e-6 and cov == 1.0 and conf > 0.99

    bad = [(0, 0, 40.0, 1.0), (800, 0, 40.0, 1.0), (0, 800, 40.0, 1.0)]
    conf_bad, rms_bad, _ = bps._score_floor_fit((400.0, 400.0), bad, SCALE)
    assert rms_bad > 5.0 and conf_bad < conf


def test_probabilities_converge_and_drop_renamed():
    bps._floor_probability.clear()
    for _ in range(30):
        probs = bps._update_floor_probabilities("e", {"a": 0.8, "b": 0.2})
    assert abs(probs["a"] - 0.8) < 0.02
    probs = bps._update_floor_probabilities("e", {"c": 1.0}, valid_floors={"c"})
    assert "a" not in probs and "b" not in probs


def test_elect_hysteresis_and_dwell():
    # No incumbent: adopt the best immediately.
    floor, ch = bps._elect_floor({"a": 0.6, "b": 0.4}, None, {"a", "b"}, None)
    assert floor == "a" and ch is None
    # Incumbent holds within the margin.
    floor, _ = bps._elect_floor({"a": 0.52, "b": 0.48}, "b", {"a", "b"}, None)
    assert floor == "b"
    # A leading challenger must persist FLOOR_SWITCH_CYCLES before switching.
    ch = None
    seen = []
    for _ in range(4):
        floor, ch = bps._elect_floor({"a": 0.7, "b": 0.3}, "b", {"a", "b"}, ch)
        seen.append(floor)
    assert seen[:bps.FLOOR_SWITCH_CYCLES] == ["b"] * (bps.FLOOR_SWITCH_CYCLES - 1) + ["a"]
