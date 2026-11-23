"""Receiver placement advisor: where would one more receiver help most?

For every point of a floor the expected position error is estimated from the
receivers that can hear it, then a virtual receiver is tried at candidate
points inside the zones to find where it lowers the error most where people
actually spend their time.

Model (all inputs are data every BPS install already has):

- Ranging noise. A receiver's distance estimate is off by a roughly constant
  *fraction* of the distance (RSSI noise is in dB, i.e. multiplicative):
  sigma(d) = d * (a + b*d) * k_rx. a, b are fitted on the receiver-to-receiver
  calibration pairs (|log bias| and log jitter of measured vs true distance);
  k_rx is how much worse/better a receiver's own pairs are than the model
  (walls, mounting, metal). Without calibration data sensible defaults apply.
- Geometry. The position error at a point is the Cramér-Rao bound of 2-D
  ranging: sqrt(trace(J^-1)) with J = sum(u u^T / sigma^2) over same-floor
  receivers within range, u the unit vector to the receiver. This captures
  distance, the number of receivers AND their spread around the point: three
  receivers in a row on one side give a poor fix even when they are close.
- Usage. Zones are weighted by how long trackers stayed in them (recorder
  history of the BPS tracker zone sensors). Short visits that bounce straight
  back ("flaps") are reported as a reality check.
- Candidates. Greedy: best single extra receiver, then the best second one
  given the first.

Absolute metres are a pessimistic model figure; the ranking and the relative
improvement are what to act on. Pure numpy/shapely so it is unit-testable.
"""
from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
import shapely
from shapely.geometry import Polygon

from .zone_adjust import _ring

MAX_RANGE_M = 15.0
GRID_M = 0.5
ERR_CAP_M = 8.0
FLAP_S = 60
DWELL_CAP_S = 2 * 3600
DEFAULT_A, DEFAULT_B = 0.6, 0.0      # used when there is no calibration data
MIN_PAIRS_FOR_FIT = 8
CANDIDATE_STRIDE = 2                 # every 2nd grid cell (1 m) is a candidate
MARGIN_M = 1.0                       # grid margin around zones/receivers


# --------------------------------------------------------------- noise model
def fit_noise_model(matrix, samples):
    """(a, b, per-receiver factor, pairs used) from calibration pairs."""
    pairs = []
    for m in matrix or []:
        true_m, corr = m.get("true_m"), m.get("corrected_m") or m.get("measured_m")
        if not true_m or not corr or true_m <= 0 or corr <= 0:
            continue
        if (m.get("measured_m") or 0) >= 31:   # clipped at the sensor's max range
            continue
        s = [v for v in (samples.get(f"{m['tx']}|{m['rx']}") or []) if v and v > 0]
        jit = float(np.std(np.log(s))) if len(s) > 5 else 0.3
        bias = abs(math.log(corr / true_m))
        pairs.append((m["tx"], m["rx"], float(true_m), math.hypot(bias, jit)))
    if len(pairs) < MIN_PAIRS_FOR_FIT:
        return DEFAULT_A, DEFAULT_B, {}, len(pairs)
    A = np.array([[1.0, p[2]] for p in pairs])
    y = np.array([p[3] for p in pairs])
    (a, b), *_ = np.linalg.lstsq(A, y, rcond=None)
    a, b = max(float(a), 0.1), max(float(b), 0.0)
    ratios = defaultdict(list)
    for tx, rx, d, err in pairs:
        r = err / (a + b * d)
        ratios[tx].append(r)
        ratios[rx].append(r)
    factor = {k: float(np.clip(np.median(v), 0.6, 2.0)) for k, v in ratios.items()}
    return a, b, factor, len(pairs)


def _info(gx, gy, receivers, a, b):
    """Fisher-information terms (j00, j01, j11) at points gx, gy (metres).

    gx, gy may be any shape; receivers [(x, y, k)] where x, y are scalars or
    arrays broadcastable against gx (used to try many candidates at once).
    """
    j00 = np.zeros(np.broadcast(gx, gy).shape)
    j01 = np.zeros_like(j00)
    j11 = np.zeros_like(j00)
    for rx, ry, k in receivers:
        dx, dy = rx - gx, ry - gy
        d = np.maximum(np.hypot(dx, dy), 0.5)
        sig = d * (a + b * d) * k
        w = np.where(d <= MAX_RANGE_M, 1.0 / sig ** 2, 0.0)
        ux, uy = dx / d, dy / d
        j00 = j00 + w * ux * ux
        j01 = j01 + w * ux * uy
        j11 = j11 + w * uy * uy
    return j00, j01, j11


def _err(j00, j01, j11):
    det = j00 * j11 - j01 ** 2
    with np.errstate(divide="ignore", invalid="ignore"):
        e = np.sqrt((j00 + j11) / det)
    e = np.where(np.isfinite(e), e, ERR_CAP_M)
    return np.minimum(e, ERR_CAP_M)


def error_field(gx, gy, receivers, a, b):
    """Position error (m) at points gx, gy (metres); receivers [(x, y, k)]."""
    return _err(*_info(gx, gy, receivers, a, b))


def best_candidate(gx, gy, info, cand_x, cand_y, k_new, w, cur_err, a, b, chunk=64):
    """Index into cand_x/cand_y of the extra receiver that lowers sum(w*err) most.

    Vectorised over candidates in chunks: a few hundred numpy calls in total
    instead of one small call per candidate (that is slow under GIL pressure
    inside Home Assistant).
    """
    best_gain, best_i, best_e = -1.0, None, None
    j00, j01, j11 = info
    for s in range(0, len(cand_x), chunk):
        cx = cand_x[s:s + chunk, None]
        cy = cand_y[s:s + chunk, None]
        n00, n01, n11 = _info(gx[None, :], gy[None, :], [(cx, cy, k_new)], a, b)
        e = _err(j00[None, :] + n00, j01[None, :] + n01, j11[None, :] + n11)
        gains = ((cur_err[None, :] - e) * w[None, :]).sum(axis=1)
        i = int(np.argmax(gains))
        if gains[i] > best_gain:
            best_gain, best_i, best_e = float(gains[i]), s + i, e[i]
    return best_i, best_gain, best_e


# --------------------------------------------------------------------- usage
def usage_from_history(histories, now_ts):
    """Dwell seconds, visits and flaps per zone from zone-sensor histories.

    histories: {entity_id: [(timestamp, zone_state), ...]} sorted by time.
    """
    dwell, visits, flaps = defaultdict(float), defaultdict(int), defaultdict(int)
    bounces = defaultdict(int)
    for rows in histories.values():
        rows = [(t, s) for t, s in rows if s is not None]
        for i, (t, z) in enumerate(rows):
            if z in ("", "unknown", "unavailable", "not_home", "away", "none"):
                continue
            end = rows[i + 1][0] if i + 1 < len(rows) else now_ts
            dur = end - t
            dwell[z] += min(dur, DWELL_CAP_S)
            visits[z] += 1
            if i + 1 < len(rows) and dur < FLAP_S:
                flaps[z] += 1
                prev = rows[i - 1][1] if i > 0 else None
                if prev and rows[i + 1][1] == prev:
                    bounces[(prev, z)] += 1
    return dwell, visits, flaps, bounces


# ------------------------------------------------------------------ analysis
def analyze_floor(floor, noise, usage):
    """Heat grid, zone stats and best extra receivers for one floor."""
    a, b, factor = noise
    dwell, visits, flaps = usage
    scale = float(floor.get("scale") or 0)
    receivers = [r for r in floor.get("receivers") or [] if r.get("cords")]
    zones = []
    for z in floor.get("zones") or []:
        if z.get("no_go"):
            continue
        ring = _ring(z.get("cords") or [], z.get("poly"))
        if len(ring) >= 3:
            poly = Polygon(ring)
            if not poly.is_valid:
                poly = poly.buffer(0)
            zones.append({"name": z.get("entity_id"), "ring": ring, "poly": poly})
    if scale <= 0 or not receivers or not zones:
        return {"name": floor.get("name"), "ok": False,
                "reason": "needs a scale, receivers and zones"}

    xs_px = [p[0] for z in zones for p in z["ring"]] + [r["cords"]["x"] for r in receivers]
    ys_px = [p[1] for z in zones for p in z["ring"]] + [r["cords"]["y"] for r in receivers]
    x0 = max(min(xs_px) / scale - MARGIN_M, 0.0)
    y0 = max(min(ys_px) / scale - MARGIN_M, 0.0)
    x1, y1 = max(xs_px) / scale + MARGIN_M, max(ys_px) / scale + MARGIN_M
    xs = np.arange(x0, x1, GRID_M) + GRID_M / 2
    ys = np.arange(y0, y1, GRID_M) + GRID_M / 2
    GX, GY = np.meshgrid(xs, ys)
    gx, gy = GX.ravel(), GY.ravel()

    zone_of = np.full(gx.shape, -1)
    for zi, z in enumerate(zones):
        inside = shapely.contains_xy(z["poly"], gx * scale, gy * scale)
        zone_of[(zone_of < 0) & inside] = zi

    rx_m = [(r["cords"]["x"] / scale, r["cords"]["y"] / scale, factor.get(r.get("entity_id"), 1.0))
            for r in receivers]
    base = error_field(gx, gy, rx_m, a, b)

    # weights: each zone's dwell (+10 min so unvisited zones still count a
    # little) spread evenly over its cells
    w = np.zeros(gx.shape)
    for zi, z in enumerate(zones):
        cells = zone_of == zi
        if cells.any():
            w[cells] = (dwell.get(z["name"], 0.0) + 600.0) / cells.sum()
    if w.sum() <= 0:
        return {"name": floor.get("name"), "ok": False, "reason": "zones are empty"}
    w /= w.sum()

    stats = []
    for zi, z in enumerate(zones):
        c = zone_of == zi
        if not c.any():
            continue
        cx, cy = gx[c].mean(), gy[c].mean()
        dists = [math.hypot(rx - cx, ry - cy) for rx, ry, _ in rx_m]
        stats.append({
            "zone": z["name"],
            "err_m": round(float(base[c].mean()), 2),
            "err_p90_m": round(float(np.percentile(base[c], 90)), 2),
            "area_m2": round(float(c.sum() * GRID_M ** 2), 1),
            "dwell_h": round(dwell.get(z["name"], 0.0) / 3600, 1),
            "visits": int(visits.get(z["name"], 0)),
            "flaps": int(flaps.get(z["name"], 0)),
            "near_receivers": sum(1 for d in dists if d <= 6.0),
            "avg_dist_m": round(float(np.mean(dists)), 1),
        })
    stats.sort(key=lambda s: -s["err_m"])

    picks = []
    cand = np.where(zone_of >= 0)[0][::CANDIDATE_STRIDE]
    k_new = float(np.median(list(factor.values()))) if factor else 1.0
    info = _info(gx, gy, rx_m, a, b)
    cur_err = base
    for _ in range(2):
        if not len(cand):
            break
        ci, gain, e = best_candidate(gx, gy, info, gx[cand], gy[cand], k_new, w, cur_err, a, b)
        if ci is None or gain <= 0:
            break
        k = cand[ci]
        before = float((w * cur_err).sum())
        zc = zone_of == zone_of[k]
        picks.append({
            "x": round(float(gx[k] * scale), 1), "y": round(float(gy[k] * scale), 1),
            "zone": zones[zone_of[k]]["name"],
            "gain_pct": round(100 * gain / before, 1),
            "weighted_err_before_m": round(before, 2),
            "weighted_err_after_m": round(float((w * e).sum()), 2),
            "zone_err_before_m": round(float(cur_err[zc].mean()), 2),
            "zone_err_after_m": round(float(e[zc].mean()), 2),
        })
        n = _info(gx, gy, [(gx[k], gy[k], k_new)], a, b)
        info = (info[0] + n[0], info[1] + n[1], info[2] + n[2])
        cur_err = e

    return {
        "name": floor.get("name"), "ok": True,
        "grid": {"x0": round(float(x0 * scale), 2), "y0": round(float(y0 * scale), 2),
                 "step": round(float(GRID_M * scale), 3), "nx": len(xs), "ny": len(ys),
                 "err": [round(float(v), 1) for v in base],
                 "in_zone": [int(v >= 0) for v in zone_of]},
        "weighted_err_m": round(float((w * base).sum()), 2),
        "zones": stats, "picks": picks,
        "receivers": [{"name": r.get("entity_id"), "x": r["cords"]["x"], "y": r["cords"]["y"],
                       "factor": round(factor.get(r.get("entity_id"), 1.0), 2)} for r in receivers],
        "zone_rings": [{"name": z["name"], "ring": [[round(p[0], 1), round(p[1], 1)] for p in z["ring"]]}
                       for z in zones],
    }


def analyze(layout, calibration, histories, now_ts, own_usage=None):
    """Whole-house report. calibration: {"results": {floor: {...matrix}}, "samples": {...}}.

    Usage comes from the recorder histories when they have any, otherwise from
    BPS's own zone statistics (own_usage = UsageStats.summary()).
    """
    matrix = []
    for res in ((calibration or {}).get("results") or {}).values():
        matrix.extend(res.get("matrix") or [])
    samples = {k: list(v) for k, v in ((calibration or {}).get("samples") or {}).items()}
    a, b, factor, n_pairs = fit_noise_model(matrix, samples)
    dwell, visits, flaps, bounces = usage_from_history(histories, now_ts)
    source, days = ("recorder", None) if sum(dwell.values()) > 0 else (None, None)
    if source is None and own_usage and sum(own_usage[0].values()) > 0:
        dwell, visits, flaps, bounces, days = own_usage
        source = "bps"
    floors = [analyze_floor(f, (a, b, factor), (dwell, visits, flaps))
              for f in (layout or {}).get("floor") or []]
    return {
        "model": {"a": round(a, 3), "b": round(b, 4), "pairs": n_pairs,
                  "calibrated": n_pairs >= MIN_PAIRS_FOR_FIT},
        "usage": {"source": source, "days": days, "sensors": len(histories),
                  "dwell_h": round(sum(dwell.values()) / 3600, 1)},
        "bounces": sorted([{"from": f, "to": t, "n": n} for (f, t), n in bounces.items()],
                          key=lambda r: -r["n"])[:8],
        "floors": floors,
    }
