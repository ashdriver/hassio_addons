"""Config flow for Roku SoundBridge Display.

Two discovery paths are offered:
  * "scan"   - actively probes every host on a subnet for an open shell
               on TCP/4444 that identifies itself as a SoundBridge. This
               is the "automatic enumeration" path.
  * "manual" - type in an IP address directly, for cases where the scan
               can't reach the device (different VLAN, HA running in a
               container without host networking, etc).
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResult

try:
    from homeassistant.helpers.service_info.ssdp import SsdpServiceInfo
except ImportError:  # pragma: no cover - older HA core versions
    from homeassistant.components.ssdp import SsdpServiceInfo  # type: ignore[no-redef]

from .client import SoundBridgeClient
from .const import DEFAULT_PORT, DOMAIN
from .discovery import async_scan_subnet, guess_local_cidr

_LOGGER = logging.getLogger(__name__)


class SoundBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Roku SoundBridge Display."""

    VERSION = 1

    def __init__(self) -> None:
        self._scan_results: dict[str, dict[str, Any]] = {}
        self._discovered_host: str | None = None
        self._discovered_name: str | None = None

    async def async_step_ssdp(self, discovery_info: SsdpServiceInfo) -> FlowResult:
        """Handle a device discovered via SSDP (UPnP broadcast)."""
        host = urlparse(discovery_info.ssdp_location or "").hostname
        if host is None:
            return self.async_abort(reason="cannot_connect")

        udn = discovery_info.ssdp_udn or (discovery_info.upnp or {}).get("UDN", "")
        unique_id = udn.removeprefix("uuid:") or host

        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})

        self._discovered_host = host
        self._discovered_name = (discovery_info.upnp or {}).get(
            "friendlyName", "SoundBridge"
        )

        self.context["title_placeholders"] = {"name": self._discovered_name}
        return await self.async_step_ssdp_confirm()

    async def async_step_ssdp_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm adding the SSDP-discovered device."""
        if user_input is not None:
            assert self._discovered_host is not None
            return await self._async_finish(self._discovered_host, DEFAULT_PORT)

        return self.async_show_form(
            step_id="ssdp_confirm",
            description_placeholders={
                "name": self._discovered_name or "SoundBridge",
                "host": self._discovered_host or "",
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ask whether to scan automatically or enter an IP manually."""
        if user_input is not None:
            if user_input["method"] == "scan":
                return await self.async_step_scan()
            return await self.async_step_manual()

        schema = vol.Schema(
            {
                vol.Required("method", default="scan"): vol.In(
                    {
                        "scan": "Scan my network automatically",
                        "manual": "Enter IP address manually",
                    }
                )
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_scan(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Run (or re-run) an active subnet scan for SoundBridge units."""
        errors: dict[str, str] = {}

        if user_input is not None:
            cidr = user_input["cidr"]
            try:
                found = await async_scan_subnet(cidr)
            except ValueError:
                errors["cidr"] = "subnet_too_large"
            else:
                if not found:
                    errors["base"] = "no_devices_found"
                else:
                    self._scan_results = {
                        info.host: {"port": info.port, "version": info.version}
                        for info in found
                    }
                    return await self.async_step_pick()

        schema = vol.Schema({vol.Required("cidr", default=guess_local_cidr()): str})
        return self.async_show_form(
            step_id="scan", data_schema=schema, errors=errors
        )

    async def async_step_pick(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Let the user pick one of the units found during the scan."""
        if user_input is not None:
            host = user_input["host"]
            info = self._scan_results[host]
            return await self._async_finish(host, info["port"])

        options = {
            host: f"{host} ({info['version']})"
            for host, info in self._scan_results.items()
        }
        schema = vol.Schema({vol.Required("host"): vol.In(options)})
        return self.async_show_form(step_id="pick", data_schema=schema)

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manual IP entry, with a live connectivity check."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            client = SoundBridgeClient(host, port)
            info = await client.async_probe(timeout=3.0)
            if info is None:
                errors["base"] = "cannot_connect"
            else:
                return await self._async_finish(host, port)

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
            }
        )
        return self.async_show_form(
            step_id="manual", data_schema=schema, errors=errors
        )

    async def _async_finish(self, host: str, port: int) -> FlowResult:
        await self.async_set_unique_id(f"{host}:{port}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=f"SoundBridge ({host})",
            data={CONF_HOST: host, CONF_PORT: port},
        )
