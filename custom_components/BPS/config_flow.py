from homeassistant import config_entries
from homeassistant.core import callback
import logging
import voluptuous as vol
from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Definiera vilka inställningar användaren kan ange
CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required("hass_token"): str,
        vol.Required("hassURL"): str,
        vol.Optional("update_interval", default=1): int,
    }
)

class BPSConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BPS."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            return self.async_create_entry(title="BLE Positioning System", data={})

        return self.async_show_form(step_id="user")
