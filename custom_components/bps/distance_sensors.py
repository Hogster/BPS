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

When Bermuda has its read API (bermuda_source.py) BPS needs none of these
sensors, and they cost: each writes to the recorder and goes out to every
dashboard about once a second. So the same setting parks them: once the API
has worked for PARK_AFTER_S, BPS turns the sensors off again (as Bermuda
itself would, disabled_by = integration) and remembers which devices it did
that for. If the API goes away (a Bermuda update without it) or stops
answering for UNPARK_AFTER_S, they are turned back on, and BPS reads them
as before. Sensors the user turned off are never touched.
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
        uid = str(e.get("unique_id") or "")
        eid = str(e.get("entity_id") or "")
        d = out.setdefault(e["device_id"], {
            "device_id": e["device_id"],
            "name": names.get(e["device_id"]) or e["device_id"],
            # Bermuda's address for the device, and the BPS tracker key
            # (the entity-id prefix of its distance sensors)
            "address": uid[:PER_RECEIVER.search(uid).start()].lower(),
            "key": eid.split(".", 1)[-1].split("_distance_to_")[0] if "_distance_to_" in eid else None,
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
        # BPS reads Bermuda's distances directly (bermuda_source.py): the
        # sensors aren't needed; "parked" when BPS has turned them off.
        "direct": _direct(hass),
        "parked": bool(getattr((hass.data.get("bps") or {}).get("distance_park"), "parked", None)),
    }


def _direct(hass) -> bool:
    from . import bermuda_source
    return bermuda_source.available(hass)


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


def to_park(entries, devices=None) -> tuple[list[str], set]:
    """Distance sensors that are on, of ``devices`` (all when None): the
    entity ids to turn off, and the devices they belong to."""
    ids, devs = [], set()
    for e in entries:
        if is_distance(e) and not e.get("disabled_by") and (devices is None or e["device_id"] in devices):
            ids.append(e["entity_id"])
            devs.add(e["device_id"])
    return sorted(ids), devs


def to_unpark(entries, devices) -> list[str]:
    """Bermuda-disabled distance sensors of the parked devices."""
    devices = set(devices or ())
    return sorted(e["entity_id"] for e in entries
                  if is_distance(e) and e.get("disabled_by") == BY_INTEGRATION and e["device_id"] in devices)


class ParkState:
    """When to park and unpark, from how long the API has worked or not.

    ``tick(ok, now)`` returns "park", "unpark" or None. Parking waits for
    PARK_AFTER_S of the API working without a break; unparking for
    UNPARK_AFTER_S without it, so a Bermuda reload (about 30 s) is not a
    failure.
    """

    def __init__(self, parked=()):
        self.parked = set(parked)
        self.ok_since = None
        self.bad_since = None

    def tick(self, ok, now):
        if ok:
            self.bad_since = None
            if self.ok_since is None:
                self.ok_since = now
            if now - self.ok_since >= PARK_AFTER_S:
                return "park"
            return None
        self.ok_since = None
        if self.bad_since is None:
            self.bad_since = now
        if self.parked and now - self.bad_since >= UNPARK_AFTER_S:
            return "unpark"
        return None


PARK_AFTER_S = 600
UNPARK_AFTER_S = 120
CHECK_S = 30


def disable(hass, entity_ids) -> int:
    """Turn the entities off the way Bermuda creates them (by integration)."""
    from homeassistant.helpers import entity_registry as er
    reg = er.async_get(hass)
    done = 0
    for eid in entity_ids:
        try:
            reg.async_update_entity(eid, disabled_by=er.RegistryEntryDisabler.INTEGRATION)
            done += 1
        except Exception as e:
            _LOGGER.warning("Could not turn off %s: %s", eid, e)
    if done:
        _LOGGER.info("BPS reads Bermuda directly: turned off %d distance sensor(s)", done)
    return done


def _tracked_device_ids(hass, entries) -> set:
    """Registry devices of what Bermuda tracks, via the sensors' names."""
    from . import bermuda_source
    keys = set(bermuda_source.async_tracked(hass) or ())
    return {d["device_id"] for d in summarize(entries) if d.get("key") in keys}


def enable_device(hass, device_id) -> int:
    return enable(hass, to_enable(_entries(hass), device_id=device_id))


async def async_setup_auto(hass, is_on):
    """Keep tracked devices' distance sensors on as receivers are added, or
    parked while Bermuda's read API works (see the module docstring).

    Runs once at start (receivers added while BPS was not running), on every
    new Bermuda entity, and every CHECK_S for the API. ``is_on`` reads the
    setting each time. Returns a stop function.
    """
    import time
    from datetime import timedelta

    from homeassistant.core import callback
    from homeassistant.helpers import entity_registry as er
    from homeassistant.helpers.event import async_track_time_interval
    from homeassistant.helpers.storage import Store

    from . import bermuda_source

    store = Store(hass, 1, "bps_distance_parked")
    try:
        saved = await store.async_load() or {}
    except Exception:
        saved = {}
    park = ParkState(saved.get("devices") or ())
    hass.data.setdefault("bps", {})["distance_park"] = park

    def _save():
        store.async_delay_save(lambda: {"devices": sorted(park.parked)}, 5)

    def _sweep():
        # Parked: the API serves BPS, so new receivers' sensors stay off.
        if is_on() and not park.parked:
            enable(hass, to_enable(_entries(hass), only_active=True))

    @callback
    def _check(_now=None):
        # Unparking is a safety net: it runs even with the setting turned off.
        on = is_on()
        if not on and not park.parked:
            return
        snap_ok = bermuda_source.available(hass) and bermuda_source.snapshot(hass) is not None
        action = park.tick(snap_ok, time.monotonic())
        entries = _entries(hass)
        if action == "park" and on:
            ids, devs = to_park(entries)
            # devices Bermuda tracks, also ones added since (their sensors were never on)
            devs |= _tracked_device_ids(hass, entries)
            if devs - park.parked:
                park.parked |= devs
                _save()
            if ids:
                disable(hass, ids)
        elif action == "unpark":
            ids = to_unpark(entries, park.parked)
            _LOGGER.warning("Bermuda's read API is gone or not answering: turning %d distance "
                            "sensor(s) back on", len(ids))
            enable(hass, ids)
            park.parked = set()
            _save()

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
        if is_on() and not park.parked:
            ids = to_enable(_entries(hass), device_id=entry.device_id, only_active=True)
            if entry.entity_id in ids:
                enable(hass, [entry.entity_id])

    try:
        _sweep()
    except Exception as e:
        _LOGGER.warning("Distance sensor sweep failed: %s", e)
    unsubs = [
        hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, _on_registry),
        async_track_time_interval(hass, _check, timedelta(seconds=CHECK_S)),
    ]

    def _stop():
        for u in unsubs:
            u()
    return _stop
