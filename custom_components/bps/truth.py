"""Truth marks: "it is actually here", and how far off BPS was.

The user picks a tracked device and clicks where it really is on the map.
For the next ``COLLECT_S`` seconds every positioning cycle of that device
is kept: the trilateration fix, the fingerprint fix and its trust, the floor
it elected, and the device's fingerprint (how the receivers heard it). The
device should stay put meanwhile; the panel says so.

With the cycles kept, a mark answers:

* how far off trilateration alone is, in metres, at that spot;
* how far off the fingerprint is, and every mix of the two
  (``evaluate``), so the panel can say which weight fits this house;
* what the receivers hear at a known point where no receiver sits: the
  mark becomes a fingerprint reference of its own (``reference``).

Idea from Sextant's truth marks by David Coulson (MIT,
https://github.com/davidcoulson/sextant). Pure: no Home Assistant imports.
"""
from __future__ import annotations

import math
import time
import uuid

COLLECT_S = 45          # cycles kept after a click
MIN_CYCLES = 5          # fewer than this: the mark tells nothing
MAX_MARKS = 60
WEIGHTS = (0.0, 0.25, 0.5, 0.75, 1.0)


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _median(values):
    ordered = sorted(values)
    n = len(ordered)
    if not n:
        return None
    mid = n // 2
    return ordered[mid] if n % 2 else 0.5 * (ordered[mid - 1] + ordered[mid])


def new_mark(entity, floor, x, y, scale, now=None) -> dict:
    now = time.time() if now is None else now
    return {"id": uuid.uuid4().hex[:10], "entity": str(entity), "floor": str(floor),
            "x": float(x), "y": float(y), "scale": float(scale), "at": now,
            "until": now + COLLECT_S, "cycles": []}


def collecting(marks, entity, now=None) -> dict | None:
    """The mark still collecting cycles for this device, if any."""
    now = time.time() if now is None else now
    for m in marks:
        if m.get("entity") == entity and now <= m.get("until", 0):
            return m
    return None


def add_cycle(mark, floor, tri, fp, trust, vector, gain):
    """One positioning cycle of a collecting mark. ``tri``/``fp`` are (x, y)
    or None; ``vector`` is the device's fingerprint, ``gain`` its gain then."""
    mark["cycles"].append({
        "floor": floor,
        "tri": [round(float(tri[0]), 1), round(float(tri[1]), 1)] if tri else None,
        "fp": [round(float(fp[0]), 1), round(float(fp[1]), 1)] if fp else None,
        "trust": round(float(trust), 3) if _num(trust) else None,
        "vector": {k: round(v, 2) for k, v in (vector or {}).items()},
        "gain": round(float(gain), 4) if _num(gain) and gain > 0 else 1.0,
    })


def _error_m(mark, p):
    return math.hypot(p[0] - mark["x"], p[1] - mark["y"]) / mark["scale"]


def evaluate(marks) -> dict:
    """Median error (m) per method over every usable mark, plus per mark.

    Methods: "tri" (trilateration only), "fp" (fingerprint only) and
    "w<weight>" mixes as the blend in fingerprint.py does them (weight times
    trust). A cycle on the wrong floor counts in ``wrong_floor``, not in the
    distances.
    """
    per_mark = []
    pooled = {}
    for m in marks:
        cycles = m.get("cycles") or []
        if len(cycles) < MIN_CYCLES or not _num(m.get("scale")) or m["scale"] <= 0:
            continue
        errs = {}
        wrong = 0
        for c in cycles:
            if c.get("floor") != m["floor"]:
                wrong += 1
                continue
            tri, fp, t = c.get("tri"), c.get("fp"), c.get("trust")
            if tri:
                errs.setdefault("tri", []).append(_error_m(m, tri))
            if fp:
                errs.setdefault("fp", []).append(_error_m(m, fp))
            if tri:
                for w in WEIGHTS:
                    we = w * (t if _num(t) else 1.0) if fp else 0.0
                    p = (tri[0] * (1 - we) + fp[0] * we, tri[1] * (1 - we) + fp[1] * we) if fp else tri
                    errs.setdefault(f"w{w}", []).append(_error_m(m, p))
        row = {"id": m["id"], "entity": m["entity"], "floor": m["floor"], "at": m["at"],
               "cycles": len(cycles), "wrong_floor": wrong,
               "error": {k: round(_median(v), 2) for k, v in errs.items() if v}}
        per_mark.append(row)
        for k, v in row["error"].items():
            pooled.setdefault(k, []).append(v)
    summary = {k: round(_median(v), 2) for k, v in pooled.items()}
    best = None
    mixes = {k: v for k, v in summary.items() if k.startswith("w")}
    if mixes:
        best = float(min(mixes, key=lambda k: (mixes[k], -float(k[1:])))[1:])
    return {"marks": per_mark, "summary": summary, "best_weight": best, "usable": len(per_mark)}


def reference(mark) -> dict | None:
    """A finished mark as a fingerprint reference: the median of what the
    receivers heard, divided by the device's gain (the receivers' references
    are in beacon scale; the match multiplies the gain back)."""
    cycles = [c for c in mark.get("cycles") or [] if c.get("vector")]
    if len(cycles) < MIN_CYCLES:
        return None
    per = {}
    for c in cycles:
        g = c.get("gain") or 1.0
        for rx, d in c["vector"].items():
            if _num(d) and d > 0:
                per.setdefault(rx, []).append(d / g)
    vector = {rx: round(_median(v), 2) for rx, v in per.items() if len(v) >= MIN_CYCLES // 2 + 1}
    if not vector:
        return None
    return {"slug": f"mark:{mark['id']}", "floor": mark["floor"], "x": mark["x"], "y": mark["y"],
            "vector": vector}


def trim(marks, now=None):
    """Keep the newest MAX_MARKS; drop marks that ended with too few cycles."""
    now = time.time() if now is None else now
    keep = [m for m in marks if now <= m.get("until", 0) or len(m.get("cycles") or []) >= MIN_CYCLES]
    return keep[-MAX_MARKS:]
