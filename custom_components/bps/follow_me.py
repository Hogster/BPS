"""Follow me: music follows a person from zone to zone (always opt-in).

A session is started by the person: the "Follow me?" notification BPS sends
when music starts in the zone they are in, a dashboard button
(``bps.follow_me_start``) or an automation. While it runs, the speaker of each
new zone the person enters joins the group; the zone left behind drops out
after ``DROP_OLD_ROOM_S``. The first person in a zone keeps it: music already
owned by someone else's session, or playing outside follow me, is never
taken over. A session ends from the notification, ``bps.follow_me_stop``,
the person leaving home (music pauses), the music being paused for
``PAUSED_STOP_MIN`` or the feature being switched off.

Speakers come from the zone links (first linked player that can group).
Publishes ``sensor.bps_follow_<person>``: ``available`` (music plays where the
person is and nobody owns it), ``active`` or ``off``, for dashboard buttons.
"""
from __future__ import annotations

import asyncio
import logging
import time

from .rooms import as_callback
from .texts import clear, notify, text

_LOGGER = logging.getLogger(__name__)

DROP_OLD_ROOM_S = 30
PAUSED_STOP_MIN = 10
ASK_COOLDOWN_MIN = 30
TICK_S = 30


def follow_state(feature_on, has_session, speaker, speaker_state, owner):
    """off / available / active (pure, unit-tested)."""
    if not feature_on:
        return "off"
    if has_session:
        return "active"
    if speaker and speaker_state == "playing" and owner is None:
        return "available"
    return "off"


class FollowMe:
    def __init__(self, hass, home, log):
        self.hass = hass
        self.home = home
        self.log = log
        self.sessions = {}     # person -> {"coord", "rooms": [...], "paused_since"}
        self.asked = {}        # speaker -> ts last asked
        self._drop_tasks = {}
        self._published = set()
        self._unsubs = []
        self._task = None

    # --- lifecycle ----------------------------------------------------------
    def start(self):
        from homeassistant.const import EVENT_STATE_CHANGED
        bus = self.hass.bus
        self._unsubs = [
            bus.async_listen(EVENT_STATE_CHANGED, as_callback(self._state_changed)),
            bus.async_listen("bps_person_zone", as_callback(self._zone_changed)),
            bus.async_listen("mobile_app_notification_action", as_callback(self._notification_action)),
        ]
        self._task = self.hass.async_create_task(self._run())

    def stop(self):
        for u in self._unsubs:
            u()
        self._unsubs = []
        if self._task:
            self._task.cancel()
            self._task = None
        for t in self._drop_tasks.values():
            t.cancel()
        for eid in self._published:
            self.hass.states.async_remove(eid)
        self._published = set()

    async def _run(self):
        n = 0
        while True:
            try:
                self.publish_all()
                if n % 2 == 0:
                    await self.housekeeping()
            except Exception as e:  # one bad tick must not stop the loop
                _LOGGER.warning("BPS follow me tick failed: %s", e)
            n += 1
            await asyncio.sleep(TICK_S)

    # --- state ----------------------------------------------------------------
    def owner(self, speaker):
        for p, s in self.sessions.items():
            if speaker in s["rooms"]:
                return p
        return None

    def group(self, speaker):
        st = self.hass.states.get(speaker)
        members = st.attributes.get("group_members") if st else None
        return list(members or [speaker])

    def state_of(self, person):
        speaker = self.home.speaker_for_zone(self.home.zone_of_person(person))
        st = self.hass.states.get(speaker) if speaker else None
        return follow_state(self.home.feature("follow_me"), person in self.sessions,
                            speaker, st.state if st else None, self.owner(speaker) if speaker else None)

    def publish(self, person, people=None):
        info = (people or self.home.people()).get(person) or {}
        zone = self.home.zone_of_person(person)
        eid = f"sensor.bps_follow_{person}"
        self.hass.states.async_set(eid, self.state_of(person), {
            "friendly_name": f"BPS follow me {info.get('name', person)}",
            "icon": "mdi:music-note-plus", "person": info.get("person"), "zone": zone,
            "speaker": self.home.speaker_for_zone(zone)})
        self._published.add(eid)

    def publish_all(self):
        people = self.home.people()
        for p in people:
            self.publish(p, people)
        for eid in list(self._published):
            if eid[len("sensor.bps_follow_"):] not in people:
                self.hass.states.async_remove(eid)
                self._published.discard(eid)
        for p in list(self.sessions):
            if p not in people:
                self.hass.async_create_task(self.stop_session(p, "removed"))

    # --- sessions ---------------------------------------------------------------
    async def start_for(self, person, speaker=None):
        """Start following; speaker defaults to the one playing where the person is."""
        people = self.home.people()
        if person not in people:
            _LOGGER.warning("follow me: unknown person %s", person)
            return
        svc = people[person]["notify"]
        if not self.home.feature("follow_me"):
            await notify(self.hass, svc, text(self.hass, "follow_title"), text(self.hass, "follow_off"))
            return
        if speaker is None:
            speaker = self.home.speaker_for_zone(self.home.zone_of_person(person))
            st = self.hass.states.get(speaker) if speaker else None
            if not st or st.state != "playing":
                speaker = None
        if not speaker:
            await notify(self.hass, svc, text(self.hass, "follow_title"), text(self.hass, "follow_nothing"))
            return
        if self.owner(speaker) not in (None, person):
            return
        self.sessions[person] = {"coord": self.group(speaker)[0], "rooms": [speaker], "paused_since": None}
        self.publish(person)
        self.log.log("follow", person=person, event="started", speaker=speaker)
        await notify(self.hass, svc, text(self.hass, "follow_started_title"),
                     text(self.hass, "follow_started"), tag=f"bps_follow_{person}",
                     actions=[{"action": f"BPS_FOLLOW_STOP|{person}", "title": text(self.hass, "follow_stop")}])

    async def stop_session(self, person, reason, pause=False):
        s = self.sessions.pop(person, None)
        if not s:
            return
        t = self._drop_tasks.pop(person, None)
        if t:
            t.cancel()
        if pause:
            await self._call("media_pause", s["coord"])
        else:
            here = self.home.speaker_for_zone(self.home.zone_of_person(person))
            keep = here if here in s["rooms"] else s["rooms"][-1]
            for room in s["rooms"]:
                if room != keep:
                    await self._call("unjoin", room)
        if person in self.home.people():
            self.publish(person)
        self.log.log("follow", person=person, event="stopped", reason=reason)
        await clear(self.hass, (self.home.people().get(person) or {}).get("notify"), f"bps_follow_{person}")

    async def follow(self, person, zone):
        s = self.sessions.get(person)
        target = self.home.speaker_for_zone(zone)
        if not s or not target or target in s["rooms"]:
            return
        owner = self.owner(target)
        if owner and owner != person:
            return  # the first person in a zone keeps it
        st = self.hass.states.get(target)
        if not owner and st and st.state == "playing" and target not in self.group(s["coord"]):
            return  # someone plays here outside follow me
        coord = self.group(s["coord"])[0]
        await self._call("join", coord, group_members=[target])
        s["rooms"].append(target)
        s["coord"] = coord
        self.log.log("follow", person=person, event="joined", speaker=target, zone=zone)
        old = self._drop_tasks.pop(person, None)
        if old:
            old.cancel()
        self._drop_tasks[person] = self.hass.async_create_task(self._drop_old_rooms(person))

    async def _drop_old_rooms(self, person):
        await asyncio.sleep(DROP_OLD_ROOM_S)
        s = self.sessions.get(person)
        if not s:
            return
        here = self.home.speaker_for_zone(self.home.zone_of_person(person))
        for room in list(s["rooms"]):
            if room == here or len(s["rooms"]) <= 1:
                continue
            await self._call("unjoin", room)
            s["rooms"].remove(room)
            self.log.log("follow", person=person, event="left", speaker=room)
        await asyncio.sleep(5)
        if s["rooms"]:
            s["coord"] = self.group(s["rooms"][-1])[0]

    async def housekeeping(self, now=None):
        now = time.time() if now is None else now
        for person, s in list(self.sessions.items()):
            if not self.home.feature("follow_me"):
                await self.stop_session(person, "feature_off")
            elif not self.home.is_home(person):
                await self.stop_session(person, "left_home", pause=True)
            else:
                st = self.hass.states.get(s["coord"])
                if st and st.state == "playing":
                    s["paused_since"] = None
                elif s["paused_since"] is None:
                    s["paused_since"] = now
                elif now - s["paused_since"] > PAUSED_STOP_MIN * 60:
                    await self.stop_session(person, "paused")

    async def _call(self, service, entity_id, **data):
        try:
            await self.hass.services.async_call(
                "media_player", service, {"entity_id": entity_id, **data}, blocking=True)
        except Exception as e:
            _LOGGER.warning("follow me: media_player.%s %s failed: %s", service, entity_id, e)

    # --- events -----------------------------------------------------------------
    def _zone_changed(self, event):
        person = str(event.data.get("person") or "").split(".", 1)[-1]
        if person not in self.home.people():
            return
        zone = event.data.get("to")
        if person in self.sessions and zone:
            self.hass.async_create_task(self.follow(person, zone))
        self.publish(person)

    def _state_changed(self, event):
        eid = event.data.get("entity_id") or ""
        if not eid.startswith("media_player."):
            return
        old, new = event.data.get("old_state"), event.data.get("new_state")
        if old is not None and new is not None and old.state == new.state:
            return  # attribute-only update (track position, volume)
        zones = self.home.zones_for_speaker(eid)
        if not zones:
            return
        self.publish_all()   # a button may appear or disappear
        if not new or new.state != "playing" or (old and old.state == "playing"):
            return
        # Started by an automation or script (e.g. restoring music after an
        # announcement): not someone pressing play, so don't ask.
        if new.context is not None and new.context.parent_id is not None:
            return
        self.maybe_ask(eid, zones)

    def maybe_ask(self, speaker, zones, now=None):
        now = time.time() if now is None else now
        if not self.home.feature("follow_me") or self.owner(speaker):
            return
        last = self.asked.get(speaker)
        if last is not None and now - last < ASK_COOLDOWN_MIN * 60:
            return
        people = [p for z in zones for p in self.home.occupants(z)]
        if not people:
            return
        self.asked[speaker] = now
        info = self.home.people()
        for p in people:
            self.log.log("suggestion", kind="follow_me", person=p, speaker=speaker, answer="asked")
            self.hass.async_create_task(notify(
                self.hass, info[p]["notify"], text(self.hass, "follow_ask_title"),
                text(self.hass, "follow_ask"), tag=f"bps_follow_{p}", actions=[
                    {"action": f"BPS_FOLLOW_YES|{p}|{speaker}", "title": text(self.hass, "yes")},
                    {"action": f"BPS_FOLLOW_NO|{p}|{speaker}", "title": text(self.hass, "no")}]))

    def _notification_action(self, event):
        action = str(event.data.get("action") or "")
        if not action.startswith("BPS_FOLLOW_"):
            return
        parts = action.split("|")
        if parts[0] == "BPS_FOLLOW_YES" and len(parts) == 3:
            self.log.log("suggestion", kind="follow_me", person=parts[1], speaker=parts[2], answer="yes")
            if self.owner(parts[2]) is None:
                self.hass.async_create_task(self.start_for(parts[1], parts[2]))
        elif parts[0] == "BPS_FOLLOW_NO" and len(parts) == 3:
            self.log.log("suggestion", kind="follow_me", person=parts[1], speaker=parts[2], answer="no")
        elif parts[0] == "BPS_FOLLOW_STOP" and len(parts) == 2:
            self.hass.async_create_task(self.stop_session(parts[1], "notification"))
