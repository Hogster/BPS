"""The home as BPS sees it: who is in which zone, and what belongs to a zone.

Everything here is derived from what the user set up in the panel:

* people and their zone   - Settings -> Persons (sensor.bps_person_<id>_zone)
* a zone's speaker        - zone links (media players); the first linked player
                            that can group (has ``group_members``, e.g. Sonos)
* a zone's room sensors   - zone links (presence sensors)
* the zone of an entity   - a linked media player / sensor, else the entity's
                            HA area when a zone is linked to that area

Install-specific naming conventions are deliberately not guessed: a zone
without links simply has no speaker. ``Home`` is the read-only view the
follow-me and suggestion engines share; ``ZoneCounts`` publishes
``sensor.bps_zone_<zone>`` (known people + unidentified ones the room sensors
see).
"""
from __future__ import annotations

import logging
import time

from .zone_links import iter_zones, norm

_LOGGER = logging.getLogger(__name__)

PRESENCE_HOLD_S = 120     # keep a room-sensor head count this long after it drops
AWAY_STATES = (None, "", "unknown", "unavailable", "away", "not_home")


def slug(text) -> str:
    """Entity-id friendly zone slug ("Hallway floor 1" -> "hallwayfloor1")."""
    return norm(text)


class Home:
    """Read-only helpers over the live layout, settings and HA states."""

    def __init__(self, hass, domain="bps"):
        self.hass = hass
        self.domain = domain
        self._area_cache = {}
        self._area_cache_layout = None
        self._seen = {}            # zone -> (count, ts last > 0)

    # --- config ---------------------------------------------------------------
    @property
    def bucket(self):
        return self.hass.data.get(self.domain, {})

    @property
    def layout(self):
        layout = self.bucket.get("layout")
        return layout if isinstance(layout, dict) else {}

    def settings(self):
        from .persons import merge_settings
        return merge_settings(self.bucket.get("settings"))

    def feature(self, name) -> bool:
        return bool(self.settings()["features"].get(name))

    def tap_path(self) -> str:
        return self.settings()["notify"].get("tap_path") or "/lovelace/0"

    # --- people ---------------------------------------------------------------
    def people(self) -> dict:
        """object_id -> {"person", "user_id", "name", "notify"} for persons with trackers."""
        out = {}
        for pid, cfg in self.settings()["persons"].items():
            if not cfg.get("trackers"):
                continue
            st = self.hass.states.get(pid)
            uid = st.attributes.get("user_id") if st else None
            name = (st.attributes.get("friendly_name") if st else None) or pid
            out[pid.split(".", 1)[1]] = {
                "person": pid, "user_id": uid, "name": name.split(" ")[0],
                "notify": cfg.get("notify") or auto_notify(self.hass, uid),
            }
        return out

    def person_for_user(self, user_id):
        if not user_id:
            return None
        for p, info in self.people().items():
            if info["user_id"] == user_id:
                return p
        return None

    def zone_of_person(self, person):
        st = self.hass.states.get(f"sensor.bps_person_{person}_zone")
        z = st.state if st else None
        return None if z in AWAY_STATES else z

    def is_home(self, person) -> bool:
        info = self.people().get(person)
        st = self.hass.states.get(info["person"]) if info else None
        return bool(st and st.state == "home")

    def occupants(self, zone) -> list:
        if not zone:
            return []
        return sorted(p for p in self.people() if self.zone_of_person(p) == zone)

    # --- zones ----------------------------------------------------------------
    def zones(self) -> list:
        return [z["entity_id"] for _f, z in iter_zones(self.layout) if not z.get("no_go")]

    def zone(self, name) -> dict:
        n = norm(name)
        for _f, z in iter_zones(self.layout):
            if norm(z["entity_id"]) == n:
                return z
        return {}

    def speaker_for_zone(self, zone):
        """First linked media player that can group (Sonos and alike)."""
        if not zone:
            return None
        for eid in self.zone(zone).get("media_players") or []:
            st = self.hass.states.get(eid)
            if st is not None and st.attributes.get("group_members") is not None:
                return eid
        return None

    def zones_for_speaker(self, speaker) -> list:
        return [z for z in self.zones() if self.speaker_for_zone(z) == speaker]

    def presence_sensors(self, zone) -> list:
        return [e for e in self.zone(zone).get("presence_sensors") or [] if isinstance(e, str)]

    def sensed_count(self, zone, now=None) -> int:
        """People the room sensors see (max over sensors), held briefly."""
        now = time.time() if now is None else now
        best = 0
        for eid in self.presence_sensors(zone):
            st = self.hass.states.get(eid)
            if st is None:
                continue
            if eid.startswith("binary_sensor."):
                best = max(best, 1 if st.state == "on" else 0)
            else:
                try:
                    best = max(best, int(float(st.state)))
                except (TypeError, ValueError):
                    pass
        prev = self._seen.get(zone)
        if best > 0:
            self._seen[zone] = (best, now)
        elif prev and now - prev[1] < PRESENCE_HOLD_S:
            best = prev[0]
        return best

    def unknown_count(self, zone) -> int:
        return max(0, self.sensed_count(zone) - len(self.occupants(zone)))

    def zone_of_entity(self, entity_id):
        """Zone an entity belongs to: a zone link, else the zone linked to its area."""
        layout = self.layout
        if self._area_cache_layout is not layout:
            self._area_cache, self._area_cache_layout = {}, layout
        if entity_id in self._area_cache:
            return self._area_cache[entity_id]
        zone, by_area = None, {}
        for _f, z in iter_zones(layout):
            if entity_id in (z.get("media_players") or []) or entity_id in (z.get("presence_sensors") or []):
                zone = z["entity_id"]
                break
            if z.get("area_id"):
                by_area.setdefault(z["area_id"], z["entity_id"])
        if zone is None and by_area:
            zone = by_area.get(area_of(self.hass, entity_id))
        self._area_cache[entity_id] = zone
        return zone


def as_callback(method):
    """Wrap a bound method as an HA @callback (runs in the event loop).

    HA marks callbacks with an attribute, which a bound method can't carry.
    """
    from homeassistant.core import callback

    def _run(event):
        return method(event)
    return callback(_run)


def area_of(hass, entity_id):
    """HA area of an entity (its own, else its device's)."""
    try:
        from homeassistant.helpers import device_registry as dr
        from homeassistant.helpers import entity_registry as er
        ent = er.async_get(hass).async_get(entity_id)
        if ent is None:
            return None
        if ent.area_id:
            return ent.area_id
        if ent.device_id:
            dev = dr.async_get(hass).async_get(ent.device_id)
            return dev.area_id if dev else None
    except Exception as e:  # registries are best effort
        _LOGGER.debug("area lookup failed for %s: %s", entity_id, e)
    return None


def auto_notify(hass, user_id):
    """The user's companion-app notify service (first registered phone)."""
    if not user_id:
        return None
    from homeassistant.util import slugify
    for entry in hass.config_entries.async_entries("mobile_app"):
        if entry.data.get("user_id") == user_id and entry.data.get("device_name"):
            svc = f"mobile_app_{slugify(entry.data['device_name'])}"
            if hass.services.has_service("notify", svc):
                return svc
    return None


class ZoneCounts:
    """sensor.bps_zone_<zone>: known people + unidentified ones per zone."""

    def __init__(self, home: Home):
        self.home = home
        self._published = set()

    def tick(self, now=None):
        hass = self.home.hass
        seen = set()
        for zone in self.home.zones():
            known = self.home.occupants(zone)
            sensors = self.home.presence_sensors(zone)
            unknown = max(0, self.home.sensed_count(zone, now) - len(known)) if sensors else 0
            eid = f"sensor.bps_zone_{slug(zone)}"
            seen.add(eid)
            hass.states.async_set(eid, len(known) + unknown, {
                "friendly_name": f"BPS {zone}", "icon": "mdi:account-group",
                "unit_of_measurement": "people", "zone": zone,
                "known": known, "unknown": unknown, "sensors": sensors})
        for eid in self._published - seen:
            hass.states.async_remove(eid)
        self._published = seen

    def stop(self):
        for eid in self._published:
            self.home.hass.states.async_remove(eid)
        self._published = set()
