"""Add a phone, watch or tag: the guided flow in the Settings tab.

Bermuda sees every Bluetooth device around the house, also the ones it does
not track. Its ``dump_devices`` service lists them with what each receiver
hears (signal, distance, when). That answers the hard question for a new
user, *which of these 160 devices is mine?*: hold the device against a
receiver and see which one suddenly comes close.

The flow: pick what to add, make it recognisable (Android: the Companion
app's BLE transmitter, which BPS reads; Apple: an IRK in Private BLE Device),
find it, add it to Bermuda's tracked devices (``configured_devices`` in
Bermuda's options, on the user's click), turn on its distance sensors
(distance_sensors.py) and link it to a person.

The pure functions take plain dicts (the dump) so they can be tested
without Home Assistant.
"""
from __future__ import annotations

import logging
import re
import time

_LOGGER = logging.getLogger(__name__)

BERMUDA = "bermuda"
CONF_DEVICES = "configured_devices"   # Bermuda's option: devices it tracks

NEAR_M = 0.8          # "held against a receiver"
FRESH_S = 20          # an advert older than this doesn't count
CLOSER_FACTOR = 0.5   # must be at most half its distance at the start

KIND_PRIVATE = "private_ble"   # Apple via IRK (Private BLE Device)
KIND_BEACON = "ibeacon"        # Android Companion app, tags, ...
KIND_DEVICE = "device"         # a fixed MAC address
KIND_RANDOM = "random"         # a changing address: can't be tracked as is


def _types(dev) -> list:
    t = dev.get("metadevice_type") or []
    return [str(x) for x in (t if isinstance(t, (list, tuple)) else [t])]


def kind_of(dev: dict) -> str | None:
    """What kind of device this dump entry is; None for what to hide.

    Hidden: receivers, and the raw radio addresses behind a beacon or a
    Private BLE device (the beacon / IRK entry is the device to pick).
    """
    if dev.get("_is_scanner"):
        return None
    types = _types(dev)
    if "beacon source" in types or "private_ble_source" in " ".join(types):
        return None
    if "private_ble_device" in types or dev.get("address_type") == "addr_type_private_ble_device":
        return KIND_PRIVATE
    if "beacon device" in types or dev.get("beacon_uuid"):
        return KIND_BEACON
    if "random" in str(dev.get("address_type") or "").lower():
        return KIND_RANDOM
    return KIND_DEVICE


def _nearest(dev: dict, now: float, scanner_names: dict) -> dict | None:
    """The receiver that hears the device closest right now."""
    best = None
    for adv in (dev.get("adverts") or {}).values():
        if not isinstance(adv, dict):
            continue
        dist, stamp = adv.get("rssi_distance"), adv.get("stamp")
        if not isinstance(dist, (int, float)) or not isinstance(stamp, (int, float)):
            continue
        if now - stamp > FRESH_S:
            continue
        if best is None or dist < best["distance"]:
            scanner = str(adv.get("scanner_address") or "").lower()
            best = {"distance": round(float(dist), 2), "rssi": adv.get("rssi"),
                    "receiver": scanner_names.get(scanner, scanner)}
    return best


def devices(dump: dict, now: float, configured=()) -> dict:
    """Pickable devices from a Bermuda dump, keyed by address.

    Each: address, value (as Bermuda's options store it), name, kind,
    tracked (Bermuda already tracks it), beacon (uuid/major/minor for
    beacons) and nearest ({receiver, distance, rssi} or None).
    """
    configured = {str(c).lower() for c in configured or ()}
    scanner_names = {}
    scanner_addrs = set()
    for addr, dev in dump.items():
        if isinstance(dev, dict) and dev.get("_is_scanner"):
            for a in (addr, dev.get("address"), dev.get("address_ble_mac")):
                if a:
                    scanner_addrs.add(str(a).lower())
                    scanner_names[str(a).lower()] = dev.get("name") or a
    # The changing radio addresses of an IRK device: the IRK entry stands for them.
    behind_irk = {
        str(s).lower()
        for dev in dump.values() if isinstance(dev, dict) and kind_of(dev) == KIND_PRIVATE
        for s in dev.get("metadevice_sources") or []
    }
    out = {}
    for addr, dev in dump.items():
        if not isinstance(dev, dict):
            continue
        kind = kind_of(dev)
        if kind is None or str(dev.get("address") or addr).lower() in behind_irk:
            continue
        sources = {str(s).lower() for s in dev.get("metadevice_sources") or []}
        if kind == KIND_BEACON and sources and sources <= scanner_addrs:
            continue   # a receiver's own calibration beacon
        address = str(dev.get("address") or addr).lower()
        out[address] = {
            "address": address,
            "value": address.upper(),
            "name": dev.get("name_by_user") or dev.get("name") or address,
            "kind": kind,
            "tracked": kind == KIND_PRIVATE or address in configured or bool(dev.get("create_sensor")),
            "nearest": _nearest(dev, now, scanner_names),
        }
    return out


def near(baseline: dict, current: dict, limit: int = 5) -> list:
    """Devices held against a receiver since the baseline was taken.

    A device counts when it is now within NEAR_M of some receiver and was
    not that close at the start (at most CLOSER_FACTOR of its distance then,
    or not heard at all). Closest first.
    """
    found = []
    for addr, dev in current.items():
        cur = dev.get("nearest")
        if not cur or cur["distance"] > NEAR_M:
            continue
        before = (baseline.get(addr) or {}).get("nearest")
        if before and before["distance"] * CLOSER_FACTOR < cur["distance"]:
            continue
        found.append({**dev, "was": before["distance"] if before else None})
    found.sort(key=lambda d: d["nearest"]["distance"])
    return found[:limit]


def beacon_value(uuid, major, minor) -> str | None:
    """Bermuda's address for an iBeacon: UUID without dashes, _major_minor."""
    u = re.sub(r"[^0-9a-fA-F]", "", str(uuid or ""))
    if len(u) != 32 or major in (None, "") or minor in (None, ""):
        return None
    try:
        return f"{u.upper()}_{int(major)}_{int(minor)}"
    except (TypeError, ValueError):
        return None


def android_transmitters(states) -> list:
    """Phones whose Companion app has the BLE transmitter sensor.

    ``states`` are (entity_id, state, attributes, friendly name) tuples of
    the ``sensor.*_ble_transmitter`` entities. The app publishes the beacon
    it sends as id / major / minor.
    """
    out = []
    for entity_id, state, attrs, name in states:
        a = {str(k).lower(): v for k, v in (attrs or {}).items()}
        value = beacon_value(a.get("id") or a.get("uuid"), a.get("major"), a.get("minor"))
        out.append({
            "entity_id": entity_id,
            "name": str(name or entity_id).replace(" BLE Transmitter", "").replace(" BLE transmitter", ""),
            "on": str(state).lower() not in ("off", "unavailable", "unknown", "stopped", ""),
            "value": value,
        })
    return out


def with_added(configured, value) -> tuple[list, bool]:
    """Bermuda's device list with ``value`` added; (list, changed)."""
    current = list(configured or [])
    if str(value).lower() in {str(c).lower() for c in current}:
        return current, False
    return current + [str(value).upper()], True


# --- Home Assistant glue --------------------------------------------------------

def _entry(hass):
    entries = hass.config_entries.async_entries(BERMUDA)
    return entries[0] if entries else None


def _now() -> float:
    try:
        from homeassistant.util.dt import monotonic_time_coarse
        return monotonic_time_coarse()
    except Exception:
        return time.monotonic()


async def async_scan(hass) -> dict:
    """All pickable devices with what the receivers hear right now."""
    entry = _entry(hass)
    if entry is None:
        return {}
    resp = await hass.services.async_call(
        BERMUDA, "dump_devices", {}, blocking=True, return_response=True)
    return devices(resp or {}, _now(), entry.options.get(CONF_DEVICES, []))


def status(hass) -> dict:
    """What the first step of the flow needs."""
    entry = _entry(hass)
    states = [
        (s.entity_id, s.state, dict(s.attributes), s.attributes.get("friendly_name"))
        for s in hass.states.async_all("sensor")
        if s.entity_id.endswith("_ble_transmitter")
    ]
    from homeassistant.helpers import device_registry as dr
    reg = dr.async_get(hass)
    pbd = []
    for e in hass.config_entries.async_entries("private_ble_device"):
        devs = dr.async_entries_for_config_entry(reg, e.entry_id)
        name = next((d.name_by_user or d.name for d in devs if d.name_by_user or d.name), None)
        pbd.append({"title": name or e.title, "entry_id": e.entry_id})
    return {
        "bermuda": entry is not None,
        "configured": list(entry.options.get(CONF_DEVICES, [])) if entry else [],
        "android": android_transmitters(states),
        "private_ble": pbd,
    }


def add(hass, value) -> bool:
    """Add a device to Bermuda's tracked devices. Bermuda reloads itself."""
    entry = _entry(hass)
    if entry is None:
        raise ValueError("Bermuda is not installed")
    devs, changed = with_added(entry.options.get(CONF_DEVICES, []), value)
    if changed:
        hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_DEVICES: devs})
        _LOGGER.info("Added %s to Bermuda's tracked devices", value)
    return changed
