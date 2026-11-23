"""Zone links: which HA area, media players and presence sensors belong to a zone.

A zone stores its links on the zone object in the layout:

    {"entity_id": "Kitchen", "zone_id": "...", "area_id": "kok",
     "media_players": ["media_player.kitchen_speaker"],
     "presence_sensors": ["sensor.camera_kitchen_person_count"]}

What the user picked is always the source of truth. To make picking fast even
when naming is sloppy, this module also *suggests* links, from (best first):

  1. HA area — an entity (or its device) in the zone's linked area. When the
     zone has no area yet, the area whose name best matches the zone name is
     suggested; the panel filters candidates by area on the client, so
     changing the area in the dialog updates the area suggestions live.
  2. Name similarity — tolerant to case, separators and typos
     ("Dinigroom" ~ "diningroom", "kitchen" ~ "media_player.kitchen_sonos").

Nothing is linked automatically; the panel shows suggestions with their reason
and the user confirms. The pure helpers here take plain data so they can be
unit-tested without Home Assistant.
"""
from __future__ import annotations

import difflib
import re

NAME_MATCH_MIN = 0.84      # token-window similarity for a name suggestion
AREA_MATCH_MIN = 0.80      # zone name ~ area name/alias for an area suggestion

PRESENCE_DEVICE_CLASSES = ("occupancy", "presence")
# Object-detection occupancy sensors (Frigate: binary_sensor.<cam>_<label>_occupancy)
# for anything but people say nothing about who is in a room.
NON_PERSON_LABELS = ("all", "cat", "dog", "bird", "horse", "car", "bicycle",
                     "motorcycle", "boat", "bus", "license_plate", "package")
LINK_FIELDS = ("media_players", "presence_sensors")


def norm(text) -> str:
    """Lowercase alphanumerics only (keeps å/ä/ö etc.)."""
    return re.sub(r"[\W_]+", "", str(text or "").lower())


def _tokens(text) -> list[str]:
    return [t for t in re.split(r"[\W_]+", str(text or "").lower()) if t]


def similarity(zone_name, candidate) -> float:
    """How well a zone name matches a candidate string (0..1).

    1.0 when the normalized zone name is contained in the candidate; otherwise
    the best difflib ratio between the zone name and any run of 1-3 adjacent
    candidate tokens, so "camera_dinigroom_person_count" still matches
    "Diningroom" despite the typo.
    """
    zn = norm(zone_name)
    if len(zn) < 3:
        return 0.0
    cn = norm(candidate)
    if not cn:
        return 0.0
    if zn in cn:
        return 1.0
    toks = _tokens(candidate)
    best = 0.0
    for i in range(len(toks)):
        for j in range(i + 1, min(i + 3, len(toks)) + 1):
            r = difflib.SequenceMatcher(None, zn, "".join(toks[i:j])).ratio()
            if r > best:
                best = r
    return best


def best_area(zone_name, areas) -> tuple[str | None, float]:
    """The area (id) whose id/name/aliases best match the zone name."""
    best_id, best_score = None, 0.0
    for a in areas:
        for label in [a.get("area_id"), a.get("name")] + list(a.get("aliases") or []):
            s = similarity(zone_name, label) if label else 0.0
            # an exact name beats a containing one ("Kitchen" vs area
            # "Kitchen island")
            if s >= 1.0 and norm(label) != norm(zone_name):
                s = 0.9
            if s > best_score:
                best_id, best_score = a["area_id"], s
    if best_score < AREA_MATCH_MIN:
        return None, best_score
    return best_id, round(best_score, 2)


def name_matches(zone_name, candidates, min_score=NAME_MATCH_MIN) -> list[dict]:
    """Candidates whose entity id or friendly name resembles the zone name."""
    out = []
    for c in candidates:
        object_id = c["entity_id"].split(".", 1)[-1]
        s = max(similarity(zone_name, object_id), similarity(zone_name, c.get("name")))
        if s >= min_score:
            out.append({"entity_id": c["entity_id"], "score": round(s, 2)})
    out.sort(key=lambda m: -m["score"])
    return out


def iter_zones(layout):
    """(floor_name, zone) for every zone in the layout."""
    if not isinstance(layout, dict):
        return
    for floor in layout.get("floor") or []:
        for zone in floor.get("zones") or []:
            if isinstance(zone, dict) and zone.get("entity_id"):
                yield floor.get("name"), zone


def build_zone_links(layout, areas, candidates) -> dict:
    """Assemble the panel payload: saved links + suggestions per zone.

    areas:      [{"area_id", "name", "aliases"}]
    candidates: {"media_players": [...], "presence_sensors": [...]} where each
                item is {"entity_id", "name", "area_id"}.
    """
    zones = []
    for floor_name, zone in iter_zones(layout):
        name = zone["entity_id"]
        sugg_area, area_score = best_area(name, areas)
        entry = {
            "zone_id": zone.get("zone_id") or name,
            "name": name,
            "floor": floor_name,
            "area_id": zone.get("area_id"),
            "suggested_area_id": sugg_area if not zone.get("area_id") else None,
            "suggested_area_score": area_score if not zone.get("area_id") else None,
            "name_matches": {},
        }
        for field in LINK_FIELDS:
            entry[field] = [e for e in (zone.get(field) or []) if isinstance(e, str)]
            entry["name_matches"][field] = name_matches(name, candidates.get(field, []))
        zones.append(entry)
    return {"zones": zones, "areas": areas, "candidates": candidates}


def links_for_zone(layout, zone_name) -> dict:
    """The saved links of a zone by name (case/separator-insensitive)."""
    target = norm(zone_name)
    for _floor, zone in iter_zones(layout):
        if norm(zone["entity_id"]) == target:
            return {
                "area_id": zone.get("area_id"),
                **{f: list(zone.get(f) or []) for f in LINK_FIELDS},
            }
    return {"area_id": None, **{f: [] for f in LINK_FIELDS}}


# --- Home Assistant side ------------------------------------------------------

def _is_presence(entity_id, device_class, unit) -> bool:
    domain = entity_id.split(".", 1)[0]
    if domain == "binary_sensor":
        m = re.search(r"_([a-z]+(?:_plate)?)_occupancy$", entity_id)
        if m and m.group(1) in NON_PERSON_LABELS:
            return False
        return device_class in PRESENCE_DEVICE_CLASSES
    if domain == "sensor":
        # people counters (Frigate *_person_count, mmWave target counts)
        return entity_id.endswith("_person_count") or (unit or "").lower() in ("person", "persons", "people")
    return False


def collect_candidates(hass) -> tuple[list[dict], dict]:
    """HA areas + linkable entities (media players, presence sensors)."""
    from homeassistant.helpers import area_registry as ar
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import entity_registry as er

    area_reg = ar.async_get(hass)
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)

    areas = sorted(
        [{"area_id": a.id, "name": a.name, "aliases": sorted(a.aliases or [])}
         for a in area_reg.async_list_areas()],
        key=lambda a: a["name"].lower())

    def area_of(entity_id):
        ent = ent_reg.async_get(entity_id)
        if ent is None:
            return None
        if ent.area_id:
            return ent.area_id
        if ent.device_id:
            dev = dev_reg.async_get(ent.device_id)
            return dev.area_id if dev else None
        return None

    media, presence = [], []
    for st in hass.states.async_all(["media_player", "binary_sensor", "sensor"]):
        eid = st.entity_id
        item = {"entity_id": eid,
                "name": st.attributes.get("friendly_name") or eid,
                "area_id": area_of(eid)}
        if eid.startswith("media_player."):
            media.append(item)
        elif _is_presence(eid, st.attributes.get("device_class"),
                          st.attributes.get("unit_of_measurement")):
            presence.append(item)
    media.sort(key=lambda c: c["name"].lower())
    presence.sort(key=lambda c: c["name"].lower())
    return areas, {"media_players": media, "presence_sensors": presence}
