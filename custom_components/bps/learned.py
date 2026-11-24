"""The Learned tab: what BPS asked, what people answered, what it does on its own.

Built from the event log (suggestion and follow-me records) and the
suggestion preferences. Privacy: an administrator sees everyone; any other
user only their own person (the server filters, the panel never gets more).

Learning progress counts days with data (someone's zone changed that day) in
the last ``WINDOW_DAYS``; learned routines need ``TARGET_DAYS`` of them.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta

TARGET_DAYS = 14
WINDOW_DAYS = 60
HISTORY_DAYS = 30
HISTORY_LIMIT = 300
MODES = ("ask", "auto", "never")


def scan_log(directory, now=None):
    """(days with zone data, suggestion/follow records) from the JSONL files.

    Cheap: the date is read from the line prefix and only the few
    suggestion/follow lines are JSON-parsed.
    """
    now = time.time() if now is None else now
    start = datetime.fromtimestamp(now) - timedelta(days=WINDOW_DAYS)
    hist_from = (datetime.fromtimestamp(now) - timedelta(days=HISTORY_DAYS)).isoformat(timespec="seconds")
    since = start.isoformat(timespec="seconds")
    months, d = set(), start
    while d <= datetime.fromtimestamp(now):
        months.add(d.strftime("%Y-%m"))
        d += timedelta(days=28)
    months.add(datetime.fromtimestamp(now).strftime("%Y-%m"))
    days, recs = set(), []
    for m in sorted(months):
        path = os.path.join(directory, f"events-{m}.jsonl")
        try:
            fh = open(path, encoding="utf-8")
        except OSError:
            continue
        with fh:
            for line in fh:
                t = line[7:26] if line.startswith('{"t": "') else ""
                if not t or t < since:
                    continue
                if '"type": "zone"' in line:
                    days.add(t[:10])
                elif t >= hist_from and ('"type": "suggestion"' in line or '"type": "follow"' in line):
                    try:
                        recs.append(json.loads(line))
                    except ValueError:
                        pass
    return sorted(days), recs


def person_key(raw, people):
    """Map a logged person to a current person id ('erik' -> 'erik_hogstrom')."""
    if not raw:
        return None
    if raw in people:
        return raw
    hits = [p for p in people if p.startswith(f"{raw}_")]
    return hits[0] if len(hits) == 1 else raw


def build_learned(days, records, defs, prefs, people, me=None, is_admin=False, now=None):
    """Panel payload; me = the viewer's person id (None: not linked to a person)."""
    now = time.time() if now is None else now
    visible = set(people) if is_admin else ({me} if me else set())

    def title_of(kind):
        if kind == "follow_me":
            return "Follow me"
        base = str(kind or "").split("@")[0]
        return (defs.get(base) or {}).get("title") or base

    history = []
    for r in records:
        p = person_key(r.get("person"), people)
        if p not in visible:
            continue
        item = {"t": r.get("t"), "person": p, "type": r.get("type")}
        if r.get("type") == "suggestion":
            kind = str(r.get("kind") or "")
            item.update({"id": kind.split("@")[0], "unknown": "@" in kind, "title": title_of(kind),
                         "answer": r.get("answer"), "via": r.get("via"), "reason": r.get("reason"),
                         "speaker": r.get("speaker")})
        else:
            item.update({"event": r.get("event"), "speaker": r.get("speaker"),
                         "zone": r.get("zone"), "reason": r.get("reason")})
        history.append(item)
    history = history[-HISTORY_LIMIT:][::-1]

    last_asked = {}
    for h in history:   # newest first
        if h["type"] == "suggestion" and h.get("answer") == "asked":
            key = f"{h['id']}@unknown" if h.get("unknown") else h["id"]
            last_asked.setdefault((h["person"], key), h["t"])
    suggestions = []
    asked_ids = {k.split("@")[0] for _p, k in last_asked if k != "follow_me"}
    ids = sorted(set(defs) | {k.split("@")[0] for pp in prefs.values() for k in pp} | asked_ids)
    for sid in ids:
        d = defs.get(sid) or {}
        rows = []
        for p in sorted(visible):
            for key in (sid, f"{sid}@unknown"):
                pref = (prefs.get(p) or {}).get(key)
                asked = last_asked.get((p, key))
                if pref is None and not asked:
                    continue
                pref = pref or {"yes": 0, "no": 0, "streak": 0, "mode": "ask"}
                rows.append({"person": p, "key": key, "unknown": "@" in key,
                             "mode": pref.get("mode", "ask"), "yes": pref.get("yes", 0),
                             "no": pref.get("no", 0), "streak": pref.get("streak", 0),
                             "last_asked": asked})
        if rows or (is_admin and d):
            suggestions.append({"id": sid, "title": d.get("title") or sid, "zone": d.get("zone"),
                                "message": d.get("message"), "action": d.get("action"), "people": rows})

    first = days[0] if days else None
    return {
        "learning": {"days": len(days), "target": TARGET_DAYS, "first_day": first,
                     "ready": len(days) >= TARGET_DAYS},
        "people": {p: {"name": people[p].get("name", p)} for p in sorted(visible) if p in people},
        "me": me, "is_admin": is_admin,
        "suggestions": suggestions, "history": history,
    }


def apply_pref_action(prefs, person, key, action):
    """forget / allow / stop_auto / never on one preference; returns True if changed."""
    pp = prefs.setdefault(person, {})
    if action == "forget":
        return pp.pop(key, None) is not None
    pref = pp.setdefault(key, {"yes": 0, "no": 0, "streak": 0, "mode": "ask"})
    if action in ("allow", "stop_auto"):
        pref["mode"], pref["streak"] = "ask", 0
    elif action == "never":
        pref["mode"], pref["streak"] = "never", 0
    else:
        raise ValueError(f"unknown action {action!r}")
    return True
