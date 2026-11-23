"""Who may configure BPS: admins always, others only with Full access on."""
import asyncio
import types

import bps
from bps.access import user_access
from bps.persons import validate_settings
from bps.storage import save_settings
from conftest import make_hass


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _Req(dict):
    def __init__(self, hass, user, body=None):
        super().__init__(hass_user=user)
        self.app = {"hass": hass}
        self._body = body

    async def json(self):
        return self._body

    async def post(self):
        return {}


ADMIN = types.SimpleNamespace(id="a", name="Admin", is_admin=True)
KID = types.SimpleNamespace(id="k", name="Kid", is_admin=False)


def _hass(all_users=False):
    hass = make_hass()
    run(save_settings(hass, validate_settings({"access": {"all_users": all_users}})))
    return hass


def test_default_is_admin_only():
    hass = _hass()
    assert user_access(hass, _Req(hass, ADMIN)) == (True, True)
    assert user_access(hass, _Req(hass, KID)) == (False, False)
    assert user_access(hass, _Req(hass, None)) == (False, False)


def test_full_access_lets_everyone_configure():
    hass = _hass(all_users=True)
    assert user_access(hass, _Req(hass, KID)) == (False, True)


def test_fresh_install_without_settings_is_admin_only():
    hass = make_hass()
    assert user_access(hass, _Req(hass, KID)) == (False, False)


def test_non_admin_save_is_denied():
    hass = _hass()
    res = run(bps.BPSSaveAPIText().post(_Req(hass, KID)))
    assert res.status == 403


def test_non_admin_cannot_change_access_itself(monkeypatch):
    hass = _hass(all_users=True)
    body = validate_settings({"access": {"all_users": False}})
    view = bps.BPSSettingsAPI()
    monkeypatch.setattr(bps, "_settings_payload", lambda h: {"ok": True})  # needs a real hass
    run(view.post(_Req(hass, KID, body)))
    assert bps.get_settings_raw(hass)["access"]["all_users"] is True
    run(view.post(_Req(hass, ADMIN, body)))
    assert bps.get_settings_raw(hass)["access"]["all_users"] is False
