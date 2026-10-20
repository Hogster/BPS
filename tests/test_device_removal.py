"""Device removal: HA's "Delete" on a BPS device.

A tracked device's BPS device is keyed by its Bermuda prefix, so renaming or
dropping a tracker leaves an empty BPS device behind. Without
async_remove_config_entry_device, HA refuses to delete it ("Config entry does
not support device removal"). Allow removal only when the device holds no
entities: one that still has live BPS sensors would just be re-created.
"""
import asyncio
import types

import bps
from homeassistant.helpers import entity_registry as er


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _device(device_id="dev1"):
    return types.SimpleNamespace(id=device_id, identifiers={("bps", "old_tracker")})


def _registry(monkeypatch, entities_by_device):
    reg = object()
    monkeypatch.setattr(er, "async_get", lambda hass: reg, raising=False)

    def entries_for_device(registry, device_id, include_disabled_entities=False):
        assert registry is reg
        assert include_disabled_entities is True
        return entities_by_device.get(device_id, [])

    monkeypatch.setattr(er, "async_entries_for_device", entries_for_device, raising=False)


def test_empty_device_can_be_removed(monkeypatch):
    _registry(monkeypatch, {})
    assert run(bps.async_remove_config_entry_device(object(), object(), _device())) is True


def test_device_with_entities_is_kept(monkeypatch):
    _registry(monkeypatch, {"dev1": [types.SimpleNamespace(entity_id="sensor.x_bps_zone")]})
    assert run(bps.async_remove_config_entry_device(object(), object(), _device())) is False
