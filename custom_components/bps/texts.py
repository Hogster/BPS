"""Notification texts in the Home Assistant language (English fallback).

Notifications go to people's phones, so they follow HA's language setting
(Settings -> System -> General), not the panel's. Add a language by adding a
dict with the same keys.
"""
from __future__ import annotations

TEXTS = {
    "en": {
        "yes": "Yes",
        "no": "No",
        "never": "Don't ask again",
        "undo": "Undo",
        "follow_ask_title": "🎵 Follow me?",
        "follow_ask": "Should the music follow you around the house?",
        "follow_started_title": "🎵 The music follows you",
        "follow_started": "Tap to stop.",
        "follow_stop": "Stop following",
        "follow_title": "Follow me",
        "follow_off": "Follow me is turned off in BPS Settings.",
        "follow_nothing": "No music is playing where you are.",
        "sensor_follow": "BPS follow me {}",
        "sensor_suggestion": "BPS suggestion",
        "sensor_zone": "BPS people {}",
        "people": "people",
    },
    "sv": {
        "yes": "Ja",
        "no": "Nej",
        "never": "Fråga inte igen",
        "undo": "Ångra",
        "follow_ask_title": "🎵 Följ mig?",
        "follow_ask": "Ska musiken följa dig genom huset?",
        "follow_started_title": "🎵 Musiken följer dig",
        "follow_started": "Tryck för att sluta.",
        "follow_stop": "Sluta följa",
        "follow_title": "Följ mig",
        "follow_off": "Följ mig är avstängt i BPS-inställningarna.",
        "follow_nothing": "Ingen musik spelar där du är.",
        "sensor_follow": "BPS följ mig {}",
        "sensor_suggestion": "BPS förslag",
        "sensor_zone": "BPS personer {}",
        "people": "personer",
    },
}


def text(hass, key: str) -> str:
    lang = str(getattr(hass.config, "language", None) or "en").split("-")[0].lower()
    return TEXTS.get(lang, TEXTS["en"]).get(key) or TEXTS["en"][key]


async def notify(hass, service, title, message, *, tag=None, actions=None, url=None):
    """Companion-app notification; silently skipped without a notify service."""
    if not service or not hass.services.has_service("notify", service):
        return
    data = {}
    if tag:
        data["tag"] = tag
    if actions:
        data["actions"] = actions
    if url:
        data["url"] = url            # iOS: tap opens this view
        data["clickAction"] = url    # Android
    payload = {"message": message, "data": data}
    if title:
        payload["title"] = title
    await hass.services.async_call("notify", service, payload, blocking=False)


async def clear(hass, service, tag):
    if service and hass.services.has_service("notify", service):
        await hass.services.async_call(
            "notify", service, {"message": "clear_notification", "data": {"tag": tag}}, blocking=False)
