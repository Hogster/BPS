"""Read Bermuda's distances straight from Bermuda, without its distance sensors.

Bermuda keeps every device's distance to every receiver in memory. Until now
BPS could only read them through Bermuda's *Distance to ...* sensors: one
entity per tracked device and receiver, each writing to the recorder and
sending a state change to every open dashboard. Bermuda creates them turned
off for that reason, and on a big house they run into the thousands.

A read API for other integrations is proposed for Bermuda
(``custom_components.bermuda.api``, agittins/bermuda#834, by David Coulson,
whose Sextant has read Bermuda this way since September; this module follows
his adapter, MIT). When Bermuda has it, BPS reads the distances from there and
the sensors are not needed. When it doesn't (older Bermuda, or the API not
merged yet), every function here returns None and BPS reads the sensors as
before.

Naming. BPS knows a tracker by its sensor prefix (``eriks_iphone_16``) and a
receiver by the slug at the end of the sensor id (``nsp_kitchen``); both are
stored in the user's map. The snapshot names them from Bermuda's *current*
names, which can differ from the sensor ids after a rename (entity ids are
frozen when the entity is created). So the names come from the entity
registry first, where Bermuda's sensors stay registered even when turned off,
and their unique ids say which device and which receiver address each one is:
``<device unique_id>_<receiver MAC>_range``. The snapshot's own slugs are the
fallback, for a device or receiver that never had a sensor.

The pure functions take plain dicts so they can be tested without Home
Assistant.
"""
from __future__ import annotations

import logging
import time

_LOGGER = logging.getLogger(__name__)

SUPPORTED_VERSIONS = frozenset({1})
DISTANCE_TO = "_distance_to_"
RANGE_SUFFIX = "_range"

SNAPSHOT_TTL = 0.5    # Bermuda updates about once a second
NAMES_TTL = 30.0      # sensor names only change when a device or receiver is added
_CACHE = "bps_bermuda_source"


# --- pure -----------------------------------------------------------------------

def names_from_registry(entries) -> tuple[dict, dict]:
    """BPS's names for Bermuda's devices and receivers, from its sensors.

    ``entries`` are (entity_id, unique_id) of the bermuda platform's
    ``sensor.<device>_distance_to_<receiver>`` entities, turned off or not.
    Returns ({device unique_id: device prefix}, {receiver address: receiver slug}),
    keys lower-cased. The unfiltered twins (``..._range_raw``) are skipped.
    """
    devices, receivers = {}, {}
    for entity_id, unique_id in entries:
        if not entity_id or not unique_id or DISTANCE_TO not in entity_id:
            continue
        uid = str(unique_id)
        if not uid.endswith(RANGE_SUFFIX):
            continue
        dev_uid, sep, address = uid[: -len(RANGE_SUFFIX)].rpartition("_")
        if not sep or not dev_uid or not address:
            continue
        prefix, slug = entity_id.split(".", 1)[-1].split(DISTANCE_TO, 1)
        if prefix.endswith("_unfiltered"):
            continue
        devices.setdefault(dev_uid.lower(), prefix)
        receivers.setdefault(address.lower(), slug)
    return devices, receivers


def readings(snapshot, device_names=None, receiver_names=None) -> dict | None:
    """Distances per tracked device and receiver, in BPS's names.

    Returns {device prefix: {receiver slug: {"distance": metres, "age": s,
    "address": receiver address}}} for the devices Bermuda tracks. A reading
    Bermuda has timed out (distance None) is left out, as an unavailable
    sensor was. None for a snapshot this module doesn't understand.
    """
    if not isinstance(snapshot, dict) or snapshot.get("version") not in SUPPORTED_VERSIONS:
        return None
    device_names = device_names or {}
    receiver_names = receiver_names or {}
    out = {}
    for address, dev in (snapshot.get("devices") or {}).items():
        if not isinstance(dev, dict) or not dev.get("tracked"):
            continue
        prefix = None
        for key in (dev.get("unique_id"), address):
            if key and str(key).lower() in device_names:
                prefix = device_names[str(key).lower()]
                break
        prefix = prefix or dev.get("slug")
        if not prefix:
            continue
        per = out.setdefault(prefix, {})
        for scanner_address, sc in (dev.get("scanners") or {}).items():
            if not isinstance(sc, dict):
                continue
            dist = sc.get("distance")
            if not isinstance(dist, (int, float)) or dist != dist or dist < 0:
                continue
            slug = None
            for key in (sc.get("address_wifi_mac"), scanner_address, sc.get("address")):
                if key and str(key).lower() in receiver_names:
                    slug = receiver_names[str(key).lower()]
                    break
            slug = slug or sc.get("slug")
            if not slug:
                continue
            age = sc.get("age")
            prev = per.get(slug)
            # Two addresses under one slug (a receiver's BLE and Wi-Fi MAC): keep the freshest.
            if prev is not None and isinstance(prev.get("age"), (int, float)) and isinstance(age, (int, float)) \
                    and prev["age"] <= age:
                continue
            per[slug] = {"distance": float(dist), "age": age,
                         "address": str(sc.get("address") or scanner_address).lower()}
    return out


def receiver_ages(snapshot, receiver_names=None) -> dict | None:
    """Seconds since each receiver last relayed anything, by BPS receiver slug.

    Taken from every device in the snapshot (the receivers hear each other's
    beacons, so a working receiver stays fresh with nobody home). None for a
    snapshot this module doesn't understand.
    """
    if not isinstance(snapshot, dict) or snapshot.get("version") not in SUPPORTED_VERSIONS:
        return None
    receiver_names = receiver_names or {}
    ages = {}
    for dev in (snapshot.get("devices") or {}).values():
        if not isinstance(dev, dict):
            continue
        for scanner_address, sc in (dev.get("scanners") or {}).items():
            if not isinstance(sc, dict):
                continue
            age = sc.get("scanner_last_seen_age")
            if not isinstance(age, (int, float)):
                age = sc.get("age")
            if not isinstance(age, (int, float)):
                continue
            slug = None
            for key in (sc.get("address_wifi_mac"), scanner_address):
                if key and str(key).lower() in receiver_names:
                    slug = receiver_names[str(key).lower()]
                    break
            slug = slug or sc.get("slug")
            if slug and (slug not in ages or age < ages[slug]):
                ages[slug] = float(age)
    return ages


# --- Home Assistant glue --------------------------------------------------------

def _api():
    """Bermuda's api module, or None when this Bermuda has none."""
    try:
        from custom_components.bermuda import api  # noqa: PLC0415
    except Exception:
        return None
    return api if hasattr(api, "async_get_advert_snapshot") else None


def has_api() -> bool:
    """Whether the installed Bermuda has the read API at all."""
    return _api() is not None


def _cache(hass) -> dict:
    return hass.data.setdefault(_CACHE, {"snap": None, "snap_at": 0.0, "names": None, "names_at": 0.0,
                                         "warned": False})


def available(hass) -> bool:
    """Whether BPS can read Bermuda directly right now."""
    api = _api()
    if api is None:
        return False
    try:
        return api.async_get_coordinator(hass) is not None
    except Exception:
        return False


def snapshot(hass) -> dict | None:
    """Bermuda's snapshot (cached for a cycle), or None."""
    c = _cache(hass)
    now = time.monotonic()
    if c["snap"] is not None and now - c["snap_at"] <= SNAPSHOT_TTL:
        return c["snap"]
    api = _api()
    if api is None:
        return None
    try:
        snap = api.async_get_advert_snapshot(hass)
    except Exception as e:
        _LOGGER.debug("Bermuda snapshot failed: %s", e)
        return None
    if not isinstance(snap, dict):
        return None
    if snap.get("version") not in SUPPORTED_VERSIONS:
        if not c["warned"]:
            c["warned"] = True
            _LOGGER.warning("Bermuda's snapshot version %s is newer than this BPS understands; "
                            "reading the distance sensors instead", snap.get("version"))
        return None
    c["snap"], c["snap_at"] = snap, now
    return snap


def names(hass) -> tuple[dict, dict]:
    """BPS names for Bermuda's devices and receivers (cached)."""
    c = _cache(hass)
    now = time.monotonic()
    if c["names"] is not None and now - c["names_at"] <= NAMES_TTL:
        return c["names"]
    from homeassistant.helpers import entity_registry as er  # noqa: PLC0415
    reg = er.async_get(hass)
    entries = [(e.entity_id, e.unique_id) for e in reg.entities.values()
               if e.platform == "bermuda" and DISTANCE_TO in e.entity_id]
    c["names"], c["names_at"] = names_from_registry(entries), now
    return c["names"]


def async_readings(hass) -> dict | None:
    """{device prefix: {receiver slug: reading}} straight from Bermuda, or None."""
    snap = snapshot(hass)
    if snap is None:
        return None
    devs, recs = names(hass)
    return readings(snap, devs, recs)


def async_receiver_ages(hass) -> dict | None:
    """{receiver slug: seconds since last heard} straight from Bermuda, or None."""
    snap = snapshot(hass)
    if snap is None:
        return None
    return receiver_ages(snap, names(hass)[1])


def async_tracked(hass) -> list | None:
    """Prefixes of the devices Bermuda tracks, or None without the API."""
    snap = snapshot(hass)
    if snap is None:
        return None
    devs, _ = names(hass)
    out = set()
    for address, dev in (snap.get("devices") or {}).items():
        if not isinstance(dev, dict) or not dev.get("tracked"):
            continue
        prefix = next((devs[str(k).lower()] for k in (dev.get("unique_id"), address)
                       if k and str(k).lower() in devs), None) or dev.get("slug")
        if prefix:
            out.add(prefix)
    return sorted(out)
