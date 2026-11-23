"""Learned tab payload: privacy, history, suggestion status, progress."""
import json

from bps.learned import apply_pref_action, build_learned, person_key, scan_log

PEOPLE = {"erik_hogstrom": {"name": "Erik"}, "sofia_hogstrom": {"name": "Sofia"}}
DEFS = {"tv_mys": {"title": "Mysigt?", "zone": "Livingroom"}}
RECS = [
    {"t": "2026-11-22T18:44:39", "type": "suggestion", "kind": "tv_mys", "person": "sofia", "answer": "asked"},
    {"t": "2026-11-22T18:50:00", "type": "suggestion", "kind": "tv_mys", "person": "sofia", "answer": "yes"},
    {"t": "2026-11-23T07:18:13", "type": "suggestion", "kind": "follow_me", "person": "erik_hogstrom",
     "speaker": "media_player.kitchen_speaker", "answer": "asked"},
    {"t": "2026-11-23T07:19:00", "type": "follow", "person": "erik_hogstrom", "event": "started"},
]
PREFS = {"sofia_hogstrom": {"tv_mys": {"yes": 1, "no": 0, "streak": 1, "mode": "ask"}}}


def test_old_short_person_names_map_to_current_people():
    assert person_key("sofia", PEOPLE) == "sofia_hogstrom"
    assert person_key("nobody", PEOPLE) == "nobody"


def test_admin_sees_everyone_newest_first():
    out = build_learned(["2026-11-22", "2026-11-23"], RECS, DEFS, PREFS, PEOPLE, "erik_hogstrom", True)
    assert [h["person"] for h in out["history"]] == ["erik_hogstrom", "erik_hogstrom", "sofia_hogstrom", "sofia_hogstrom"]
    assert out["history"][-1]["title"] == "Mysigt?"
    row = out["suggestions"][0]["people"][0]
    assert row["person"] == "sofia_hogstrom" and row["yes"] == 1 and row["last_asked"] == "2026-11-22T18:44:39"
    assert out["learning"] == {"days": 2, "target": 14, "first_day": "2026-11-22", "ready": False}


def test_user_only_sees_own_person():
    out = build_learned([], RECS, DEFS, PREFS, PEOPLE, "erik_hogstrom", False)
    assert {h["person"] for h in out["history"]} == {"erik_hogstrom"}
    assert all(r["person"] == "erik_hogstrom" for s in out["suggestions"] for r in s["people"])
    assert set(out["people"]) == {"erik_hogstrom"}
    nobody = build_learned([], RECS, DEFS, PREFS, PEOPLE, None, False)
    assert nobody["history"] == [] and nobody["suggestions"] == []


def test_pref_actions():
    prefs = json.loads(json.dumps(PREFS))
    apply_pref_action(prefs, "sofia_hogstrom", "tv_mys", "never")
    assert prefs["sofia_hogstrom"]["tv_mys"]["mode"] == "never"
    apply_pref_action(prefs, "sofia_hogstrom", "tv_mys", "allow")
    assert prefs["sofia_hogstrom"]["tv_mys"]["mode"] == "ask"
    assert apply_pref_action(prefs, "sofia_hogstrom", "tv_mys", "forget")
    assert "tv_mys" not in prefs["sofia_hogstrom"]


def test_scan_log_counts_zone_days_and_reads_history(tmp_path):
    import datetime as dt
    now = dt.datetime(2026, 11, 23, 22, 0).timestamp()
    lines = [
        {"t": "2026-11-21T10:00:00", "type": "zone", "person": "erik"},
        {"t": "2026-11-23T10:00:00", "type": "zone", "person": "erik"},
        {"t": "2026-11-23T10:01:00", "type": "action", "entity": "light.x"},
        RECS[0],
    ]
    (tmp_path / "events-2026-11.jsonl").write_text("\n".join(json.dumps(r) for r in lines) + "\n")
    days, recs = scan_log(str(tmp_path), now)
    assert days == ["2026-11-21", "2026-11-23"]
    assert recs == [RECS[0]]


def test_suggestion_known_only_from_history_is_listed():
    out = build_learned([], RECS[:1], {}, {}, PEOPLE, None, True)
    assert [s["id"] for s in out["suggestions"]] == ["tv_mys"]
    assert out["suggestions"][0]["people"][0]["mode"] == "ask"
