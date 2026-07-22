from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
import logging

_LOGGER = logging.getLogger(__name__)

DOMAIN = "bps_sensors"

# (entity_id suffix / unique_id prefix, display label) per tracked device.
SENSOR_KINDS = [
    ("bps_zone", "BPS Zone"),
    ("bps_floor", "BPS Floor"),
    ("bps_nearest_zone", "BPS Nearest Zone"),
    ("bps_sub_zone", "BPS Sub-Zone"),
]


def find_bermuda_via_device(hass, entity):
    """Identifier of the Bermuda device that owns this tracker's distance_to
    sensors, so the BPS device can nest under it (via_device). None when it
    can't be resolved (e.g. Bermuda not loaded yet) — the BPS device then just
    stands on its own.
    """
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    prefix = f"sensor.{entity}_distance_to_"
    for e in ent_reg.entities.values():
        if e.platform == "bermuda" and e.device_id and e.entity_id.startswith(prefix):
            dev = dev_reg.async_get(e.device_id)
            if dev and dev.identifiers:
                # Prefer a bermuda identifier so the link points at the tracker
                # device even if it carries identifiers from several integrations.
                berm = [i for i in dev.identifiers if i[0] == "bermuda"]
                return berm[0] if berm else next(iter(dev.identifiers))
    return None


def ensure_sensors_for_entity(hass, entity, sensors_cache, new_sensors):
    """Create any missing BPS sensors for a tracked device.

    Only the in-memory cache decides whether a sensor exists. A registry
    entry without a live entity object is exactly the situation to recover
    from: it survives a reboot whenever the previous shutdown could not run
    the unload cleanly, and skipping creation for it would leave the sensor
    permanently dead (updates are dropped when the cache has no object).
    async_add_entities re-claims the registry entry via unique_id.
    """
    # Resolve the Bermuda parent (a full entity-registry scan) ONLY when a
    # sensor actually needs creating. In steady state every sensor is already
    # cached, so this returns before touching the registry — the old
    # unconditional scan here ran on every state_changed event and stalled HA
    # (issue #51).
    missing = [(suffix, label) for suffix, label in SENSOR_KINDS
               if f"sensor.{entity}_{suffix}" not in sensors_cache]
    if not missing:
        return
    via_device = find_bermuda_via_device(hass, entity)
    for suffix, label in missing:
        entity_id = f"sensor.{entity}_{suffix}"
        sensor = CustomDistanceSensor(f"{entity} {label}", f"{suffix}_{entity}", entity_id, entity, via_device)
        sensors_cache[entity_id] = sensor
        new_sensors.append(sensor)


def is_legacy_bps_entity_id(entity_id):
    """Detect old duplicated-name entity IDs like sensor.name_name_bps_floor."""
    if not entity_id.startswith("sensor.") or "_bps_" not in entity_id:
        return False

    if not (entity_id.endswith("_bps_floor") or entity_id.endswith("_bps_zone")):
        return False

    object_id = entity_id.replace("sensor.", "")
    base_name = object_id.rsplit("_bps_", 1)[0]
    parts = base_name.split("_")

    # Legacy format duplicates the full object id: <name>_<name>
    if len(parts) % 2 != 0:
        return False

    half = len(parts) // 2
    return parts[:half] == parts[half:]

def get_filtered_entities(hass):
    """Tracked-device slugs from Bermuda's per-scanner distance sensors.

    Only entities from the `bermuda` integration count. Other integrations also
    expose `_distance_to_` sensors (e.g. an ESPHome mmWave presence sensor's
    `..._distance_to_detection_object`); those aren't trackers and must not get
    BPS zone/floor sensors or a device.
    """
    ent_reg = er.async_get(hass)
    filtered = set()
    for state in hass.states.async_all():
        eid = state.entity_id
        if not (eid.startswith("sensor.") and "_distance_to_" in eid):
            continue
        entry = ent_reg.async_get(eid)
        if entry is None or entry.platform != "bermuda":
            continue
        filtered.add(eid.replace("sensor.", "").split("_distance_to_")[0])
    return list(filtered)

class CustomDistanceSensor(SensorEntity):
    """A representation of a custom sensor"""
    def __init__(self, name, unique_id, entity_id, device_key=None, via_device=None):
        self._name = name
        self._unique_id = unique_id
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._state = "unknown"
        self._attrs = {}
        self.entity_id = entity_id
        # Group each tracked device's BPS sensors under their own device rather
        # than one shared "BLE Positioning System" bucket. All four sensors for
        # a tracked device share the same identifier, so they land together, and
        # via_device nests that device under its Bermuda tracker device.
        if device_key:
            info = DeviceInfo(
                identifiers={("bps", device_key)},
                name=f"{device_key} (BPS)",
                manufacturer="BPS",
                model="BLE Positioning System",
            )
            if via_device:
                info["via_device"] = via_device
            self._attr_device_info = info

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        # Used by the sub-zone sensor to carry "parent_zone"; empty for the rest.
        return self._attrs

def cleanup_legacy_bps_entities(hass):
    """Remove old duplicated-name BPS entities from entity registry."""
    entity_registry = er.async_get(hass)
    stale_entities = [
        entry.entity_id
        for entry in entity_registry.entities.values()
        if is_legacy_bps_entity_id(entry.entity_id)
    ]

    for entity_id in stale_entities:
        _LOGGER.info("Removing legacy BPS entity: %s", entity_id)
        entity_registry.async_remove(entity_id)

    cleanup_legacy_bps_states(hass)


def cleanup_legacy_bps_states(hass):
    """Remove lingering legacy states from the state machine."""
    legacy_state_ids = [
        state.entity_id
        for state in hass.states.async_all()
        if is_legacy_bps_entity_id(state.entity_id)
    ]
    for entity_id in legacy_state_ids:
        _LOGGER.info("Removing legacy BPS state: %s", entity_id)
        hass.states.async_remove(entity_id)


def normalize_bps_registry_entity_ids(hass, entities):
    """Ensure BPS registry entries use stable non-legacy entity_id by unique_id."""
    entity_registry = er.async_get(hass)
    expected_by_uid = {}
    for entity in entities:
        for suffix, _label in SENSOR_KINDS:
            expected_by_uid[f"{suffix}_{entity}"] = f"sensor.{entity}_{suffix}"

    for entry in list(entity_registry.entities.values()):
        expected_entity_id = expected_by_uid.get(entry.unique_id)
        if expected_entity_id and entry.entity_id != expected_entity_id:
            _LOGGER.info(
                "Migrating BPS entity_id from %s to %s",
                entry.entity_id,
                expected_entity_id,
            )
            try:
                entity_registry.async_update_entity(
                    entry.entity_id,
                    new_entity_id=expected_entity_id,
                )
            except ValueError:
                # If the target id is blocked by stale data/entry, remove old entry and recreate.
                _LOGGER.info("Removing conflicting BPS registry entity: %s", entry.entity_id)
                entity_registry.async_remove(entry.entity_id)


def normalize_bps_registry_entity_ids_from_cache(hass):
    """Normalize BPS entity_ids using the in-memory sensor cache unique_ids."""
    sensors_cache = hass.data.get("bps_sensors", {})
    if not sensors_cache:
        return

    expected_by_uid = {}
    for expected_entity_id, sensor in sensors_cache.items():
        uid = getattr(sensor, "unique_id", None)
        if uid and expected_entity_id.startswith("sensor."):
            expected_by_uid[uid] = expected_entity_id

    if not expected_by_uid:
        return

    entity_registry = er.async_get(hass)
    for entry in list(entity_registry.entities.values()):
        expected_entity_id = expected_by_uid.get(entry.unique_id)
        if expected_entity_id and entry.entity_id != expected_entity_id:
            _LOGGER.info(
                "Post-add migration of BPS entity_id from %s to %s",
                entry.entity_id,
                expected_entity_id,
            )
            try:
                entity_registry.async_update_entity(
                    entry.entity_id,
                    new_entity_id=expected_entity_id,
                )
            except ValueError:
                _LOGGER.info("Removing conflicting BPS registry entity: %s", entry.entity_id)
                entity_registry.async_remove(entry.entity_id)

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set dynamic sensors based on the filtered entities"""
    _LOGGER.info("async_setup_entry in sensor.py has been called")
    
    if "bps_sensors" not in hass.data:
        hass.data["bps_sensors"] = {}

    cleanup_legacy_bps_entities(hass)

    entities = get_filtered_entities(hass)
    _LOGGER.info(f"Creating sensors for entities: {entities}")
    normalize_bps_registry_entity_ids(hass, entities)

    expected_entity_ids = set()
    for entity in entities:
        for suffix, _label in SENSOR_KINDS:
            expected_entity_ids.add(f"sensor.{entity}_{suffix}")

    # Remove stale BPS registry entries that are no longer expected.
    entity_registry = er.async_get(hass)
    if expected_entity_ids:
        stale_bps_ids = [
            entry.entity_id
            for entry in entity_registry.entities.values()
            if entry.platform == "bps" and entry.entity_id not in expected_entity_ids
        ]
        for entity_id in stale_bps_ids:
            _LOGGER.info("Removing stale BPS registry entity: %s", entity_id)
            entity_registry.async_remove(entity_id)

    new_sensors = []
    for entity in entities:
        ensure_sensors_for_entity(hass, entity, hass.data["bps_sensors"], new_sensors)

    if new_sensors:
        async_add_entities(new_sensors, update_before_add=True)
        normalize_bps_registry_entity_ids_from_cache(hass)

    @callback
    def state_changed_listener(event):
        """Create BPS sensors when a NEW distance sensor appears.

        This is bound to the GLOBAL state bus, so it fires for every entity's
        every state change in all of HA (the busiest event there is). It must be
        O(1) for the overwhelming majority of those events. Only a newly-ADDED
        ``sensor.*_distance_to_*`` entity (``old_state`` is None) can introduce a
        new tracker; the constant value-updates of existing distance sensors and
        every unrelated entity are skipped cheaply. Without this filter the
        handler ran a full states + entity-registry scan on every state change
        and stalled the event loop (issue #51).
        """
        sensors_cache = hass.data.get("bps_sensors")
        if sensors_cache is None:
            # Integration is unloading/reloading; ignore late state events.
            return

        entity_id = event.data.get("entity_id") or ""
        if "_distance_to_" not in entity_id or event.data.get("old_state") is not None:
            return

        new_entities = get_filtered_entities(hass)
        new_sensors = []

        for entity in new_entities:
            ensure_sensors_for_entity(hass, entity, sensors_cache, new_sensors)

        if new_sensors:
            async_add_entities(new_sensors, update_before_add=True)
            normalize_bps_registry_entity_ids_from_cache(hass)

    old_unsub = hass.data.pop("bps_state_listener_unsub", None)
    if old_unsub:
        old_unsub()
    hass.data["bps_state_listener_unsub"] = hass.bus.async_listen("state_changed", state_changed_listener)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """If using configuration in configuration.yaml"""
    await async_setup_entry(hass, config, async_add_entities)
