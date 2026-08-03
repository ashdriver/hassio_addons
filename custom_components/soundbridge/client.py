"""Async client for the Roku SoundBridge debug shell (port 4444).

The SoundBridge shell is a simple line-oriented prompt ("SoundBridge> ").
Typing "sketch" drops you into a drawing sub-shell ("sketch> ") with
commands like `clear`, `text x y "..."`, `marquee -start "..."`, etc.

IMPORTANT BEHAVIOR (confirmed empirically, not documented anywhere):
leaving the `sketch` sub-shell (typing `quit`) immediately hands the
display back to the SoundBridge's own firmware UI (clock / now-playing
screen), which then overwrites whatever `sketch` drew. Simply closing the
TCP connection while still inside `sketch` does NOT do this - the drawn
content stays up. So: to make text persist on screen, we have to hold a
connection open *inside* the sketch sub-shell indefinitely, and only issue
`quit` when we actually want to hand control back.

This means, while a message is being held, the device's own UI (clock,
now-playing, menus) is frozen and won't update - `sketch` and the normal
firmware UI can't both drive the screen at once. Callers should generally
use a bounded `duration` when sending a message rather than holding it
forever, unless a persistent display is genuinely what's wanted.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from .const import (
    DEFAULT_CMD_TIMEOUT,
    DEFAULT_FONT,
    DEFAULT_PORT,
    DEFAULT_SCAN_TIMEOUT,
    DEFAULT_SCROLL_REPEAT,
    DISPLAY_WIDTH_PX,
    FONT_HEIGHT_PX,
    GLYPH_ASPECT,
    MARQUEE_SPEED_PX_PER_SEC,
    MIN_SCROLL_INTERVAL,
)

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


def estimate_scroll_seconds(text: str, font: int | None) -> float:
    """Estimate how long one marquee pass takes, in seconds.

    The text enters from one edge and has to fully exit the other, so it
    travels the display width plus its own width. Only ever an estimate -
    callers can pass an explicit interval instead (see MARQUEE_SPEED_PX_PER_SEC).
    """
    height = FONT_HEIGHT_PX.get(font if font is not None else DEFAULT_FONT, 16)
    text_px = len(text) * height * GLYPH_ASPECT
    travel_px = DISPLAY_WIDTH_PX + text_px
    return max(travel_px / MARQUEE_SPEED_PX_PER_SEC, MIN_SCROLL_INTERVAL)


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
    """Holds a persistent shell connection to a SoundBridge display.

    A single connection is opened lazily on first use and kept inside the
    `sketch` sub-shell across calls, so drawn content survives between
    send_text() calls. Call async_release() to hand control back to the
    device's own UI (clock/now-playing) and close the connection.
    """

    def __init__(self, host: str, port: int = DEFAULT_PORT) -> None:
        self._host = host
        self._port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()
        self._release_handle: asyncio.TimerHandle | None = None
        self._scroll_task: asyncio.Task | None = None

    # -- one-shot probing (used by discovery / config flow) -----------------

    async def async_probe(
        self, timeout: float = DEFAULT_SCAN_TIMEOUT
    ) -> SoundBridgeInfo | None:
        """Connect and confirm this is actually a SoundBridge shell.

        Uses a throwaway connection, independent of the persistent one
        used for drawing - safe to call at any time, including while a
        message is currently being held on screen.
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

    # -- persistent connection management ------------------------------------

    async def _ensure_in_sketch(self, timeout: float) -> None:
        """Make sure we have a live connection sitting at the sketch> prompt."""
        if self._writer is not None and not self._writer.is_closing():
            return  # assume still good; a failed write below will tell us otherwise

        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self._host, self._port), timeout=timeout
        )
        await _read_until(reader, (SHELL_PROMPT,), timeout)
        writer.write(b"sketch\r\n")
        await writer.drain()
        await _read_until(reader, (SKETCH_PROMPT,), timeout)
        self._reader, self._writer = reader, writer

    async def _run_sketch_command(self, cmd: str, timeout: float) -> None:
        """Send one sketch command over the held-open connection, with one
        automatic reconnect-and-retry if the connection turned out to be
        stale (e.g. device rebooted, or something else closed it)."""
        for attempt in (1, 2):
            try:
                await self._ensure_in_sketch(timeout)
                assert self._writer is not None and self._reader is not None
                self._writer.write(cmd.encode("latin-1", errors="replace") + b"\r\n")
                await self._writer.drain()
                await _read_until(self._reader, (SKETCH_PROMPT,), timeout)
                return
            except (SoundBridgeError, OSError):
                await self._reset_connection()
                if attempt == 2:
                    raise

    async def _reset_connection(self) -> None:
        """Drop our idea of the connection without trying to be polite
        about it (used when the connection is already presumed broken)."""
        if self._writer is not None:
            self._writer.close()
        self._reader = None
        self._writer = None

    def _cancel_pending_release(self) -> None:
        if self._release_handle is not None:
            self._release_handle.cancel()
            self._release_handle = None

    # -- marquee looping -------------------------------------------------------

    def _stop_scroll_loop(self) -> None:
        """Stop re-issuing the marquee. Does not stop the marquee itself -
        callers that need the display quiet send `marquee -stop` too."""
        if self._scroll_task is not None:
            self._scroll_task.cancel()
            self._scroll_task = None

    def _start_scroll_loop(self, cmd: str, interval: float) -> None:
        self._stop_scroll_loop()
        self._scroll_task = asyncio.create_task(self._scroll_loop(cmd, interval))

    async def _scroll_loop(self, cmd: str, interval: float) -> None:
        """Re-issue the marquee every `interval` seconds so it loops.

        Errors are logged rather than raised: the service call that started
        this returned long ago, so there is no caller left to receive them,
        and one failed restart just means the scrolling stops.
        """
        while True:
            try:
                await asyncio.sleep(interval)
                async with self._lock:
                    if self._scroll_task is not asyncio.current_task():
                        return  # superseded by a newer message
                    # Stop first so a pass that is somehow still running
                    # can't overlap with the one we're about to start.
                    await self._run_sketch_command('marquee -stop ""', DEFAULT_CMD_TIMEOUT)
                    await self._run_sketch_command(cmd, DEFAULT_CMD_TIMEOUT)
            except asyncio.CancelledError:
                raise
            except (SoundBridgeError, OSError) as err:
                _LOGGER.warning(
                    "SoundBridge %s: could not restart marquee, scrolling stops: %s",
                    self._host,
                    err,
                )
                return

    # -- public drawing API ---------------------------------------------------

    async def async_send_text(
        self,
        text: str,
        x: str = "c",
        y: str = "c",
        font: int | None = DEFAULT_FONT,
        clear: bool = True,
        scroll: bool = False,
        duration: float | None = None,
        scroll_repeat: bool = DEFAULT_SCROLL_REPEAT,
        scroll_interval: float | None = None,
        timeout: float = DEFAULT_CMD_TIMEOUT,
    ) -> None:
        """Render text on the display via the sketch sub-shell.

        The connection is left open afterwards so the text stays visible.
        If `duration` is given (seconds), the display is automatically
        released back to the device's normal UI after that many seconds
        via async_release(). If omitted, the message stays up until the
        next send_text()/clear() call or an explicit async_release().

        The device's marquee makes a single pass and stops, so with
        `scroll_repeat` (the default) the command is re-issued every
        `scroll_interval` seconds to keep it going. If no interval is
        given one is estimated from the text length and font height.
        """
        safe_text = sanitize_text(text)

        async with self._lock:
            self._cancel_pending_release()
            self._stop_scroll_loop()

            if clear:
                await self._run_sketch_command("clear", timeout)
            if font is not None:
                await self._run_sketch_command(f"font {int(font)}", timeout)

            if scroll:
                marquee = f'marquee -start "{safe_text}"'
                await self._run_sketch_command(marquee, timeout)
                if scroll_repeat:
                    interval = (
                        scroll_interval
                        if scroll_interval is not None
                        else estimate_scroll_seconds(safe_text, font)
                    )
                    _LOGGER.debug(
                        "Looping marquee on %s every %.1fs", self._host, interval
                    )
                    self._start_scroll_loop(marquee, interval)
            else:
                await self._run_sketch_command(f'text {x} {y} "{safe_text}"', timeout)

        if duration is not None:
            loop = asyncio.get_running_loop()
            self._release_handle = loop.call_later(
                duration, lambda: asyncio.ensure_future(self.async_release())
            )

    async def async_clear(self, timeout: float = DEFAULT_CMD_TIMEOUT) -> None:
        """Clear the display (also stops any running marquee).

        Leaves the connection held open in sketch mode, same as
        async_send_text - call async_release() to hand control back.
        """
        async with self._lock:
            self._cancel_pending_release()
            self._stop_scroll_loop()
            await self._run_sketch_command('marquee -stop ""', timeout)
            await self._run_sketch_command("clear", timeout)

    async def async_release(self, timeout: float = DEFAULT_CMD_TIMEOUT) -> None:
        """Hand the display back to the device's own UI and disconnect."""
        async with self._lock:
            self._cancel_pending_release()
            self._stop_scroll_loop()
            if self._writer is None:
                return
            try:
                self._writer.write(b"quit\r\n")
                await self._writer.drain()
                if self._reader is not None:
                    await _read_until(self._reader, (SHELL_PROMPT,), timeout)
            except (SoundBridgeError, OSError):
                pass  # best-effort - we're closing the socket regardless
            finally:
                await self._reset_connection()
