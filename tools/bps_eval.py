#!/usr/bin/env python3
"""BPS positioning evaluation harness.

Record what BPS actually publishes, then score it, so a change to the
positioning pipeline can be judged on numbers instead of vibes. The v1.4.0
Kalman filter and the v1.7.0 slant correction both shipped unmeasured; this
tool is the guardrail for the precision/jumpiness work that follows.

Pure standard library on purpose: copy it onto the HA host (or any machine
that can reach it) and run with `python3` — no pip install.

Two subcommands
---------------
  record   Poll /api/bps/cords at ~1 Hz into a JSONL file, de-duplicating on
           each entry's `updated` stamp (a 1 Hz poll of a 1 Hz publisher
           otherwise aliases the same fix many times). Snapshots each floor's
           pixel-per-metre scale from /api/bps/read_text once, so scoring can
           report metres.

  score    Read a recording and print metrics per tracker: stationary scatter
           (CEP50/CEP95 and, with --truth, systematic bias), jumpiness
           (per-tick step length median/p95 — the headline number), floor and
           zone flap counts, and the mean fit residual. Everything is computed
           for BOTH the published (filtered + zone-snapped) `cords` and the
           raw pre-Kalman `raw` fix, so an improvement can be attributed to the
           solver vs. the filter. --baseline scores a second file alongside and
           prints the delta for A/B before/after runs.

Typical use
-----------
  # Park a beacon somewhere for 10+ minutes, then:
  python3 bps_eval.py record --url http://homeassistant.local:8123 \
      --token "$BPS_TOKEN" --out before.jsonl --duration 600

  # ...make ONE pipeline change, re-record after.jsonl the same way, then:
  python3 bps_eval.py score after.jsonl --baseline before.jsonl

A long-lived access token (Profile -> Security -> Long-lived access tokens)
is read from --token or the BPS_TOKEN environment variable. The tool only
reads (/api/bps/cords, /api/bps/read_text); it never writes to HA.
"""
import argparse
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request


# --------------------------------------------------------------------------- #
# HTTP (record)
# --------------------------------------------------------------------------- #
def _get(url, token, timeout=10):
    """GET a BPS endpoint, returning parsed JSON or None on 404/no-data."""
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None  # /cords 404s until a tracker has a fix
        raise
    body = body.strip()
    if not body:
        return None
    return json.loads(body)


def _fetch_scales(base, token):
    """Map floor name -> pixel-per-metre scale, from the saved layout.

    read_text returns the layout as a JSON *string* (or "" on a fresh install).
    A missing/zero scale is dropped so scoring falls back to pixel units rather
    than dividing by a bogus number.
    """
    scales = {}
    try:
        raw = _get(base + "/api/bps/read_text", token)
    except Exception as e:  # noqa: BLE001 - scale is best-effort context
        print(f"warning: could not read layout for scales: {e}", file=sys.stderr)
        return scales
    coords = raw.get("coordinates") if isinstance(raw, dict) else raw
    if isinstance(coords, str):
        coords = json.loads(coords) if coords.strip() else {}
    if not isinstance(coords, dict):
        return scales
    for floor in coords.get("floor", []) or []:
        name, scale = floor.get("name"), floor.get("scale")
        if name and isinstance(scale, (int, float)) and scale > 0:
            scales[name] = float(scale)
    return scales


def cmd_record(args):
    token = args.token or os.environ.get("BPS_TOKEN")
    if not token:
        print("error: pass --token or set BPS_TOKEN", file=sys.stderr)
        return 2
    base = args.url.rstrip("/")
    scales = _fetch_scales(base, token)
    started = time.time()

    last_updated = {}          # ent -> last `updated` written (dedup key)
    n_samples = 0
    deadline = started + args.duration if args.duration else None

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "type": "header", "started": started, "url": base, "scales": scales,
        }) + "\n")
        fh.flush()
        print(f"recording -> {args.out}  (scales: {scales or 'none - pixel units'})")
        print("Ctrl-C to stop." if not deadline else f"stops after {args.duration}s.")
        try:
            while deadline is None or time.time() < deadline:
                t = time.time()
                try:
                    rows = _get(base + "/api/bps/cords", token)
                except Exception as e:  # noqa: BLE001 - keep recording through blips
                    print(f"  poll error: {e}", file=sys.stderr)
                    rows = None
                for row in rows or []:
                    ent = row.get("ent")
                    upd = row.get("updated")
                    if ent is None or upd is None or last_updated.get(ent) == upd:
                        continue  # not a new fix for this tracker
                    last_updated[ent] = upd
                    fh.write(json.dumps({
                        "ent": ent, "updated": upd,
                        "cords": row.get("cords"), "raw": row.get("raw"),
                        "floor": row.get("floor"), "zone": row.get("zone"),
                        "rms_m": row.get("rms_m"), "conf": row.get("conf"),
                    }) + "\n")
                    n_samples += 1
                fh.flush()
                if n_samples and n_samples % 30 == 0:
                    print(f"  {n_samples} samples...", end="\r", flush=True)
                slept = args.interval - (time.time() - t)
                if slept > 0:
                    time.sleep(slept)
        except KeyboardInterrupt:
            print("\nstopped.")
    print(f"done: {n_samples} deduped samples over "
          f"{time.time() - started:.0f}s -> {args.out}")
    return 0


# --------------------------------------------------------------------------- #
# Scoring (pure functions - unit tested)
# --------------------------------------------------------------------------- #
def load_recording(path):
    """Return (header, {ent: [sample, ...]}) from a JSONL recording.

    Tolerant of a partial final line and rows missing `ent`: a recording ended
    by anything other than a clean Ctrl-C (terminal closed, SIGKILL, disk full
    mid-flush) leaves a truncated last line, and one bad line must not throw
    away an otherwise-usable long recording. Malformed lines are skipped with a
    warning rather than aborting the score.
    """
    header, by_ent = {}, {}
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                print(f"warning: skipping malformed line {lineno} in {path}", file=sys.stderr)
                continue
            if rec.get("type") == "header":
                header = rec
                continue
            if rec.get("ent") is None:
                continue  # not a scorable sample
            by_ent.setdefault(rec["ent"], []).append(rec)
    return header, by_ent


def _ts(sample):
    """A sample's `updated` epoch; missing/null/non-numeric sorts first as 0.0."""
    t = sample.get("updated")
    return float(t) if isinstance(t, (int, float)) else 0.0


def percentile(values, pct):
    """Linear-interpolation percentile of an unsorted list (pct in 0..100)."""
    if not values:
        return float("nan")
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    rank = (pct / 100.0) * (len(s) - 1)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return s[lo]
    return s[lo] + (s[hi] - s[lo]) * (rank - lo)


def _point_seg_dist(p, a, b):
    """Distance from point p to segment a-b (all (x, y) tuples)."""
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    seg2 = dx * dx + dy * dy
    if seg2 == 0.0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _polyline_dist(p, waypoints):
    """Min distance from p to a polyline given as [(x, y), ...]."""
    if len(waypoints) == 1:
        return math.hypot(p[0] - waypoints[0][0], p[1] - waypoints[0][1])
    return min(_point_seg_dist(p, waypoints[i], waypoints[i + 1])
               for i in range(len(waypoints) - 1))


def _series_metrics(points, floors, scale, truth=None, waypoints=None):
    """Metrics for one coordinate series (either published `cords` or `raw`).

    points  : [(x, y), ...] in pixels (samples with no coord are pre-filtered)
    floors  : parallel list of floor names, to skip cross-floor step pairs
    scale   : px per metre for unit conversion (1.0 => report in pixels)
    """
    out = {"n": len(points), "units": "m" if scale != 1.0 else "px"}
    if not points:
        return out

    # Jumpiness: consecutive step lengths, skipping cross-floor jumps (a floor
    # change is not a planar step and would swamp the distribution).
    steps = [math.hypot(points[i][0] - points[i - 1][0],
                        points[i][1] - points[i - 1][1]) / scale
             for i in range(1, len(points)) if floors[i] == floors[i - 1]]
    if steps:
        out["step_median"] = percentile(steps, 50)
        out["step_p95"] = percentile(steps, 95)
        out["step_max"] = max(steps)

    # Stationary scatter: spread about the centroid (needs no ground truth).
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    radial = [math.hypot(p[0] - cx, p[1] - cy) / scale for p in points]
    out["cep50"] = percentile(radial, 50)
    out["cep95"] = percentile(radial, 95)
    out["centroid_px"] = [round(cx, 2), round(cy, 2)]
    if truth is not None:
        out["bias"] = math.hypot(cx - truth[0], cy - truth[1]) / scale

    # Walk: cross-track error vs. an intended path polyline (pixels in).
    if waypoints:
        ct = [_polyline_dist(p, waypoints) / scale for p in points]
        out["crosstrack_rms"] = math.sqrt(sum(d * d for d in ct) / len(ct))
        out["crosstrack_p95"] = percentile(ct, 95)
    return out


def score_entity(samples, scales, truth=None, waypoints=None):
    """Full metric set for one tracker's samples (both cords and raw)."""
    samples = sorted(samples, key=_ts)
    floors = [s.get("floor") for s in samples]

    # Representative scale = the most-sampled floor's scale; pixel units if
    # unknown so we never divide by a made-up number.
    counts = {}
    for f in floors:
        counts[f] = counts.get(f, 0) + 1
    main_floor = max(counts, key=counts.get) if counts else None
    scale = scales.get(main_floor, 1.0) if scales else 1.0

    def _series(key):
        pts, fls = [], []
        for s in samples:
            c = s.get(key)
            if isinstance(c, (list, tuple)) and len(c) >= 2 \
                    and c[0] is not None and c[1] is not None:
                pts.append((float(c[0]), float(c[1])))
                fls.append(s.get("floor"))
        return _series_metrics(pts, fls, scale, truth, waypoints)

    rms = [s["rms_m"] for s in samples if isinstance(s.get("rms_m"), (int, float))]
    conf = [s["conf"] for s in samples if isinstance(s.get("conf"), (int, float))]
    floor_flaps = sum(1 for i in range(1, len(floors)) if floors[i] != floors[i - 1])
    zones = [s.get("zone") for s in samples]
    zone_flaps = sum(1 for i in range(1, len(zones)) if zones[i] != zones[i - 1])

    return {
        "n": len(samples),
        "main_floor": main_floor,
        "scale_px_per_m": scale,
        "duration_s": round(_ts(samples[-1]) - _ts(samples[0]), 1) if samples else 0,
        "floor_flaps": floor_flaps,
        "zone_flaps": zone_flaps,
        "rms_m_mean": round(sum(rms) / len(rms), 3) if rms else None,
        "conf_mean": round(sum(conf) / len(conf), 3) if conf else None,
        "published": _series("cords"),
        "raw": _series("raw"),
    }


def score_recording(path, truth=None, waypoints=None):
    header, by_ent = load_recording(path)
    scales = header.get("scales", {})
    return {ent: score_entity(s, scales, truth, waypoints)
            for ent, s in by_ent.items()}


# --------------------------------------------------------------------------- #
# Scoring (CLI / reporting)
# --------------------------------------------------------------------------- #
_SERIES_KEYS = [
    ("step_median", "step median"), ("step_p95", "step p95"),
    ("step_max", "step max"), ("cep50", "CEP50"), ("cep95", "CEP95"),
    ("bias", "bias"), ("crosstrack_rms", "crosstrack rms"),
    ("crosstrack_p95", "crosstrack p95"),
]


def _fmt(v):
    return f"{v:.3f}" if isinstance(v, (int, float)) and not math.isnan(v) else "-"


def _print_series(title, series, base_series=None):
    unit = series.get("units", "")
    print(f"    {title} ({series.get('n', 0)} pts, {unit}):")
    for key, label in _SERIES_KEYS:
        if key not in series:
            continue
        cur = series[key]
        line = f"      {label:<16} {_fmt(cur)}"
        if base_series and key in base_series:
            delta = cur - base_series[key]
            arrow = "improved" if delta < 0 else "worse" if delta > 0 else "same"
            line += f"   (baseline {_fmt(base_series[key])}, {delta:+.3f} {arrow})"
        print(line)


def cmd_score(args):
    truth = None
    if args.truth:
        try:
            parts = [float(v) for v in args.truth.split(",")]
        except ValueError:
            print("error: --truth must be 'x,y' numbers in pixels", file=sys.stderr)
            return 2
        if len(parts) != 2:
            print("error: --truth must be exactly two values, 'x,y'", file=sys.stderr)
            return 2
        truth = (parts[0], parts[1])
    waypoints = None
    if args.waypoints:
        with open(args.waypoints, encoding="utf-8") as fh:
            wp = json.load(fh)
        try:
            waypoints = [(float(p["x"]), float(p["y"])) for p in wp]
        except (KeyError, TypeError, ValueError):
            print('error: --waypoints must be a JSON list of {"x":num,"y":num}', file=sys.stderr)
            return 2
        if not waypoints:
            print("error: --waypoints file has no points", file=sys.stderr)
            return 2

    result = score_recording(args.file, truth, waypoints)
    baseline = score_recording(args.baseline, truth, waypoints) if args.baseline else {}

    if args.json:
        print(json.dumps({"file": result, "baseline": baseline}, indent=2))
        return 0

    if not result:
        print("no tracker samples in recording.")
        return 0

    for ent, m in result.items():
        b = baseline.get(ent, {})
        print(f"\n=== {ent} ===")
        print(f"  samples={m['n']}  duration={m['duration_s']}s  "
              f"floor={m['main_floor']}  scale={m['scale_px_per_m']} px/m")
        print(f"  floor flaps={m['floor_flaps']}  zone flaps={m['zone_flaps']}  "
              f"rms_m(mean)={m['rms_m_mean']}  conf(mean)={m['conf_mean']}")
        if truth:
            print(f"  truth=({truth[0]}, {truth[1]}) px")
        _print_series("published (filtered+snapped)", m["published"], b.get("published"))
        _print_series("raw (pre-Kalman)", m["raw"], b.get("raw"))
    print("\nLower is better for every metric. Watch step p95 (jumpiness) and "
          "CEP95 (precision); guard walk-lag by re-recording a walk, not only a park.")
    return 0


# --------------------------------------------------------------------------- #
def build_parser():
    p = argparse.ArgumentParser(
        description="BPS positioning evaluation harness (record + score).")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("record", help="poll /api/bps/cords into a JSONL file")
    r.add_argument("--url", required=True, help="HA base URL, e.g. http://homeassistant.local:8123")
    r.add_argument("--token", help="long-lived access token (or set BPS_TOKEN)")
    r.add_argument("--out", required=True, help="output JSONL path")
    r.add_argument("--interval", type=float, default=1.0, help="poll interval s (default 1)")
    r.add_argument("--duration", type=float, default=0, help="stop after N s (default: until Ctrl-C)")
    r.set_defaults(func=cmd_record)

    s = sub.add_parser("score", help="score a recording")
    s.add_argument("file", help="JSONL recording to score")
    s.add_argument("--baseline", help="second recording to diff against (before/after)")
    s.add_argument("--truth", help="true position 'x,y' in PIXELS, for a stationary bias number")
    s.add_argument("--waypoints", help="JSON file [{\"x\":px,\"y\":py},...] for a walk crosstrack score")
    s.add_argument("--json", action="store_true", help="emit metrics as JSON")
    s.set_defaults(func=cmd_score)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
