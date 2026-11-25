"""Bermuda's per-receiver distance sensors ("Distance to <receiver>").

Bermuda creates one distance sensor per tracked device and receiver, but
creates them disabled, so a new user has to open every device and enable
every "Distance to ..." entity by hand before BPS sees anything. This module
lists them per device and turns them on: on request from the Settings tab,
and automatically for receivers added later to a device that already has
distance sensors on (setting ``features.auto_distance``).

Only sensors Bermuda itself disabled (disabled_by = integration) are turned
on; one the user disabled stays off. The unfiltered variants (unique id
``..._range_raw``) are left alone: BPS reads the filtered ones.
"""
from __future__ import annotations

import logging
import re

_LOGGER = logging.getLogger(__name__)

BERMUDA = "bermuda"
RANGE_SUFFIX = "_range"      # filtered distance; "_range_raw" is unfiltered
# "<device>_<receiver MAC>_range" is a per-receiver distance; "<device>_range"
# alone is the device's overall "Distance" (to the nearest receiver).
PER_RECEIVER = re.compile(r"_([0-9a-f]{2}:){5}[0-9a-f]{2}_range$", re.IGNORECASE)
BY_INTEGRATION = "integration"


def is_distance(entry: dict) -> bool:
    return (entry.get("platform") == BERMUDA
            and bool(PER_RECEIVER.search(str(entry.get("unique_id") or "")))
            and bool(entry.get("device_id")))


def summarize(entries, names=None) -> list[dict]:
    """Per device: how many distance sensors exist, are on, are off.

    ``entries`` are plain dicts (entity_id, unique_id, device_id, platform,
    disabled_by); ``names`` maps device id -> name. Sorted by name.
    """
    names = names or {}
    out = {}
    for e in entries:
        if not is_distance(e):
            continue
        d = out.setdefault(e["device_id"], {
            "device_id": e["device_id"],
            "name": names.get(e["device_id"]) or e["device_id"],
            "total": 0, "on": 0, "off_integration": 0, "off_user": 0,
        })
        d["total"] += 1
        if not e.get("disabled_by"):
            d["on"] += 1
        elif e["disabled_by"] == BY_INTEGRATION:
            d["off_integration"] += 1
        else:
            d["off_user"] += 1
    return sorted(out.values(), key=lambda d: str(d["name"]).lower())


def to_enable(entries, device_id=None, only_active=False) -> list[str]:
    """Entity ids to turn on: Bermuda-disabled distance sensors.

    ``device_id`` limits it to one device. ``only_active`` limits it to
    devices that already have at least one distance sensor on (the automatic
    mode: a device the user tracks gets its new receivers, an untracked
    device is left alone).
    """
    dist = [e for e in entries if is_distance(e)]
    active = {e["device_id"] for e in dist if not e.get("disabled_by")}
    return sorted(
        e["entity_id"] for e in dist
        if e.get("disabled_by") == BY_INTEGRATION
        and (device_id is None or e["device_id"] == device_id)
        and (not only_active or e["device_id"] in active)
    )


# --- Home Assistant glue --------------------------------------------------------

def _entries(hass) -> list[dict]:
    from homeassistant.helpers import entity_registry as er
    out = []
    for e in er.async_get(hass).entities.values():
        if e.platform != BERMUDA:
            continue
        out.append({
            "entity_id": e.entity_id,
            "unique_id": e.unique_id,
            "device_id": e.device_id,
            "platform": e.platform,
            "disabled_by": getattr(e.disabled_by, "value", e.disabled_by),
        })
    return out


def _names(hass) -> dict:
    from homeassistant.helpers import device_registry as dr
    return {d.id: (d.name_by_user or d.name or d.id)
            for d in dr.async_get(hass).devices.values()}


def status(hass) -> dict:
    return {
        "bermuda": bool(hass.config_entries.async_entries(BERMUDA)),
        "devices": summarize(_entries(hass), _names(hass)),
    }


def enable(hass, entity_ids) -> int:
    """Turn the entities on. Home Assistant reloads Bermuda about 30 s later,
    and the sensors then appear."""
    from homeassistant.helpers import entity_registry as er
    reg = er.async_get(hass)
    done = 0
    for eid in entity_ids:
        try:
            reg.async_update_entity(eid, disabled_by=None)
            done += 1
        except Exception as e:  # removed meanwhile, or not ours to touch
            _LOGGER.warning("Could not turn on %s: %s", eid, e)
    if done:
        _LOGGER.info("Turned on %d Bermuda distance sensor(s)", done)
    return done


def enable_device(hass, device_id) -> int:
    return enable(hass, to_enable(_entries(hass), device_id=device_id))


async def async_setup_auto(hass, is_on):
    """Keep tracked devices' distance sensors on as receivers are added.

    Runs once at start (receivers added while BPS was not running) and on
    every new Bermuda entity. ``is_on`` reads the setting each time. Returns
    a stop function.
    """
    from homeassistant.core import callback
    from homeassistant.helpers import entity_registry as er

    def _sweep():
        if is_on():
            enable(hass, to_enable(_entries(hass), only_active=True))

    # @callback: run in the event loop. A plain function is run in a worker
    # thread, where updating the entity registry is refused.
    @callback
    def _on_registry(event):
        data = event.data
        if data.get("action") not in ("create", "update"):
            return
        entry = er.async_get(hass).async_get(data.get("entity_id"))
        if entry is None or entry.platform != BERMUDA:
            return
        if not PER_RECEIVER.search(str(entry.unique_id)):
            return
        if getattr(entry.disabled_by, "value", entry.disabled_by) != BY_INTEGRATION:
            return
        if is_on():
            ids = to_enable(_entries(hass), device_id=entry.device_id, only_active=True)
            if entry.entity_id in ids:
                enable(hass, [entry.entity_id])

    try:
        _sweep()
    except Exception as e:
        _LOGGER.warning("Distance sensor sweep failed: %s", e)
    return hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, _on_registry)
