"""Zone link suggestions (pure helpers, no HA)."""
from bps.zone_links import (
    best_area, build_zone_links, links_for_zone, name_matches, similarity,
)

AREAS = [
    {"area_id": "kok", "name": "Kök", "aliases": ["Kitchen"]},
    {"area_id": "matsal", "name": "Matsal", "aliases": []},
    {"area_id": "vardagsrum", "name": "Livingroom", "aliases": []},
]
MEDIA = [
    {"entity_id": "media_player.kitchen_speaker", "name": "Kitchen", "area_id": "kok"},
    {"entity_id": "media_player.sonos_3", "name": "Sonos 3", "area_id": "matsal"},
    {"entity_id": "media_player.livingroom_tv", "name": "Frame", "area_id": None},
]
PRES = [
    {"entity_id": "sensor.camera_dinigroom_person_count", "name": "Cam", "area_id": None},
    {"entity_id": "binary_sensor.office_presence", "name": "Office mmWave", "area_id": None},
]
CANDS = {"media_players": MEDIA, "presence_sensors": PRES}


def test_similarity_tolerates_typos_and_separators():
    assert similarity("Diningroom", "camera_dinigroom_person_count") >= 0.84
    assert similarity("Kitchen", "media_player.kitchen_speaker") == 1.0
    assert similarity("Office", "media_player.kitchen_speaker") < 0.84
    assert similarity("Up", "anything") == 0.0  # too short to match on


def test_best_area_uses_aliases_and_prefers_exact():
    assert best_area("Kitchen", AREAS)[0] == "kok"
    assert best_area("Livingroom", AREAS) == ("vardagsrum", 1.0)
    assert best_area("Garage", AREAS)[0] is None


def test_name_matches_sorted_and_filtered():
    m = name_matches("Diningroom", PRES)
    assert [x["entity_id"] for x in m] == ["sensor.camera_dinigroom_person_count"]
    assert name_matches("Bathroom", MEDIA) == []


def test_build_zone_links_keeps_saved_links_and_suggests():
    layout = {"floor": [{"name": "First", "zones": [
        {"entity_id": "Kitchen", "zone_id": "z1", "area_id": "kok",
         "media_players": ["media_player.kitchen_speaker"]},
        {"entity_id": "Diningroom", "zone_id": "z2"},
    ]}]}
    out = build_zone_links(layout, AREAS, CANDS)
    k, d = out["zones"]
    assert k["area_id"] == "kok" and k["suggested_area_id"] is None
    assert k["media_players"] == ["media_player.kitchen_speaker"]
    assert d["area_id"] is None
    assert d["name_matches"]["presence_sensors"][0]["entity_id"].endswith("dinigroom_person_count")
    assert out["candidates"] is CANDS


def test_links_for_zone_by_normalized_name():
    layout = {"floor": [{"name": "F", "zones": [
        {"entity_id": "Main entrance", "presence_sensors": ["binary_sensor.x"]}]}]}
    assert links_for_zone(layout, "main_entrance")["presence_sensors"] == ["binary_sensor.x"]
    assert links_for_zone(layout, "nope") == {"area_id": None, "media_players": [], "presence_sensors": [], "lights": []}
    assert links_for_zone([], "x")["media_players"] == []


def test_presence_filter_skips_non_person_detections():
    from bps.zone_links import _is_presence
    assert _is_presence("binary_sensor.camera_kitchen_person_occupancy", "occupancy", None)
    assert not _is_presence("binary_sensor.camera_kitchen_cat_occupancy", "occupancy", None)
    assert not _is_presence("binary_sensor.camera_kitchen_all_occupancy", "occupancy", None)
    assert _is_presence("binary_sensor.office_mmwave", "presence", None)
    assert not _is_presence("binary_sensor.door", "door", None)
    assert _is_presence("sensor.camera_kitchen_person_count", None, None)
