"""The Roku SoundBridge Display integration.

Exposes two services (see services.yaml for the full field list):
  soundbridge.send_text  - render text on the display (static or scrolling)
  soundbridge.clear      - clear the display / stop any running marquee

Both take a `device_id` target so multiple SoundBridge units can be
configured and addressed independently.
"""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .client import SoundBridgeClient, SoundBridgeError
from .const import (
    CONF_CLEAR,
    CONF_FONT,
    CONF_SCROLL,
    CONF_X,
    CONF_Y,
    DEFAULT_FONT,
    DEFAULT_X,
    DEFAULT_Y,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

SERVICE_SEND_TEXT = "send_text"
SERVICE_CLEAR = "clear"

SEND_TEXT_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): vol.All(cv.ensure_list, [cv.string]),
        vol.Required("message"): cv.string,
        vol.Optional(CONF_X, default=DEFAULT_X): cv.string,
        vol.Optional(CONF_Y, default=DEFAULT_Y): cv.string,
        vol.Optional(CONF_FONT, default=DEFAULT_FONT): vol.Coerce(int),
        vol.Optional(CONF_CLEAR, default=True): cv.boolean,
        vol.Optional(CONF_SCROLL, default=False): cv.boolean,
    }
)

CLEAR_SCHEMA = vol.Schema({vol.Required("device_id"): vol.All(cv.ensure_list, [cv.string])})


def _client_for_device(hass: HomeAssistant, device_id: str) -> SoundBridgeClient:
    """Resolve a device_id (from the device registry) to its client."""
    device_reg = dr.async_get(hass)
    device = device_reg.async_get(device_id)
    if device is None:
        raise HomeAssistantError(f"Unknown device_id: {device_id}")

    for entry_id in device.config_entries:
        client = hass.data.get(DOMAIN, {}).get(entry_id)
        if client is not None:
            return client

    raise HomeAssistantError(f"Device {device_id} is not a SoundBridge managed by this entry")


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the soundbridge.* services once, globally."""

    async def handle_send_text(call: ServiceCall) -> None:
        for device_id in call.data["device_id"]:
            client = _client_for_device(hass, device_id)
            try:
                await client.async_send_text(
                    call.data["message"],
                    x=call.data[CONF_X],
                    y=call.data[CONF_Y],
                    font=call.data.get(CONF_FONT),
                    clear=call.data[CONF_CLEAR],
                    scroll=call.data[CONF_SCROLL],
                )
            except SoundBridgeError as err:
                raise HomeAssistantError(f"SoundBridge send_text failed: {err}") from err

    async def handle_clear(call: ServiceCall) -> None:
        for device_id in call.data["device_id"]:
            client = _client_for_device(hass, device_id)
            try:
                await client.async_clear()
            except SoundBridgeError as err:
                raise HomeAssistantError(f"SoundBridge clear failed: {err}") from err

    if not hass.services.has_service(DOMAIN, SERVICE_SEND_TEXT):
        hass.services.async_register(
            DOMAIN, SERVICE_SEND_TEXT, handle_send_text, schema=SEND_TEXT_SCHEMA
        )
    if not hass.services.has_service(DOMAIN, SERVICE_CLEAR):
        hass.services.async_register(DOMAIN, SERVICE_CLEAR, handle_clear, schema=CLEAR_SCHEMA)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SoundBridge Display from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]

    client = SoundBridgeClient(host, port)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = client

    device_reg = dr.async_get(hass)
    device_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.unique_id or f"{host}:{port}")},
        manufacturer="Roku",
        model="SoundBridge",
        name=entry.title,
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return True
