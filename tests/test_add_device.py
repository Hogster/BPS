"""Add a phone, watch or tag: picking the device out of Bermuda's dump."""
from bps.add_device import (
    KIND_BEACON, KIND_DEVICE, KIND_PRIVATE, KIND_RANDOM,
    android_transmitters, beacon_value, devices, kind_of, near, with_added,
)

NOW = 1000.0


def adv(scanner, dist, age=1.0):
    return {"scanner_address": scanner, "rssi_distance": dist, "rssi": -60, "stamp": NOW - age}


DUMP = {
    # a receiver, and its own calibration beacon (+ that beacon's raw source)
    "aa:aa:aa:aa:aa:01": {"name": "Nsp-Kitchen", "address": "aa:aa:aa:aa:aa:01", "_is_scanner": True},
    "aa:aa:aa:aa:aa:02": {"name": "Nsp-Hall", "address": "aa:aa:aa:aa:aa:02", "_is_scanner": True},
    "fde3_1_1": {"address": "fde3_1_1", "metadevice_type": ["beacon device"], "beacon_uuid": "fde3",
                 "metadevice_sources": ["aa:aa:aa:aa:aa:01"], "adverts": {"x": adv("aa:aa:aa:aa:aa:02", 4.0)}},
    "aa:aa:aa:aa:aa:01x": {"address": "aa:aa:aa:aa:aa:01x", "metadevice_type": ["beacon source"]},
    # an iPhone via IRK, and one of its changing addresses
    "irk1": {"address": "irk1", "name": "Private BLE Device irk1", "name_by_user": "Anna iPhone",
             "metadevice_type": ["private_ble_device"], "metadevice_sources": ["7a:00:00:00:00:01"],
             "adverts": {"x": adv("aa:aa:aa:aa:aa:01", 6.0)}},
    "7a:00:00:00:00:01": {"address": "7a:00:00:00:00:01", "address_type": "bd_addr_random_resolvable"},
    # an Android beacon, not tracked yet
    "abcd_100_1": {"address": "abcd_100_1", "name": "abcd_100_1", "metadevice_type": ["beacon device"],
                   "beacon_uuid": "abcd", "metadevice_sources": ["c0:00:00:00:00:01"],
                   "adverts": {"x": adv("aa:aa:aa:aa:aa:01", 3.0)}},
    # a tag with a fixed address, a random stranger
    "d0:00:00:00:00:01": {"address": "d0:00:00:00:00:01", "name": "Key tag", "address_type": "bd_addr_type_unknown",
                          "adverts": {"x": adv("aa:aa:aa:aa:aa:02", 2.0)}},
    "5f:00:00:00:00:09": {"address": "5f:00:00:00:00:09", "address_type": "bd_addr_random_resolvable"},
}


def test_kinds_and_what_is_hidden():
    out = devices(DUMP, NOW, configured=["D0:00:00:00:00:01"])
    assert set(out) == {"irk1", "abcd_100_1", "d0:00:00:00:00:01", "5f:00:00:00:00:09"}
    assert out["irk1"]["kind"] == KIND_PRIVATE and out["irk1"]["tracked"] is True
    assert out["irk1"]["name"] == "Anna iPhone"
    assert out["abcd_100_1"]["kind"] == KIND_BEACON and out["abcd_100_1"]["tracked"] is False
    assert out["abcd_100_1"]["value"] == "ABCD_100_1"
    assert out["d0:00:00:00:00:01"]["kind"] == KIND_DEVICE and out["d0:00:00:00:00:01"]["tracked"] is True
    assert out["5f:00:00:00:00:09"]["kind"] == KIND_RANDOM
    assert out["abcd_100_1"]["nearest"] == {"distance": 3.0, "rssi": -60, "receiver": "Nsp-Kitchen"}
    assert kind_of(DUMP["aa:aa:aa:aa:aa:01"]) is None


def test_old_adverts_do_not_count():
    dump = {"t": {"address": "t", "adverts": {"x": adv("s", 0.2, age=60)}}}
    assert devices(dump, NOW)["t"]["nearest"] is None


def test_near_finds_the_device_that_came_close():
    before = devices(DUMP, NOW)
    dump = {**DUMP, "abcd_100_1": {**DUMP["abcd_100_1"], "adverts": {"x": adv("aa:aa:aa:aa:aa:01", 0.3)}}}
    found = near(before, devices(dump, NOW))
    assert [d["address"] for d in found] == ["abcd_100_1"]
    assert found[0]["was"] == 3.0 and found[0]["nearest"]["receiver"] == "Nsp-Kitchen"


def test_near_ignores_what_was_already_close():
    close = {"t": {"address": "t", "adverts": {"x": adv("s", 0.5)}}}
    assert near(devices(close, NOW), devices(close, NOW)) == []
    # new since the start and close: counts
    assert [d["address"] for d in near({}, devices(close, NOW))] == ["t"]


def test_beacon_value_and_android():
    assert beacon_value("fde3b150-2f64-43ba-aee9-867f75ee4a6f", "1", 19) == "FDE3B1502F6443BAAEE9867F75EE4A6F_1_19"
    assert beacon_value("short", 1, 1) is None
    assert beacon_value("fde3b1502f6443baaee9867f75ee4a6f", None, 1) is None
    phones = android_transmitters([
        ("sensor.pixel_ble_transmitter", "Transmitting",
         {"id": "fde3b150-2f64-43ba-aee9-867f75ee4a6f", "Major": "100", "Minor": "40004"}, "Pixel BLE Transmitter"),
        ("sensor.old_ble_transmitter", "Stopped", {}, "Old BLE transmitter"),
    ])
    assert phones[0] == {"entity_id": "sensor.pixel_ble_transmitter", "name": "Pixel", "on": True,
                         "value": "FDE3B1502F6443BAAEE9867F75EE4A6F_100_40004"}
    assert phones[1]["on"] is False and phones[1]["value"] is None


def test_with_added():
    assert with_added(["AA_1_1"], "bb_1_1") == (["AA_1_1", "BB_1_1"], True)
    assert with_added(["AA_1_1"], "aa_1_1") == (["AA_1_1"], False)
    assert with_added(None, "x") == (["X"], True)
