"""Fingerprint positioning: the receivers as reference points.

Trilateration turns each receiver's distance into a circle and solves the
geometry. A wall that makes a receiver read a device 2x too far bends every
fix it takes part in.

The receivers that send a beacon (ESPHome probes) are heard by every other
receiver, and auto-calibration already samples those pairs. So BPS knows,
for every placed receiver, how the rest of the house hears *that spot*: a
fingerprint at a known position, refreshed for free. A device's own
fingerprint (how the receivers hear it now) is compared with them, and the
device is placed between the receivers whose fingerprints look most like it.
A wall that makes receiver X read the device long makes X read the receivers
behind that wall long too, and the comparison cancels it.

The fingerprint fix is a second opinion that __init__ blends with the
trilateration (``fingerprint_weight`` in the layout, 0 = off; the fix is
still computed and published as telemetry, so truth marks can measure it
before anyone turns it on). Truth marks (truth.py) can also add references
where no receiver sits.

Ported from Sextant's fingerprint.py by David Coulson (MIT,
https://github.com/davidcoulson/sextant), adapted to BPS: the reference
ranges come from the calibration's receiver-pair samples, keyed by receiver
slug. Pure: no Home Assistant imports.
"""
from __future__ import annotations

import math

SELF_DISTANCE_M = 0.5      # a device standing at a receiver
REF_SAMPLES = 20           # latest samples per pair in a reference (10 min at 30 s)
MIN_SAMPLES = 3            # fewer than this: the pair is not a reference yet
MISSING_M = 12.0           # "out of range" stands in for a receiver only one side hears
SCORE_SCALE = math.log(2.0)
NEIGHBOUR_SCORE_RATIO = 3.0
K = 3

LEARN_ALPHA = 0.02         # shared gain: beacons vs the devices tracked
THING_LEARN_ALPHA = 0.1    # each device's own radio
GAIN_MIN, GAIN_MAX = 0.25, 4.0
TRUST_SCALE = math.log(3.0)
MIN_SHARED_FOR_RATIO = 3
MIN_CONF = 0.2             # a match worse than this is not used


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _median(values):
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    return ordered[mid] if n % 2 else 0.5 * (ordered[mid - 1] + ordered[mid])


class Gain:
    """How much hotter or cooler the tracked devices read than the beacons.

    A probe's beacon and a phone don't transmit at the same power, so the
    references are scaled by a learned gain: shared, plus a faster
    multiplier per device (a watch reads weaker than a phone).
    """

    def __init__(self):
        self.shared = 1.0
        self.per = {}

    def get(self, entity=None) -> float:
        return self.shared * self.per.get(entity, 1.0)

    def learn(self, ratio, conf=1.0, entity=None):
        if not _num(ratio) or ratio <= 0:
            return
        w = max(0.0, min(1.0, float(conf)))
        self.shared = min(GAIN_MAX, max(GAIN_MIN, self.shared * ratio ** (LEARN_ALPHA * w)))
        if entity is not None:
            own = self.per.get(entity, 1.0) * ratio ** (THING_LEARN_ALPHA * w)
            self.per[entity] = min(GAIN_MAX, max(GAIN_MIN, own))

    def to_dict(self):
        return {"shared": round(self.shared, 4), "per": {k: round(v, 4) for k, v in self.per.items()}}


def references(layout, samples, extra=None) -> dict:
    """Per floor, the reference points: {floor: [{slug, x, y, vector}]}.

    ``samples`` are the calibration's {"tx|rx": [raw metres, ...]}. A placed
    receiver is a reference when other placed receivers have ranged it; its
    vector is {rx slug: median metres x rx's correction} (the same correction
    update_receiver_radii applies to a device's reading from rx), plus
    SELF_DISTANCE_M for itself. ``extra`` adds truth-mark references
    ({floor, x, y, vector, slug}), already in this scale.
    """
    floors = (layout or {}).get("floor") if isinstance(layout, dict) else None
    if not floors:
        return {}
    correction = {}
    for floor in floors:
        for r in floor.get("receivers") or []:
            slug = r.get("entity_id")
            if isinstance(slug, str) and slug:
                c = r.get("correction")
                correction[slug] = float(c) if _num(c) and c > 0 else 1.0
    heard = {}
    for key, values in (samples or {}).items():
        tx, sep, rx = str(key).partition("|")
        if not sep or tx == rx or rx not in correction:
            continue
        vals = [float(v) for v in list(values)[-REF_SAMPLES:] if _num(v) and v > 0]
        if len(vals) < MIN_SAMPLES:
            continue
        heard.setdefault(tx, {})[rx] = _median(vals) * correction[rx]
    out = {}
    for floor in floors:
        if not floor.get("scale"):
            continue
        refs = []
        for r in floor.get("receivers") or []:
            slug = r.get("entity_id")
            cords = r.get("cords") or {}
            if not isinstance(slug, str) or not _num(cords.get("x")) or not _num(cords.get("y")):
                continue
            vector = dict(heard.get(slug) or {})
            if not vector:
                continue
            vector[slug] = SELF_DISTANCE_M
            refs.append({"slug": slug, "x": float(cords["x"]), "y": float(cords["y"]), "vector": vector})
        for ref in extra or []:
            if ref.get("floor") == floor.get("name") and ref.get("vector"):
                refs.append({"slug": ref.get("slug"), "x": float(ref["x"]), "y": float(ref["y"]),
                             "vector": dict(ref["vector"])})
        if refs:
            out[floor.get("name")] = refs
    return out


def thing_vector(layout) -> dict:
    """{receiver slug: metres} from this cycle's readings, all floors."""
    vector = {}
    for floor in ((layout or {}).get("floor") or []):
        for r in floor.get("receivers") or []:
            slug, d = r.get("entity_id"), r.get("distance")
            if isinstance(slug, str) and slug and _num(d) and d > 0:
                vector[slug] = float(d)
    return vector


def similarity(thing, reference, missing_m=MISSING_M):
    """Weighted RMS log-ratio between two range vectors; lower is closer.

    A receiver only one side hears counts as hearing the other at
    ``missing_m``: not hearing is information too. Near receivers weigh more.
    """
    log = math.log
    num = den = 0.0
    for rx, dr in reference.items():
        dt = thing.get(rx)
        if dt is None:
            w = 1.0 / (1.0 + dr)
            if dr < missing_m:
                e = log(missing_m / dr)
                num += w * e * e
        else:
            e = log(dt / dr)
            w = 1.0 / (1.0 + min(dt, dr))
            num += w * e * e
        den += w
    for rx, dt in thing.items():
        if rx in reference:
            continue
        w = 1.0 / (1.0 + dt)
        if dt < missing_m:
            e = log(dt / missing_m)
            num += w * e * e
        den += w
    if den <= 0:
        return None
    return math.sqrt(num / den)


def match(thing, refs, gain=1.0, k=K):
    """Place a device's vector among one floor's references.

    None when nothing compares, else {x, y, conf, score, refs, ratio}: the
    inverse-score-weighted mean of the best ``k`` references, a confidence
    that is 0.5 when the best reference still differs by a factor 2 on
    average, and the device/reference range ratio (gain evidence).
    """
    if not thing or not refs:
        return None
    scored = []
    for ref in refs:
        vector = {rx: d * gain for rx, d in ref["vector"].items()}
        s = similarity(thing, vector)
        if s is not None:
            scored.append((s, ref, vector))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0])
    best = scored[0][0]
    chosen = [item for item in scored[:max(1, k)] if item[0] <= best * NEIGHBOUR_SCORE_RATIO + 1e-9]
    wsum = x = y = 0.0
    for s, r, _v in chosen:
        w = 1.0 / (s + 0.05) ** 2
        wsum += w
        x += w * r["x"]
        y += w * r["y"]
    best_ref, best_vec = scored[0][1], scored[0][2]
    logs = [math.log(thing[rx] / best_vec[rx]) for rx in thing
            if rx in best_vec and rx != best_ref.get("slug") and best_vec[rx] > 0]
    ratio = math.exp(_median(logs)) if len(logs) >= MIN_SHARED_FOR_RATIO else None
    return {
        "x": x / wsum, "y": y / wsum,
        "conf": 1.0 / (1.0 + (best / SCORE_SCALE) ** 2),
        "score": best,
        "refs": [(r.get("slug"), round(s, 3)) for s, r, _v in chosen],
        "ratio": ratio,
    }


def trust(ratio) -> float:
    """1 when the device and its best reference read alike, falling to 0 at a factor 3."""
    if not _num(ratio) or ratio <= 0:
        return 1.0
    return max(0.0, 1.0 - abs(math.log(ratio)) / TRUST_SCALE)


def blend(fix, fp, weight):
    """Trilateration fix and fingerprint fix mixed: weight 0 = trilateration only.

    The weight shrinks with the match's trust, so a fingerprint that doesn't
    look like anything only nudges. ``fix`` is (x, y); returns (x, y).
    """
    if fp is None or not _num(weight) or weight <= 0 or fp.get("conf", 0) < MIN_CONF:
        return fix
    w = min(1.0, float(weight)) * trust(fp.get("ratio"))
    return (fix[0] * (1 - w) + fp["x"] * w, fix[1] * (1 - w) + fp["y"] * w)
