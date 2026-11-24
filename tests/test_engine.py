"""Home engine: follow me, suggestions and activity attribution with a fake HA."""
import asyncio
import types

import pytest

from bps.eventlog import describe_action
from bps.follow_me import FollowMe, follow_state
from bps.rooms import Home
from bps.suggest import Suggestions, learn, period_key, validate_definition


def run(coro):
    return asyncio.run(coro)


class _State:
    def __init__(self, entity_id, state, attributes=None):
        self.entity_id, self.state, self.attributes = entity_id, state, dict(attributes or {})


class _States:
    def __init__(self):
        self.d = {}

    def get(self, eid):
        return self.d.get(eid)

    def async_set(self, eid, state, attrs=None):
        self.d[eid] = _State(eid, str(state), attrs)

    def async_remove(self, eid):
        self.d.pop(eid, None)

    def async_all(self, domain=None):
        return [s for e, s in self.d.items() if domain is None or e.startswith(domain + ".")]


class _Services:
    def __init__(self):
        self.calls = []

    def has_service(self, domain, service):
        return domain == "notify"

    async def async_call(self, domain, service, data=None, blocking=False):
        self.calls.append((domain, service, dict(data or {})))


class _Log:
    def __init__(self):
        self.recs = []

    def log(self, rec_type, **data):
        self.recs.append((rec_type, data))


def make_hass(follow=True, suggestions=True):
    hass = types.SimpleNamespace()
    hass.states = _States()
    hass.services = _Services()
    hass.config = types.SimpleNamespace(language="en")
    hass.config_entries = types.SimpleNamespace(async_entries=lambda d: [])
    hass.async_create_task = lambda coro: asyncio.get_event_loop().create_task(coro)
    hass.data = {"bps": {
        "settings": {"features": {"follow_me": follow, "suggestions": suggestions},
                     "persons": {"person.anna": {"trackers": [{"key": "a"}], "notify": "mobile_app_anna"},
                                 "person.bo": {"trackers": [{"key": "b"}], "notify": "mobile_app_bo"}}},
        "layout": {"floor": [{"name": "F", "zones": [
            {"entity_id": "Kitchen", "area_id": "kok", "media_players": ["media_player.kitchen"],
             "presence_sensors": ["sensor.kitchen_count"], "lights": ["light.k"]},
            {"entity_id": "Livingroom", "media_players": ["media_player.tv_box", "media_player.living"],
             "lights": ["light.a", "light.b"]},
            {"entity_id": "Office"},
        ]}]},
    }}
    s = hass.states
    s.async_set("person.anna", "home", {"user_id": "u_anna", "friendly_name": "Anna A"})
    s.async_set("person.bo", "home", {"user_id": "u_bo", "friendly_name": "Bo B"})
    s.async_set("media_player.kitchen", "idle", {"group_members": ["media_player.kitchen"]})
    s.async_set("media_player.living", "idle", {"group_members": ["media_player.living"]})
    s.async_set("media_player.tv_box", "idle", {})          # cannot group
    return hass


def put(hass, person, zone):
    hass.states.async_set(f"sensor.bps_person_{person}_zone", zone)


# --- pure ---------------------------------------------------------------------

def test_follow_state():
    assert follow_state(False, True, "m", "playing", None) == "off"
    assert follow_state(True, True, None, None, None) == "active"
    assert follow_state(True, False, "m", "playing", None) == "available"
    assert follow_state(True, False, "m", "playing", "bo") == "off"
    assert follow_state(True, False, "m", "paused", None) == "off"


def test_learn_auto_after_three_yes_and_back():
    p = {"yes": 0, "no": 0, "streak": 0, "mode": "ask"}
    for _ in range(3):
        learn(p, "yes", "tv")
    assert p["mode"] == "auto"
    learn(p, "undo", "tv")
    assert p["mode"] == "ask" and p["streak"] == 0
    q = {"yes": 0, "no": 0, "streak": 0, "mode": "ask"}
    for _ in range(5):
        learn(q, "yes", "tv@unknown")
    assert q["mode"] == "ask"   # never automatic for unidentified people


def test_period_key_evening_resets_at_noon():
    import datetime as dt
    eleven = dt.datetime(2026, 11, 24, 11, 0).timestamp()
    thirteen = dt.datetime(2026, 11, 24, 13, 0).timestamp()
    late = dt.datetime(2026, 11, 23, 22, 0).timestamp()
    assert period_key("evening", eleven) == period_key("evening", late)
    assert period_key("evening", thirteen) != period_key("evening", eleven)
    assert period_key("none") is None


def test_validate_definition():
    d = validate_definition({"id": "tv", "zone": "Livingroom", "title": "T", "message": "M",
                             "changes": {"light.a": 30, "light.b": "off"}})
    assert d["changes"] == {"light.a": {"state": "on", "brightness_pct": 30}, "light.b": {"state": "off"}}
    assert d["once_per"] == "evening"
    base = {"id": "x", "zone": "Z", "title": "T", "message": "M"}
    for bad in ({"id": "a b"}, dict(base, action="script.x", changes={"light.a": 30}),
                dict(base, changes={"script.x": "on"}), dict(base, changes={"light.a": 130}), base):
        with pytest.raises(ValueError):
            validate_definition(bad)


# --- rooms --------------------------------------------------------------------

def test_speaker_is_first_groupable_link_and_entity_zone_by_area(monkeypatch):
    hass = make_hass()
    home = Home(hass)
    assert home.speaker_for_zone("Livingroom") == "media_player.living"
    assert home.speaker_for_zone("Office") is None
    assert home.zone_of_entity("media_player.kitchen") == "Kitchen"
    monkeypatch.setattr("bps.rooms.area_of", lambda h, e: "kok")
    assert home.zone_of_entity("light.kitchen_ceiling") == "Kitchen"


def test_unknown_people_from_room_sensor():
    hass = make_hass()
    home = Home(hass)
    hass.states.async_set("sensor.kitchen_count", "2")
    put(hass, "anna", "Kitchen")
    assert home.unknown_count("Kitchen") == 1


def test_activity_attribution():
    hass = make_hass()
    home = Home(hass)
    put(hass, "anna", "Kitchen")
    rec = describe_action(home, "media_player.kitchen", "idle", "playing", {}, None)
    assert rec["by"] == "anna" and rec["how"] == "presence"
    rec = describe_action(home, "media_player.kitchen", "idle", "playing", {}, "u_bo")
    assert rec["by"] == "bo" and rec["how"] == "app"
    put(hass, "bo", "Kitchen")
    rec = describe_action(home, "media_player.kitchen", "idle", "playing", {}, None)
    assert rec["by"] is None and rec["occupants"] == ["anna", "bo"]


# --- suggestions ------------------------------------------------------------------

DEF = {"id": "tv", "zone": "Livingroom", "title": "TV", "message": "Cozy?",
       "changes": {"light.a": {"state": "on", "brightness_pct": 30}, "light.b": {"state": "off"}},
       "done_message": "", "unknown_message": "", "once_per": "evening"}


def _sugg(**kw):
    hass = make_hass(**kw)
    s = Suggestions(hass, Home(hass), _Log())
    return hass, s


def test_suggest_asks_people_in_zone_once_per_evening():
    hass, s = _sugg()
    put(hass, "anna", "Livingroom")
    put(hass, "bo", "Kitchen")
    assert run(s.suggest(dict(DEF))) == "asked"
    notes = [c for c in hass.services.calls if c[0] == "notify"]
    assert [c[1] for c in notes] == ["mobile_app_anna"]
    assert hass.states.get("sensor.bps_suggestion").state == "ask"
    assert run(s.suggest(dict(DEF))) == "already_handled"   # still open, same evening
    run(s.answer_open("anna", "no"))
    assert hass.states.get("sensor.bps_suggestion").state == "none"
    assert run(s.suggest(dict(DEF))) == "already_handled"


def test_yes_runs_action_with_undo_snapshot_and_learns_auto():
    hass, s = _sugg()
    put(hass, "anna", "Livingroom")
    for i in range(3):
        s.reask()
        run(s.suggest(dict(DEF)))
        run(s.answer_open("anna", "yes"))
    calls = [(d, sv) for d, sv, _ in hass.services.calls]
    assert ("scene", "create") in calls
    assert ("light", "turn_on", {"entity_id": "light.a", "brightness_pct": 30}) in hass.services.calls
    assert ("light", "turn_off", {"entity_id": "light.b"}) in hass.services.calls
    assert s.pref("anna", "tv")["mode"] == "auto"
    s.reask()
    hass.services.calls.clear()
    assert run(s.suggest(dict(DEF))) == "auto"
    assert ("light", "turn_off", {"entity_id": "light.b"}) in hass.services.calls
    hass.states.async_set("scene.bps_undo_tv", "scening")
    run(s.answer_open("anna", "undo"))
    assert ("scene", "turn_on") in [(d, sv) for d, sv, _ in hass.services.calls]
    assert s.pref("anna", "tv")["mode"] == "ask"


def test_never_and_feature_off():
    hass, s = _sugg()
    put(hass, "anna", "Livingroom")
    run(s.suggest(dict(DEF)))
    run(s.answer_open("anna", "never"))
    s.reask()
    assert run(s.suggest(dict(DEF))) == "nobody"
    hass2, s2 = _sugg(suggestions=False)
    put(hass2, "anna", "Livingroom")
    assert run(s2.suggest(dict(DEF))) == "feature_off"


def test_unidentified_people_ask_everyone_home():
    hass, s = _sugg()
    hass.data["bps"]["layout"]["floor"][0]["zones"][1]["presence_sensors"] = ["binary_sensor.lr"]
    hass.states.async_set("binary_sensor.lr", "on")
    put(hass, "anna", "Kitchen")
    put(hass, "bo", "Office")
    d = dict(DEF, unknown_message="Someone watches TV")
    assert run(s.suggest(d)) == "asked"
    assert s.open["tv"]["key"] == "tv@unknown" and sorted(s.open["tv"]["asked"]) == ["anna", "bo"]


def test_unanswered_question_expires():
    hass, s = _sugg()
    put(hass, "anna", "Livingroom")
    run(s.suggest(dict(DEF), now=1000))
    run(s.expire(now=1000 + 31 * 60))
    assert not s.open
    assert ("suggestion", {"kind": "tv", "person": "anna", "answer": "expired", "reason": "timeout"}) in s.log.recs


# --- follow me -------------------------------------------------------------------

def _follow():
    hass = make_hass()
    f = FollowMe(hass, Home(hass), _Log())
    return hass, f


def test_follow_me_start_join_and_drop_on_stop():
    hass, f = _follow()
    put(hass, "anna", "Kitchen")
    hass.states.async_set("media_player.kitchen", "playing", {"group_members": ["media_player.kitchen"]})
    assert f.state_of("anna") == "available"

    async def scenario():
        await f.start_for("anna")
        assert f.state_of("anna") == "active"
        put(hass, "anna", "Livingroom")
        await f.follow("anna", "Livingroom")
        assert ("media_player", "join", {"entity_id": "media_player.kitchen",
                                         "group_members": ["media_player.living"]}) in hass.services.calls
        await f.stop_session("anna", "manual")
        for t in list(f._drop_tasks.values()):
            t.cancel()
    run(scenario())
    assert ("media_player", "unjoin", {"entity_id": "media_player.kitchen"}) in hass.services.calls
    assert "anna" not in f.sessions


def test_follow_me_never_takes_someone_elses_room():
    hass, f = _follow()
    put(hass, "anna", "Kitchen")
    put(hass, "bo", "Livingroom")
    hass.states.async_set("media_player.kitchen", "playing", {"group_members": ["media_player.kitchen"]})
    hass.states.async_set("media_player.living", "playing", {"group_members": ["media_player.living"]})

    async def scenario():
        await f.start_for("anna")
        await f.follow("anna", "Livingroom")   # bo plays there outside follow me
    run(scenario())
    assert not [c for c in hass.services.calls if c[1] == "join"]


def test_follow_me_off_tells_the_person():
    hass = make_hass(follow=False)
    f = FollowMe(hass, Home(hass), _Log())
    put(hass, "anna", "Kitchen")
    run(f.start_for("anna"))
    assert not f.sessions
    assert hass.services.calls[-1][1] == "mobile_app_anna"


def test_ask_when_music_starts_where_someone_is():
    hass, f = _follow()
    put(hass, "anna", "Kitchen")

    async def scenario():
        f.maybe_ask("media_player.kitchen", ["Kitchen"], now=0)
        f.maybe_ask("media_player.kitchen", ["Kitchen"], now=60)   # cooldown
        await asyncio.sleep(0)
    run(scenario())
    asks = [c for c in hass.services.calls if c[0] == "notify"]
    assert len(asks) == 1 and asks[0][2]["data"]["actions"][0]["action"] == "BPS_FOLLOW_YES|anna|media_player.kitchen"


def test_engine_parts_start_and_stop_with_ha_callbacks():
    from bps.eventlog import ActivityLogger
    hass = make_hass()
    listeners = []
    hass.bus = types.SimpleNamespace(async_listen=lambda ev, fn: listeners.append((ev, fn)) or (lambda: None))

    async def scenario():
        home = Home(hass)
        parts = [ActivityLogger(hass, home, _Log()), FollowMe(hass, home, _Log()), Suggestions(hass, home, _Log())]
        for p in parts:
            p.start()
        for p in parts:
            p.stop()
    run(scenario())
    assert all(getattr(fn, "_hass_callback", False) for _ev, fn in listeners)
    assert {ev for ev, _ in listeners} >= {"state_changed", "bps_person_zone", "mobile_app_notification_action"}


def test_no_question_for_a_room_follow_me_just_joined():
    hass, f = _follow()
    put(hass, "anna", "Kitchen")
    hass.states.async_set("media_player.kitchen", "playing", {"group_members": ["media_player.kitchen"]})
    real_call = hass.services.async_call

    async def call(domain, service, data=None, blocking=False):
        if service == "join":   # Sonos reports "playing" before the join call returns
            f.maybe_ask("media_player.living", ["Livingroom"])
        return await real_call(domain, service, data, blocking)
    hass.services.async_call = call

    async def scenario():
        await f.start_for("anna")
        put(hass, "anna", "Livingroom")
        await f.follow("anna", "Livingroom")
        await asyncio.sleep(0)
        for t in list(f._drop_tasks.values()):
            t.cancel()
    run(scenario())
    assert not [c for c in hass.services.calls if c[0] == "notify" and "actions" in c[2]["data"]
                and c[2]["data"]["actions"][0]["action"].startswith("BPS_FOLLOW_YES")]


def test_no_question_for_a_group_member():
    hass, f = _follow()
    put(hass, "anna", "Livingroom")
    hass.states.async_set("media_player.living", "playing",
                          {"group_members": ["media_player.kitchen", "media_player.living"]})

    async def scenario():
        f.maybe_ask("media_player.living", ["Livingroom"], now=0)
        await asyncio.sleep(0)
    run(scenario())
    assert not [c for c in hass.services.calls if c[0] == "notify"]


# --- exact changes and extras --------------------------------------------------------

def test_suggestion_refuses_lights_outside_the_zone():
    hass, s = _sugg()
    put(hass, "anna", "Livingroom")
    with pytest.raises(ValueError, match="not linked to the zone"):
        run(s.suggest(dict(DEF, changes={"light.k": {"state": "off"}})))
    assert not [c for c in hass.services.calls if c[0] == "notify"]


def test_question_lists_exactly_what_happens_per_person():
    hass, s = _sugg()
    hass.states.async_set("light.a", "on", {"friendly_name": "Ceiling"})
    hass.states.async_set("light.b", "on", {"friendly_name": "Spots"})
    s.extras["tv"] = [{"id": "x1", "entity": "all_speakers", "do": {"media": "mute"}, "people": ["anna"]}]
    put(hass, "anna", "Livingroom")
    put(hass, "bo", "Livingroom")
    run(s.suggest(dict(DEF)))
    msg = {c[1]: c[2]["message"] for c in hass.services.calls if c[0] == "notify"}
    assert msg["mobile_app_anna"].endswith("Ceiling 30 % · Spots off · All speakers muted")
    assert msg["mobile_app_bo"].endswith("Ceiling 30 % · Spots off")


def test_extras_run_only_for_ticked_people_and_other_rooms_are_safe():
    hass, s = _sugg()
    put(hass, "anna", "Livingroom")
    put(hass, "bo", "Kitchen")
    s.extras["tv"] = [
        {"id": "x1", "entity": "all_speakers", "do": {"media": "mute"}, "people": ["anna"]},
        {"id": "x2", "entity": "light.k", "do": {"state": "off"}, "people": ["anna"]},
        {"id": "x3", "entity": "script.bo_only", "do": {"run": True}, "people": ["bo"]},
    ]
    s.overrides["tv"] = {"light.a": {"state": "on", "brightness_pct": 20}}
    run(s.suggest(dict(DEF)))
    run(s.answer_open("anna", "yes"))
    calls = hass.services.calls
    assert ("light", "turn_on", {"entity_id": "light.a", "brightness_pct": 20}) in calls   # override
    assert ("media_player", "volume_mute", {"entity_id": "media_player.kitchen", "is_volume_muted": True}) in calls
    assert ("media_player", "volume_mute", {"entity_id": "media_player.living", "is_volume_muted": True}) in calls
    assert not [c for c in calls if c[2].get("entity_id") == "light.k"]      # bo is in the kitchen
    assert not [c for c in calls if c[0] == "script"]                         # bo's extra, anna's yes


def test_definition_is_saved_even_when_nobody_is_asked():
    hass, s = _sugg()
    saved = []
    s._save = lambda: saved.append(dict(s.defs))
    assert run(s.suggest(dict(DEF))) == "nobody"
    assert saved and "tv" in saved[-1]
