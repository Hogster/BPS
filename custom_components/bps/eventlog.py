"""BPS event log: what happened at home, kept locally for history and learning.

One JSON object per line in ``<config>/bps_data/events-YYYY-MM.jsonl``:

* ``zone``       a person's confirmed zone changed
* ``action``     a manual change of a light, player, cover, climate, fan or
                 switch (automation/script driven changes are skipped), with
                 who did it when known: the HA user, or the only person in
                 that zone
* ``suggestion`` a question asked / answered / expired, and automatic runs
* ``follow``     follow-me sessions (started, joined, left, stopped)

Nothing leaves the install. Writing is append-only and batched off the event
loop; files older than ``KEEP_MONTHS`` are deleted. Turn it off with Settings
-> Features -> History (then nothing is written; follow me and suggestions
keep working).
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime

from .rooms import as_callback

_LOGGER = logging.getLogger(__name__)

KEEP_MONTHS = 3
FLUSH_S = 5
STARTUP_GRACE_S = 120      # integrations restoring state after a restart aren't actions
LOG_DOMAINS = ("light", "media_player", "cover", "climate", "fan", "switch")
NOISE = ("unavailable", "unknown")
ATTRS = ("brightness", "color_temp_kelvin", "media_title", "media_artist", "source",
         "app_name", "temperature", "current_position")


def _month_key(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m")


class EventLog:
    def __init__(self, hass, directory=None):
        self.hass = hass
        self.dir = directory or hass.config.path("bps_data")
        self._buf = []
        self._flush_handle = None
        self.enabled = lambda: True

    def log(self, rec_type, **data):
        if rec_type not in ("suggestion", "follow") and not self.enabled():
            return
        rec = {"t": datetime.now().isoformat(timespec="seconds"), "type": rec_type}
        rec.update({k: v for k, v in data.items() if v is not None})
        self._buf.append(rec)
        if self._flush_handle is None:
            self._flush_handle = self.hass.loop.call_later(FLUSH_S, self._schedule_flush)

    def _schedule_flush(self):
        self._flush_handle = None
        self.hass.async_create_task(self.async_flush())

    async def async_flush(self):
        if not self._buf:
            return
        recs, self._buf = self._buf, []
        await self.hass.async_add_executor_job(self._write, recs)

    def _write(self, recs):
        os.makedirs(self.dir, exist_ok=True)
        by_file = {}
        for r in recs:
            month = r["t"][:7]
            by_file.setdefault(os.path.join(self.dir, f"events-{month}.jsonl"), []).append(r)
        for path, rows in by_file.items():
            with open(path, "a", encoding="utf-8") as fh:
                for r in rows:
                    fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")

    def prune(self, now=None):
        """Delete month files older than KEEP_MONTHS (runs in the executor)."""
        now = time.time() if now is None else now
        d = datetime.fromtimestamp(now)
        idx = d.year * 12 + d.month - 1 - KEEP_MONTHS
        cutoff = f"{idx // 12:04d}-{idx % 12 + 1:02d}"
        try:
            names = os.listdir(self.dir)
        except OSError:
            return
        for name in names:
            if name.startswith("events-") and name.endswith(".jsonl") and name[7:14] < cutoff:
                try:
                    os.remove(os.path.join(self.dir, name))
                except OSError as e:
                    _LOGGER.warning("Could not prune %s: %s", name, e)

    def read(self, since_ts, types=None, limit=None):
        """Records since since_ts (newest last); runs in the executor."""
        since = datetime.fromtimestamp(since_ts).isoformat(timespec="seconds")
        months = sorted({_month_key(since_ts), _month_key(time.time())})
        out = []
        for m in months:
            path = os.path.join(self.dir, f"events-{m}.jsonl")
            try:
                fh = open(path, encoding="utf-8")
            except OSError:
                continue
            with fh:
                for line in fh:
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    if r.get("t", "") >= since and (types is None or r.get("type") in types):
                        out.append(r)
        return out[-limit:] if limit else out


class ActivityLogger:
    """Feeds the event log from HA state changes and BPS zone events."""

    def __init__(self, hass, home, log: EventLog):
        self.hass = hass
        self.home = home
        self.log = log
        self.started = time.time()
        self._unsubs = []

    def start(self):
        from homeassistant.const import EVENT_STATE_CHANGED
        # @callback: run in the event loop (not the executor), cheap filters first.
        self._unsubs.append(self.hass.bus.async_listen(EVENT_STATE_CHANGED, as_callback(self._state_changed)))
        self._unsubs.append(self.hass.bus.async_listen("bps_person_zone", as_callback(self._zone_changed)))

    def stop(self):
        for u in self._unsubs:
            u()
        self._unsubs = []

    def _zone_changed(self, event):
        d = event.data
        person = str(d.get("person") or "").split(".", 1)[-1]
        self.log.log("zone", person=person, **{"from": d.get("from"), "to": d.get("to")},
                     tracker=d.get("tracker"))

    def _state_changed(self, event):
        eid = event.data.get("entity_id") or ""
        if eid.split(".", 1)[0] not in LOG_DOMAINS:
            return
        if time.time() - self.started < STARTUP_GRACE_S:
            return
        old, new = event.data.get("old_state"), event.data.get("new_state")
        if old is None or new is None or old.state == new.state:
            return
        if new.state in NOISE or old.state in NOISE:
            return
        ctx = new.context
        if ctx is None or ctx.parent_id is not None:
            return  # automation/script driven
        rec = describe_action(self.home, eid, old.state, new.state, new.attributes, ctx.user_id)
        self.log.log("action", **rec)


def describe_action(home, entity_id, old, new, attributes, user_id):
    """Who probably did it: the HA user, else the only person in that zone."""
    by, how = home.person_for_user(user_id), "app"
    zone = home.zone_of_entity(entity_id)
    occ = home.occupants(zone) if zone else []
    if by is None:
        how = "unknown"
        if len(occ) == 1:
            by, how = occ[0], "presence"
    attrs = {k: attributes.get(k) for k in ATTRS if attributes.get(k) is not None}
    return {"entity": entity_id, "from": old, "to": new, "attrs": attrs or None,
            "zone": zone, "occupants": occ, "by": by, "how": how}
