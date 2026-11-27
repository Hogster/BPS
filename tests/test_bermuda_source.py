"""Reading Bermuda's distances through its read API (bermuda_source.py)."""
from bps.bermuda_source import names_from_registry, readings, receiver_ages

ENTRIES = [
    ("sensor.eriks_iphone_16_distance_to_nsp_kitchen", "b9be12_7c:00:00:00:00:0a_range"),
    ("sensor.eriks_iphone_16_unfiltered_distance_to_nsp_kitchen", "b9be12_7c:00:00:00:00:0a_range_raw"),
    # a receiver renamed after its sensors were made: the sensor keeps the old name
    ("sensor.eriks_iphone_16_distance_to_nsp_office", "b9be12_48:00:00:00:00:42_range"),
    # an iBeacon device: its unique id has underscores of its own
    ("sensor.pixel_distance_to_nsp_kitchen", "fde3_100_1_7c:00:00:00:00:0a_range"),
    ("sensor.radar_distance_to_detection_object", "radar_target"),
]


def snap(devices, version=1):
    return {"version": version, "stamp": 100.0, "devices": devices}


def sc(address, slug, dist, age=1.0, seen=0.5):
    return {"address": address, "slug": slug, "distance": dist, "age": age, "scanner_last_seen_age": seen}


DEVICES = {
    "irk_addr": {"slug": "erik_s_iphone", "unique_id": "b9be12", "tracked": True, "scanners": {
        "7c:00:00:00:00:0a": sc("7c:00:00:00:00:0a", "nsp_kitchen", 2.5),
        "48:00:00:00:00:42": sc("48:00:00:00:00:42", "study", 4.0),
        "aa:00:00:00:00:01": sc("aa:00:00:00:00:01", "garage_tesla", None),   # timed out
        "aa:00:00:00:00:02": sc("aa:00:00:00:00:02", "nsp_garage", 7.0, seen=3.0),
    }},
    "fde3_100_1": {"slug": "fde3_100_1", "unique_id": "fde3_100_1", "tracked": True, "scanners": {
        "7c:00:00:00:00:0a": sc("7c:00:00:00:00:0a", "nsp_kitchen", 1.0),
    }},
    "c0:ff:ee:00:00:01": {"slug": "stranger", "tracked": False, "scanners": {
        "7c:00:00:00:00:0a": sc("7c:00:00:00:00:0a", "nsp_kitchen", 0.5, seen=0.2),
    }},
}


def test_names_from_registry():
    devs, recs = names_from_registry(ENTRIES)
    assert devs == {"b9be12": "eriks_iphone_16", "fde3_100_1": "pixel"}
    assert recs == {"7c:00:00:00:00:0a": "nsp_kitchen", "48:00:00:00:00:42": "nsp_office"}


def test_readings_use_the_sensor_names_and_fall_back_to_slugs():
    out = readings(snap(DEVICES), *names_from_registry(ENTRIES))
    assert set(out) == {"eriks_iphone_16", "pixel"}             # untracked device left out
    phone = out["eriks_iphone_16"]
    assert phone["nsp_kitchen"]["distance"] == 2.5
    assert phone["nsp_office"]["distance"] == 4.0               # renamed receiver: sensor name wins
    assert "garage_tesla" not in phone                          # timed-out reading left out
    assert phone["nsp_garage"] == {"distance": 7.0, "age": 1.0, "address": "aa:00:00:00:00:02"}
    assert out["pixel"]["nsp_kitchen"]["distance"] == 1.0
    # without any sensors registered, the snapshot's own names
    assert set(readings(snap(DEVICES))) == {"erik_s_iphone", "fde3_100_1"}


def test_unknown_version_means_read_the_sensors():
    assert readings(snap(DEVICES, version=2)) is None
    assert receiver_ages(snap(DEVICES, version=2)) is None
    assert readings(None) is None


def test_receiver_ages_freshest_per_receiver():
    ages = receiver_ages(snap(DEVICES), names_from_registry(ENTRIES)[1])
    assert ages["nsp_kitchen"] == 0.2      # heard via the untracked device too
    assert ages["nsp_office"] == 0.5
    assert ages["nsp_garage"] == 3.0
