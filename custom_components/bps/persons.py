"""People: which tracker represents a person right now, and which zone they are in.

A person (HA ``person.*``) can carry several BPS trackers — a wearable, a
watch, a phone. The user orders them in the panel (Settings → Persons); the
first *usable* one wins:

  * usable  = position fresh (seen within ``stale_s``), not charging, zone known
  * a tracker that has been still for ``still_min`` while a lower-priority one
    moved within ``moved_recent_s`` is skipped — a watch left on the
    nightstand must not pin its owner to the bedroom while the phone walks
    around the house.

The chosen tracker's zone must hold for ``dwell_s`` before the person's zone
changes (no flicker on room borders). Result per person:
``sensor.bps_person_<person object id>_zone`` plus a ``bps_person_zone`` event
on every confirmed change.

Feature switches (follow me, suggestions) and the notification tap target are
stored here too, so one Settings page owns everything the user can toggle.
The pure helpers take plain data and are unit-tested without Home Assistant.
"""
from __future__ import annotations

import asyncio
import copy
import difflib
import logging
import math
import re
import time

from .zone_links import similarity

_LOGGER = logging.getLogger(__name__)

KINDS = ("wearable", "watch", "phone", "tag")
CHARGING_STATES = ("charging", "full", "on", "true")
TICK_S = 5

DEFAULT_SETTINGS = {
    "features": {"follow_me": False, "suggestions": False, "history": True, "auto_distance": True},
    "notify": {"tap_path": "/lovelace/0"},
    "tracking": {"dwell_s": 15, "still_min": 10, "moved_recent_s": 120,
                 "move_m": 1.5, "stale_s": 120},
    "persons": {},
    # Non-admin HA users: by default they may only view (the map card, and
    # later their own learned patterns). all_users=True gives every HA user
    # full configuration access, like BPS before 0.3.0.
    "access": {"all_users": False},
}
_LIMITS = {"dwell_s": (0, 600), "still_min": (1, 240), "moved_recent_s": (10, 3600),
           "move_m": (0.3, 10), "stale_s": (10, 3600)}


# --- settings ---------------------------------------------------------------

def merge_settings(stored) -> dict:
    """Stored settings on top of the defaults (missing keys filled in)."""
    out = copy.deepcopy(DEFAULT_SETTINGS)
    if not isinstance(stored, dict):
        return out
    for section in ("features", "notify", "tracking", "access"):
        if isinstance(stored.get(section), dict):
            out[section].update(stored[section])
    if isinstance(stored.get("persons"), dict):
        out["persons"] = copy.deepcopy(stored["persons"])
    return out


def validate_settings(data) -> dict:
    """Clean a settings payload from the panel; raises ValueError when invalid."""
    if not isinstance(data, dict):
        raise ValueError("settings must be an object")
    out = merge_settings({})
    feats = data.get("features") or {}
    for k in out["features"]:
        out["features"][k] = bool(feats.get(k, DEFAULT_SETTINGS["features"][k]))
    tap = str((data.get("notify") or {}).get("tap_path") or "").strip()
    if tap and not re.fullmatch(r"/[A-Za-z0-9_\-/]*", tap):
        raise ValueError("tap_path must be a path like /lovelace/0")
    out["notify"]["tap_path"] = tap or DEFAULT_SETTINGS["notify"]["tap_path"]
    trk = data.get("tracking") or {}
    for k, (lo, hi) in _LIMITS.items():
        v = trk.get(k, out["tracking"][k])
        try:
            v = float(v)
        except (TypeError, ValueError) as e:
            raise ValueError(f"tracking.{k} must be a number") from e
        if not lo <= v <= hi:
            raise ValueError(f"tracking.{k} must be between {lo} and {hi}")
        out["tracking"][k] = int(v) if float(v).is_integer() else v
    persons = {}
    for pid, p in (data.get("persons") or {}).items():
        if not re.fullmatch(r"person\.[a-z0-9_]+", str(pid)) or not isinstance(p, dict):
            raise ValueError(f"bad person id {pid!r}")
        trackers, seen = [], set()
        for t in p.get("trackers") or []:
            key = str((t or {}).get("key") or "")
            if not re.fullmatch(r"[a-z0-9_]+", key) or key in seen:
                raise ValueError(f"bad or duplicate tracker {key!r}")
            seen.add(key)
            kind = t.get("kind") if t.get("kind") in KINDS else "tag"
            charging = t.get("charging") or None
            if charging and not re.fullmatch(r"(sensor|binary_sensor)\.[a-z0-9_]+", charging):
                raise ValueError(f"bad charging entity {charging!r}")
            trackers.append({"key": key, "kind": kind, "charging": charging})
        notify = p.get("notify") or None
        if notify and not re.fullmatch(r"[a-z0-9_]+", notify):
            raise ValueError(f"bad notify service {notify!r}")
        persons[pid] = {"trackers": trackers, "notify": notify}
    out["persons"] = persons
    out["access"]["all_users"] = bool((data.get("access") or {}).get("all_users", False))
    return out


# --- suggestions for the panel ---------------------------------------------

def guess_kind(key: str) -> str:
    k = key.lower()
    if "watch" in k:
        return "watch"
    if re.search(r"band|ring|oura|fitbit|whoop|garmin|amazfit|tracker", k):
        return "wearable"
    if re.search(r"phone|pixel|galaxy|android|mobile", k):
        return "phone"
    return "tag"


def guess_charging(key: str, candidates: list[str]) -> str | None:
    """The battery-state / charging entity that best matches a tracker key."""
    best, score = None, 0.0
    stem = re.sub(r"_(ble|bermuda|tracker|irk)$", "", key)
    for eid in candidates:
        obj = eid.split(".", 1)[1]
        obj = re.sub(r"_(battery_state|charging|is_charging|battery_charging)$", "", obj)
        # whole-string ratio (not containment): "iphone" must not grab every
        # phone's battery sensor
        s = max(difflib.SequenceMatcher(None, key, obj).ratio(),
                difflib.SequenceMatcher(None, stem, obj).ratio())
        if s > score:
            best, score = eid, s
    return best if score >= 0.85 else None


def suggest_trackers(person_name: str, person_trackers: list[str], keys: list[str]) -> list[str]:
    """BPS tracker keys that probably belong to a person (device_trackers / name)."""
    out = []
    linked = {t.split(".", 1)[-1] for t in person_trackers}
    for key in keys:
        if key in linked or any([similarity(key, t) >= 0.9 for t in linked]):
            out.append(key)
    first = (person_name or "").split(" ")[0]
    for key in keys:
        if key not in out and len(first) >= 3 and similarity(first, key) >= 0.9:
            out.append(key)
    return out


# --- tracker choice (pure) --------------------------------------------------

def tracker_status(t, info, now, cfg) -> str | None:
    """None when usable, else a short reason."""
    if not info or info.get("updated") is None or now - info["updated"] > cfg["stale_s"]:
        return "not seen"
    if info.get("charging"):
        return "charging"
    if not info.get("zone"):
        return "no zone"
    return None


def pick_tracker(trackers, infos, now, cfg):
    """(chosen key or None, {key: status}) for an ordered tracker list."""
    status = {t["key"]: tracker_status(t, infos.get(t["key"]), now, cfg) for t in trackers}
    usable = [t["key"] for t in trackers if status[t["key"]] is None]
    still_s = cfg["still_min"] * 60
    for i, key in enumerate(usable):
        moved = infos[key].get("moved_at")
        still_for = now - moved if moved is not None else None
        if still_for is not None and still_for > still_s:
            lower_moving = [k for k in usable[i + 1:]
                            if infos[k].get("moved_at") is not None
                            and now - infos[k]["moved_at"] <= cfg["moved_recent_s"]]
            if lower_moving:
                status[key] = f"still {int(still_for // 60)} min"
                continue
        status[key] = "active"
        return key, status
    if usable:  # every usable one was skipped as still: fall back to the first
        status[usable[0]] = "active"
        return usable[0], status
    return None, status


class Dwell:
    """Confirm a value only after it has held for dwell_s."""

    def __init__(self):
        self.value = None
        self.since = None
        self._pending = None
        self._pending_at = None

    def feed(self, value, now, dwell_s) -> bool:
        """Returns True when the confirmed value changed."""
        if value == self.value:
            self._pending = None
            return False
        if value != self._pending:
            self._pending, self._pending_at = value, now
        if now - self._pending_at >= dwell_s or self.value is None and value is not None:
            self.value, self.since, self._pending = value, now, None
            return True
        return False


# --- runtime ----------------------------------------------------------------

class PersonTracker:
    """Background loop publishing sensor.bps_person_<id>_zone."""

    def __init__(self, hass, get_settings, domain="bps"):
        self.hass = hass
        self.get_settings = get_settings
        self.domain = domain
        self.motion = {}      # key -> {"anchor": (x, y, floor), "moved_at": ts}
        self.dwell = {}       # person -> Dwell
        self.status = {}      # person -> {"tracker", "trackers": {key: status}, "zone"}
        self._published = set()
        self._task = None

    def start(self):
        if self._task is None:
            self._task = self.hass.async_create_task(self._run())

    def stop(self):
        if self._task:
            self._task.cancel()
            self._task = None
        for eid in self._published:
            self.hass.states.async_remove(eid)
        self._published.clear()

    async def _run(self):
        while True:
            try:
                self.tick(time.time())
            except Exception as e:  # never let one bad tick kill the loop
                _LOGGER.warning("BPS persons tick failed: %s", e)
            await asyncio.sleep(TICK_S)

    def _scales(self):
        layout = self.hass.data.get(self.domain, {}).get("layout")
        out = {}
        if isinstance(layout, dict):
            for f in layout.get("floor") or []:
                if f.get("scale"):
                    out[f.get("name")] = float(f["scale"])
        return out

    def _update_motion(self, now, move_m):
        scales = self._scales()
        for rec in self.hass.data.get(self.domain, {}).get("apitricords") or []:
            key, c = rec.get("ent"), rec.get("cords") or {}
            if not key or "x" not in c:
                continue
            m = self.motion.setdefault(key, {"anchor": None, "moved_at": None})
            a = m["anchor"]
            scale = scales.get(rec.get("floor")) or 0
            if a is None:
                m["anchor"], m["moved_at"] = (c["x"], c["y"], rec.get("floor")), now
            elif a[2] != rec.get("floor") or (
                    scale and math.hypot(c["x"] - a[0], c["y"] - a[1]) / scale >= move_m):
                m["anchor"], m["moved_at"] = (c["x"], c["y"], rec.get("floor")), now

    def _info(self, t, updated_by_key):
        st = self.hass.states.get(f"sensor.{t['key']}_bps_zone")
        zone = st.state if st and st.state not in ("unknown", "unavailable", "") else None
        charging = False
        if t.get("charging"):
            cs = self.hass.states.get(t["charging"])
            charging = bool(cs and cs.state.lower() in CHARGING_STATES)
        return {"zone": zone, "updated": updated_by_key.get(t["key"]),
                "moved_at": (self.motion.get(t["key"]) or {}).get("moved_at"),
                "charging": charging}

    def tick(self, now):
        settings = self.get_settings()
        cfg = settings["tracking"]
        self._update_motion(now, cfg["move_m"])
        updated = {r.get("ent"): r.get("updated")
                   for r in self.hass.data.get(self.domain, {}).get("apitricords") or []}
        seen = set()
        for pid, p in settings["persons"].items():
            trackers = p.get("trackers") or []
            if not trackers:
                continue
            infos = {t["key"]: self._info(t, updated) for t in trackers}
            key, statuses = pick_tracker(trackers, infos, now, cfg)
            person_state = self.hass.states.get(pid)
            away = person_state is not None and person_state.state not in ("home",)
            raw = "away" if away and key is None else (infos[key]["zone"] if key else None)
            d = self.dwell.setdefault(pid, Dwell())
            old = d.value
            changed = d.feed(raw, now, cfg["dwell_s"])
            self.status[pid] = {"tracker": key, "trackers": statuses, "zone": d.value}
            eid = f"sensor.bps_person_{pid.split('.', 1)[1]}_zone"
            seen.add(eid)
            name = person_state.attributes.get("friendly_name") if person_state else pid
            self.hass.states.async_set(eid, d.value or "unknown", {
                "friendly_name": f"{name} BPS zone",
                "icon": "mdi:account-badge",
                "person": pid,
                "tracker": key,
                "trackers": statuses,
                "since": d.since,
            })
            self._published.add(eid)
            if changed and old is not None:
                self.hass.bus.async_fire("bps_person_zone", {
                    "person": pid, "from": old, "to": d.value, "tracker": key})
        for eid in list(self._published - seen):  # person removed from settings
            self.hass.states.async_remove(eid)
            self._published.discard(eid)
