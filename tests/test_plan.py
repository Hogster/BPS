import pytest

from bps import plan as P


def test_light_spec_forms():
    assert P.light_spec(30) == {"state": "on", "brightness_pct": 30}
    assert P.light_spec("20%") == {"state": "on", "brightness_pct": 20}
    assert P.light_spec("off") == {"state": "off"}
    assert P.light_spec(0) == {"state": "off"}
    assert P.light_spec({"brightness_pct": 40, "color_temp_kelvin": 2200}) == \
        {"state": "on", "brightness_pct": 40, "color_temp_kelvin": 2200}
    for bad in (130, "dim", {"rgb_color": [1, 2]}, {"kelvin": 100}):
        with pytest.raises(ValueError):
            P.light_spec(bad)


def test_parse_changes_only_lights():
    assert P.parse_changes([{"entity_id": "light.a", "level": 30}]) == {"light.a": {"state": "on", "brightness_pct": 30}}
    with pytest.raises(ValueError):
        P.parse_changes({"switch.x": "on"})
    with pytest.raises(ValueError):
        P.parse_changes({})


def test_check_zone():
    P.check_zone({"light.a": {}}, "Z", ["light.a", "light.b"])
    with pytest.raises(ValueError, match="light.c is not linked"):
        P.check_zone({"light.a": {}, "light.c": {}}, "Z", ["light.a"])


def test_override_and_skip():
    ch = {"light.a": {"state": "on", "brightness_pct": 30}, "light.b": {"state": "off"}}
    ov = {}
    P.set_override(ov, "light.a", 20)
    P.set_override(ov, "light.b", "skip")
    assert P.base_changes(ch, ov) == {"light.a": {"state": "on", "brightness_pct": 20}}
    P.set_override(ov, "light.a", None)
    assert P.base_changes(ch, ov)["light.a"]["brightness_pct"] == 30


def test_plan_unlinked_light_is_skipped_and_own_level_wins():
    d = {"zone": "Z", "changes": {"light.a": {"state": "on", "brightness_pct": 30}, "light.gone": {"state": "off"}}}
    extras = [{"id": "1", "entity": "light.a", "do": {"state": "on", "brightness_pct": 10}, "people": ["me"]}]
    steps, skipped = P.plan(d, {}, extras, ["me"], zone_lights=["light.a"], zone_of=lambda e: "Z",
                            occupants=lambda z: [], speakers=[])
    assert [(s["entity"], s["do"]["brightness_pct"]) for s in steps] == [("light.a", 10)]
    assert skipped == [{"entity": "light.gone", "reason": "not_linked", "zone": "Z"}]


def test_extra_permissions():
    mine = {"entity": "light.x", "do": {"state": "off"}, "people": ["me"]}
    both = dict(mine, people=["me", "you"])
    assert P.may_change_extra(None, mine, "me", False)
    assert not P.may_change_extra(None, both, "me", False)
    assert P.may_change_extra(both, dict(both, people=["you"]), "me", False)      # untick myself
    assert not P.may_change_extra(both, dict(both, do={"state": "on"}), "me", False)
    assert not P.may_change_extra(both, None, "me", False)
    assert P.may_change_extra(both, None, "me", True)
    with pytest.raises(ValueError):
        P.make_extra({"entity": "switch.x", "people": ["me"]}, {"me": {}})
    with pytest.raises(ValueError):
        P.make_extra({"entity": "light.x", "do": "off", "people": []}, {"me": {}})
    e = P.make_extra({"entity": "all_speakers", "do": {"media": "volume", "volume": "15"}, "people": ["me"]}, {"me": {}})
    assert e["do"] == {"media": "volume", "volume": 15}


def test_service_calls_and_summary():
    steps = [{"entity": "light.a", "do": {"state": "on", "brightness_pct": 30}, "extra": False, "zone": "Z"},
             {"entity": "light.h", "do": {"state": "off"}, "extra": True, "zone": "Hall"},
             {"entity": "media_player.k", "do": {"media": "volume", "volume": 10}, "extra": True, "zone": None},
             {"entity": "script.s", "do": {"run": True}, "extra": True, "zone": None}]
    calls = P.service_calls(steps)
    assert ("media_player", "volume_set", {"entity_id": "media_player.k", "volume_level": 0.1}) in calls
    assert ("script", "turn_on", {"entity_id": "script.s"}) in calls
    assert P.undo_entities(steps) == ["light.a", "light.h", "media_player.k"]
    words = {"do_off": "off", "do_volume": "volume {} %", "do_run": "Run"}
    text = P.summary(steps, lambda e: e.split(".")[1], words.get, "Z")
    assert text == "a 30 % · h off (Hall) · k volume 10 % · Run s"
