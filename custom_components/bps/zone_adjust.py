"""Zone geometry cleanup for the BPS floor-plan editor ("Adjust zones").

Given a floor's zones — independent polygons drawn by hand in the 2000px panel
coordinate space, with no shared-edge topology — this proposes a cleaner plan:

  1. squares rooms that are already nearly rectilinear (leaves L-shaped and
     diagonal rooms alone),
  2. snaps near-coincident boundaries so neighbours share edges — both
     corner-to-corner clusters (T1) and a corner meeting the middle of a
     neighbour's wall (T2, by inserting a vertex into that wall),
  3. removes overlaps deterministically,

then re-clamps sub-zones into their (possibly moved) parents. It is PURE
geometry: it returns proposed zones + sub-zones + a per-zone change report and
never persists anything. Tolerances are conservative so genuine gaps (a real
gap between a closet and the next room) are left untouched.

Depends only on shapely + the standard library, so it is unit-testable off HA.
"""

import math

from shapely.geometry import Polygon, MultiPolygon, Point, LineString
from shapely.validation import make_valid
from shapely.ops import unary_union

# All lengths are in the panel's 2000px coordinate space.
DEFAULTS = {
    "tolerance": 22.0,        # max gap/overlap span that counts as "should be shared"
    "square": True,
    "square_angle_deg": 8.0,  # an edge within this of the room axis is treated as axis-aligned
    "aligned_frac_min": 0.85, # square only rooms this rectilinear...
    "rectfill_min": 0.90,     # ...and this close to filling their bounding rectangle
    "min_edge": 3.0,          # drop shorter edges as degenerate
}


# --------------------------------------------------------------------------- #
# Polygon <-> cords helpers
# --------------------------------------------------------------------------- #
def _ring(cords, poly_flag):
    """(x,y) list for a zone's outer ring, normalizing legacy 4-point order.

    Non-finite / unparseable points are dropped so one bad coordinate can't
    crash the whole adjust (the zone just falls back to pass-through if too few
    points survive).
    """
    pts = []
    for p in cords:
        try:
            x, y = float(p["x"]), float(p["y"])
        except (TypeError, ValueError, KeyError):
            continue
        if math.isfinite(x) and math.isfinite(y):
            pts.append((x, y))
    if not poly_flag and len(pts) == 4:
        # Legacy rectangles are stored TL,TR,BL,BR; reorder to a simple ring.
        pts = [pts[0], pts[1], pts[3], pts[2]]
    return pts


def _polygon(pts):
    pts = [(x, y) for (x, y) in pts if math.isfinite(x) and math.isfinite(y)]
    if len(pts) < 3:
        return None
    poly = Polygon(pts)
    if not poly.is_valid:
        poly = make_valid(poly)
    return _largest_polygon(poly)


def _largest_polygon(geom):
    """Reduce a (possibly Multi) geometry to its largest simple Polygon."""
    if geom is None or geom.is_empty:
        return None
    if isinstance(geom, Polygon):
        return geom
    polys = [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon) and not g.is_empty]
    if not polys:
        return None
    return max(polys, key=lambda g: g.area)


def _out_cords(poly):
    """Outer ring as [{x,y}], without the duplicated closing point."""
    ring = list(poly.exterior.coords)[:-1]
    return [{"x": round(x, 3), "y": round(y, 3)} for x, y in ring]


def _dedupe_ring(pts, min_edge):
    """Drop consecutive points closer than min_edge (degenerate edges)."""
    out = []
    for p in pts:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) >= min_edge:
            out.append(p)
    if len(out) >= 2 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) < min_edge:
        out.pop()
    return out


# --------------------------------------------------------------------------- #
# 1D / point clustering
# --------------------------------------------------------------------------- #
def _cluster_1d(values, tol):
    """Map each value to the mean of its run of within-tol neighbours (sorted)."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    result = [0.0] * len(values)
    group = []
    for k, idx in enumerate(order):
        if group and values[idx] - values[order[k - 1]] > tol:
            mean = sum(values[g] for g in group) / len(group)
            for g in group:
                result[g] = mean
            group = []
        group.append(idx)
    if group:
        mean = sum(values[g] for g in group) / len(group)
        for g in group:
            result[g] = mean
    return result


class _UnionFind:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


# --------------------------------------------------------------------------- #
# Squaring
# --------------------------------------------------------------------------- #
def _dominant_axis(poly):
    mrr = poly.minimum_rotated_rectangle
    rc = list(mrr.exterior.coords)
    return math.atan2(rc[1][1] - rc[0][1], rc[1][0] - rc[0][0])  # radians


def _is_boxy(poly, axis, cfg):
    pts = list(poly.exterior.coords)
    total = aligned = 0.0
    axdeg = math.degrees(axis) % 90
    for i in range(len(pts) - 1):
        dx = pts[i + 1][0] - pts[i][0]
        dy = pts[i + 1][1] - pts[i][1]
        length = math.hypot(dx, dy)
        total += length
        a = math.degrees(math.atan2(dy, dx)) % 90
        da = min(abs(a - axdeg), 90 - abs(a - axdeg))
        if da < cfg["square_angle_deg"]:
            aligned += length
    if total == 0:
        return False
    rectfill = poly.area / poly.minimum_rotated_rectangle.area
    return (aligned / total) >= cfg["aligned_frac_min"] and rectfill >= cfg["rectfill_min"]


def _square(poly, cfg):
    """Snap a rectilinear room's edges to its dominant axis. Returns (poly, did)."""
    axis = _dominant_axis(poly)
    if not _is_boxy(poly, axis, cfg):
        return poly, False
    cx, cy = poly.centroid.x, poly.centroid.y
    ext = list(poly.exterior.coords)[:-1]
    # Rotate into the room's own frame, cluster x's and y's (near-equal edges
    # become exactly axis-aligned), rotate back.
    ca, sa = math.cos(-axis), math.sin(-axis)
    rot = [((x - cx) * ca - (y - cy) * sa, (x - cx) * sa + (y - cy) * ca) for x, y in ext]
    xs = _cluster_1d([p[0] for p in rot], cfg["tolerance"])
    ys = _cluster_1d([p[1] for p in rot], cfg["tolerance"])
    cb, sb = math.cos(axis), math.sin(axis)
    out = [(cx + xs[i] * cb - ys[i] * sb, cy + xs[i] * sb + ys[i] * cb) for i in range(len(rot))]
    out = _dedupe_ring(out, cfg["min_edge"])
    sq = _polygon(out)
    if sq is None or sq.area < poly.area * 0.5:
        return poly, False  # squaring collapsed the room — keep the original
    return sq, True


# --------------------------------------------------------------------------- #
# Snapping (T1 corner clusters + T2 t-junctions)
# --------------------------------------------------------------------------- #
def _snap_boundaries(rings, cfg, fixed_mask=None):
    """Weld near-coincident boundaries across a set of rings.

    rings: list of [(x,y),...] outer rings. Returns new rings (same length).
    fixed_mask[i]=True marks ring i as a fixed reference (e.g. a parent wall):
    its vertices/edges are snap TARGETS but the ring is never moved and never
    gets a vertex inserted — so movers snap onto walls without the walls shifting.
    T1: cluster vertices from different rings within tolerance -> shared point.
    T2: a vertex near the interior of another ring's edge -> project onto it and
        (for a movable target ring) insert a matching vertex so it is shared.
    """
    if fixed_mask is None:
        fixed_mask = [False] * len(rings)
    tol = cfg["tolerance"]
    # Flat index of every vertex: (zone i, position k).
    index = [(i, k) for i, r in enumerate(rings) for k in range(len(r))]
    pos = {(i, k): rings[i][k] for (i, k) in index}

    # --- T1: cluster cross-zone vertices, but never merge two vertices of the
    #     SAME zone into one cluster — that would weld a room's own two corners
    #     to one point and silently drop part of the room. Weld nearest-first.
    uf = _UnionFind(len(index))
    comp_zones = {n: {index[n][0]} for n in range(len(index))}
    pairs = []
    for a in range(len(index)):
        ia, ka = index[a]
        for b in range(a + 1, len(index)):
            ib, kb = index[b]
            if ia == ib:
                continue
            (x1, y1), (x2, y2) = pos[(ia, ka)], pos[(ib, kb)]
            d = math.hypot(x1 - x2, y1 - y2)
            if d <= tol:
                pairs.append((d, a, b))
    for _d, a, b in sorted(pairs, key=lambda p: p[0]):
        ra, rb = uf.find(a), uf.find(b)
        if ra == rb or (comp_zones[ra] & comp_zones[rb]):
            continue  # already together, or merging would duplicate a zone
        uf.union(a, b)
        comp_zones[uf.find(a)] = comp_zones[ra] | comp_zones[rb]
    groups = {}
    for n in range(len(index)):
        groups.setdefault(uf.find(n), []).append(index[n])
    target = dict(pos)
    for members in groups.values():
        if len({ik[0] for ik in members}) < 2:  # need >=2 rings -> shared corner
            continue
        fixed_members = [ik for ik in members if fixed_mask[ik[0]]]
        if fixed_members:
            # Snap movers onto the fixed reference corner; don't move the wall.
            fx, fy = pos[fixed_members[0]]
        else:
            fx = sum(pos[ik][0] for ik in members) / len(members)
            fy = sum(pos[ik][1] for ik in members) / len(members)
        for ik in members:
            if not fixed_mask[ik[0]]:
                target[ik] = (fx, fy)

    # --- T2: vertex near the interior of another zone's edge ---------------- #
    inserts = {}  # ring i -> list of (edge_start_k, point) to insert
    for (i, k) in index:
        if fixed_mask[i]:
            continue  # a fixed reference vertex never moves
        if target[(i, k)] != pos[(i, k)]:
            continue  # already welded to a corner
        v = Point(pos[(i, k)])
        best = None
        for j, r in enumerate(rings):
            if j == i:
                continue
            for e in range(len(r)):
                a = r[e]
                b = r[(e + 1) % len(r)]
                seg = LineString([a, b])
                d = seg.distance(v)
                if d > tol:
                    continue
                proj = seg.project(v)
                if proj <= tol or proj >= seg.length - tol:
                    continue  # near an endpoint -> that's a T1 case, not T2
                if best is None or d < best[0]:
                    best = (d, j, e, seg.interpolate(proj))
        if best is not None:
            _, j, e, pt = best
            tp = (pt.x, pt.y)
            target[(i, k)] = tp
            if not fixed_mask[j]:  # never insert into a fixed reference ring
                inserts.setdefault(j, []).append((e, tp))

    # --- Rebuild rings: apply targets, then splice inserts ------------------ #
    new = [[target[(i, k)] for k in range(len(rings[i]))] for i in range(len(rings))]
    for j, items in inserts.items():
        # Insert each point after its edge-start, deepest offset first so
        # earlier insertions don't shift later indices within the same edge.
        by_edge = {}
        for e, pt in items:
            by_edge.setdefault(e, []).append(pt)
        ring = new[j]
        for e in sorted(by_edge, reverse=True):
            a = ring[e]
            pts = sorted(by_edge[e], key=lambda p: (p[0] - a[0]) ** 2 + (p[1] - a[1]) ** 2)
            for pt in reversed(pts):
                ring.insert(e + 1, pt)
    return [_dedupe_ring(r, cfg["min_edge"]) for r in new]


# --------------------------------------------------------------------------- #
# Overlap removal
# --------------------------------------------------------------------------- #
def _remove_overlaps(polys, order):
    """Subtract already-finalized zones from each subsequent zone (stable order),
    so the output has no overlaps. Larger zones keep contested boundaries."""
    finalized = []
    result = [None] * len(polys)
    union = None
    for idx in order:
        p = polys[idx]
        if p is None:
            continue
        if union is not None and p.intersects(union):
            p = _largest_polygon(make_valid(p.difference(union)))
        if p is None or p.is_empty:
            result[idx] = polys[idx]  # never drop a room; fall back to original
            continue
        result[idx] = p
        finalized.append(p)
        union = p if union is None else unary_union([union, p])
    return result


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
def _cfg(options):
    cfg = dict(DEFAULTS)
    if options:
        cfg.update({k: v for k, v in options.items() if v is not None})
    return cfg


def _load(items, warnings):
    """Parse each item's polygon; None (+ a warning) for anything unparseable."""
    orig = []
    for z in items:
        poly = _polygon(_ring(z.get("cords", []), z.get("poly")))
        if poly is None and z.get("cords"):
            warnings.append(f"Skipped '{z.get('entity_id')}' (invalid polygon).")
        orig.append(poly)
    return orig


def _build_out(items, orig, final_by_i, squared_by_i):
    """Output list (input dicts with updated cords) + a per-item change report."""
    out, changes = [], []
    for i, z in enumerate(items):
        if orig[i] is None:
            out.append(dict(z))  # unparseable -> passed through untouched
            continue
        final = final_by_i.get(i) or orig[i]
        nz = dict(z)
        nz["cords"] = _out_cords(final)
        nz["poly"] = True
        out.append(nz)
        changes.append({
            "id": z.get("zone_id") or z.get("sub_zone_id") or z.get("entity_id"),
            "name": z.get("entity_id"),
            "squared": bool(squared_by_i.get(i, False)),
            "max_move_px": round(_max_vertex_move(orig[i], final), 1),
            "area_change_pct": round((final.area - orig[i].area) / orig[i].area * 100, 1) if orig[i].area else 0.0,
            "vertices_before": len(orig[i].exterior.coords) - 1,
            "vertices_after": len(final.exterior.coords) - 1,
        })
    return out, changes


def _adjust_group(orig_polys, cfg, warnings, label_of, fixed_polys=None, clamp_polys=None):
    """Square + snap + de-overlap a set of movable polygons.

    fixed_polys: extra polygons used ONLY as snap targets (e.g. parent walls);
    never moved or returned. clamp_polys[i]: intersect mover i with this at the
    end (None skips). Returns (final_polys, squared_flags) aligned to orig_polys.
    """
    n = len(orig_polys)
    squared = [False] * n
    rings = [list(p.exterior.coords)[:-1] for p in orig_polys]
    if cfg["square"]:
        for i in range(n):
            sq, did = _square(orig_polys[i], cfg)
            squared[i] = did
            rings[i] = list(sq.exterior.coords)[:-1]

    fixed_rings = [list(p.exterior.coords)[:-1] for p in (fixed_polys or [])]
    snapped = _snap_boundaries(rings + fixed_rings, cfg,
                               [False] * n + [True] * len(fixed_rings))

    polys = []
    for i in range(n):
        cand = _polygon(snapped[i])
        # Keep the original if a snap would have collapsed/distorted the shape
        # (e.g. a pinch that make_valid split into lobes, keeping the largest).
        if cand is not None and cand.area >= orig_polys[i].area * 0.5:
            polys.append(cand)
        else:
            polys.append(orig_polys[i])
            warnings.append(f"'{label_of(i)}' left unchanged (adjust would have distorted it).")

    order = sorted(range(n), key=lambda i: polys[i].area, reverse=True)
    polys = _remove_overlaps(polys, order)
    polys = [polys[i] if polys[i] is not None else orig_polys[i] for i in range(n)]

    if clamp_polys:
        for i in range(n):
            cp = clamp_polys[i]
            if cp is None or cp.covers(polys[i]):
                continue
            clipped = _largest_polygon(make_valid(polys[i].intersection(cp)))
            if clipped is not None and not clipped.is_empty and clipped.area > 1:
                polys[i] = clipped
            else:
                warnings.append(f"'{label_of(i)}' falls outside its parent.")
    return polys, squared


# --------------------------------------------------------------------------- #
# Public entry points
# --------------------------------------------------------------------------- #
def adjust_zones(zones, subzones=None, options=None):
    """Clean up the MAIN zones (square boxy rooms, snap shared boundaries, remove
    overlaps). Sub-zones are returned unchanged — tidy them separately with
    adjust_subzones so the two are never actuated at once. Input is not mutated.
    """
    cfg = _cfg(options)
    subzones = subzones or []
    warnings = []
    orig = _load(zones, warnings)
    idxs = [i for i in range(len(zones)) if orig[i] is not None]
    finals, squared = _adjust_group(
        [orig[i] for i in idxs], cfg, warnings,
        lambda n: zones[idxs[n]].get("entity_id"),
    )
    final_by_i = {idxs[n]: finals[n] for n in range(len(idxs))}
    squared_by_i = {idxs[n]: squared[n] for n in range(len(idxs))}
    out_zones, changes = _build_out(zones, orig, final_by_i, squared_by_i)
    return {
        "zones": out_zones,
        "subzones": [dict(s) for s in subzones],
        "changes": changes,
        "warnings": warnings,
    }


def adjust_subzones(zones, subzones=None, options=None):
    """Clean up the SUB-zones, per parent: square them, snap them to their
    parent's walls and to each other, remove overlaps between siblings, and clamp
    each inside its parent. Main zones are returned unchanged. Not mutated.
    """
    cfg = _cfg(options)
    zones = zones or []
    subzones = subzones or []
    warnings = []

    parent_poly = {}
    for z in zones:
        p = _polygon(_ring(z.get("cords", []), z.get("poly")))
        if p is not None:
            parent_poly[z.get("zone_id") or z.get("entity_id")] = p

    orig = _load(subzones, warnings)
    idxs = [i for i in range(len(subzones)) if orig[i] is not None]
    groups = {}
    for i in idxs:
        groups.setdefault(subzones[i].get("parent"), []).append(i)

    final_by_i, squared_by_i = {}, {}
    for pid, members in groups.items():
        parent = parent_poly.get(pid)
        fixed = [parent] if parent is not None else None
        clamp = [parent] * len(members) if parent is not None else None
        finals, squared = _adjust_group(
            [orig[i] for i in members], cfg, warnings,
            lambda n, m=members: subzones[m[n]].get("entity_id"),
            fixed_polys=fixed, clamp_polys=clamp,
        )
        for n, i in enumerate(members):
            final_by_i[i] = finals[n]
            squared_by_i[i] = squared[n]

    out_subs, changes = _build_out(subzones, orig, final_by_i, squared_by_i)
    return {
        "zones": [dict(z) for z in zones],
        "subzones": out_subs,
        "changes": changes,
        "warnings": warnings,
    }


def _max_vertex_move(a, b):
    """Largest distance from an original vertex to the nearest new-boundary point."""
    bb = b.exterior
    return max((Point(p).distance(bb) for p in list(a.exterior.coords)[:-1]), default=0.0)
