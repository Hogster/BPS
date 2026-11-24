"""Wires the home engine into Home Assistant: event log, zone counts,
follow me, suggestions and the bps.* services that drive them."""
from __future__ import annotations

import asyncio
import logging

from .eventlog import ActivityLogger, EventLog
from .follow_me import FollowMe
from .rooms import Home, ZoneCounts
from .suggest import ANSWERS, ONCE_PER, Suggestions, validate_definition

_LOGGER = logging.getLogger(__name__)

ZONE_COUNT_S = 30


async def async_setup_engine(hass, domain):
    """Start everything; returns an async stop function."""
    bucket = hass.data.setdefault(domain, {})
    home = Home(hass, domain)
    log = EventLog(hass)
    log.enabled = lambda: home.feature("history")
    await hass.async_add_executor_job(log.prune)
    activity = ActivityLogger(hass, home, log)
    follow = FollowMe(hass, home, log)
    suggestions = Suggestions(hass, home, log)
    await suggestions.async_load()
    counts = ZoneCounts(home)

    async def _counts_loop():
        while True:
            try:
                counts.tick()
            except Exception as e:
                _LOGGER.warning("BPS zone counts failed: %s", e)
            await asyncio.sleep(ZONE_COUNT_S)

    activity.start()
    follow.start()
    suggestions.start()
    counts_task = hass.async_create_task(_counts_loop())
    bucket.update({"home": home, "eventlog": log, "follow": follow, "suggestions": suggestions})

    async def _stop():
        counts_task.cancel()
        activity.stop()
        follow.stop()
        suggestions.stop()
        counts.stop()
        await log.async_flush()
        for k in ("home", "eventlog", "follow", "suggestions"):
            bucket.pop(k, None)

    return _stop


def _service_error(msg):
    """An error the automation editor shows (ValueError outside HA, e.g. tests)."""
    try:
        from homeassistant.exceptions import ServiceValidationError
        return ServiceValidationError(msg)
    except ImportError:
        return ValueError(msg)


def register_services(hass, domain):
    """bps.follow_me_start/stop, bps.suggest, bps.suggestion_answer/clear/reask.

    The person is the HA user behind the call (a dashboard button), or the
    optional `person` field for automations.
    """
    def _engine(name):
        part = hass.data.get(domain, {}).get(name)
        if part is None:
            _LOGGER.warning("BPS is still starting; bps service call ignored")
        return part

    def _person(call):
        p = str(call.data.get("person") or "").removeprefix("person.")
        if p:
            return p
        home = hass.data.get(domain, {}).get("home")
        p = home.person_for_user(call.context.user_id) if home else None
        if not p:
            _LOGGER.warning("bps: no BPS person is linked to the calling user")
        return p

    async def follow_start(call):
        follow, person = _engine("follow"), _person(call)
        if follow and person:
            await follow.start_for(person)

    async def follow_stop(call):
        follow, person = _engine("follow"), _person(call)
        if follow and person:
            await follow.stop_session(person, "manual")

    async def suggest(call):
        sugg = _engine("suggestions")
        if not sugg:
            return
        try:
            d = validate_definition(dict(call.data))
            result = await sugg.suggest(d)
        except ValueError as e:
            _LOGGER.warning("bps.suggest: %s", e)
            raise _service_error(f"bps.suggest: {e}") from e
        _LOGGER.debug("bps.suggest %s -> %s", d["id"], result)

    async def answer(call):
        sugg, person = _engine("suggestions"), _person(call)
        ans = str(call.data.get("answer") or "").lower()
        if not sugg or not person:
            return
        if ans not in ANSWERS:
            _LOGGER.warning("bps.suggestion_answer: unknown answer %r", ans)
            return
        await sugg.answer_open(person, ans, "dashboard", call.data.get("key"))

    async def clear_(call):
        sugg = _engine("suggestions")
        if sugg:
            await sugg.clear_suggestion(str(call.data.get("id") or ""), "ended")

    async def reask(call):
        sugg = _engine("suggestions")
        if sugg:
            sugg.reask(call.data.get("id"))

    for name, handler in (("follow_me_start", follow_start), ("follow_me_stop", follow_stop),
                          ("suggest", suggest), ("suggestion_answer", answer),
                          ("suggestion_clear", clear_), ("suggestion_reask", reask)):
        if not hass.services.has_service(domain, name):
            hass.services.async_register(domain, name, handler)


__all__ = ["async_setup_engine", "register_services", "ONCE_PER"]
