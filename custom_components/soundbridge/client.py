"""Low-level async client for the Roku SoundBridge debug shell (port 4444).

The SoundBridge shell is a simple line-oriented prompt ("SoundBridge> ").
Typing "sketch" drops you into a drawing sub-shell ("sketch> ") with
commands like `clear`, `text x y "..."`, `marquee -start "..."`, etc.
See: SoundBridgeRCPSpecification2-4.pdf and the interactive `sketch ?`
help text for the full command set.

This client opens a fresh connection for each operation. The device is a
single embedded unit from ~2005-2008; there's no evidence it supports more
than one shell session cleanly, so we keep sessions short-lived rather than
holding a persistent connection open.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from .const import DEFAULT_CMD_TIMEOUT, DEFAULT_FONT, DEFAULT_PORT, DEFAULT_SCAN_TIMEOUT

_LOGGER = logging.getLogger(__name__)

SHELL_PROMPT = b"SoundBridge>"
SKETCH_PROMPT = b"sketch>"


class SoundBridgeError(Exception):
    """Base error talking to a SoundBridge unit."""


class SoundBridgeConnectionError(SoundBridgeError):
    """Could not connect / device did not behave like a SoundBridge shell."""


class SoundBridgeTimeoutError(SoundBridgeError):
    """Device did not respond in time."""


@dataclass
class SoundBridgeInfo:
    """Result of probing a candidate host."""

    host: str
    port: int
    version: str


async def _read_until(
    reader: asyncio.StreamReader, markers: tuple[bytes, ...], timeout: float
) -> bytes:
    """Read from the stream until one of `markers` appears in the buffer."""
    buf = b""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise SoundBridgeTimeoutError(
                f"Timed out waiting for {markers!r}; got so far: {buf[-200:]!r}"
            )
        try:
            chunk = await asyncio.wait_for(reader.read(256), timeout=remaining)
        except asyncio.TimeoutError as err:
            raise SoundBridgeTimeoutError(
                f"Timed out waiting for {markers!r}; got so far: {buf[-200:]!r}"
            ) from err
        if not chunk:
            raise SoundBridgeConnectionError(
                f"Connection closed while waiting for {markers!r}; got: {buf[-200:]!r}"
            )
        buf += chunk
        if any(marker in buf for marker in markers):
            return buf


def sanitize_text(text: str) -> str:
    """Make arbitrary user text safe to embed in a quoted sketch command.

    The shell's tokenizer isn't documented, so we don't rely on any
    backslash-escaping working. Instead we simply remove characters that
    would break single-line, double-quoted argument parsing.
    """
    text = text.replace("\r", " ").replace("\n", " ")
    text = text.replace('"', "'")
    return text.strip()


class SoundBridgeClient:
    """Helper for probing and sending text to a SoundBridge display."""

    def __init__(self, host: str, port: int = DEFAULT_PORT) -> None:
        self._host = host
        self._port = port

    async def async_probe(
        self, timeout: float = DEFAULT_SCAN_TIMEOUT
    ) -> SoundBridgeInfo | None:
        """Connect and confirm this is actually a SoundBridge shell.

        Returns SoundBridgeInfo on success, or None if the host doesn't
        look like a SoundBridge (used during subnet scanning, where a
        "no match" is a normal, expected outcome rather than an error).
        """
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port), timeout=timeout
            )
        except (OSError, asyncio.TimeoutError):
            return None

        try:
            await _read_until(reader, (SHELL_PROMPT,), timeout)
            writer.write(b"version\r\n")
            await writer.drain()
            resp = await _read_until(reader, (SHELL_PROMPT,), timeout)
            text = resp.decode(errors="replace")
            if "soundbridge" not in text.lower():
                return None
            # First non-empty line of the response is typically the
            # version string itself.
            version_line = next(
                (
                    line.strip()
                    for line in text.splitlines()
                    if line.strip() and "SoundBridge>" not in line
                ),
                "unknown",
            )
            return SoundBridgeInfo(host=self._host, port=self._port, version=version_line)
        except SoundBridgeError:
            return None
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001 - best-effort cleanup
                pass

    async def async_send_text(
        self,
        text: str,
        x: str = "c",
        y: str = "c",
        font: int | None = DEFAULT_FONT,
        clear: bool = True,
        scroll: bool = False,
        timeout: float = DEFAULT_CMD_TIMEOUT,
    ) -> None:
        """Render text on the display via the sketch sub-shell."""
        safe_text = sanitize_text(text)

        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self._host, self._port), timeout=timeout
        )
        try:
            await _read_until(reader, (SHELL_PROMPT,), timeout)

            writer.write(b"sketch\r\n")
            await writer.drain()
            await _read_until(reader, (SKETCH_PROMPT,), timeout)

            if clear:
                writer.write(b"clear\r\n")
                await writer.drain()
                await _read_until(reader, (SKETCH_PROMPT,), timeout)

            if font is not None:
                writer.write(f"font {int(font)}\r\n".encode())
                await writer.drain()
                await _read_until(reader, (SKETCH_PROMPT,), timeout)

            if scroll:
                cmd = f'marquee -start "{safe_text}"\r\n'
            else:
                cmd = f'text {x} {y} "{safe_text}"\r\n'
            writer.write(cmd.encode())
            await writer.drain()
            await _read_until(reader, (SKETCH_PROMPT,), timeout)

            writer.write(b"quit\r\n")
            await writer.drain()
            await _read_until(reader, (SHELL_PROMPT,), timeout)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001 - best-effort cleanup
                pass

    async def async_clear(self, timeout: float = DEFAULT_CMD_TIMEOUT) -> None:
        """Clear the display (also stops any running marquee)."""
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self._host, self._port), timeout=timeout
        )
        try:
            await _read_until(reader, (SHELL_PROMPT,), timeout)
            writer.write(b"sketch\r\n")
            await writer.drain()
            await _read_until(reader, (SKETCH_PROMPT,), timeout)

            writer.write(b'marquee -stop ""\r\n')
            await writer.drain()
            await _read_until(reader, (SKETCH_PROMPT,), timeout)

            writer.write(b"clear\r\n")
            await writer.drain()
            await _read_until(reader, (SKETCH_PROMPT,), timeout)

            writer.write(b"quit\r\n")
            await writer.drain()
            await _read_until(reader, (SHELL_PROMPT,), timeout)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass
