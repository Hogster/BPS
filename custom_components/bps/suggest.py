"""Suggestions: ask the people in a zone before doing something for them.

Any automation can make a suggestion with ``bps.suggest``: *when* it is a good
moment is the automation's trigger, *who* to ask and *how* is BPS's job.

    action: bps.suggest
    data:
      id: tv_cozy                 # stable key; answers are learned per id
      zone: Livingroom            # ask the people BPS sees in this zone
      title: "📺 Cozy?"
      message: Dim the lights for the TV?
      changes:                    # only lights linked to the zone
        light.livingroom_ceiling: 30      # %
        light.livingroom_spots: "off"
      unknown_message: Someone is watching TV ...   # optional, see below

A suggestion only ever changes the zone's own linked lights (see plan.py):
BPS refuses anything else and never runs scripts on its own. People add
their own extras (other lights, speakers, scripts they pick) in the Learned
tab, ticked per person.

BPS then
* asks each known person in the zone (notification with Yes / No / Don't ask
  again) and shows the open question in ``sensor.bps_suggestion`` for a
  dashboard card; the first answer settles it for everyone asked;
* when only unidentified people are in the zone (room sensors see someone
  without a tracker, e.g. kids or guests) and ``unknown_message`` is given,
  asks the people at home instead, never automatically;
* learns per person: 3 yes in a row and it just happens next time (with an
  Undo button), "Don't ask again" stops it, Undo goes back to asking;
* asks at most once per ``once_per`` (default: evening, reset at noon);
* drops an unanswered question after 30 min or on ``bps.suggestion_clear``.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta

from . import plan as planner
from .rooms import as_callback
from .texts import clear, notify, text

_LOGGER = logging.getLogger(__name__)

AUTO_AFTER_YES = 3
EXPIRE_MIN = 30
ANSWERS = ("yes", "no", "never", "undo")
ONCE_PER = ("evening", "day", "hour", "none")
STORE_KEY = "bps_suggestions"
TICK_S = 60


def period_key(once_per, now=None):
    """Bucket a suggestion may be asked once in ('none' never repeats a bucket)."""
    d = datetime.fromtimestamp(time.time() if now is None else now)
    if once_per == "day":
        return d.date().isoformat()
    if once_per == "hour":
        return d.strftime("%Y-%m-%dT%H")
    if once_per == "none":
        return None
    return (d - timedelta(hours=12)).date().isoformat()   # evening: resets at noon


def learn(pref, answer, key):
    """Update one person's preference for a suggestion key (pure)."""
    if answer == "yes":
        pref["yes"] += 1
        pref["streak"] += 1
        if pref["streak"] >= AUTO_AFTER_YES and "@" not in key:
            pref["mode"] = "auto"
    elif answer == "no":
        pref["no"] += 1
        pref["streak"] = 0
    elif answer == "never":
        pref["mode"] = "never"
        pref["streak"] = 0
    elif answer == "undo":
        pref["mode"] = "ask"
        pref["streak"] = 0
    return pref


def validate_definition(data) -> dict:
    """Clean a bps.suggest call; raises ValueError."""
    sid = str(data.get("id") or "").strip()
    if not sid or not all(c.isalnum() or c in "_-" for c in sid):
        raise ValueError("id must be letters, digits, _ or -")
    if data.get("action"):
        raise ValueError("action is not supported: a suggestion only changes the zone's own "
                         "lights (changes). Add scripts as your own extras in the Learned tab.")
    for f in ("zone", "title", "message"):
        if not str(data.get(f) or "").strip():
            raise ValueError(f"{f} is required")
    changes = planner.parse_changes(data.get("changes"))
    once = str(data.get("once_per") or "evening")
    if once not in ONCE_PER:
        raise ValueError(f"once_per must be one of {', '.join(ONCE_PER)}")
    return {"id": sid, "zone": str(data["zone"]).strip(), "title": str(data["title"]),
            "message": str(data["message"]), "changes": changes,
            "done_message": str(data.get("done_message") or ""),
            "unknown_message": str(data.get("unknown_message") or ""),
            "once_per": once}


class Suggestions:
    def __init__(self, hass, home, log):
        self.hass = hass
        self.home = home
        self.log = log
        self.prefs = {}      # person -> key -> {yes, no, streak, mode}
        self.handled = {}    # id -> period key it was last asked/done in
        self.defs = {}       # id -> last definition (answers may come later)
        self.open = {}       # id -> open question for the dashboard
        self.overrides = {}  # id -> light -> spec | {"skip": True} (administrator)
        self.extras = {}     # id -> [extra] (people's own additions)
        self._store = None
        self._unsubs = []
        self._task = None

    # --- lifecycle --------------------------------------------------------------
    async def async_load(self):
        from homeassistant.helpers.storage import Store
        self._store = Store(self.hass, 1, STORE_KEY)
        try:
            data = await self._store.async_load() or {}
        except Exception:
            data = {}
        self.prefs = data.get("prefs") or {}
        self.handled = data.get("handled") or {}
        self.defs = {k: v for k, v in (data.get("defs") or {}).items() if "changes" in v}
        self.overrides = data.get("overrides") or {}
        self.extras = data.get("extras") or {}

    def _save(self):
        if self._store:
            self._store.async_delay_save(
                lambda: {"prefs": self.prefs, "handled": self.handled, "defs": self.defs,
                         "overrides": self.overrides, "extras": self.extras}, 2)

    def start(self):
        self._unsubs = [self.hass.bus.async_listen(
            "mobile_app_notification_action", as_callback(self._notification_action))]
        self.publish()
        self._task = self.hass.async_create_task(self._run())

    def stop(self):
        for u in self._unsubs:
            u()
        self._unsubs = []
        if self._task:
            self._task.cancel()
            self._task = None

    async def _run(self):
        while True:
            await asyncio.sleep(TICK_S)
            try:
                await self.expire()
            except Exception as e:
                _LOGGER.warning("BPS suggestions tick failed: %s", e)

    # --- prefs ------------------------------------------------------------------
    def pref(self, person, key):
        return self.prefs.setdefault(person, {}).setdefault(
            key, {"yes": 0, "no": 0, "streak": 0, "mode": "ask"})

    # --- what it does -------------------------------------------------------------
    def name_of(self, eid):
        st = self.hass.states.get(eid)
        name = str((st.attributes.get("friendly_name") if st else None) or "").strip()
        return name or eid.split(".", 1)[-1].replace("_", " ")

    def plan(self, d, deciders):
        home = self.home
        return planner.plan(
            d, self.overrides.get(d["id"]), self.extras.get(d["id"]), deciders,
            zone_lights=home.lights(d["zone"]), zone_of=home.zone_of_entity,
            occupants=home.occupants, speakers=home.speakers())

    def summary(self, d, deciders):
        steps, _skipped = self.plan(d, deciders)
        return planner.summary(steps, self.name_of, lambda k: text(self.hass, k), d["zone"])

    def check(self, d):
        """Refuse a definition that touches anything outside the zone's lights."""
        planner.check_zone(d["changes"], d["zone"], self.home.lights(d["zone"]))

    # --- asking -----------------------------------------------------------------
    async def suggest(self, d, now=None):
        """Handle a bps.suggest call (definition already validated)."""
        now = time.time() if now is None else now
        sid = d["id"]
        self.check(d)
        if self.defs.get(sid) != d:
            self.defs[sid] = d
            self._save()      # the Learned tab shows it even if nobody was asked
        if not self.home.feature("suggestions"):
            return "feature_off"
        period = period_key(d["once_per"], now)
        if period is not None and self.handled.get(sid) == period:
            return "already_handled"
        if sid in self.open:
            return "open"
        people = self.home.occupants(d["zone"])
        key, ask_text = sid, d["message"]
        if not people and d["unknown_message"] and self.home.unknown_count(d["zone"]) > 0:
            people = [p for p in self.home.people() if self.home.is_home(p)]
            key, ask_text = f"{sid}@unknown", d["unknown_message"]
        active = [p for p in people if self.pref(p, key)["mode"] != "never"]
        if not active:
            return "nobody"
        if period is not None:
            self.handled[sid] = period
        self._save()
        info = self.home.people()
        url = self.home.tap_path()
        tag = f"bps_sugg_{sid}"
        auto = [p for p in active if self.pref(p, key)["mode"] == "auto"] if key == sid else []
        if auto:
            await self._run_action(d, auto)
            done = d["done_message"] or d["title"]
            what = self.summary(d, auto)
            for p in active:
                self.log.log("suggestion", kind=sid, person=p, answer="auto")
                await notify(self.hass, info[p]["notify"], d["title"], f"{done}\n{what}", tag=tag, url=url,
                             actions=[{"action": f"BPS_SUGG|{sid}|{p}|undo", "title": text(self.hass, "undo")}])
            self._set_open(sid, key, "done", d["title"], done, active, now, what)
            return "auto"
        for p in active:
            self.log.log("suggestion", kind=key, person=p, answer="asked")
            what = self.summary(d, [p])
            await notify(self.hass, info[p]["notify"], d["title"], f"{ask_text}\n{what}", tag=tag, url=url, actions=[
                {"action": f"BPS_SUGG|{key}|{p}|yes", "title": text(self.hass, "yes")},
                {"action": f"BPS_SUGG|{key}|{p}|no", "title": text(self.hass, "no")},
                {"action": f"BPS_SUGG|{key}|{p}|never", "title": text(self.hass, "never"),
                 "destructive": True}])
        self._set_open(sid, key, "ask", d["title"], ask_text, active, now, self.summary(d, []))
        return "asked"

    async def _run_action(self, d, deciders):
        """Base changes + the deciders' own extras; snapshot first for Undo."""
        steps, skipped = self.plan(d, deciders)
        undo = planner.undo_entities(steps)
        if undo:
            try:
                await self.hass.services.async_call("scene", "create", {
                    "scene_id": f"bps_undo_{d['id']}", "snapshot_entities": undo}, blocking=True)
            except Exception as e:
                _LOGGER.warning("suggestion %s: undo snapshot failed: %s", d["id"], e)
        for domain, service, data in planner.service_calls(steps):
            try:
                await self.hass.services.async_call(domain, service, data, blocking=False)
            except Exception as e:
                _LOGGER.warning("suggestion %s: %s.%s %s failed: %s", d["id"], domain, service,
                                data.get("entity_id"), e)
        for sk in skipped:
            _LOGGER.info("suggestion %s: %s skipped (%s)", d["id"], sk["entity"], sk["reason"])
        return steps, skipped

    async def _undo(self, d):
        if self.hass.states.get(f"scene.bps_undo_{d['id']}") is not None:
            await self.hass.services.async_call(
                "scene", "turn_on", {"entity_id": f"scene.bps_undo_{d['id']}"}, blocking=False)

    # --- answers ----------------------------------------------------------------
    async def answer(self, key, person, answer, via):
        sid = key.split("@")[0]
        d = self.defs.get(sid)
        if d is None or answer not in ANSWERS or person not in self.home.people():
            _LOGGER.warning("suggestion answer ignored: %s / %s / %s", key, person, answer)
            return False
        self.log.log("suggestion", kind=key, person=person, answer=answer, via=via)
        if answer == "yes":
            await self._run_action(d, [person])
        elif answer == "undo":
            await self._undo(d)
        learn(self.pref(person, key), answer, key)
        await self._clear_open(sid)   # one answer settles it for everyone asked
        self._save()
        return True

    async def answer_open(self, person, answer, via="dashboard", key=None):
        if key is None:
            if not self.open:
                return False
            key = next(iter(self.open.values()))["key"]
        return await self.answer(key, person, answer, via)

    def _notification_action(self, event):
        action = str(event.data.get("action") or "")
        if not action.startswith("BPS_SUGG|"):
            return
        parts = action.split("|")
        if len(parts) == 4:
            self.hass.async_create_task(self.answer(parts[1], parts[2], parts[3], "notification"))

    # --- open questions (dashboard) ---------------------------------------------
    def publish(self):
        attrs = {"friendly_name": text(self.hass, "sensor_suggestion"), "icon": "mdi:lightbulb-question-outline"}
        if not self.open:
            self.hass.states.async_set("sensor.bps_suggestion", "none", attrs)
            return
        sid, q = next(iter(self.open.items()))
        attrs.update({"icon": "mdi:lightbulb-question", "suggestion": sid, "key": q["key"],
                      "title": q["title"], "text": q["text"], "changes": q.get("changes", ""),
                      "asked": q["asked"],
                      "since": datetime.fromtimestamp(q["at"]).isoformat(timespec="seconds"),
                      "open_count": len(self.open)})
        self.hass.states.async_set("sensor.bps_suggestion", q["kind"], attrs)

    def _set_open(self, sid, key, kind, title, body, asked, now, changes=""):
        self.open[sid] = {"key": key, "kind": kind, "title": title, "text": body,
                          "changes": changes, "asked": list(asked), "at": now}
        self.publish()

    async def _clear_open(self, sid):
        q = self.open.pop(sid, None)
        self.publish()
        if q:
            info = self.home.people()
            for p in q["asked"]:
                await clear(self.hass, (info.get(p) or {}).get("notify"), f"bps_sugg_{sid}")

    async def clear_suggestion(self, sid, reason="ended"):
        q = self.open.get(sid)
        if not q:
            return
        if q["kind"] == "ask":
            for p in q["asked"]:   # unanswered: neither yes nor no
                self.log.log("suggestion", kind=q["key"], person=p, answer="expired", reason=reason)
        await self._clear_open(sid)

    async def expire(self, now=None):
        now = time.time() if now is None else now
        if not self.home.feature("suggestions"):
            for sid in list(self.open):
                await self._clear_open(sid)
            return
        for sid, q in list(self.open.items()):
            if now - q["at"] > EXPIRE_MIN * 60:
                await self.clear_suggestion(sid, "timeout")

    def reask(self, sid=None):
        for s in ([sid] if sid else list(self.handled)):
            self.handled.pop(s, None)
        self._save()
