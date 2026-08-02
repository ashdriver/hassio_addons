"""Active-scan discovery for SoundBridge units.

We don't have a confirmed SSDP/Bonjour fingerprint captured from a real
unit, so rather than guess at manufacturer/model strings and risk silent
discovery failures, we scan the local subnet for hosts with TCP/4444 open
and confirm each one is genuinely a SoundBridge by running `version` and
checking the response. This is slower than passive SSDP but deterministic.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging

from .client import SoundBridgeClient, SoundBridgeInfo
from .const import DEFAULT_PORT, DEFAULT_SCAN_TIMEOUT

_LOGGER = logging.getLogger(__name__)

MAX_CONCURRENT_PROBES = 64


async def async_scan_subnet(
    cidr: str, port: int = DEFAULT_PORT, timeout: float = DEFAULT_SCAN_TIMEOUT
) -> list[SoundBridgeInfo]:
    """Probe every host in `cidr` (e.g. '192.168.1.0/24') for a SoundBridge."""
    network = ipaddress.ip_network(cidr, strict=False)
    hosts = list(network.hosts())

    if len(hosts) > 4096:
        raise ValueError("Subnet too large to scan (max /20)")

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_PROBES)

    async def _probe_one(ip: ipaddress.IPv4Address) -> SoundBridgeInfo | None:
        async with semaphore:
            client = SoundBridgeClient(str(ip), port)
            return await client.async_probe(timeout=timeout)

    results = await asyncio.gather(*(_probe_one(ip) for ip in hosts))
    return [r for r in results if r is not None]


def guess_local_cidr() -> str:
    """Best-effort guess of the local /24 network, for pre-filling the UI."""
    import socket

    try:
        # Doesn't actually send anything (UDP, no connect handshake) - just
        # used to ask the OS which local interface would route to the
        # internet, so we can read its address.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            local_ip = sock.getsockname()[0]
        network = ipaddress.ip_network(f"{local_ip}/24", strict=False)
        return str(network)
    except OSError:
        return "192.168.1.0/24"
