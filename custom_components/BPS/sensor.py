from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
import logging

_LOGGER = logging.getLogger(__name__)

DOMAIN = "bps_sensors"

def get_filtered_entities(hass):
    """Fetch and filter sensors based on their entity_id"""
    sensors = [state for state in hass.states.async_all() if state.entity_id.startswith("sensor.")]
    filtered = [
        state.entity_id.replace("sensor.", "").split("_distance_to_")[0]
        for state in sensors
        if "_distance_to_" in state.entity_id
    ]
    return list(set(filtered))

class CustomDistanceSensor(SensorEntity):
    """A representation of a custom sensor"""
    def __init__(self, name, unique_id):
        self._name = name
        self._unique_id = unique_id
        self._state = "unknown"
    
    @property
    def name(self):
        return self._name
    
    @property
    def unique_id(self):
        return self._unique_id
    
    @property
    def state(self):
        return self._state

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set dynamic sensors based on the filtered entities"""
    _LOGGER.info("async_setup_entry in sensor.py has been called")
    
    if "bps_sensors" not in hass.data:
        hass.data["bps_sensors"] = {}

    entities = get_filtered_entities(hass)
    _LOGGER.info(f"Creating sensors for entities: {entities}")

    existing_sensors = {state.entity_id for state in hass.states.async_all() if state.entity_id.startswith("sensor.")}

    new_sensors = []
    for entity in entities:
        unique_zone_id = f"sensor.{entity}_bps_zone"
        unique_floor_id = f"sensor.{entity}_bps_floor"

        if not any(s.startswith(unique_zone_id) for s in existing_sensors):
            sensor = CustomDistanceSensor(f"{entity} BPS Zone", unique_zone_id)
            hass.data["bps_sensors"][unique_zone_id] = sensor
            new_sensors.append(sensor)

        if not any(s.startswith(unique_floor_id) for s in existing_sensors):
            sensor = CustomDistanceSensor(f"{entity} BPS Floor", unique_floor_id)
            hass.data["bps_sensors"][unique_floor_id] = sensor
            new_sensors.append(sensor)

    if new_sensors:
        async_add_entities(new_sensors, update_before_add=True)

    @callback
    def state_changed_listener(event):
        """Listen for state changes to update dynamic sensors"""
        new_entities = get_filtered_entities(hass)
        new_sensors = []

        existing_sensors = {state.entity_id for state in hass.states.async_all() if state.entity_id.startswith("sensor.")}

        for entity in new_entities:
            unique_zone_id = f"sensor.{entity}_bps_zone"
            unique_floor_id = f"sensor.{entity}_bps_floor"

            if not any(s.startswith(unique_zone_id) for s in existing_sensors):
                sensor = CustomDistanceSensor(f"{entity} BPS Zone", unique_zone_id)
                hass.data["bps_sensors"][unique_zone_id] = sensor
                new_sensors.append(sensor)

            if not any(s.startswith(unique_floor_id) for s in existing_sensors):
                sensor = CustomDistanceSensor(f"{entity} BPS Floor", unique_floor_id)
                hass.data["bps_sensors"][unique_floor_id] = sensor
                new_sensors.append(sensor)

        if new_sensors:
            async_add_entities(new_sensors, update_before_add=True)

    hass.bus.async_listen("state_changed", state_changed_listener)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """If using configuration in configuration.yaml"""
    await async_setup_entry(hass, config, async_add_entities)
