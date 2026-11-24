"""Zone usage statistics: how long trackers stay in each zone, and how jumpy.

The placement advisor weighs zones by where people actually spend time. The
recorder can't be relied on for that (many installs exclude the chatty BPS
sensors), so BPS keeps its own small rolling summary: per day and zone the
dwell seconds, the number of visits, the short visits ("flaps") and
A -> B -> A bounces. Fed by state changes of the tracker zone sensors
(sensor.<tracker>_bps_zone), persisted in .storage/bps_zone_usage.
"""
from __future__ import annotations

import time
from collections import defaultdict
from datetime import date, timedelta

FLAP_S = 60
DWELL_CAP_S = 2 * 3600
KEEP_DAYS = 14
SAVE_DELAY_S = 600
INVALID = ("", "unknown", "unavailable", "not_home", "away", "none", None)


def _valid(z):
    return None if z in INVALID else z


class UsageStats:
    """Pure accumulator (unit-testable); the HA wiring is in async_setup_usage."""

    def __init__(self, data=None):
        self.days = dict((data or {}).get("days") or {})
        self._cur = {}   # entity -> (zone, since_ts, zone_before)

    def feed(self, entity_id, zone, ts):
        zone = _valid(zone)
        cur = self._cur.get(entity_id)
        if cur and cur[0] == zone:
            return False
        changed = False
        if cur and cur[0] is not None:
            prev_zone, since, before = cur
            dur = max(0.0, ts - since)
            day = self._day(ts)
            day["dwell"][prev_zone] = day["dwell"].get(prev_zone, 0.0) + min(dur, DWELL_CAP_S)
            day["visits"][prev_zone] = day["visits"].get(prev_zone, 0) + 1
            if dur < FLAP_S:
                day["flaps"][prev_zone] = day["flaps"].get(prev_zone, 0) + 1
                if before and zone == before:
                    key = f"{before}|{prev_zone}"
                    day["bounces"][key] = day["bounces"].get(key, 0) + 1
            changed = True
        before = cur[0] if cur else None
        self._cur[entity_id] = (zone, ts, before)
        return changed

    def _day(self, ts):
        key = date.fromtimestamp(ts).isoformat()
        if key not in self.days:
            self.days[key] = {"dwell": {}, "visits": {}, "flaps": {}, "bounces": {}}
            self.prune(ts)
        return self.days[key]

    def prune(self, ts):
        cutoff = (date.fromtimestamp(ts) - timedelta(days=KEEP_DAYS)).isoformat()
        for k in [k for k in self.days if k < cutoff]:
            del self.days[k]

    def summary(self):
        """(dwell, visits, flaps, bounces{(from, to): n}, days with data)."""
        dwell, visits, flaps, bounces = defaultdict(float), defaultdict(int), defaultdict(int), defaultdict(int)
        for d in self.days.values():
            for z, v in d["dwell"].items():
                dwell[z] += v
            for z, v in d["visits"].items():
                visits[z] += v
            for z, v in d["flaps"].items():
                flaps[z] += v
            for k, v in d["bounces"].items():
                a, _, b = k.partition("|")
                bounces[(a, b)] += v
        return dwell, visits, flaps, bounces, len(self.days)

    def to_data(self):
        return {"days": self.days}


async def async_setup_usage(hass, domain):
    """Load the stats, listen to tracker zone sensors, save every few minutes."""
    from homeassistant.core import callback
    from homeassistant.const import EVENT_STATE_CHANGED
    from homeassistant.helpers.storage import Store

    store = Store(hass, 1, "bps_zone_usage")
    try:
        data = await store.async_load()
    except Exception:  # corrupt file: start over rather than break BPS
        data = None
    stats = UsageStats(data)
    now = time.time()
    for st in hass.states.async_all("sensor"):
        if st.entity_id.endswith("_bps_zone"):
            stats.feed(st.entity_id, st.state, now)

    @callback
    def _changed(event):
        eid = event.data.get("entity_id") or ""
        if not eid.endswith("_bps_zone") or not eid.startswith("sensor."):
            return
        new = event.data.get("new_state")
        if stats.feed(eid, new.state if new else None, time.time()):
            store.async_delay_save(stats.to_data, SAVE_DELAY_S)

    unsub = hass.bus.async_listen(EVENT_STATE_CHANGED, _changed)
    hass.data.setdefault(domain, {})["usage"] = stats

    async def _stop():
        unsub()
        await store.async_save(stats.to_data())

    return _stop
