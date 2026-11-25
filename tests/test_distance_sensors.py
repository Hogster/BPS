"""Bermuda distance sensors: which to list and which to turn on."""
from bps.distance_sensors import is_distance, summarize, to_enable


def ent(eid, dev, uid_suffix="_range", disabled=None, platform="bermuda", mac=None):
    mac = mac or "aa:bb:cc:%02x:%02x:%02x" % tuple(eid.encode()[-3:])
    return {"entity_id": eid, "unique_id": f"abc123_{mac}{uid_suffix}", "device_id": dev,
            "platform": platform, "disabled_by": disabled}


ENTRIES = [
    # phone: tracked, one receiver added later (off), one the user turned off
    ent("sensor.phone_distance_to_kitchen", "phone"),
    ent("sensor.phone_distance_to_hall", "phone", disabled="integration"),
    ent("sensor.phone_distance_to_attic", "phone", disabled="user"),
    ent("sensor.phone_unfiltered_distance_to_kitchen", "phone", "_range_raw", "integration"),
    # tag: new in Bermuda, everything off
    ent("sensor.tag_distance_to_kitchen", "tag", disabled="integration"),
    ent("sensor.tag_distance_to_hall", "tag", disabled="integration"),
    # not distance sensors: the overall "Distance" (to the nearest receiver)
    {"entity_id": "sensor.phone_distance", "unique_id": "abc123_range", "device_id": "phone",
     "platform": "bermuda", "disabled_by": None},
    ent("sensor.phone_area", "phone", "_area"),
    ent("sensor.radar_distance_to_detection_object", "radar", platform="esphome"),
    ent("sensor.orphan_distance_to_hall", None, disabled="integration"),
]


def test_is_distance_only_filtered_bermuda_with_device():
    ids = [e["entity_id"] for e in ENTRIES if is_distance(e)]
    assert ids == ["sensor.phone_distance_to_kitchen", "sensor.phone_distance_to_hall",
                   "sensor.phone_distance_to_attic", "sensor.tag_distance_to_kitchen",
                   "sensor.tag_distance_to_hall"]


def test_summarize_counts_per_device():
    out = summarize(ENTRIES, {"phone": "Phone", "tag": "Key tag"})
    assert out == [
        {"device_id": "tag", "name": "Key tag", "total": 2, "on": 0, "off_integration": 2, "off_user": 0},
        {"device_id": "phone", "name": "Phone", "total": 3, "on": 1, "off_integration": 1, "off_user": 1},
    ]


def test_enable_one_device_skips_user_disabled_and_unfiltered():
    assert to_enable(ENTRIES, device_id="phone") == ["sensor.phone_distance_to_hall"]
    assert to_enable(ENTRIES, device_id="tag") == ["sensor.tag_distance_to_hall",
                                                   "sensor.tag_distance_to_kitchen"]


def test_automatic_mode_only_touches_tracked_devices():
    assert to_enable(ENTRIES, only_active=True) == ["sensor.phone_distance_to_hall"]


def test_nothing_to_do():
    assert to_enable([], device_id="x") == []
    assert summarize([]) == []


def test_registry_listener_runs_in_the_event_loop(monkeypatch):
    """HA runs a listener without @callback in a worker thread, where the
    entity registry refuses updates (0.3.0b2: new receivers stayed off)."""
    import asyncio
    import types
    import homeassistant.helpers.entity_registry as er
    from bps import distance_sensors

    monkeypatch.setattr(er, "EVENT_ENTITY_REGISTRY_UPDATED", "entity_registry_updated", raising=False)
    seen = {}
    hass = types.SimpleNamespace(bus=types.SimpleNamespace(
        async_listen=lambda event, fn: seen.update(event=event, fn=fn) or (lambda: None)))

    asyncio.run(distance_sensors.async_setup_auto(hass, lambda: False))

    assert seen["event"] == "entity_registry_updated"
    assert getattr(seen["fn"], "_hass_callback", False) is True
