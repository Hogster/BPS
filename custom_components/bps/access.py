"""Who may configure BPS.

The panel is visible to every HA user (the map card and, later, a person's own
learned patterns are for everyone), so configuration is gated on the server:
administrators always, other users only when Settings -> Access "Full access
for all users" is on. Read-only endpoints the map card needs stay open.
"""
from __future__ import annotations

from aiohttp import web

from .persons import merge_settings
from .storage import get_settings_raw

DENIED_HEADER = "X-BPS-Access"


def user_access(hass, request) -> tuple[bool, bool]:
    """(is_admin, can_configure) for the user behind this request."""
    user = request.get("hass_user")
    if user is None:
        return False, False
    if user.is_admin:
        return True, True
    all_users = merge_settings(get_settings_raw(hass))["access"]["all_users"]
    return False, bool(all_users)


def can_configure(hass, request) -> bool:
    return user_access(hass, request)[1]


def denied() -> web.Response:
    """403 marked as an access decision (not a bad token) for the panel."""
    return web.Response(
        status=403,
        text="BPS configuration is limited to administrators (Settings → Access).",
        headers={DENIED_HEADER: "denied"},
    )
