"""Regression tests for open GitHub issues fixed together.

- #38: device registry must not be read as a mapping (HA 2026.9 deprecation).
- #7/#32: /api/bps/cords answers 200 [] when nothing is tracked, not 404.
- #8: every map extension the upload accepts is also listed back.
- #40: a calibration dump reports why no receiver pairs were heard.
- PR #42: empty BPS devices can be deleted from the UI.
"""
import asyncio
import json
import types

import bps
import bps.calibration as cal_mod
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from conftest import make_hass


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# --- #38 --------------------------------------------------------------------
class _NoMappingDevices:
    """dev_reg.devices that fails on mapping-style access, like HA 2027.9."""

    def values(self):
        raise AssertionError("device_registry.devices used as a mapping")

    def __getitem__(self, key):
        raise AssertionError("device_registry.devices used as a mapping")


def test_device_availability_avoids_devices_mapping(monkeypatch):
    devices = {
        "d1": types.SimpleNamespace(id="d1", name="Kitchen Proxy", name_by_user=None),
        "d2": types.SimpleNamespace(id="d2", name="Hall", name_by_user="Hall Proxy"),
    }
    dev_reg = types.SimpleNamespace(devices=_NoMappingDevices(), async_get=devices.get)
    ent_reg = types.SimpleNamespace(entities={
        "a": types.SimpleNamespace(entity_id="sensor.k_rssi", device_id="d1"),
        "b": types.SimpleNamespace(entity_id="binary_sensor.h_status", device_id="d2"),
        "c": types.SimpleNamespace(entity_id="sensor.orphan", device_id=None),
        "d": types.SimpleNamespace(entity_id="sensor.gone", device_id="missing"),
    })
    monkeypatch.setattr(dr, "async_get", lambda hass: dev_reg, raising=False)
    monkeypatch.setattr(er, "async_get", lambda hass: ent_reg, raising=False)

    slug_to_device, device_entities = bps._build_device_availability(object())

    # conftest's slugify is identity, so the slug is the (user) name itself.
    assert slug_to_device == {"Kitchen Proxy": "d1", "Hall Proxy": "d2"}
    assert device_entities["d1"] == ["sensor.k_rssi"]
    assert device_entities["d2"] == ["binary_sensor.h_status"]


def test_duplicate_device_names_are_ambiguous(monkeypatch):
    devices = {
        "d1": types.SimpleNamespace(id="d1", name="proxy", name_by_user=None),
        "d2": types.SimpleNamespace(id="d2", name="proxy", name_by_user=None),
    }
    dev_reg = types.SimpleNamespace(devices=_NoMappingDevices(), async_get=devices.get)
    ent_reg = types.SimpleNamespace(entities={
        "a": types.SimpleNamespace(entity_id="sensor.a", device_id="d1"),
        "b": types.SimpleNamespace(entity_id="sensor.b", device_id="d2"),
    })
    monkeypatch.setattr(dr, "async_get", lambda hass: dev_reg, raising=False)
    monkeypatch.setattr(er, "async_get", lambda hass: ent_reg, raising=False)
    slug_to_device, _ = bps._build_device_availability(object())
    assert "proxy" not in slug_to_device


# --- #7 / #32 -----------------------------------------------------------------
def test_cords_endpoint_empty_is_200_list():
    hass = make_hass()
    view = bps.BPSCordsAPI(hass)
    resp = run(view.get(None))
    assert resp.status == 200
    assert resp.json_body == []


def test_cords_endpoint_returns_positions():
    hass = make_hass()
    hass.data.setdefault("bps", {})["apitricords"] = [{"ent": "phone", "cords": [1, 2]}]
    resp = run(bps.BPSCordsAPI(hass).get(None))
    assert resp.status == 200
    assert resp.json_body[0]["ent"] == "phone"


# --- #8 ---------------------------------------------------------------------
def test_map_listing_matches_upload_allowlist(tmp_path):
    names = ["a.png", "b.JPEG", "c.gif", "d.svg", "e.avif", "f.jfif",
             "bpsdata.txt", "bps_calibration_state.json", "notes.md"]
    for n in names:
        (tmp_path / n).write_bytes(b"x")
    (tmp_path / "subdir.png").mkdir()
    listed = set(bps.BPSMapsListAPI._list_map_files(str(tmp_path)))
    assert listed == {"a.png", "b.JPEG", "c.gif", "d.svg", "e.avif", "f.jfif"}


# --- #40 --------------------------------------------------------------------
def _cal(receivers):
    return {
        "receivers": {s: {"x": 0, "y": 0, "scale": 1, "floor": "f", "uid": None, "height": None}
                      for s in receivers},
        "samples": {},
    }


def test_dump_diag_no_matching_scanners():
    cal = _cal(["proxy_a", "proxy_b"])
    devices = {"x": {"_is_scanner": True, "name": "other", "address": "aa:aa:aa:aa:aa:01",
                     "adverts": {}}}
    cal_mod._ingest_dump(cal, devices)
    d = cal["last_dump"]
    assert d["scanners"] == 1 and d["matched"] == 0 and d["placed"] == 2


def test_dump_diag_matched_but_not_beaconing():
    cal = _cal(["proxy_a", "proxy_b"])
    devices = {
        "a": {"_is_scanner": True, "name": "proxy_a", "address": "aa:aa:aa:aa:aa:01", "adverts": {}},
        "b": {"_is_scanner": True, "name": "proxy_b", "address": "aa:aa:aa:aa:aa:02", "adverts": {}},
    }
    cal_mod._ingest_dump(cal, devices)
    d = cal["last_dump"]
    assert d["matched"] == 2 and d["beaconing"] == 0 and d["usable"] == 0
    assert cal["samples"] == {}


def test_dump_diag_counts_usable_adverts():
    cal = _cal(["proxy_a", "proxy_b"])
    advert = {"scanner_address": "aa:aa:aa:aa:aa:02", "stamp": 100.0, "rssi_distance_raw": 3.2}
    devices = {
        "a": {"_is_scanner": True, "name": "proxy_a", "address": "aa:aa:aa:aa:aa:01",
              "adverts": {"k": advert}},
        "b": {"_is_scanner": True, "name": "proxy_b", "address": "aa:aa:aa:aa:aa:02", "adverts": {}},
    }
    cal_mod._ingest_dump(cal, devices)
    d = cal["last_dump"]
    assert d["beaconing"] == 1 and d["usable"] == 1
    assert list(cal["samples"]) == ["proxy_a|proxy_b"]


def test_status_payload_exposes_last_dump():
    hass = make_hass()
    cal = cal_mod.get_calibration_state(hass)
    cal["last_dump"] = {"scanners": 3}
    assert cal_mod._status_payload(cal)["last_dump"] == {"scanners": 3}


# --- PR #42 -----------------------------------------------------------------
def _registry(monkeypatch, entities_by_device):
    reg = object()
    monkeypatch.setattr(er, "async_get", lambda hass: reg, raising=False)

    def entries_for_device(registry, device_id, include_disabled_entities=False):
        assert registry is reg and include_disabled_entities is True
        return entities_by_device.get(device_id, [])

    monkeypatch.setattr(er, "async_entries_for_device", entries_for_device, raising=False)


def test_empty_device_can_be_removed(monkeypatch):
    _registry(monkeypatch, {})
    dev = types.SimpleNamespace(id="dev1")
    assert run(bps.async_remove_config_entry_device(object(), object(), dev)) is True


def test_device_with_entities_is_kept(monkeypatch):
    _registry(monkeypatch, {"dev1": [types.SimpleNamespace(entity_id="sensor.x_bps_zone")]})
    dev = types.SimpleNamespace(id="dev1")
    assert run(bps.async_remove_config_entry_device(object(), object(), dev)) is False
