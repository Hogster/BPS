"""Person tracker choice, dwell and settings validation (pure, no HA)."""
import pytest

from custom_components.bps.persons import (
    DEFAULT_SETTINGS, Dwell, guess_charging, guess_kind, merge_settings,
    pick_tracker, suggest_trackers, validate_settings,
)

CFG = dict(DEFAULT_SETTINGS["tracking"])
NOW = 10_000.0
TRACKERS = [{"key": "band", "kind": "wearable", "charging": None},
            {"key": "phone", "kind": "phone", "charging": "sensor.phone_battery_state"}]


def info(zone="Kitchen", age=5, moved_ago=5, charging=False):
    return {"zone": zone, "updated": NOW - age, "moved_at": NOW - moved_ago, "charging": charging}


def test_first_usable_wins():
    key, st = pick_tracker(TRACKERS, {"band": info(), "phone": info()}, NOW, CFG)
    assert key == "band" and st == {"band": "active", "phone": None}


def test_charging_and_stale_fall_back():
    key, st = pick_tracker(TRACKERS, {"band": info(charging=True), "phone": info()}, NOW, CFG)
    assert key == "phone" and st["band"] == "charging"
    key, st = pick_tracker(TRACKERS, {"band": info(age=999), "phone": info()}, NOW, CFG)
    assert key == "phone" and st["band"] == "not seen"
    key, st = pick_tracker(TRACKERS, {"band": info(zone=None), "phone": info()}, NOW, CFG)
    assert key == "phone" and st["band"] == "no zone"


def test_still_tracker_skipped_only_while_lower_one_moves():
    still = info(moved_ago=30 * 60)
    key, st = pick_tracker(TRACKERS, {"band": still, "phone": info(moved_ago=30)}, NOW, CFG)
    assert key == "phone" and st["band"] == "still 30 min"
    # nobody moving (asleep): keep the highest priority one
    key, _ = pick_tracker(TRACKERS, {"band": still, "phone": info(moved_ago=3600)}, NOW, CFG)
    assert key == "band"


def test_nothing_usable():
    key, st = pick_tracker(TRACKERS, {}, NOW, CFG)
    assert key is None and st == {"band": "not seen", "phone": "not seen"}


def test_dwell_confirms_after_hold_and_first_value_immediately():
    d = Dwell()
    assert d.feed("Kitchen", 0, 15) and d.value == "Kitchen"
    assert not d.feed("Office", 1, 15)
    assert not d.feed("Office", 10, 15)
    assert d.feed("Office", 16, 15) and d.value == "Office"
    assert not d.feed("Kitchen", 20, 15)
    assert not d.feed("Office", 21, 15) and d.value == "Office"  # bounce back cancels


def test_validate_settings_cleans_and_rejects():
    out = validate_settings({
        "features": {"follow_me": 1},
        "notify": {"tap_path": "/lovelace/home"},
        "tracking": {"dwell_s": "20"},
        "persons": {"person.anna": {"trackers": [{"key": "annas_watch", "kind": "bogus"}], "notify": "mobile_app_x"}},
    })
    assert out["features"] == {"follow_me": True, "suggestions": False, "history": True}
    assert out["tracking"]["dwell_s"] == 20 and out["tracking"]["still_min"] == 10
    assert out["persons"]["person.anna"]["trackers"][0] == {"key": "annas_watch", "kind": "tag", "charging": None}
    for bad in ({"notify": {"tap_path": "https://evil"}},
                {"tracking": {"dwell_s": 9999}},
                {"persons": {"light.x": {}}},
                {"persons": {"person.a": {"trackers": [{"key": "a"}, {"key": "a"}]}}},
                {"persons": {"person.a": {"trackers": [{"key": "a", "charging": "x; rm"}]}}}):
        with pytest.raises(ValueError):
            validate_settings(bad)


def test_merge_settings_fills_defaults():
    m = merge_settings({"features": {"follow_me": True}})
    assert m["features"] == {"follow_me": True, "suggestions": False, "history": True}
    assert m["notify"]["tap_path"] == "/lovelace/0" and m["persons"] == {}
    assert merge_settings(None) == DEFAULT_SETTINGS


def test_guesses():
    assert guess_kind("eriks_apple_watch") == "watch"
    assert guess_kind("oura_ring") == "wearable"
    assert guess_kind("eriks_iphone_16") == "phone"
    assert guess_kind("keys_tile") == "tag"
    cands = ["sensor.eriks_iphone_16_battery_state", "sensor.sofias_iphone_battery_state"]
    assert guess_charging("eriks_iphone_16", cands) == cands[0]
    assert guess_charging("sofias_iphone_ble", cands) == cands[1]
    assert guess_charging("dog_tag", cands) is None
    keys = ["eriks_iphone_16", "sofias_iphone_ble", "car_tag"]
    assert suggest_trackers("Erik Svensson", ["device_tracker.eriks_iphone_16"], keys) == ["eriks_iphone_16"]
    assert suggest_trackers("Sofia S", [], keys) == ["sofias_iphone_ble"]
