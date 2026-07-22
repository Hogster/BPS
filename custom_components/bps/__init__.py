import aiofiles
import aiofiles.os
import time
from pathlib import Path
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.frontend import async_remove_panel
from homeassistant.components import panel_custom
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.template import Template
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import device_registry as dr
from homeassistant.const import UnitOfLength
from homeassistant.util.unit_conversion import DistanceConverter
from homeassistant.util import slugify
import numpy as np
from scipy.optimize import least_squares
import voluptuous as vol
import logging
import asyncio
import math
import os
import json
import re
import copy
import difflib
from shapely.geometry import Point, Polygon
from shapely.ops import nearest_points, unary_union
try:
    from shapely.validation import make_valid as shapely_make_valid
except ImportError:  # very old shapely
    shapely_make_valid = None
from asyncio import Lock, Queue, wait_for, TimeoutError

from .calibration import (
    BPSCalibrationAPI,
    async_restore_calibration_state,
    async_shutdown_calibration,
    async_start_auto_if_enabled,
    refresh_receivers_from_coords,
)
from .storage import (
    BPS_FILE_LOCK,
    get_bps_data,
    load_bps_data,
    migrate_legacy,
    save_bps_data,
)
from .zone_adjust import adjust_zones, adjust_subzones

_LOGGER = logging.getLogger(__name__)

DOMAIN = "bps"
OPTION_SHOW_SIDEBAR_PANEL = "show_sidebar_panel"
FRONTEND_PATH = Path(__file__).parent / "frontend"
LEGACY_BPS_ENTITY_PATTERN = re.compile(r"^sensor\.(.+)_\1_bps_(zone|floor)$")

# Global data (the layout now lives in the Store; see storage.get_bps_data)
state_change_lock = Lock()
state_change_counter = {}
update_queue = Queue()
tracked_listeners = {}
tracked_entities = []
new_global_data = {}
secToUpdate = 1
# A scanner Bermuda hasn't heard for this long is treated as offline; the
# liveness is polled from dump_devices every RECEIVER_DUMP_INTERVAL seconds.
RECEIVER_OFFLINE_SECS = 30
RECEIVER_DUMP_INTERVAL = 15
apitricords = []
# A tracker not detected by any receiver for this long disappears from the
# map and its zone/floor sensors go to unknown. Override with a top-level
# "position_timeout" (seconds) in bpsdata.txt.
STALE_POSITION_SECS = 300

# --- Output-position smoothing (constant-velocity Kalman filter) -------------
# The published position is smoothed with a constant-velocity 2D Kalman filter
# (state [x, y, vx, vy]) instead of a fixed-length moving average. Unlike the
# old 3-sample mean, the filter carries a motion model, so it lags less while a
# tracker is walking and settles more while it is still, and it adapts its gain
# to the estimated uncertainty rather than weighting every past fix equally.
#
# The noise parameters are defined in METRES (and metres/second) and converted
# into each floor's pixel space via the floor scale, so the filter behaves the
# same on maps of any resolution. They are deliberately "trusting": BPS already
# reads Bermuda's smoothed rssi_distance (20-sample average + velocity gate), so
# the trilateration fixes fed in here are not raw-RSSI noisy. Tune KF_MEAS_NOISE_M
# up for more smoothing, or KF_ACCEL_NOISE_MS2 up for a snappier response.
KF_MEAS_NOISE_M = 1.5        # per-fix position uncertainty (m); larger = smoother
KF_ACCEL_NOISE_MS2 = 0.5     # expected acceleration (m/s^2); larger = more responsive
KF_INIT_VEL_UNC_MS = 1.0     # initial velocity uncertainty (m/s) at (re)init
KF_MAX_DT_S = 10.0           # cap the prediction step so a gap can't blow up P
KF_MAX_GAP_S = 30.0          # gap beyond which state is reset (tracker was away)
# Soft-gate scale for spiky per-receiver distances: a reading whose radius
# changed by this fraction versus the previous update is down-weighted to 0.5
# (was a hard 50% discard). Nothing is dropped, so the solver keeps enough
# points to fix a position even while every distance is legitimately changing
# during movement.
RADIUS_JUMP_TOL = 0.5

# Uploaded floor-plan maps: accepted image extensions and a size cap. Client
# filenames are never trusted for filesystem paths (see _safe_maps_child).
# .jfif/.jpe are ordinary JPEG variants a browser's image/jpeg picker yields.
_ALLOWED_MAP_EXTS = {
    ".png", ".jpg", ".jpeg", ".jfif", ".jpe", ".gif", ".webp", ".bmp", ".svg", ".avif",
}
MAX_MAP_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB
# Non-map files that live in www/bps_maps and must never be deletable via the
# save_text "remove" field (that field is only meant to drop an old map image).
_PROTECTED_MAPS_FILES = {"bpsdata.txt", "bps_calibration_state.json"}
# Longest to wait on Bermuda's dump_devices before treating it as unavailable,
# so a hung/slow service can't stall the liveness or calibration loops.
DUMP_DEVICES_TIMEOUT_S = 10.0


def _safe_maps_child(maps_path, raw_name, allowed_exts=None):
    """Resolve raw_name to a path guaranteed to sit directly inside maps_path.

    Returns the resolved Path, or None if raw_name is unsafe. Path(name).name
    strips any directory component (so '../x' and '/etc/x' both collapse to a
    bare filename), and the resolved result is re-checked against maps_path as
    belt-and-suspenders. Client-supplied filenames must never reach the
    filesystem unfiltered (unauthenticated write endpoints, issue: audit #2).
    """
    if not raw_name:
        return None
    name = Path(str(raw_name)).name
    if not name or name in (".", ".."):
        return None
    if allowed_exts is not None and Path(name).suffix.lower() not in allowed_exts:
        return None
    base = Path(maps_path).resolve()
    target = (base / name).resolve()
    try:
        if not target.is_relative_to(base):
            return None
    except AttributeError:  # Python < 3.9 (HA is 3.12+; defensive only)
        if base != target and base not in target.parents:
            return None
    return target

# --- Receiver mount heights (optional per-receiver "height", metres) ---------
# Bermuda's distance estimates are line-of-sight SLANT ranges, but the map
# solve is 2D: a ceiling probe reading 2.3 m to a tracker right below it is
# really ~0.6 m away horizontally. When a receiver's mount height is set in
# the panel, the vertical leg is removed before trilateration
# (horizontal = sqrt(slant^2 - dz^2)). Trackers are assumed to be carried at
# TRACKER_HEIGHT_M above the floor; override with a top-level
# "tracker_height" (metres) in bpsdata.txt.
TRACKER_HEIGHT_M = 1.0
# Slant->horizontal legitimately produces very short radii (tracker nearly
# under a ceiling probe). The solver's geometric 1/r^2 weight would explode
# there and let that one receiver dominate the fit, so for WEIGHTING (not for
# the residual) radii are clamped to this physical minimum, converted to each
# floor's pixel scale.
MIN_WEIGHT_RADIUS_M = 0.5

# --- Floor election by hypothesis competition ---------------------------------
# The floor used to be elected by the single nearest receiver — one noisy
# reading through a ceiling could steal the tracker for a cycle (kitchen <->
# bedroom flapping, issue #94). Now every plausible floor is SOLVED and
# SCORED: the fit's agreement with all of that floor's receivers feeds a
# smoothed per-floor probability, and the elected floor only changes when a
# challenger clearly and persistently outscores the incumbent.
FLOOR_CANDIDATES = 3         # solve at most this many floors per cycle
FLOOR_PROB_SMOOTHING = 0.7   # EMA weight on the previous probability
FLOOR_SWITCH_MARGIN = 0.05   # probability lead that starts/keeps a challenge
FLOOR_SWITCH_CYCLES = 3      # consecutive leading cycles before the floor switches
FLOOR_DARK_GRACE_CYCLES = 3  # cycles a dark incumbent holds everything frozen
FLOOR_RESIDUAL_SCALE_M = 2.0 # weighted RMS residual (m) at which fit quality = 0.5
COVERAGE_TARGET_N = 5.0      # heard receivers at which the coverage term saturates

# No-go zones (issue #60): areas a tracker can't physically be — the upper
# footprint of a double-height foyer/great room open to the floor below.
# When a floor's fit lands in one of its no-go zones the fit is impossible on
# THAT floor, so its election confidence is multiplied down: the competition
# then prefers the floor where the same spot is a real room (the open space
# means that floor's receivers already hear the tracker and solve it as a
# candidate). The penalty only DOWN-WEIGHTS — a no-go floor that is the sole
# candidate still wins and its position is snapped out to the nearest allowed
# zone — so a tracker is never left position-less.
NO_GO_CONF_PENALTY = 0.15
# When snapping a fix out of dead space, grow the no-go footprint by this many
# pixels before subtracting it from the allowed region, so the snap target's
# boundary sits clear of the (boundary-inclusive) no-go edge rather than
# exactly on it — otherwise the snapped point still reads as "in the no-go
# zone" to covers()-based tests.
NO_GO_SNAP_MARGIN_PX = 3.0

# Per-tracker election state, all reset when the tracker is pruned:
# smoothed floor probabilities (entity -> {floor name: P}), the pending
# challenge (a floor out-scoring the incumbent, counted per cycle: entity ->
# {"floor": name, "count": n}), and how many consecutive cycles the incumbent
# floor has been dark (unsolvable) while a competitor solved.
_floor_probability = {}
_floor_challenge = {}
_floor_dark_cycles = {}

# Per-tracker Kalman state: entity -> {"x": np.array(4), "P": np.array(4,4),
# "ts": float, "floor": str}. Reset on floor change, long gap, or prune.
_kf_position_state = {}


def _tracker_height(data):
    """Assumed tracker height above the floor (m); "tracker_height" override."""
    if isinstance(data, dict):
        configured = data.get("tracker_height")
        if isinstance(configured, (int, float)) and 0 <= configured <= 5:
            return float(configured)
    return TRACKER_HEIGHT_M


def _floor_scale(data, entity, floor_name):
    """Pixels-per-metre for a tracker's elected floor (None if unknown)."""
    for ent in data:
        if ent.get("entity") == entity:
            for floor in ent["data"]["floor"]:
                if floor["name"] == floor_name:
                    return floor.get("scale")
    return None


def _kalman_position_update(entity, floor_name, meas, scale, bounds):
    """Constant-velocity Kalman filter on the trilaterated pixel position.

    ``meas`` is the newest ``(x, y)`` fix in this floor's pixel space. Noise is
    specified in metres via the module KF_* constants and scaled to pixels with
    ``scale`` (pixels per metre) so the smoothing is resolution-independent. The
    state is (re)initialised at the measurement with zero velocity whenever there
    is no prior state, the elected floor changed (coordinates live in a different
    pixel space), or the gap since the last fix exceeds KF_MAX_GAP_S (the tracker
    was out of range, so its velocity is meaningless). Returns the filtered
    ``(x, y)`` clipped to ``bounds``; the raw fix is what feeds the filter, so the
    estimate is never biased by zone snapping applied downstream.
    """
    s = scale if isinstance(scale, (int, float)) and scale > 0 else 1.0
    r_var = (KF_MEAS_NOISE_M * s) ** 2          # measurement variance (px^2)
    a_var = (KF_ACCEL_NOISE_MS2 * s) ** 2       # accel variance (px^2/s^4)
    zx, zy = float(meas[0]), float(meas[1])
    now = time.time()
    st = _kf_position_state.get(entity)

    def _clip(px, py):
        if bounds is None:
            return px, py
        minx, miny, maxx, maxy = bounds
        return min(max(px, minx), maxx), min(max(py, miny), maxy)

    if st is None or st["floor"] != floor_name or now - st["ts"] > KF_MAX_GAP_S:
        v_var = (KF_INIT_VEL_UNC_MS * s) ** 2
        _kf_position_state[entity] = {
            "x": np.array([zx, zy, 0.0, 0.0], dtype=float),
            "P": np.diag([r_var, r_var, v_var, v_var]).astype(float),
            "ts": now,
            "floor": floor_name,
        }
        return _clip(zx, zy)

    dt = min(max(now - st["ts"], 1e-3), KF_MAX_DT_S)
    x, P = st["x"], st["P"]
    F = np.array(
        [[1, 0, dt, 0], [0, 1, 0, dt], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=float
    )
    # Piecewise white-noise-acceleration process covariance, per axis.
    dt2 = dt * dt
    dt3 = dt2 * dt
    dt4 = dt3 * dt
    q_axis = np.array([[dt4 / 4.0, dt3 / 2.0], [dt3 / 2.0, dt2]]) * a_var
    Q = np.zeros((4, 4))
    Q[np.ix_([0, 2], [0, 2])] = q_axis  # x, vx
    Q[np.ix_([1, 3], [1, 3])] = q_axis  # y, vy

    # Predict.
    x = F @ x
    P = F @ P @ F.T + Q
    # Update with the position measurement.
    H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=float)
    R = np.diag([r_var, r_var]).astype(float)
    z = np.array([zx, zy], dtype=float)
    S = H @ P @ H.T + R
    K = P @ H.T @ np.linalg.inv(S)
    x = x + K @ (z - H @ x)
    P = (np.eye(4) - K @ H) @ P

    st["x"], st["P"], st["ts"], st["floor"] = x, P, now, floor_name
    return _clip(float(x[0]), float(x[1]))


def cleanup_legacy_bps_registry_and_states(hass: HomeAssistant):
    """Remove legacy duplicated BPS ids from entity registry and state machine."""
    entity_registry = er.async_get(hass)
    legacy_registry_ids = [
        entry.entity_id
        for entry in entity_registry.entities.values()
        if LEGACY_BPS_ENTITY_PATTERN.match(entry.entity_id)
    ]
    for entity_id in legacy_registry_ids:
        _LOGGER.info("Removing legacy BPS registry entity: %s", entity_id)
        entity_registry.async_remove(entity_id)

    legacy_state_ids = [
        state.entity_id
        for state in hass.states.async_all()
        if LEGACY_BPS_ENTITY_PATTERN.match(state.entity_id)
    ]
    for entity_id in legacy_state_ids:
        _LOGGER.info("Removing legacy BPS state: %s", entity_id)
        hass.states.async_remove(entity_id)

async def update_tracked_entities(hass, jinja_code):
    """Update tracked_entities with the result of the Jinja code once per second."""
    global tracked_entities, tracked_listeners, new_global_data
    global secToUpdate
    template = Template(jinja_code, hass)  # compile once; async_render re-evaluates each tick
    while True:
        try:
            tracked_entities = template.async_render()
            # The template matches every "_distance_to_" sensor; keep only the
            # ones Bermuda actually owns, so look-alike sensors from other
            # integrations (e.g. an mmWave sensor's
            # "_distance_to_detection_object") never become tracked devices.
            allowed = set(_bermuda_distance_sensor_ids(hass))
            tracked_entities = [e for e in tracked_entities if e in allowed]

            await prune_stale_positions(hass)

            num_points = len(tracked_entities)
            if num_points == 0:
                _LOGGER.info("There are no devices present to track, sleep 10 seconds")
                await asyncio.sleep(10)
                continue  # Skip and start over
            if num_points < 3:
                _LOGGER.info("There are not enough trackers with available data to track, sleep 10 seconds")
                await asyncio.sleep(10)
                continue  # Skip and start over
            
            cleaned = [item.split("_distance_to_")[0].replace("sensor.", "") for item in tracked_entities]
            unique_values = list(set(cleaned))
            # Use a separate copy per entity to avoid cross-entity mutation side effects.
            layout = get_bps_data(hass)
            new_global_data = [{"entity": ent, "data": copy.deepcopy(layout)} for ent in unique_values]
            
            await process_entities(hass, new_global_data)

        except Exception as e:
            _LOGGER.info(f"Error executing Jinja code: {e}")

        # Refresh receiver liveness on its own slower cadence.
        now_ts = time.time()
        if now_ts - getattr(update_tracked_entities, "last_liveness", 0.0) >= RECEIVER_DUMP_INTERVAL:
            update_tracked_entities.last_liveness = now_ts
            await update_receiver_liveness(hass)

        await asyncio.sleep(secToUpdate)  # Run every X seconds, set timer in global variables


# State strings that mean "not working" when a status/availability entity is read.
_OFFLINE_STATES = {
    "", "unavailable", "unknown", "none", "off", "false",
    "not_home", "offline", "disconnected", "no",
}


def _state_looks_online(state):
    """Whether a status/availability entity's state reads as online."""
    if state is None:
        return False
    return str(state).strip().lower() not in _OFFLINE_STATES


def _bermuda_distance_sensor_ids(hass):
    """Entity ids of the ``sensor.*_distance_to_*`` sensors that actually belong
    to the ``bermuda`` integration.

    Other integrations expose look-alike distance sensors — e.g. an ESPHome
    mmWave presence sensor's ``..._distance_to_detection_object`` — which are not
    tracker-to-scanner distances and must never feed BPS. Every place that
    enumerates distance sensors (device tracking, the receiver/beacon debug
    views, the receiver picker) goes through this, mirroring the same
    ``platform == "bermuda"`` guard ``sensor.get_filtered_entities`` already
    applies to the sensor-creation path.
    """
    ent_reg = er.async_get(hass)
    ids = []
    for st in hass.states.async_all("sensor"):
        eid = st.entity_id
        if "_distance_to_" not in eid:
            continue
        entry = ent_reg.async_get(eid)
        if entry is None or entry.platform != "bermuda":
            continue
        ids.append(eid)
    return ids


def _scanner_slugs_and_readings(hass):
    """Single pass over Bermuda distance sensors: every scanner slug Bermuda
    exposes, and the subset that currently has a live reading (for the heuristic
    tier)."""
    slugs = set()
    with_reading = set()
    allowed = set(_bermuda_distance_sensor_ids(hass))
    for st in hass.states.async_all("sensor"):
        eid = st.entity_id
        if eid not in allowed:
            continue
        slug = eid.split("_distance_to_", 1)[1]
        slugs.add(slug)
        if st.state not in (None, "", "unknown", "unavailable"):
            with_reading.add(slug)
    return slugs, with_reading


_SCANNER_TOKEN_RE = re.compile(r"^[0-9a-f]{5,12}$")


def _scanner_token(slug):
    """The trailing hardware id Bermuda embeds in a scanner slug — the hex group
    derived from the device's MAC, e.g. 'master_bedroom_esp32c5_f17464' ->
    'f17464'. This survives renames of the human-readable prefix, so it is a
    stable identity for a physical scanner. None when the slug has no hex tail.
    """
    if not slug:
        return None
    last = str(slug).rsplit("_", 1)[-1].lower()
    return last if _SCANNER_TOKEN_RE.match(last) else None


def _suggest_scanner(placement_slug, stored_uid, candidates):
    """Best live scanner slug to re-link a stale placement to. Prefer a shared
    hardware token (an explicitly-stored uid, else the placement's own trailing
    token — the same physical scanner after a rename); otherwise fall back to
    plain string similarity. Returns a candidate slug or None.
    """
    token = stored_uid or _scanner_token(placement_slug)
    if token:
        tok_matches = [c for c in candidates if _scanner_token(c) == token]
        if len(tok_matches) == 1:
            return tok_matches[0]
    best, best_score = None, 0.0
    for c in candidates:
        score = difflib.SequenceMatcher(None, str(placement_slug), c).ratio()
        if score > best_score:
            best, best_score = c, score
    return best if best_score >= 0.55 else None


def _placed_receivers(coordinates_json):
    """Placed receivers as (floor_name, entity_id slug, stored scanner_uid).

    Parsed defensively: a malformed or hand-edited bpsdata.txt yields [] rather
    than raising into a caller (diagnostics must never break read_text). Each
    entity_id must be a non-empty string — a non-string slug isn't a real
    scanner name and would be unhashable when callers build a set of slugs.
    """
    placed = []
    try:
        parsed = json.loads(coordinates_json)
        floors = parsed.get("floor") if isinstance(parsed, dict) else None
        for fl in floors if isinstance(floors, list) else []:
            if not isinstance(fl, dict):
                continue
            receivers_ = fl.get("receivers")
            for rec in receivers_ if isinstance(receivers_, list) else []:
                if isinstance(rec, dict) and isinstance(rec.get("entity_id"), str) and rec["entity_id"]:
                    placed.append((fl.get("name"), rec["entity_id"], rec.get("scanner_uid")))
    except Exception:
        return []
    return placed


# Distance-sensor states that mean "no distance right now" (as opposed to a
# real numeric reading). Shared by the diagnostics and the linking debug view.
_NO_DISTANCE_STATES = (None, "", "unknown", "unavailable")


def _scanner_diagnostics(hass, coordinates_json):
    """Compare placed receivers against the scanner slugs Bermuda actually
    exposes, to flag naming mismatches (issue #64):
      - unmatched_receivers: a placed slug that has NO matching distance sensor
        (a genuinely wrong/stale name), each with a suggested live scanner.
      - unplaced_scanners: scanner slugs currently reporting a distance that
        aren't placed on any floor.
    """
    slugs, with_reading = _scanner_slugs_and_readings(hass)
    placed = _placed_receivers(coordinates_json)
    placed_slugs = {p[1] for p in placed}
    # Candidates for a re-link: live scanner slugs not already correctly placed.
    free = [s for s in slugs if s not in placed_slugs]
    unmatched = []
    for fname, slug, uid in placed:
        if slug in slugs:
            continue  # a real sensor exists (offline is a separate concern)
        unmatched.append({
            "entity_id": slug,
            "floor": fname,
            "suggested": _suggest_scanner(slug, uid, free),
        })
    unplaced = sorted(with_reading - placed_slugs)
    return {"unmatched_receivers": unmatched, "unplaced_scanners": unplaced}


def _scanner_linking(hass, coordinates_json):
    """Debug view for issue #64: for every placed receiver, the Bermuda distance
    sensors that feed it and each one's current state.

    This distinguishes the two failure modes David couldn't tell apart from the
    map alone: a receiver correctly linked but simply not reporting a distance
    right now ("silent" — usually just no recent BLE contact), versus one whose
    name matches no distance sensor at all ("unmatched" — a real naming
    mismatch). Reads live HA state directly, so it does not depend on a device
    being actively tracked. Returns:
      - placed:   one row per placed receiver with its status and per-device
                  readings (the exact `<device>_distance_to_<slug>` sensors
                  update_receiver_radii looks up).
      - unplaced: scanner slugs that have distance sensors but no placement,
                  for context (a superset of the diagnostics' "reporting" list).
    """
    by_slug = {}
    allowed = set(_bermuda_distance_sensor_ids(hass))
    for st in hass.states.async_all("sensor"):
        eid = st.entity_id
        if eid not in allowed:
            continue
        device_part, slug = eid.split("_distance_to_", 1)
        device = device_part[len("sensor."):] if device_part.startswith("sensor.") else device_part
        state = None if st.state is None else str(st.state)
        by_slug.setdefault(slug, []).append({"device": device, "entity_id": eid, "state": state})

    def _reporting(sensors):
        return [s for s in sensors if s["state"] not in _NO_DISTANCE_STATES]

    placed = _placed_receivers(coordinates_json)
    placed_slugs = {p[1] for p in placed}
    rows = []
    for fname, slug, uid in placed:
        sensors = sorted(by_slug.get(slug, []), key=lambda s: s["device"])
        reporting = _reporting(sensors)
        if not sensors:
            status = "unmatched"
        elif reporting:
            status = "live"
        else:
            status = "silent"
        rows.append({
            "entity_id": slug,
            "floor": fname,
            "scanner_uid": uid,
            "token": _scanner_token(slug),
            "status": status,
            "sensor_count": len(sensors),
            "reporting_count": len(reporting),
            "sensors": sensors,
        })
    unplaced = []
    for slug, sensors in by_slug.items():
        if slug in placed_slugs:
            continue
        unplaced.append({
            "entity_id": slug,
            "token": _scanner_token(slug),
            "sensor_count": len(sensors),
            "reporting_count": len(_reporting(sensors)),
        })
    unplaced.sort(key=lambda u: u["entity_id"])
    return {"placed": rows, "unplaced": unplaced}


def _beacon_links(hass):
    """Debug view: for every tracked device (beacon), the receivers currently
    detecting it, sorted closest -> farthest. The inverse of _scanner_linking
    (grouped by the tracked device instead of by the scanner). Distances are
    normalized to metres only for sorting — Bermuda reports per-entity feet or
    metres — while the value is shown in its own unit. A beacon with no live
    reading still appears (empty list) so a device that's gone dark is visible.
    """
    beacons = {}  # device -> [{scanner, distance, unit}]
    allowed = set(_bermuda_distance_sensor_ids(hass))
    for st in hass.states.async_all("sensor"):
        eid = st.entity_id
        if eid not in allowed:
            continue
        device_part, slug = eid.split("_distance_to_", 1)
        device = device_part[len("sensor."):] if device_part.startswith("sensor.") else device_part
        beacons.setdefault(device, [])
        if st.state in _NO_DISTANCE_STATES:
            continue
        try:
            val = float(st.state)
        except (ValueError, TypeError):
            continue
        unit = st.attributes.get("unit_of_measurement")
        meters = val * 0.3048 if unit == "ft" else val
        beacons[device].append({
            "scanner": slug,
            "distance": round(val, 2),
            "unit": unit if isinstance(unit, str) and unit else "m",
            "_m": meters,
        })
    out = []
    for device in sorted(beacons):
        recs = sorted(beacons[device], key=lambda r: r["_m"])
        for r in recs:
            r.pop("_m", None)  # internal sort key only
        out.append({"device": device, "receivers": recs})
    return out


def _refresh_dump_ages(hass, dom, devices):
    """Update the cached per-scanner Bermuda-liveness ages from a dump payload.

    last_seen is monotonic (seconds since HA boot), not epoch; the freshest
    stamp in the payload is "now" on that clock. Re-anchor only when the payload
    aged forward — if newest didn't advance (every scanner stopped hearing
    adverts, a real fleet-wide outage) keep the previous ages so they grow with
    wall time and cross the timeout; a large backward jump is a monotonic clock
    reset (HA reboot), so accept it.
    """
    newest = 0.0
    for dev in devices.values():
        ls = dev.get("last_seen") if isinstance(dev, dict) else None
        if isinstance(ls, (int, float)) and ls > newest:
            newest = ls
    prev_newest = dom.get("rl_newest")
    now = time.time()
    if not (prev_newest is not None and prev_newest - 60 < newest <= prev_newest):
        ages = {}
        for dev in devices.values():
            if not isinstance(dev, dict) or dev.get("_is_scanner") is not True:
                continue
            slug = slugify(str(dev.get("name") or ""))
            if not slug:
                continue
            ls = dev.get("last_seen")
            ages[slug] = (newest - ls) if isinstance(ls, (int, float)) else float("inf")
        dom["rl_newest"] = newest
        dom["rl_anchor_wall"] = now
        dom["rl_ages"] = ages


def _build_device_availability(hass):
    """Maps for the device-availability tier: slug -> device, device -> entities.

    A device slug that isn't unique is dropped (ambiguous) so a stale/duplicate
    device can't decide a receiver's status.
    """
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    slug_to_device = {}
    ambiguous = set()
    for d in dev_reg.devices.values():
        name = d.name_by_user or d.name
        if not name:
            continue
        slug = slugify(name)
        if not slug:
            continue
        if slug in slug_to_device and slug_to_device[slug] != d.id:
            ambiguous.add(slug)
        else:
            slug_to_device[slug] = d.id
    for slug in ambiguous:
        slug_to_device.pop(slug, None)
    device_entities = {}
    for ent in ent_reg.entities.values():
        if ent.device_id:
            device_entities.setdefault(ent.device_id, []).append(ent.entity_id)
    return slug_to_device, device_entities


async def update_receiver_liveness(hass):
    """Recompute the set of offline receivers, mirroring the Lovelace card's
    tiered status so the panel and the card agree.

    For each receiver slug Bermuda exposes, the first tier that resolves wins:
      1. Bermuda scanner liveness — last advert heard within RECEIVER_OFFLINE_SECS.
         Proximity-independent: the probes advertise iBeacons the scanners hear
         from each other, so a live scanner ages fresh even with no tracked
         device home. But Bermuda drops a downed proxy from the scanner list, so
         this tier can't see it at all — hence the fallbacks below.
      2. A `binary_sensor.<slug>_status` connectivity sensor.
      3. The receiver's HA device: online while any of its entities is not
         `unavailable`; a connectivity entity on the device is authoritative.
      4. Distance heuristic (last resort): working if some tracker got a reading
         through it recently. Only reached for a scanner with no liveness and no
         mapped device (6 of this install's receivers, whose device name doesn't
         slugify to the receiver id). An *up* scanner is caught by tier 1, so
         this can't misfire when every tracked device leaves home — it only
         decides a scanner that is both absent from the dump and deviceless.
    A receiver no tier can resolve at all is left ONLINE (never flagged).
    """
    dom = hass.data.setdefault(DOMAIN, {})
    try:
        devices = await wait_for(
            hass.services.async_call(
                "bermuda", "dump_devices", {"configured_devices": True},
                blocking=True, return_response=True,
            ),
            timeout=DUMP_DEVICES_TIMEOUT_S,
        ) or {}
    except TimeoutError:
        _LOGGER.warning(
            "Receiver liveness: bermuda.dump_devices timed out after %ss; "
            "skipping this refresh", DUMP_DEVICES_TIMEOUT_S,
        )
        devices = None
    except Exception as e:
        _LOGGER.info(f"Receiver liveness: dump_devices unavailable: {e}")
        devices = None

    if isinstance(devices, dict):
        _refresh_dump_ages(hass, dom, devices)
    ages = dom.get("rl_ages", {})
    elapsed = max(0.0, time.time() - dom["rl_anchor_wall"]) if dom.get("rl_anchor_wall") else 0.0

    receivers, with_reading = _scanner_slugs_and_readings(hass)
    slug_to_device, device_entities = _build_device_availability(hass)

    def device_online(slug):
        device_id = slug_to_device.get(slug)
        if not device_id:
            return None
        eids = device_entities.get(device_id)
        if not eids:
            return None
        # A connectivity entity reports link state directly and is authoritative:
        # ESPHome keeps its status sensor available with state "off" when the
        # proxy disconnects, so "any entity not unavailable" would miss it.
        for eid in eids:
            st = hass.states.get(eid)
            if st and st.attributes.get("device_class") == "connectivity" and st.state is not None:
                return _state_looks_online(st.state)
        saw_state = False
        for eid in eids:
            st = hass.states.get(eid)
            if st is None or st.state is None:
                continue
            saw_state = True
            if st.state != "unavailable":
                return True
        return False if saw_state else None

    def is_online(slug):
        age = ages.get(slug)
        if age is not None:
            return (age + elapsed) <= RECEIVER_OFFLINE_SECS
        st = hass.states.get(f"binary_sensor.{slug}_status")
        if st and st.attributes.get("device_class") == "connectivity":
            return _state_looks_online(st.state)
        resolved = device_online(slug)
        if resolved is not None:
            return resolved
        # tier 4: distance heuristic (last resort). Matches the card: a receiver
        # here is online only while some tracker reads a distance through it.
        return slug in with_reading

    dom["rl_offline"] = sorted(s for s in receivers if not is_online(s))


async def update_receiver_radii(hass, eids):
    """Update receiver 'r' values (pixels) and raw 'distance' (meters) for an entity"""
    tracker_h = _tracker_height(eids["data"])
    for floor in (f for f in eids["data"]["floor"] if f["scale"] is not None):
        for receiver in floor["receivers"]:
            entity_id = "sensor." + eids["entity"] + "_distance_to_" + receiver["entity_id"]
            rec_value = hass.states.get(entity_id)
            if rec_value is not None:
                try:
                    distance = float(rec_value.state)
                    # Bermuda's distance_to sensors can report in feet or
                    # meters, chosen per entity. The floor scale and the
                    # calibration corrections are both in meters, so normalize
                    # to meters first — otherwise a feet sensor reads ~3.28x too
                    # far (treated as metres), inflating its circle and pulling
                    # the trilateration toward it.
                    unit = rec_value.attributes.get("unit_of_measurement")
                    if unit in DistanceConverter.VALID_UNITS and unit != UnitOfLength.METERS:
                        distance = DistanceConverter.convert(distance, unit, UnitOfLength.METERS)
                    # Per-receiver correction factor learned by the
                    # calibration (calibration.py); equivalent to a
                    # per-scanner RSSI offset in Bermuda's exponential model.
                    correction = receiver.get("correction")
                    if isinstance(correction, (int, float)) and correction > 0:
                        distance = distance * correction
                    # Known mount height: the estimate is a slant range, so
                    # remove the vertical leg (mount height vs the assumed
                    # tracker height) to get the horizontal distance the 2D
                    # solve actually needs. A slant shorter than the vertical
                    # leg means "practically underneath" — horizontal ~ 0; the
                    # solver's MIN_WEIGHT_RADIUS_M clamp keeps such a near-zero
                    # radius from monopolizing the fit. The range guard also
                    # rejects NaN/Infinity from a hand-edited data file (NaN
                    # fails both comparisons), which would otherwise poison
                    # every solve on the floor.
                    horizontal = distance
                    height = receiver.get("height")
                    if isinstance(height, (int, float)) and 0 <= height <= 10:
                        dz = float(height) - tracker_h
                        horizontal = math.sqrt(max(distance * distance - dz * dz, 0.0))
                    receiver["cords"]["r"] = floor["scale"] * horizontal
                    # Raw SLANT distance for the floor election: radii are in
                    # per-floor pixel scales and must not be compared across
                    # floors — and the dz correction must not leak in here
                    # either. sqrt(d^2 - dz^2) is only valid when the tracker
                    # is on the receiver's own floor, which is exactly what
                    # the election hasn't decided yet: electing on corrected
                    # values lets a high-mounted probe hearing the tracker
                    # through the slab shrink its through-floor slant and
                    # steal the election from the correct floor.
                    receiver["distance"] = distance
                except ValueError:
                    #_LOGGER.info(f"Invalid numerical value: {rec_value.state}")
                    pass
            else:
                #_LOGGER.info(f"Entity had no value: {receiver['entity_id']}")
                pass

async def update_trilateration_and_zone(hass, new_global_data, entity):
    """Trilateration with floor hypothesis competition, soft radius-jump
    weighting and Kalman position smoothing.

    The floor used to be elected by the single nearest receiver before any
    position existed — one noisy reading through a ceiling could steal the
    tracker for a cycle (issue #94). Now the top FLOOR_CANDIDATES floors (by
    nearest receiver) are each SOLVED, scored by how well the fix explains
    that floor's whole receiver ensemble, folded into smoothed per-floor
    probabilities, and elected with incumbent hysteresis. The winning floor's
    fix continues into the unchanged Kalman/zone/publish pipeline.
    """
    global apitricords

    # Store last r-values per sensor and entity (for soft radius-jump weighting).
    if not hasattr(update_trilateration_and_zone, "last_r_values"):
        update_trilateration_and_zone.last_r_values = {}
    if not hasattr(update_trilateration_and_zone, "last_floor"):
        update_trilateration_and_zone.last_floor = {}

    candidates = extract_candidate_floors(new_global_data, entity)

    if not candidates:
        # No receiver reports any distance for this device: it is out of
        # range. The zone/floor sensors keep their last value (historical
        # behavior), but nearest-zone explicitly reports unknown.
        update_bps_sensor_state(hass, f"sensor.{entity}_bps_nearest_zone", "unknown")
        return

    # Get previous r-values for this entity
    last_r = update_trilateration_and_zone.last_r_values.get(entity, {})

    # Remember radii for EVERY floor with data — not only the ones solved
    # below — so a floor stays jump-gated even while unelected or briefly
    # pushed out of the candidate cut (keys include the floor: radii are in
    # per-floor pixel scales and must not be compared across floors).
    new_last_r = {}
    for cand in candidates:
        new_last_r.update({(cand["name"], x, y): r for (x, y, r) in cand["cords"]})

    incumbent = update_trilateration_and_zone.last_floor.get(entity)

    # Only floors with enough receivers to trilaterate compete for the solve
    # slots: an unsolvable floor whose single through-slab receiver reads
    # short must not consume a slot and push the only solvable floor out.
    # The incumbent, when solvable, ALWAYS defends its title — even ranked
    # below the cut — so nearest-slant noise alone can never evict it.
    solvable = [c for c in candidates if len(c["cords"]) >= 3]
    to_solve = solvable[:FLOOR_CANDIDATES]
    if incumbent is not None and not any(c["name"] == incumbent for c in to_solve):
        inc_cand = next((c for c in solvable if c["name"] == incumbent), None)
        if inc_cand is not None:
            to_solve.append(inc_cand)

    solved = {}  # floor name -> everything the publish pipeline needs
    for cand in to_solve:
        floor_name, cords = cand["name"], cand["cords"]

        # Physical floor for the geometric weight and the jump comparison, in
        # this floor's pixels. Slant correction (known mount heights) makes
        # near-zero radii a normal reading, and 1/r^2 must not hand one such
        # receiver the whole fit.
        scale = _floor_scale(new_global_data, entity, floor_name)
        min_wr = MIN_WEIGHT_RADIUS_M * scale if scale else 1e-3

        # Soft radius-jump weighting (replaces the old hard 50% discard). A
        # receiver whose radius jumped versus its previous update is
        # DOWN-WEIGHTED rather than dropped, so the solver keeps enough points
        # to fix a position even while every distance is legitimately changing
        # during movement. Radii are clamped to the physical minimum for the
        # comparison: slant correction turns noisy near-readings into exact
        # 0.0, and an untamed 0 <-> nonzero transition is an infinite relative
        # jump that used to escape the gate entirely (r > 0 guard) and enter
        # the fit fully trusted at maximum geometric weight.
        weighted = []
        for (x, y, r) in cords:
            prev_r = last_r.get((floor_name, x, y))
            if prev_r is not None:
                r_eff, prev_eff = max(r, min_wr), max(prev_r, min_wr)
                rel = max(r_eff / prev_eff, prev_eff / r_eff)  # symmetric relative change, >= 1
                w = 1.0 / (1.0 + ((rel - 1.0) / RADIUS_JUMP_TOL) ** 2)
            else:
                w = 1.0  # first sighting on this floor: no basis to distrust it
            weighted.append((x, y, r, w))

        # The device cannot be outside the floor: bound the solver to the
        # extent of the floor's receivers and zones (with some margin) so the
        # fitted position is the best point WITHIN the map, not a runaway fix
        # that would need clamping afterwards.
        zone_polys = list(_floor_zone_polygons(new_global_data, entity, floor_name))
        xs = [p[0] for p in weighted]
        ys = [p[1] for p in weighted]
        for _zone_id, polygon, _buffer_size, _no_go in zone_polys:
            minx, miny, maxx, maxy = polygon.bounds
            xs.extend((minx, maxx))
            ys.extend((miny, maxy))
        margin = 0.1 * max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
        floor_bounds = (min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin)

        fix = trilaterate(weighted, bounds=floor_bounds, min_weight_radius=min_wr)
        if fix is None:
            continue  # this floor's readings don't converge; not a contender
        conf, rms_m, coverage = _score_floor_fit(fix, weighted, scale)
        # A fit landing in this floor's no-go zone is physically impossible
        # here (issue #60): down-weight it so the competition prefers the
        # floor where that spot is a real room. Down-weight, not eliminate —
        # a sole candidate still wins and is snapped out below.
        if _point_in_no_go(fix, zone_polys):
            conf *= NO_GO_CONF_PENALTY
        solved[floor_name] = {
            "fix": fix,
            "weighted": weighted,
            "bounds": floor_bounds,
            "zone_polys": zone_polys,
            "scale": scale,
            "conf": conf,
            "rms_m": rms_m,     # kept for the elected floor's telemetry payload
        }

    # Store current r-values for next time
    update_trilateration_and_zone.last_r_values[entity] = new_last_r

    if not solved:
        # No candidate floor has three converging receivers (historical
        # behavior: sensors keep their last value until pruned).
        return

    valid_floors = {
        f["name"]
        for e in new_global_data if e["entity"] == entity
        for f in e["data"]["floor"]
    }

    # The elected floor was renamed or deleted in the data file: that is a
    # change of world, not a dark blip — routing it into the grace below
    # would freeze the ghost name for the grace period and then elect
    # whichever OTHER floor inherited the stale probability mass. Reset the
    # whole election state instead (exactly like a prune), so this cycle's
    # fresh scores elect the renamed floor immediately.
    if incumbent is not None and incumbent not in valid_floors:
        _floor_probability.pop(entity, None)
        _floor_challenge.pop(entity, None)
        _floor_dark_cycles.pop(entity, None)
        update_trilateration_and_zone.last_floor.pop(entity, None)
        incumbent = None

    # Dark-incumbent grace: the elected floor blipping below three receivers
    # (or its solve failing) for a few cycles is a sensor hiccup, not
    # evidence the tracker moved — hold everything frozen: last published
    # values stand, probabilities are NOT updated (a competitor must not
    # accumulate election lead from the incumbent's blind cycles), and no
    # other floor inherits incumbency by forfeit. Only a disappearance
    # longer than the grace lapses the incumbency, and then the best solved
    # floor is adopted on its merits.
    if incumbent is not None and incumbent not in solved \
            and incumbent in _floor_probability.get(entity, {}):
        dark = _floor_dark_cycles.get(entity, 0) + 1
        if dark <= FLOOR_DARK_GRACE_CYCLES:
            _floor_dark_cycles[entity] = dark
            return
        incumbent = None  # dark beyond grace: incumbency lapses
    _floor_dark_cycles.pop(entity, None)
    probs = _update_floor_probabilities(
        entity, {f: s["conf"] for f, s in solved.items()}, valid_floors
    )
    lowest_floor_name, challenge = _elect_floor(
        probs, incumbent, solved, _floor_challenge.get(entity)
    )
    if challenge is None:
        _floor_challenge.pop(entity, None)
    else:
        _floor_challenge[entity] = challenge
    if lowest_floor_name is None:
        return  # nothing electable this cycle: keep last values

    if update_trilateration_and_zone.last_floor.get(entity) != lowest_floor_name:
        # The Kalman state holds pixel coordinates in the previously elected
        # floor's map space; it must not carry over to the newly elected floor.
        _kf_position_state.pop(entity, None)
        update_trilateration_and_zone.last_floor[entity] = lowest_floor_name

    elected = solved[lowest_floor_name]
    weighted = elected["weighted"]
    zone_polys = elected["zone_polys"]
    floor_bounds = elected["bounds"]
    scale = elected["scale"]
    tricords = elected["fix"]

    if tricords is not None:
        # Constant-velocity Kalman smoothing of the published position. The RAW
        # trilaterated fix feeds the filter (so the estimate is never biased by
        # the zone snapping applied below); the filtered output is clipped to the
        # floor bounds inside the helper.
        avg_x, avg_y = _kalman_position_update(
            entity, lowest_floor_name, tricords, scale, floor_bounds
        )

        # A fix outside every zone is physically implausible (BLE noise pushed
        # it into a wall or off the apartment): publish the nearest point on
        # the zone union instead. Snapping is applied to the filter OUTPUT only;
        # the filter state keeps the raw fix, so smoothing is not biased toward
        # the boundary.
        test_point = Point(float(avg_x), float(avg_y))
        snapped = snap_point_into_zones(zone_polys, test_point)
        if snapped is not None:
            test_point = snapped
            avg_x, avg_y = float(snapped.x), float(snapped.y)
        zone = find_zone_for_point(new_global_data, entity, lowest_floor_name, test_point)
        nearest_zone = find_nearest_zone(new_global_data, entity, lowest_floor_name, test_point)
        sub_zone, sub_parent = find_sub_zone_for_point(new_global_data, entity, lowest_floor_name, test_point)
        # parent_zone always names the enclosing main zone: the sub-zone's
        # declared parent when inside one, otherwise the current main zone.
        parent_zone = sub_parent if sub_parent else zone
        apitricords = update_or_add_entry(
            apitricords,
            {
                "ent": entity,
                "cords": [avg_x, avg_y],
                "zone": zone,
                "floor": lowest_floor_name,
                # The exact solver input (post-correction, post-filter), for
                # the panel's trilateration circles.
                "radii": [[float(px), float(py), float(pr)] for (px, py, pr, _w) in weighted],
                # Smoothed floor-election probabilities, for debugging "why
                # did it pick this floor" (issue #94).
                "floors": {f: round(p, 3) for f, p in probs.items()},
                # Positioning telemetry for the eval harness (tools/bps_eval.py)
                # and the debug tab: the pre-Kalman, pre-snap trilaterated fix
                # next to the published (filtered + snapped) `cords`, so solver
                # bias can be told apart from filter lag; plus this fix's
                # weighted RMS residual (m) and the elected floor's confidence.
                # Both frontends read named fields, so these keys are inert.
                "raw": [round(float(tricords[0]), 2), round(float(tricords[1]), 2)],
                "rms_m": round(elected["rms_m"], 3),
                "conf": round(elected["conf"], 3),
                "updated": time.time(),
            },
        )
        await update_apitricords(hass, apitricords)
        update_bps_sensor_state(hass, f"sensor.{entity}_bps_zone", zone)
        update_bps_sensor_state(hass, f"sensor.{entity}_bps_nearest_zone", nearest_zone)
        update_bps_sensor_state(hass, f"sensor.{entity}_bps_floor", lowest_floor_name)
        update_bps_sensor_state(hass, f"sensor.{entity}_bps_sub_zone", sub_zone, {"parent_zone": parent_zone})

def update_or_add_entry(data, new_entry):
    for item in data:
        if item["ent"] == new_entry["ent"]:  # Check if "ent" already exists
            item["cords"] = new_entry["cords"]  # Update "cords"
            item["zone"] = new_entry["zone"]  # Update "zone"
            item["floor"] = new_entry["floor"]  # Floor the fix belongs to
            item["radii"] = new_entry["radii"]  # Solver input, for circles
            item["floors"] = new_entry["floors"]  # Election probabilities
            item["raw"] = new_entry["raw"]  # Pre-Kalman fix (telemetry)
            item["rms_m"] = new_entry["rms_m"]  # Fit residual, m (telemetry)
            item["conf"] = new_entry["conf"]  # Elected floor confidence
            item["updated"] = new_entry["updated"]  # Freshness for pruning
            return data

    # If "ent" was not found, add as new post
    data.append(new_entry)
    return data


async def prune_stale_positions(hass):
    """Drop trackers not detected by any receiver for the timeout period.

    Without this, a person who left home stayed on the map at their last
    position forever, and the zone/floor sensors kept the stale values.
    """
    global apitricords
    timeout = STALE_POSITION_SECS
    layout = get_bps_data(hass)
    if isinstance(layout, dict):
        configured = layout.get("position_timeout")
        if isinstance(configured, (int, float)) and configured > 0:
            timeout = configured

    now = time.time()
    stale_ents = {e["ent"] for e in apitricords if now - e.get("updated", now) > timeout}
    if not stale_ents:
        return
    apitricords = [e for e in apitricords if e["ent"] not in stale_ents]
    await update_apitricords(hass, apitricords)
    for ent in sorted(stale_ents):
        # Drop the Kalman state too: a returning tracker should re-seed fresh
        # rather than predict velocity across the whole absence. Same for the
        # whole election state — probabilities, pending challenge, and the
        # INCUMBENCY itself: it may well come back on another floor, and an
        # hours-stale incumbent must not enjoy hysteresis against it (with
        # freshly-reset probabilities the margin could pin the wrong floor
        # indefinitely). Jump-gate radii from before the absence are equally
        # meaningless.
        _kf_position_state.pop(ent, None)
        _floor_probability.pop(ent, None)
        _floor_challenge.pop(ent, None)
        _floor_dark_cycles.pop(ent, None)
        getattr(update_trilateration_and_zone, "last_floor", {}).pop(ent, None)
        getattr(update_trilateration_and_zone, "last_r_values", {}).pop(ent, None)
        _LOGGER.info("Tracker %s not seen for %ss; clearing its position", ent, timeout)
        update_bps_sensor_state(hass, f"sensor.{ent}_bps_zone", "unknown")
        update_bps_sensor_state(hass, f"sensor.{ent}_bps_floor", "unknown")
        update_bps_sensor_state(hass, f"sensor.{ent}_bps_nearest_zone", "unknown")
        update_bps_sensor_state(hass, f"sensor.{ent}_bps_sub_zone", "unknown", {"parent_zone": "unknown"})

async def update_apitricords(hass, new_data):
    """Update apitricords in hass.data"""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["apitricords"] = new_data


def update_bps_sensor_state(hass, entity_id, state, attributes=None):
    """Update state (and optional extra attributes) on a registered BPS SensorEntity."""
    sensors_cache = hass.data.get("bps_sensors")
    if not sensors_cache:
        return
    sensor = sensors_cache.get(entity_id)
    if sensor is None:
        return
    sensor._state = state
    if attributes is not None:
        sensor._attrs = attributes
    sensor.async_write_ha_state()

async def process_single_entity(hass, new_global_data, eids):
    """Process a single entity: first receivers, then trilateration"""
    await update_receiver_radii(hass, eids)  # Wait for the receivers to update
    await update_trilateration_and_zone(hass, new_global_data, eids["entity"])  # When it is complete → perform trilateration

async def process_entities(hass, new_global_data):
    """Process multiple entities in parallel, but ensure the correct order for each individual entity"""
    tasks = [process_single_entity(hass, new_global_data, eids) for eids in new_global_data]
    await asyncio.gather(*tasks)  # Run all entities in parallel, but maintain the correct internal order

def extract_candidate_floors(new_global_data, tmpentity):
    """Every floor hearing the tracker, ranked by its nearest receiver.

    Returns a list of {"name", "cords": [(x, y, r), ...], "placed", "nearest_m"}
    sorted by nearest_m. The ranking compares raw slant distances (meters),
    not radii: radii are scaled into each floor's own pixel space, so
    comparing them across floors would let the floor with the smallest scale
    win regardless of where the tracker actually is. Ties (the same receiver
    placed on several floors) keep the data file's floor order. Each floor's
    cords feed that floor's own candidate solve — cords from different floors
    live in different pixel coordinate systems and never mix.
    """
    candidates = []
    for entity in new_global_data:
        if entity["entity"] != tmpentity:
            continue
        for floor in entity["data"]["floor"]:
            nearest, cords = float("inf"), []
            for receiver in floor["receivers"]:
                distance = receiver.get("distance")
                if distance is None or "r" not in receiver.get("cords", {}):
                    continue
                nearest = min(nearest, distance)
                cords.append((receiver["cords"]["x"], receiver["cords"]["y"], receiver["cords"]["r"]))
            if cords:
                candidates.append({
                    "name": floor["name"],
                    "cords": cords,
                    "nearest_m": nearest,
                })
    candidates.sort(key=lambda c: c["nearest_m"])  # stable: file order breaks ties
    return candidates


def _score_floor_fit(fix, weighted, scale):
    """Score one candidate floor's solve. Returns (confidence, rms_m, coverage).

    Confidence blends how well the fix explains ALL of the floor's reporting
    receivers (weighted RMS residual, converted to metres so floors with
    different pixel scales compare fairly) with how many receivers corroborate
    it. Modelled on ESPresense's scenario confidence (fit quality + node
    coverage): the tracker's true floor tends to explain its whole receiver
    ensemble, while a wrong floor fits one loud through-slab reading and
    contradicts the rest.
    """
    x, y = fix
    n = len(weighted)
    num = den = 0.0
    for (xi, yi, ri, wi) in weighted:
        res = math.hypot(xi - x, yi - y) - ri
        num += wi * res * res
        den += wi
    rms_px = math.sqrt(num / den) if den > 0 else float("inf")
    # Reduced-chi-square-style correction: a 3-receiver floor fits the 2
    # position unknowns almost perfectly no matter what (a single residual
    # degree of freedom), which flatters exactly the floors with the least
    # evidence. Inflate by sqrt(n / (n - 2)) so fits compete on evidence.
    rms_px *= math.sqrt(n / max(n - 2.0, 1.0))
    rms_m = rms_px / scale if scale else rms_px
    quality = 1.0 / (1.0 + (rms_m / FLOOR_RESIDUAL_SCALE_M) ** 2)
    # Corroboration: how many receivers hear the tracker on this floor,
    # saturating at COVERAGE_TARGET_N. An absolute count, NOT a share of the
    # floor's placed receivers: a dead or unmatched placement must not
    # handicap its floor forever, and a tiny fully-reporting 3-receiver floor
    # must not out-cover a floor with 6 of 8 receivers reporting.
    coverage = min(1.0, n / COVERAGE_TARGET_N)
    return 0.5 * coverage + 0.5 * quality, rms_m, coverage


def _update_floor_probabilities(entity, scores, valid_floors=None):
    """Fold this cycle's per-floor confidences into smoothed probabilities.

    Each floor's probability moves 1-FLOOR_PROB_SMOOTHING of the way toward
    its share of this cycle's total confidence; floors with no data this
    cycle decay toward zero and are dropped once negligible, so the dict
    cannot grow unbounded. Floors no longer present in the data file
    (renamed/deleted) are dropped immediately — a ghost name must not hold
    probability mass nor appear in the published election. Returns a
    normalized copy.
    """
    probs = _floor_probability.setdefault(entity, {})
    if valid_floors is not None:
        for floor in [f for f in probs if f not in valid_floors]:
            del probs[floor]
    total = sum(scores.values())
    for floor in set(probs) | set(scores):
        target = (scores.get(floor, 0.0) / total) if total > 0 else 0.0
        probs[floor] = FLOOR_PROB_SMOOTHING * probs.get(floor, 0.0) \
            + (1.0 - FLOOR_PROB_SMOOTHING) * target
    for floor in [f for f, p in probs.items() if p < 0.01]:
        del probs[floor]
    norm = sum(probs.values())
    if norm > 0:
        for floor in probs:
            probs[floor] /= norm
    return dict(probs)


def _elect_floor(probs, incumbent, solved, challenge):
    """Pick the floor to publish. Returns (floor, challenge_state).

    The caller guarantees the incumbent is either solved this cycle or None
    (a dark incumbent is handled by the grace hold upstream, and one dark
    beyond the grace loses its standing entirely — incumbency is never
    transferred by forfeit, it lapses).

    A solved incumbent only loses to a challenger that leads its probability
    by FLOOR_SWITCH_MARGIN for FLOOR_SWITCH_CYCLES consecutive cycles
    (challenge_state carries the count between cycles). The small margin
    filters share noise, the dwell filters single-cycle geometry flukes, and
    together they cannot permanently dead-band a genuinely better floor the
    way a large margin alone would — floor flapping was the disease
    (issue #94), a stuck wrong floor must not be the cure.
    """
    contenders = {f: p for f, p in probs.items() if f in solved}
    if not contenders:
        return None, None
    best = max(contenders, key=contenders.get)
    if incumbent is None or incumbent not in contenders:
        return best, None  # no standing incumbent: adopt the best immediately
    if best == incumbent or contenders[best] - contenders[incumbent] < FLOOR_SWITCH_MARGIN:
        return incumbent, None
    count = challenge["count"] + 1 if challenge and challenge.get("floor") == best else 1
    if count >= FLOOR_SWITCH_CYCLES:
        return best, None
    return incumbent, {"floor": best, "count": count}

def _floor_zone_polygons(data, entity, floor_name):
    """Yield (zone entity_id, polygon, buffer_size, no_go) for the floor.

    no_go marks a zone a tracker can't be in (issue #60). Callers keep no-go
    zones for the solver bounds (they still bound the floor) but exclude them
    from zone assignment and snapping — a fix must never be reported as, or
    snapped into, dead space.
    """
    buffer_percent = 0.05  # set to 5%

    def order_zone_points(coords):
        """Order polygon points clockwise around centroid to avoid self-intersections.

        Only for legacy rectangle zones, whose four corners were stored in
        scan order. Polygon zones (poly: true) keep their drawn order — a
        centroid sort would corrupt concave shapes.
        """
        if len(coords) < 3:
            return coords
        center_x = sum(coord["x"] for coord in coords) / len(coords)
        center_y = sum(coord["y"] for coord in coords) / len(coords)
        return sorted(
            coords,
            key=lambda coord: np.arctan2(coord["y"] - center_y, coord["x"] - center_x)
        )

    for entity_data in data:
        if entity_data["entity"] == entity:
            for floor in entity_data["data"]["floor"]:
                if floor["name"] == floor_name:
                    for zone in floor["zones"]:
                        coords = zone.get("cords") or []
                        if len(coords) < 3:
                            continue
                        if not zone.get("poly") and len(coords) == 4:
                            coords = order_zone_points(coords)
                        polygon = Polygon([(coord["x"], coord["y"]) for coord in coords])
                        if not polygon.is_valid:
                            # Self-intersecting drawing; make_valid keeps every
                            # lobe (buffer(0) can drop one). Keep only the
                            # areal parts of the repair.
                            repaired = (
                                shapely_make_valid(polygon)
                                if shapely_make_valid
                                else polygon.buffer(0)
                            )
                            if repaired.geom_type == "GeometryCollection":
                                parts = [
                                    g for g in repaired.geoms
                                    if g.geom_type in ("Polygon", "MultiPolygon")
                                ]
                                repaired = unary_union(parts) if parts else None
                            if repaired is None or repaired.is_empty:
                                continue
                            polygon = repaired
                        xs = [coord["x"] for coord in coords]
                        ys = [coord["y"] for coord in coords]
                        width = max(xs) - min(xs)
                        height = max(ys) - min(ys)
                        buffer_size = ((width + height) / 2) * buffer_percent
                        yield zone["entity_id"], polygon, buffer_size, bool(zone.get("no_go"))


def _point_in_no_go(point, zone_polys):
    """True if the point falls strictly inside any no-go zone in zone_polys.

    zone_polys is the (zone_id, polygon, buffer_size, no_go) list from
    _floor_zone_polygons. Accepts a shapely Point or an (x, y) pair. Uses
    strict containment (not boundary-inclusive covers): a no-go zone's edge is
    typically a physical railing, and a tracker genuinely ON the walkway there
    sits on that boundary — it must not be penalised as if over the void.
    """
    if not isinstance(point, Point):
        point = Point(float(point[0]), float(point[1]))
    return any(no_go and polygon.contains(point)
               for _zone_id, polygon, _buffer_size, no_go in zone_polys)


def find_zone_for_point(data, entity, floor_name, point):
    """Find zone for point, prioritize correct polygon, select nearest buffer if no correct zone matches.

    No-go zones (issue #60) are skipped: a tracker can't be in one, so a fix
    there is reported as belonging to the nearest real zone (or "unknown").
    """
    buffer_candidates = []
    for zone_id, polygon, buffer_size, no_go in _floor_zone_polygons(data, entity, floor_name):
        if no_go:
            continue
        # covers() also matches points on the polygon boundary.
        if polygon.covers(point):
            return zone_id  # Prioritize correct polygon
        if polygon.buffer(buffer_size).contains(point):
            # Save candidate: (distance to edge, entity_id)
            # boundary works for Polygon and MultiPolygon alike.
            buffer_candidates.append((polygon.boundary.distance(point), zone_id))
    if buffer_candidates:
        # Select zone whose edge is closest to the point
        buffer_candidates.sort()
        return buffer_candidates[0][1]
    return "unknown"


def snap_point_into_zones(zone_polys, point):
    """Project a point onto valid (allowed, non-no-go) space.

    Returns the snapped Point, or None when the point is already in valid
    space (or there is nowhere valid to put it). No-go zones (issue #60) are
    subtracted from the allowed region — grown by NO_GO_SNAP_MARGIN_PX first —
    so a fix in dead space is pushed to the nearest genuinely-allowed point,
    clear of the boundary-inclusive no-go edge. This holds even when a no-go
    zone is drawn overlapping or nested inside an allowed room (subtraction
    carves the void out of the room), and when the floor's only zones are
    no-go (the point is at least pushed off the dead-space footprint).
    """
    allowed = [polygon for _zone_id, polygon, _buffer_size, no_go in zone_polys if not no_go]
    nogo = [polygon for _zone_id, polygon, _buffer_size, no_go in zone_polys if no_go]
    nogo_union = unary_union(nogo) if nogo else None
    nogo_blocks = nogo_union is not None and not nogo_union.is_empty

    valid = None
    if allowed:
        valid = unary_union(allowed)
        if nogo_blocks:
            # Grow-and-subtract: the snap target's boundary ends up
            # NO_GO_SNAP_MARGIN_PX outside the dead space, so the snapped point
            # is not still read as inside it by the boundary-inclusive tests.
            valid = valid.difference(nogo_union.buffer(NO_GO_SNAP_MARGIN_PX))

    if valid is not None and not valid.is_empty:
        if valid.covers(point):
            return None  # already in valid space
        snapped, _ = nearest_points(valid, point)
        return snapped

    # No allowed space to land in. If the point sits in declared dead space,
    # at least push it just off the no-go footprint; otherwise leave it as-is.
    if nogo_blocks and nogo_union.covers(point):
        snapped, _ = nearest_points(nogo_union.buffer(NO_GO_SNAP_MARGIN_PX).boundary, point)
        return snapped
    return None


def find_nearest_zone(data, entity, floor_name, point):
    """The zone closest to the point, no matter how far away.

    Trilateration jitter can land a fix between two zones or outside the map
    entirely; this always names the closest zone on the elected floor (a point
    inside a zone has distance 0, so it matches find_zone_for_point there).
    Returns "unknown" only when the floor has no usable zones.
    """
    nearest_id = "unknown"
    nearest_distance = None
    for zone_id, polygon, _buffer_size, no_go in _floor_zone_polygons(data, entity, floor_name):
        if no_go:
            continue  # dead space is never "the nearest zone" (issue #60)
        distance = polygon.distance(point)
        if nearest_distance is None or distance < nearest_distance:
            nearest_id, nearest_distance = zone_id, distance
    return nearest_id


def _floor_sub_zone_polygons(data, entity, floor_name):
    """Yield (sub-zone name, parent zone name, polygon) for the entity's floor.

    Sub-zones are small precise areas drawn inside a zone (a couch, a desk), so
    they are matched strictly (no soft buffer). They live in a separate
    "subzones" list, so the main-zone election/snap/nearest logic is untouched.
    """
    for entity_data in data:
        if entity_data["entity"] != entity:
            continue
        for floor in entity_data["data"]["floor"]:
            if floor["name"] != floor_name:
                continue
            # Sub-zones link to their parent by the zone's stable id; resolve it
            # to the zone's display name for the parent_zone attribute.
            zone_name_by_id = {}
            for z in floor.get("zones") or []:
                zone_name_by_id[z.get("zone_id") or z.get("entity_id")] = z.get("entity_id")
            for sub in floor.get("subzones") or []:
                coords = sub.get("cords") or []
                if len(coords) < 3:
                    continue
                polygon = Polygon([(c["x"], c["y"]) for c in coords])
                if not polygon.is_valid:
                    repaired = (
                        shapely_make_valid(polygon)
                        if shapely_make_valid
                        else polygon.buffer(0)
                    )
                    if repaired is None or repaired.is_empty:
                        continue
                    polygon = repaired
                parent_ref = sub.get("parent")
                yield sub.get("entity_id"), zone_name_by_id.get(parent_ref, parent_ref), polygon


def find_sub_zone_for_point(data, entity, floor_name, point):
    """The sub-zone containing the point and its parent zone name.

    Returns (sub_zone_name, parent_zone_name); ("unknown", None) when the point
    is in no sub-zone.
    """
    for sub_id, parent_id, polygon in _floor_sub_zone_polygons(data, entity, floor_name):
        if polygon.covers(point):
            return sub_id, parent_id
    return "unknown", None


async def async_setup(hass, config):
    """Set up the BPS integration."""
    _LOGGER.info("BPS integration initierad.")

    if hass.data.get("bps_initialized", False):
        _LOGGER.debug("BPS already initialized in current runtime; skipping duplicate init.")
        return True  # Abort if already running

    hass.data["bps_initialized"] = True  # Set flag

    async def initialize_bps():
        """Initialize the BPS component"""
        _LOGGER.info("Initializing BPS...")

        if "bps_views_registered" not in hass.data:
            hass.http.register_view(BPSFrontendView())
            hass.http.register_view(BPSSaveAPIText())
            hass.http.register_view(BPSMapsListAPI())
            hass.http.register_view(BPSTrackerIconsListAPI())
            hass.http.register_view(BPSUploadTrackerIconAPI())
            hass.http.register_view(BPSReadAPIText())
            hass.http.register_view(BPSAdjustZonesAPI())
            hass.http.register_view(BPSReceiverStatusAPI())
            hass.http.register_view(BPSScannerLinkingAPI())
            hass.http.register_view(BPSCordsAPI(hass))
            hass.http.register_view(BPSCalibrationAPI())
            hass.data["bps_views_registered"] = True

        config_path = hass.config.path()
        target_dir = os.path.join(config_path, "www", "bps_maps")
        tracker_icons_dir = os.path.join(config_path, "www", "bps_icons")

        try:
            await aiofiles.os.makedirs(target_dir, exist_ok=True)
            _LOGGER.info(f"Folder {target_dir} has been created or already existed")
        except Exception as e:
            _LOGGER.error(f"Could not create the folder {target_dir}: {e}")
            return

        try:
            await aiofiles.os.makedirs(tracker_icons_dir, exist_ok=True)
            _LOGGER.info(f"Folder {tracker_icons_dir} has been created or already existed")
        except Exception as e:
            _LOGGER.error(f"Could not create the folder {tracker_icons_dir}: {e}")
            return

        show_sidebar_panel = True
        if hasattr(config, "options"):
            show_sidebar_panel = config.options.get(OPTION_SHOW_SIDEBAR_PANEL, True)
        else:
            entries = hass.config_entries.async_entries(DOMAIN)
            if entries:
                show_sidebar_panel = entries[0].options.get(OPTION_SHOW_SIDEBAR_PANEL, True)
        panels = hass.data.get("frontend_panels", {})
        if "bps" in panels:
            async_remove_panel(hass, "bps")

        if show_sidebar_panel:
            try:
                _LOGGER.debug("Registering the custom panel for BPS...")
                # A custom panel (not a bare iframe) so the panel element
                # receives `hass` and can hand the app an HA access token to
                # authenticate its /api/bps/* calls (those views now require
                # auth). The element (bps-panel.js) still hosts the existing
                # app in an inner iframe and only couriers the token in.
                await panel_custom.async_register_panel(
                    hass,
                    frontend_url_path="bps",
                    webcomponent_name="bps-panel",
                    module_url="/bps/bps-panel.js",
                    sidebar_title="BPS",
                    sidebar_icon="mdi:map",
                    require_admin=False,
                    embed_iframe=False,
                )
                _LOGGER.info("Panel registered successfully.")
            except Exception as e:
                _LOGGER.error(f"Failed to register panel: {e}")
        else:
            _LOGGER.info("BPS sidebar panel is disabled by integration options.")

        # Move any legacy www/bps_maps flat files into the Store (once), then
        # load the layout into the in-memory cache. Store writes are atomic, so
        # a crash can no longer leave a 0-byte layout (issue #104).
        await migrate_legacy(hass)
        await load_bps_data(hass)

        jinja_code = """
        {{
            states.sensor
            | selectattr("entity_id", "search", "_distance_to_")
            | map(attribute="entity_id")
            | unique
            | list
        }}
        """

        old_task = hass.data.get("bps_update_task")
        if old_task:
            old_task.cancel()
        hass.data["bps_update_task"] = hass.async_create_task(update_tracked_entities(hass, jinja_code))

        async def handle_homeassistant_stop(event):
            """Stop background work promptly so shutdown cannot drag or leave
            the unload half-done (which strands stale registry entries)."""
            update_task = hass.data.pop("bps_update_task", None)
            if update_task:
                update_task.cancel()
            await async_shutdown_calibration(hass)

        hass.bus.async_listen_once("homeassistant_stop", handle_homeassistant_stop)

        await async_restore_calibration_state(hass)
        await async_start_auto_if_enabled(hass)

        _LOGGER.info("The BPS integration is fully initialized")

    async def handle_homeassistant_started(event):
        """Handles the 'homeassistant_started' event"""
        await initialize_bps()

    if hass.is_running:
        await initialize_bps()
    else:
        hass.bus.async_listen_once("homeassistant_started", handle_homeassistant_started)

    return True

async def async_unload_entry(hass: HomeAssistant, entry):
    """Remove a configuration entry"""
    _LOGGER.info("Attempting to offload platforms for entry: %s", entry.entry_id)

    state_listener_unsub = hass.data.pop("bps_state_listener_unsub", None)
    if state_listener_unsub:
        state_listener_unsub()

    cleanup_legacy_bps_registry_and_states(hass)

    entity_registry = er.async_get(hass)

    # Find and remove all entities that belong to "bps"
    entities_to_remove = [
        entity.entity_id for entity in entity_registry.entities.values()
        if entity.platform == "bps"
    ]

    for entity_id in entities_to_remove:
        _LOGGER.info(f"Removes sensor: {entity_id}")
        entity_registry.async_remove(entity_id)

    try: # Attempt to unload platforms
        unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    except Exception as e:
        _LOGGER.error(f"Error during offloading of platforms for entry {entry.entry_id}: {e}")
        return False

    if not unload_ok:
        _LOGGER.error("Failed to offload platforms for entry: %s", entry.entry_id)
        return False

    try: #Remove the frontend panel
        async_remove_panel(hass, frontend_url_path="bps")
        _LOGGER.info("Frontend-panel removed for entry: %s", entry.entry_id)
    except Exception as e:
        _LOGGER.error(f"Error when removing frontend-panel for entry {entry.entry_id}: {e}")
        return False

    update_task = hass.data.pop("bps_update_task", None)
    if update_task:
        update_task.cancel()

    await async_shutdown_calibration(hass)

    # Remove BPS states from the state machine when integration is unloaded.
    bps_state_ids = [
        state.entity_id
        for state in hass.states.async_all()
        if state.entity_id.startswith("sensor.")
        and state.entity_id.endswith(("_bps_zone", "_bps_floor", "_bps_nearest_zone", "_bps_sub_zone"))
    ]
    for entity_id in bps_state_ids:
        hass.states.async_remove(entity_id)

    # Allow clean setup after integration reload/removal.
    hass.data.pop("bps_initialized", None)
    hass.data.pop("bps_sensors", None)

    return True


async def async_setup_entry(hass, entry):
    """Set the integration from a configuration entry"""
    _LOGGER.info("async_setup_entry called")
    cleanup_legacy_bps_registry_and_states(hass)
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    """Set up BPS from a config entry."""
    return await async_setup(hass, entry)


async def async_update_options(hass, entry):
    """Reload integration when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)

class BPSFrontendView(HomeAssistantView):
    """Serve the frontend files."""

    url = "/bps/{file_name}"
    name = "bps:frontend"
    requires_auth = False

    async def get(self, request, file_name):
        """Serve static files from the frontend folder."""
        frontend_path = FRONTEND_PATH / file_name

        _LOGGER.info(f"Serving file: {frontend_path}")

        if not frontend_path.is_file():
            _LOGGER.error(f"Requested file not found: {frontend_path}")
            return web.Response(status=404, text="File not found")

        response = web.FileResponse(path=str(frontend_path))
        # The panel's script.js/CSS change on every integration update. Without
        # an explicit directive, browsers cache these heuristically and keep
        # serving the old panel after an update. "no-cache" keeps the cached
        # copy but forces revalidation (a cheap 304 when unchanged, the new file
        # when it changed), so updates show up on a normal reload.
        response.headers["Cache-Control"] = "no-cache"
        # bps-panel.js is loaded as an ES module (panel_custom), and browsers
        # refuse a module served with a non-JS MIME type. Force it rather than
        # trust the host's mimetypes registry (a Windows HA host can map .js to
        # text/plain, which would silently blank the panel).
        if file_name.endswith(".js"):
            response.headers["Content-Type"] = "text/javascript"
        return response

class BPSSaveAPIText(HomeAssistantView):
    """Handle saving of BPS coordinates to a text file."""

    url = "/api/bps/save_text"
    name = "api:bps:save_text"
    requires_auth = True

    async def post(self, request):
        """Handle saving coordinates to a text file."""
        hass = request.app["hass"]
        data = await request.post()

        coordinates = data.get("coordinates")

        if not coordinates:
            return web.Response(status=400, text="Missing coordinates")
        # Reject a non-JSON layout blob before it can reach the store.
        try:
            coords_obj = json.loads(coordinates)
        except (ValueError, TypeError):
            return web.Response(status=400, text="Coordinates must be valid JSON")

        maps_path = hass.config.path("www/bps_maps")

        try: # Persist the layout to the store + handle map upload/removal
            # Serialized with the calibration writers so read-modify-write
            # cycles on the layout cannot interleave.
            async with BPS_FILE_LOCK:
                error = await self._write_save(hass, maps_path, data, coords_obj)
            if error is not None:
                return error
            # A calibration window may be sampling right now; hand it the
            # edited placements so a re-linked/added receiver starts matching
            # on the next dump instead of after the next window/solve cycle.
            refresh_receivers_from_coords(hass, coordinates)
            _LOGGER.info(f"Saved coordinates to bpsdata: {coordinates}")
            return web.Response(status=200, text="Coordinates saved successfully")

        except Exception as e:
            _LOGGER.error(f"Failed to save coordinates: {e}")
            return web.Response(status=500, text="Failed to save coordinates")

    async def _write_save(self, hass, maps_path, data, coords_obj):
        """Validate all inputs, THEN persist; returns an error Response or None.

        Ordering matters: the new-floor map upload and the removal target are
        validated (and the upload read + size-checked) BEFORE the layout is
        saved, so a rejected upload can no longer strand the saved layout.
        Every filesystem target derived from client input is constrained to
        maps_path via _safe_maps_child (audit #2: path traversal / arbitrary
        write+delete). The layout goes to the Store (atomic); only the map
        images live under maps_path.
        """
        # --- Validate the optional new-floor map upload ---
        map_target = None
        map_bytes = None
        if data.get("new_floor") == "true":
            map_file = data.get("file")
            if not map_file:
                return web.Response(status=400, text="Missing file")
            map_target = _safe_maps_child(maps_path, map_file.filename, _ALLOWED_MAP_EXTS)
            if map_target is None:
                return web.Response(status=400, text="Invalid map filename")
            map_bytes = map_file.file.read()
            if len(map_bytes) > MAX_MAP_UPLOAD_BYTES:
                return web.Response(status=413, text="Map file too large")

        # --- Validate the optional removal target ---
        # No extension allowlist here: a map stored under any earlier-accepted
        # extension must stay deletable (the allowlist is an UPLOAD guard, not a
        # reason to strand an existing floor). Containment still applies, and
        # the layout/calibration files are explicitly protected.
        remove_target = None
        remove_file = data.get("remove")
        if remove_file:
            remove_target = _safe_maps_child(maps_path, remove_file, None)
            if remove_target is None or remove_target.name in _PROTECTED_MAPS_FILES:
                return web.Response(status=400, text="Invalid remove target")

        # --- Inputs valid: persist. Map first (so the saved layout never names
        # a map that failed to write), then the layout, then delete the old map. ---
        if map_target is not None:
            try:
                async with aiofiles.open(map_target, "wb") as f:
                    await f.write(map_bytes)
            except Exception as e:
                _LOGGER.error(f"Failed to save maps: {e}")
                return web.Response(status=500, text="Failed to save maps")

        await save_bps_data(hass, coords_obj)

        # Never delete the map we just wrote (a replace with the same filename).
        if remove_target is not None and remove_target != map_target and remove_target.exists():
            try:
                remove_target.unlink()
                _LOGGER.info(f"Removed file: {remove_target.name}")
            except Exception as e:
                _LOGGER.error(f"Failed to remove file {remove_target.name}: {e}")
                return web.Response(status=500, text="Failed to remove file")
        return None


class BPSAdjustZonesAPI(HomeAssistantView):
    """Propose a cleaned-up set of zones (square boxy rooms, snap shared
    boundaries incl. T-junctions, remove overlaps, re-clamp sub-zones).

    Pure-geometry PREVIEW: computes and returns a proposal plus a per-zone
    change report; it does NOT save. The panel renders the proposal, lets the
    user accept/reject, then persists via the existing save_text endpoint.
    """

    url = "/api/bps/adjust_zones"
    name = "api:bps:adjust_zones"
    requires_auth = True

    async def post(self, request):
        hass = request.app["hass"]
        try:
            body = await request.json()
        except Exception:
            return web.Response(status=400, text="Invalid JSON body")
        if not isinstance(body, dict):
            return web.Response(status=400, text="Body must be a JSON object")
        target = "subzones" if body.get("target") == "subzones" else "zones"
        zones = body.get("zones") or []
        subzones = body.get("subzones") or []
        options = body.get("options") or {}
        if not isinstance(zones, list):
            zones = []
        if not isinstance(subzones, list):
            subzones = []
        if not isinstance(options, dict):
            options = {}
        if target == "subzones":
            if not subzones:
                return web.Response(status=400, text="No sub-zones to adjust")
        elif not zones:
            return web.Response(status=400, text="No zones to adjust")
        func = adjust_subzones if target == "subzones" else adjust_zones
        try:
            # shapely work is synchronous; keep it off the event loop.
            result = await hass.async_add_executor_job(func, zones, subzones, options)
        except Exception as e:
            _LOGGER.error(f"adjust_zones ({target}) failed: {e}")
            return web.Response(status=500, text="Zone adjustment failed")
        return web.json_response(result)


class BPSReadAPIText(HomeAssistantView):
    """Return the stored BPS layout plus the tracked-device / receiver lists."""

    url = "/api/bps/read_text"
    name = "api:bps:read_text"
    requires_auth = True

    async def get(self, request):
        hass = request.app["hass"]
        # Both the tracked devices and their receivers come from the same
        # Bermuda "_distance_to_" sensors — the device is the part before
        # "_distance_to_", the receiver (scanner) the part after. Filtering to
        # Bermuda's own sensors keeps look-alike sensors from other integrations
        # out of both the tracked-device list and the receiver picker.
        entities = []
        receivers = []
        try:
            allowed = _bermuda_distance_sensor_ids(hass)
            entities = sorted({eid[len("sensor."):].split("_distance_to_")[0] for eid in allowed})
            receivers = sorted({eid.split("_distance_to_", 1)[1] for eid in allowed})
        except Exception as e:
            _LOGGER.info(f"Error listing Bermuda distance sensors: {e}")

        # Offline scanners come from the Bermuda-liveness poller (proximity-
        # independent), refreshed on a slower cadence by the background loop.
        offline_receivers = list(hass.data.get(DOMAIN, {}).get("rl_offline", []))

        try:
            # The layout now lives in the Store; a fresh install has none, and
            # the frontend's `if (data.coordinates)` guard expects "" (not "[]")
            # in that case so it never JSON.parses an empty layout.
            layout = get_bps_data(hass)
            content = json.dumps(layout) if layout else ""
            return web.json_response({
                "coordinates": content,
                "entities": entities,
                "receivers": receivers,
                "offline_receivers": offline_receivers,
                # Naming-mismatch diagnostics (issue #64): placed receivers whose
                # slug has no Bermuda distance sensor, and reporting scanners not
                # placed anywhere.
                "scanner_diagnostics": _scanner_diagnostics(hass, content),
            })

        except Exception as e:
            _LOGGER.error(f"Failed to read coordinates: {e}")
            return web.Response(status=500, text="Failed to read coordinates")

class BPSReceiverStatusAPI(HomeAssistantView):
    """Current offline receivers (Bermuda liveness), polled live by the panel."""
    url = "/api/bps/receiver_status"
    name = "api:bps:receiver_status"
    requires_auth = True

    async def get(self, request):
        hass = request.app["hass"]
        offline = hass.data.get(DOMAIN, {}).get("rl_offline", [])
        return web.json_response({"offline": list(offline)})


class BPSScannerLinkingAPI(HomeAssistantView):
    """On-demand debug view (issue #64): how each placed receiver links to its
    Bermuda distance sensors and whether each is reporting right now. Fetched
    live only when the panel's 'Scanner linking' section is expanded, so it
    never adds cost to a normal panel load or the tracking loop."""
    url = "/api/bps/scanner_linking"
    name = "api:bps:scanner_linking"
    requires_auth = True

    async def get(self, request):
        hass = request.app["hass"]
        # No placements to compare against is fine; still report the sensors.
        layout = get_bps_data(hass)
        content = json.dumps(layout) if layout else ""
        try:
            data = _scanner_linking(hass, content)
        except Exception as e:
            _LOGGER.error(f"scanner_linking failed: {e}")
            data = {"placed": [], "unplaced": []}
        try:
            data["beacons"] = _beacon_links(hass)
        except Exception as e:
            _LOGGER.error(f"beacon_links failed: {e}")
            data["beacons"] = []
        return web.json_response(data)


class BPSMapsListAPI(HomeAssistantView):
    """API to list map files in /www/bps_maps."""
    url = "/api/bps/maps"
    name = "api:bps:maps"
    requires_auth = True

    @staticmethod
    def _list_map_files(maps_path):
        """List map file names from disk (runs in executor)."""
        with os.scandir(maps_path) as entries:
            return [
                entry.name
                for entry in entries
                if entry.is_file() and entry.name.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
            ]

    async def get(self, request):
        """Return a list of map files as JSON."""
        hass = request.app["hass"]
        maps_path = hass.config.path("www/bps_maps")

        try:
            file_names = await hass.async_add_executor_job(self._list_map_files, maps_path)
            return web.json_response(file_names)
        except Exception as e:
            _LOGGER.error(f"Error listing map files: {e}")
            return web.Response(status=500, text="Error listing map files")


class BPSTrackerIconsListAPI(HomeAssistantView):
    """API to list tracker icon files."""

    url = "/api/bps/tracker_icons"
    name = "api:bps:tracker_icons"
    requires_auth = True

    @staticmethod
    def _list_tracker_icons(icons_path):
        if not os.path.isdir(icons_path):
            return []
        with os.scandir(icons_path) as entries:
            return [
                {"value": f"/local/bps_icons/{entry.name}", "label": entry.name}
                for entry in entries
                if entry.is_file() and entry.name.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".svg"))
            ]

    async def get(self, request):
        hass = request.app["hass"]
        icons_path = hass.config.path("www/bps_icons")
        try:
            custom_icons = await hass.async_add_executor_job(self._list_tracker_icons, icons_path)
            defaults = [
                {"value": "/bps/person.svg", "label": "Person (default)"},
                {"value": "/bps/beacon.svg", "label": "Beacon"},
            ]
            return web.json_response(defaults + custom_icons)
        except Exception as e:
            _LOGGER.error(f"Error listing tracker icons: {e}")
            return web.Response(status=500, text="Error listing tracker icons")


class BPSUploadTrackerIconAPI(HomeAssistantView):
    """API to upload custom tracker icons."""

    url = "/api/bps/upload_tracker_icon"
    name = "api:bps:upload_tracker_icon"
    requires_auth = True

    async def post(self, request):
        hass = request.app["hass"]
        data = await request.post()
        icon_file = data.get("icon")
        if not icon_file:
            return web.Response(status=400, text="Missing icon")

        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(icon_file.filename).name)
        if not safe_name:
            return web.Response(status=400, text="Invalid filename")

        icons_path = hass.config.path("www/bps_icons")
        try:
            await aiofiles.os.makedirs(icons_path, exist_ok=True)
            target_path = Path(icons_path) / safe_name
            async with aiofiles.open(target_path, "wb") as f:
                await f.write(icon_file.file.read())
        except Exception as e:
            _LOGGER.error(f"Failed to upload tracker icon: {e}")
            return web.Response(status=500, text="Failed to upload icon")

        return web.json_response({
            "icon_url": f"/local/bps_icons/{safe_name}",
            "icon_name": safe_name,
        })


class BPSCordsAPI(HomeAssistantView):
    """API endpoint that returns apitricords."""

    url = "/api/bps/cords"
    name = "api:bps:cords"
    requires_auth = True

    def __init__(self, hass):
        """Spara referens till hass"""
        self.hass = hass

    async def get(self, request):
        """Return apitricords from hass.data."""
        apitricords = self.hass.data.get(DOMAIN, {}).get("apitricords", {})

        if not apitricords:
            return web.json_response({"error": "No data available"}, status=404)

        return web.json_response(apitricords)

# Trilateration function
def trilaterate(known_points, bounds=None, min_weight_radius=1e-3):
    """Weighted least-squares position fit.

    known_points are (x, y, r) or (x, y, r, w) tuples. The optional w is a
    per-point reliability in [0, 1] (1 = fully trusted); it multiplies the
    geometric 1/r^2 weight, so a spiky reading pulls the fit less without being
    dropped. Missing w defaults to 1.

    bounds, when given as (minx, miny, maxx, maxy), constrains the solution to
    the floor's extent: the fit then finds the best position WITHIN the map,
    which lands on the boundary when an unconstrained fit would escape it.

    min_weight_radius clamps the radius used in the 1/r^2 WEIGHT (never the
    residual). Callers pass a physical floor in pixels (MIN_WEIGHT_RADIUS_M x
    floor scale): a near-zero radius — device at the receiver, or a slant range
    fully consumed by a known mount height — is an honest reading, but its
    weight must stay finite or that single receiver decides the whole fit. The
    default keeps the bare no-scale fallback safe against division by zero.
    """
    num_points = len(known_points)

    if num_points < 3: # Make sure there are enough points (min 3) to do a trilataration
        _LOGGER.error("At least three known points are required for trilateration.")
        return None

    def objective_function(X, known_points): # Define the objective function loss for the least squares method.
        x, y = X
        residuals = []
        weights = []
        for pt in known_points:
            xi, yi, ri = pt[0], pt[1], pt[2]
            wi = pt[3] if len(pt) > 3 else 1.0
            residuals.append(np.sqrt((xi - x)**2 + (yi - y)**2) - ri)
            weights.append(wi / max(ri, min_weight_radius)**2)  # reliability x geometric (1/r^2) weight
        return np.sqrt(np.array(weights)) * np.array(residuals)

    # Start from the receiver centroid: it is always a plausible position,
    # unlike the map corner, and it must lie inside any given bounds.
    x0 = np.array([
        float(np.mean([p[0] for p in known_points])),
        float(np.mean([p[1] for p in known_points])),
    ])
    if bounds is not None:
        minx, miny, maxx, maxy = bounds
        x0[0] = np.clip(x0[0], minx, maxx)
        x0[1] = np.clip(x0[1], miny, maxy)
        result = least_squares(
            objective_function, x0, args=(known_points,),
            bounds=([minx, miny], [maxx, maxy]),
        )
    else:
        result = least_squares(objective_function, x0, args=(known_points,)) # Perform weighting adjustment for the least squares method.

    if not result.success: # Check if the fitting was successful
        _LOGGER.error("Weighted nonlinear least squares fitting did not converge.")
        return None
    x, y = result.x # Extract the calculated coordinates
    return x, y # return the result
