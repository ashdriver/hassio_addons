"""Media player entity for a Roku SoundBridge.

The SoundBridge is a pull client, not a renderer: it has no DLNA/AirPlay/
Cast receiver and nothing can push audio at it. What it does have is
`PlayStation <url>` in its RCP sub-shell, which points it at an arbitrary
HTTP stream (the same mechanism as its internet-radio presets).

That is exactly the shape Music Assistant's Home Assistant player provider
needs - it hands a media player a stream URL and expects it to play it, and
filters out any entity that does not support play_media. So exposing
play_media here is what makes the SoundBridge selectable as a Music
Assistant target. Set that player's output codec to MP3 (Music Assistant's
default for HA players); this hardware predates FLAC streaming support.
"""
from __future__ import annotations

import logging

from homeassistant.components import media_source
from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    async_process_play_media_url,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .client import SoundBridgeClient, SoundBridgeError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# GetTransportState -> HA state. "Standby" is the device's soft-off.
_TRANSPORT_STATES = {
    "play": MediaPlayerState.PLAYING,
    "pause": MediaPlayerState.PAUSED,
    "stop": MediaPlayerState.IDLE,
    "standby": MediaPlayerState.OFF,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SoundBridge media player from a config entry."""
    client: SoundBridgeClient = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SoundBridgeMediaPlayer(client, entry)])


class SoundBridgeMediaPlayer(MediaPlayerEntity):
    """A SoundBridge exposed as a URL-playing speaker."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_media_content_type = MediaType.MUSIC
    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.NEXT_TRACK
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.BROWSE_MEDIA
    )

    def __init__(self, client: SoundBridgeClient, entry: ConfigEntry) -> None:
        self._client = client
        self._attr_unique_id = entry.unique_id or (
            f"{entry.data[CONF_HOST]}:{entry.data[CONF_PORT]}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            manufacturer="Roku",
            model="SoundBridge",
            name=entry.title,
        )

    # -- state ----------------------------------------------------------------

    async def async_update(self) -> None:
        """Poll transport state and volume."""
        try:
            state = await self._client.async_rcp_value("GetTransportState")
            self._attr_state = _TRANSPORT_STATES.get(
                (state or "").strip().lower(), MediaPlayerState.IDLE
            )

            volume = await self._client.async_rcp_value("GetVolume")
            if volume is not None and volume.isdigit():
                self._attr_volume_level = int(volume) / 100
            self._attr_available = True
        except SoundBridgeError as err:
            if self._attr_available:
                _LOGGER.warning("SoundBridge unavailable: %s", err)
            self._attr_available = False

    # -- playback -------------------------------------------------------------

    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs
    ) -> None:
        """Point the device at a stream URL.

        This is the entry point Music Assistant uses: it resolves a track to
        a URL served by its own stream server and hands it over here.
        """
        if media_source.is_media_source_id(media_id):
            play_item = await media_source.async_resolve_media(
                self.hass, media_id, self.entity_id
            )
            media_id = play_item.url

        url = async_process_play_media_url(self.hass, media_id)

        # PlayStation takes a bare, unquoted URL and wakes the device from
        # standby on its own (it replies PowerStateOn before OK).
        await self._client.async_rcp(f"PlayStation {url}")
        self._attr_state = MediaPlayerState.PLAYING
        self.async_write_ha_state()

    async def async_browse_media(self, media_content_type=None, media_content_id=None):
        """Expose HA media sources, so the entity is useful outside MA too."""
        return await media_source.async_browse_media(self.hass, media_content_id)

    async def async_media_play(self) -> None:
        await self._client.async_rcp("Play")

    async def async_media_pause(self) -> None:
        await self._client.async_rcp("Pause")

    async def async_media_stop(self) -> None:
        await self._client.async_rcp("Stop")

    async def async_media_next_track(self) -> None:
        await self._client.async_rcp("Next")

    async def async_turn_on(self) -> None:
        await self._client.async_rcp("SetPowerState on")

    async def async_turn_off(self) -> None:
        await self._client.async_rcp("SetPowerState standby")

    async def async_set_volume_level(self, volume: float) -> None:
        await self._client.async_rcp(f"SetVolume {round(volume * 100)}")
        self._attr_volume_level = volume

    async def async_volume_up(self) -> None:
        current = self._attr_volume_level or 0
        await self.async_set_volume_level(min(current + 0.05, 1.0))

    async def async_volume_down(self) -> None:
        current = self._attr_volume_level or 0
        await self.async_set_volume_level(max(current - 0.05, 0.0))
