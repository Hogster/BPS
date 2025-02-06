import aiofiles
import aiofiles.os
from pathlib import Path
from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.frontend import async_register_built_in_panel, async_remove_panel
from homeassistant.components.websocket_api import async_register_command, ActiveConnection, websocket_command
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.template import Template
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import numpy as np
from scipy.optimize import least_squares
import voluptuous as vol
import logging
import asyncio
import os
import json
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from shapely.geometry import Point, Polygon
from asyncio import Lock, Queue, wait_for, TimeoutError

_LOGGER = logging.getLogger(__name__)

DOMAIN = "bps"
FRONTEND_PATH = Path(__file__).parent / "frontend"

# Global data
global_data = []
state_change_lock = Lock()
state_change_counter = {}
update_queue = Queue()
tracked_listeners = {}
tracked_entities = []
new_global_data = {}
secToUpdate = 1
apitricords = []

class FileWatcher(FileSystemEventHandler):
    """A class to handle file changes"""
    def __init__(self, file_path, callback, hass: HomeAssistant):
        self.file_path = file_path
        self.callback = callback
        self.hass = hass  # Reference to the Home Assistant instance

    def on_modified(self, event):
        """Called when the file changes"""
        if event.src_path == self.file_path:
            asyncio.run_coroutine_threadsafe(self.callback(), self.hass.loop)

async def read_file(file_path):
    """Read data asynchronously from the file"""
    try:
        async with aiofiles.open(file_path, mode="r") as file:
            content = await file.read()
        return content
    except FileNotFoundError:
        _LOGGER.warning("File not found: %s", file_path)
        return ""
    except Exception as e:
        _LOGGER.error("Error reading file %s: %s", file_path, e)
        return ""

def setup_file_watcher(file_path, update_callback, hass: HomeAssistant):
    """Set up a file watcher to monitor changes"""
    event_handler = FileWatcher(file_path, update_callback, hass)
    observer = Observer()
    observer.schedule(event_handler, os.path.dirname(file_path), recursive=False)
    observer.start()
    return observer

async def update_global_data(file_path):
    """Update global_data with the contents of the file"""
    global global_data
    new_data = await read_file(file_path) 
    try:
        global_data = json.loads(new_data) if new_data else []

        _LOGGER.info("Updated global_data: %s", global_data)
    except json.JSONDecodeError as e:
        _LOGGER.error("Error parsing JSON data: %s", e)

async def update_tracked_entities(hass, jinja_code):
    """Update tracked_entities with the result of the Jinja code once per second."""
    global tracked_entities, tracked_listeners, global_data, new_global_data
    global secToUpdate
    while True:
        try:
            template = Template(jinja_code, hass)
            tracked_entities = template.async_render()

            num_points = len(tracked_entities)
            if num_points < 3: # There are no devices close enough to track, wait 10 seconds until try again
                _LOGGER.info("There are no devices present to track, sleep 10 seconds")
                await asyncio.sleep(10)
                continue  # Skip and start over
            
            cleaned = [item.split("_distance_to_")[0].replace("sensor.", "") for item in tracked_entities]
            unique_values = list(set(cleaned))
            new_global_data = [{"entity": ent, "data": global_data} for ent in unique_values]
            
            await process_entities(hass, new_global_data)

        except Exception as e:
            _LOGGER.info(f"Error executing Jinja code: {e}")

        await asyncio.sleep(secToUpdate)  # Run every X seconds, set timer in global variables

async def update_receiver_radii(hass, eids):
    """Update receiver 'r' values for an entity"""
    for floor in (f for f in eids["data"]["floor"] if f["scale"] is not None):
        for receiver in floor["receivers"]:
            entity_id = "sensor." + eids["entity"] + "_distance_to_" + receiver["entity_id"]
            rec_value = hass.states.get(entity_id)
            if rec_value is not None:
                try:
                    radius = floor["scale"] * float(rec_value.state)
                    receiver["cords"]["r"] = radius
                except ValueError:
                    #_LOGGER.info(f"Invalid numerical value: {rec_value.state}")
                    pass
            else:
                #_LOGGER.info(f"Entity had no value: {receiver['entity_id']}")
                pass

async def update_trilateration_and_zone(hass, new_global_data, entity):
    """Performs trilateration and updates sensors with zone and floor"""
    global apitricords
    lowest_floor_name, filtered_cords = extract_floor_and_receivers(new_global_data, entity)
    tricords = trilaterate(filtered_cords)
    if tricords is not None:
        test_point = Point(float(tricords[0]), float(tricords[1]))
        zone = find_zone_for_point(new_global_data, entity, lowest_floor_name, test_point)
        apitricords = update_or_add_entry(apitricords, {"ent": entity, "cords": tricords, "zone": zone})
        await update_apitricords(hass, apitricords)
        hass.states.async_set(f"sensor.{entity}_bps_zone", zone)
        hass.states.async_set(f"sensor.{entity}_bps_floor", lowest_floor_name)

def update_or_add_entry(data, new_entry):
    for item in data:
        if item["ent"] == new_entry["ent"]:  # Kolla om "ent" redan finns
            item["cords"] = new_entry["cords"]  # Uppdatera "cords"
            item["zone"] = new_entry["zone"]  # Uppdatera "zone"
            return data

    # Om "ent" inte hittades, lägg till som ny post
    data.append(new_entry)
    return data

async def update_apitricords(hass, new_data):
    """Uppdatera apitricords i hass.data"""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["apitricords"] = new_data

async def process_single_entity(hass, new_global_data, eids):
    """Process a single entity: first receivers, then trilateration"""
    await update_receiver_radii(hass, eids)  # Wait for the receivers to update
    await update_trilateration_and_zone(hass, new_global_data, eids["entity"])  # When it is complete → perform trilateration

async def process_entities(hass, new_global_data):
    """Process multiple entities in parallel, but ensure the correct order for each individual entity"""
    tasks = [process_single_entity(hass, new_global_data, eids) for eids in new_global_data]
    await asyncio.gather(*tasks)  # Run all entities in parallel, but maintain the correct internal order

def extract_floor_and_receivers(new_global_data, tmpentity):
    """Find lowest floor and filter receiver cords."""
    lowest_floor_name, lowest_r = None, float("inf")
    filtered_cords = []

    for entity in new_global_data:
        if entity["entity"] == tmpentity:
            for floor in entity["data"]["floor"]:
                for receiver in floor["receivers"]:
                    if "cords" in receiver and "r" in receiver["cords"]:
                        r_value = receiver["cords"]["r"]
                        if r_value < lowest_r:
                            lowest_r, lowest_floor_name = r_value, floor["name"]
                        if floor["name"] == lowest_floor_name:
                            filtered_cords.append(tuple(receiver["cords"].values()))
    return lowest_floor_name, filtered_cords

def find_zone_for_point(data, entity, floor_name, point):
    """Find the zone containing a point."""
    for entity_data in data:
        if entity_data["entity"] == entity:
            for floor in entity_data["data"]["floor"]:
                if floor["name"] == floor_name:
                    for zone in floor["zones"]:
                        polygon = Polygon([(coord["x"], coord["y"]) for coord in zone["cords"]])
                        if polygon.contains(point):
                            return zone["entity_id"]
    return "unknown"

async def async_setup(hass, config):
    """Set up the BPS integration."""
    _LOGGER.info("BPS integration initierad.")

    if hass.data.get("bps_initialized", False):
        _LOGGER.warning("BPS has already been initialized. Aborting")
        return True  # Abort if already running

    hass.data["bps_initialized"] = True  # Set flag

    async def initialize_bps():
        """Initialize the BPS component"""
        _LOGGER.info("Initializing BPS...")

        if "bps_views_registered" not in hass.data:
            hass.http.register_view(BPSFrontendView())
            hass.http.register_view(BPSSaveAPIText())
            hass.http.register_view(BPSMapsListAPI())
            hass.http.register_view(BPSReadAPIText())
            hass.http.register_view(BPSCordsAPI(hass))
            hass.data["bps_views_registered"] = True

        if "bps_websocket" not in hass.data:
            websocket = BPSEntityWebSocket(hass)
            websocket.register()
            hass.data["bps_websocket"] = websocket

        config_path = hass.config.path()
        target_dir = os.path.join(config_path, "www", "bps_maps")
        target_file = os.path.join(target_dir, "bpsdata.txt")

        try:
            await aiofiles.os.makedirs(target_dir, exist_ok=True)
            _LOGGER.info(f"Folder {target_dir} has been created or already existed")
        except Exception as e:
            _LOGGER.error(f"Could not create the folder {target_dir}: {e}")
            return

        panels = hass.data.get("frontend_panels", {})
        if "bps" in panels:
            async_remove_panel(hass, "bps")
        try:
            _LOGGER.debug("Registering the built-in panel for BPS...")
            async_register_built_in_panel(
                hass=hass,
                component_name="iframe",
                sidebar_title="BPS",
                sidebar_icon="mdi:map",
                frontend_url_path="bps",
                config={"url": "/bps/index.html"},
            )
            _LOGGER.info("Panel registered successfully.")
        except Exception as e:
            _LOGGER.error(f"Failed to register panel: {e}")

        try:
            if not os.path.exists(target_file):
                async with aiofiles.open(target_file, mode="w") as file:
                    await file.write("")  # Skapa en tom fil
                _LOGGER.info(f"File {target_file} has been created.")
            else:
                _LOGGER.info(f"File {target_file} already exist.")
        except Exception as e:
            _LOGGER.error(f"Could not create file {target_file}: {e}")

        await update_global_data(target_file)

        observer = setup_file_watcher(target_file, lambda: update_global_data(target_file), hass)

        jinja_code = """
        {{
            expand(states.sensor)
            | selectattr("entity_id", "search", "_distance_to_")
            | selectattr("state", "is_number")
            | map(attribute="entity_id")
            | unique
            | list
        }}
        """

        hass.async_create_task(update_tracked_entities(hass, jinja_code))

        hass.bus.async_listen_once("homeassistant_stop", lambda event: observer.stop())

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

    return True


async def async_setup_entry(hass, entry):
    """Set the integration from a configuration entry"""
    _LOGGER.info("async_setup_entry har anropats")
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    """Set up BPS from a config entry."""
    return await async_setup(hass, entry)

class BPSFrontendView(HomeAssistantView):
    """Serve the frontend files."""

    url = "/bps/{file_name}"
    name = "bps:frontend"
    requires_auth = False
    #requires_auth = True

    async def get(self, request, file_name):
        """Serve static files from the frontend folder."""
        frontend_path = FRONTEND_PATH / file_name

        _LOGGER.info(f"Serving file: {frontend_path}")

        if not frontend_path.is_file():
            _LOGGER.error(f"Requested file not found: {frontend_path}")
            return web.Response(status=404, text="File not found")

        return web.FileResponse(path=str(frontend_path))

class BPSSaveAPIText(HomeAssistantView):
    """Handle saving of BPS coordinates to a text file."""

    url = "/api/bps/save_text"
    name = "api:bps:save_text"
    requires_auth = False

    async def post(self, request):
        """Handle saving coordinates to a text file."""
        hass = request.app["hass"]
        data = await request.post()

        coordinates = data.get("coordinates")
        
        if not coordinates:
            return web.Response(status=400, text="Missing coordinates")
        
        # Define the path to the bpsdata file
        maps_path = hass.config.path("www/bps_maps")
        bpsdata_file_path = Path(maps_path) / "bpsdata.txt"
        
        try: # Save coordinates to the bpsdata file
            async with aiofiles.open(bpsdata_file_path, "w") as f:
                await f.write(coordinates)
                _LOGGER.warning(f"New file: {data.get("new_floor")}")
                if data.get("new_floor") == "true": # If it is a new floor then save the file
                    map_file = data.get("file")
                    if not map_file:
                        return web.Response(status=400, text="Missing file")
                    map_file_path = Path(maps_path) / map_file.filename
                    try:
                        async with aiofiles.open(map_file_path, "wb") as f:
                            await f.write(map_file.file.read())
                    except Exception as e:
                        _LOGGER.error(f"Failed to save maps: {e}")
                        return web.Response(status=500, text="Failed to save maps")
                    
                # Check if "remove" key exists and delete the specified file
                remove_file = data.get("remove")
                if remove_file:
                    remove_file_path = Path(maps_path) / remove_file
                    if remove_file_path.exists():
                        _LOGGER.warning(f"File exist: {remove_file_path}")
                        try:
                            remove_file_path.unlink()  # Delete the file
                            _LOGGER.info(f"Removed file: {remove_file_path}")
                        except Exception as e:
                            _LOGGER.error(f"Failed to remove file {remove_file_path}: {e}")
                            return web.Response(status=500, text="Failed to remove file")
               
            _LOGGER.info(f"Saved coordinates to bpsdata: {coordinates}")
            return web.Response(status=200, text="Coordinates saved successfully")
        
        except Exception as e:
            _LOGGER.error(f"Failed to save coordinates: {e}")
            return web.Response(status=500, text="Failed to save coordinates")
        
class BPSReadAPIText(HomeAssistantView):
    """Handle reading of BPS coordinates from a text file."""

    url = "/api/bps/read_text"
    name = "api:bps:read_text"
    requires_auth = False

    async def get(self, request):
        """Handle reading coordinates from the text file."""
        hass = request.app["hass"]
        maps_path = hass.config.path("www/bps_maps") # Define the path to the bpsdata file
        bpsdata_file_path = Path(maps_path) / "bpsdata.txt"
        entityjinja = """
        {{
            expand(states.sensor) 
            | selectattr("entity_id", "search", "_distance_to_")
            | map(attribute="entity_id")
            | map("replace", "sensor.", "")  
            | map("regex_replace", "_distance_to_.*", "")  
            | unique
            | list
        }}
        """

        try:
            template = Template(entityjinja, hass) # Render Jinja code
            entities = template.async_render()
        except Exception as e:
            _LOGGER.info(f"Error during the execution of the Jinja code: {e}")

        try:
            if not bpsdata_file_path.is_file(): # Check if the file exists
                return web.Response(status=404, text="bpsdata.txt not found")

            async with aiofiles.open(bpsdata_file_path, "r") as f: # Read the content of the file
                content = await f.read()

            _LOGGER.info(f"Read coordinates from bpsdata: {content}")
            return web.json_response({
                "coordinates": content,
                "entities": entities
            })
        
        except Exception as e:
            _LOGGER.error(f"Failed to read coordinates: {e}")
            return web.Response(status=500, text="Failed to read coordinates")

class BPSMapsListAPI(HomeAssistantView):
    """API to list map files in /www/bps_maps."""
    url = "/api/bps/maps"
    name = "api:bps:maps"
    requires_auth = False

    async def get(self, request):
        """Return a list of map files as JSON."""
        hass = request.app["hass"]
        maps_path = hass.config.path("www/bps_maps")

        try:
            files = [
                f for f in os.scandir(maps_path) 
                if f.is_file() and f.name.lower().endswith(('.png', '.jpg'))
            ]
            file_names = [f.name for f in files]
            return web.json_response(file_names)
        except Exception as e:
            _LOGGER.error(f"Error listing map files: {e}")
            return web.Response(status=500, text="Error listing map files")
        
class BPSCordsAPI(HomeAssistantView):
    """API för att skicka tillbaka apitricords"""

    url = "/api/bps/cords"
    name = "api:bps:cords"
    requires_auth = False  # Ändra till True om du vill kräva autentisering

    def __init__(self, hass):
        """Spara referens till hass"""
        self.hass = hass

    async def get(self, request):
        """Returnera apitricords från hass.data"""
        apitricords = self.hass.data.get(DOMAIN, {}).get("apitricords", {})

        if not apitricords:
            return web.json_response({"error": "No data available"}, status=404)

        return web.json_response(apitricords)

class BPSEntityWebSocket:
    def __init__(self, hass):
        self.hass = hass
        self.tracked_entities = {}
        self.connections = []

    async def handle_subscribe(self, hass, connection: ActiveConnection, msg: dict):
        """Managing subscription for entities"""
        _LOGGER.debug(f"Received subscription request: {msg}")
        entity_ids = msg["entities"]
        if not entity_ids:
            connection.send_message({
                "id": msg["id"],
                "type": "result",
                "success": False,
                "error": {"code": "invalid_request", "message": "No entities provided."},
            })
            return

        self.connections.append(connection) # Add a connection to subscribed entities
        for entity_id in entity_ids:
            if entity_id not in self.tracked_entities:
                self.tracked_entities[entity_id] = []
            self.tracked_entities[entity_id].append(connection)

        current_states = [] # Send the current state for all subscribed entities
        for entity_id in entity_ids:
            state = hass.states.get(entity_id)
            if state:
                current_states.append({
                    "entity_id": entity_id,
                    "state": state.state,
                    "attributes": state.attributes,
                })

        connection.send_message({
            "id": msg["id"],
            "type": "result",
            "success": True,
            "message": f"Subscribed to entities: {entity_ids}",
            "current_states": current_states,  
        })
        async_track_state_change_event(hass, entity_ids, self.state_change_listener) # Listen for state_change


    async def handle_unsubscribe(self, hass, connection: ActiveConnection, msg: dict):
        """Managing unsubscription"""
        _LOGGER.debug(f"Received unsubscribe request: {msg}")
        entity_ids = msg.get("entities", [])
        for entity_id in entity_ids:
            if entity_id in self.tracked_entities:
                if connection in self.tracked_entities[entity_id]:
                    self.tracked_entities[entity_id].remove(connection)
                if not self.tracked_entities[entity_id]:
                    del self.tracked_entities[entity_id]

        connection.send_message({
            "id": msg["id"],
            "type": "result",
            "success": True,
            "message": f"Unsubscribed from entities: {entity_ids}",
        })

    async def handle_known_points(self, hass, connection: ActiveConnection, msg: dict):
        try:
            known_points = msg.get("knownPoints") # Read knownPoints from the message
            if not known_points:
                connection.send_message({
                    "id": msg["id"],
                    "type": "tri_result",
                    "success": False,
                    "error": {"code": "invalid_request", "message": "No knownPoints provided."}
                })
                return

            result = trilaterate(known_points) # Perform trilateration

            if result is None: # If the result is None, return an error
                connection.send_message({
                    "id": msg["id"],
                    "type": "tri_result",
                    "success": False,
                    "error": {"code": "calculation_error", "message": "Trilateration failed."}
                })
                return

            connection.send_message({ # Send back the result
                "id": msg["id"],
                "type": "tri_result",
                "success": True,
                "result": {
                    "x": result[0],
                    "y": result[1]
                }
            })

        except Exception as e:
            _LOGGER.error(f"Error processing knownPoints: {e}")
            connection.send_message({
                "id": msg["id"],
                "type": "tri_result",
                "success": False,
                "error": {"code": "server_error", "message": str(e)}
            })

    async def state_change_listener(self, event):
        """Listens for status changes and sends them to connections."""
        entity_id = event.data.get("entity_id")
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")

        _LOGGER.debug(f"State change for {entity_id}: {old_state} -> {new_state}")

        # Create the message to send to subscribing clients
        message = {
            "type": "state_changed",
            "entity_id": entity_id,
            "old_state": old_state.state if old_state else None,
            "new_state": new_state.state if new_state else None,
        }

        # Send to all connected clients who are subscribed to this entity
        for connection in self.tracked_entities.get(entity_id, []):
            connection.send_message(message)


    def register(self):
        """Registers WebSocket commands"""
        _LOGGER.debug("Registering WebSocket commands")

        def subscribe_wrapper(hass, connection, msg):
            """Wrapper to invoke handle_subscribe."""
            hass.async_create_task(self.handle_subscribe(hass, connection, msg))
        def unsubscribe_wrapper(hass, connection, msg):
            """Wrapper to invoke handle_unsubscribe."""
            hass.async_create_task(self.handle_unsubscribe(hass, connection, msg))
        def known_points_wrapper(hass, connection, msg):
            """Wrapper to invoke handle_known_points."""
            hass.async_create_task(self.handle_known_points(hass, connection, msg))

        async_register_command(
            self.hass,
            "bps/subscribe",
            subscribe_wrapper,  # The wrapper handles async
            schema=vol.Schema({
                vol.Required("type"): "bps/subscribe", # Type for API
                vol.Required("entities"): [str],
                vol.Optional("id"): int,
            }),
        )
        async_register_command(
            self.hass,
            "bps/unsubscribe",
            unsubscribe_wrapper,  # The wrapper handles async
            schema=vol.Schema({
                vol.Required("type"): "bps/unsubscribe", # Type for API
                vol.Required("entities"): [str],
                vol.Optional("id"): int,
            }),
        )
        async_register_command(
            self.hass,
            "bps/known_points",
            known_points_wrapper,  # The wrapper handles async
            schema=vol.Schema({
                vol.Required("type"): "bps/known_points",  # Type for API
                vol.Required("knownPoints"): vol.All(
                    list,
                    [vol.All([float, float, float])]  
                ),
                vol.Optional("id"): int,  
                }),
        )

        _LOGGER.info("All WebSocket commands registered successfully.")
    
# Trilateration function
def trilaterate(known_points):
    num_points = len(known_points)

    if num_points < 3: # Make sure there are enough points (min 3) to do a trilataration
        _LOGGER.error("At least three known points are required for trilateration.")
        return None

    def objective_function(X, known_points): # Define the objective function loss for the least squares method.
        x, y = X
        residuals = []
        for xi, yi, ri in known_points:
            residual = np.sqrt((xi - x)**2 + (yi - y)**2) - ri
            residuals.append(residual)
        weights = 1.0 / np.array([ri**2 for _, _, ri in known_points])
        return np.sqrt(weights) * np.array(residuals)

    x0 = np.array([0, 0]) # Initial guess value for unknown coordinates

    result = least_squares(objective_function, x0, args=(known_points,)) # Perform weighting adjustment for the least squares method.

    if not result.success: # Check if the fitting was successful
        _LOGGER.error("Weighted nonlinear least squares fitting did not converge.")
        return None
    x, y = result.x # Extract the calculated coordinates
    return x, y # return the result