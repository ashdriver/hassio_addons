"""Constants for the Roku SoundBridge Display integration."""

DOMAIN = "soundbridge"

DEFAULT_PORT = 4444
DEFAULT_SCAN_TIMEOUT = 0.35  # per-host connect timeout during subnet scan
DEFAULT_CMD_TIMEOUT = 4.0    # per-command timeout during normal operation

CONF_FONT = "font"
CONF_X = "x"
CONF_Y = "y"
CONF_SCROLL = "scroll"
CONF_CLEAR = "clear"

DEFAULT_X = "c"
DEFAULT_Y = "c"
DEFAULT_FONT = 3

# While the device is powered on and stopped, its firmware puts up a
# "Playback Stopped - Press Play to start" marquee and repaints it ~37 times
# a second, overwriting anything drawn through the sketch sub-shell. Dropping
# to standby silences the firmware completely (measured: 0 repaints/sec) and
# hands the display back, so the two are mutually exclusive on this hardware.
#
# DISABLED. Standby does not just silence the firmware - it powers the VFD
# panel off, so the display goes dark. That was missed because GetDisplayData
# returns the framebuffer, which still accepts sketch writes and still reads
# back lit pixels while the panel itself is unlit. Repaint rate cannot tell an
# idle firmware apart from a dark panel; both read 0/sec. Do not re-enable
# without confirming against the physical display.
AUTO_STANDBY_ON_STOP = False

# How long the transport must stay stopped before we drop to standby. A queue
# transition can report Stop for a moment, and standby-ing there would kill
# playback mid-queue - so this needs to comfortably outlast a track change.
AUTO_STANDBY_DELAY = 30.0

CONF_SCROLL_REPEAT = "scroll_repeat"
CONF_SCROLL_INTERVAL = "scroll_interval"

# `marquee -start` makes exactly one pass and then stops, and returns the
# shell prompt immediately rather than when the pass ends - so looping it
# means re-issuing the command on a timer we work out ourselves.
DEFAULT_SCROLL_REPEAT = True

# Used to estimate how long one pass takes, when no explicit interval is
# given. Travel distance is the display width plus the width of the text
# (the text has to enter from one edge and fully leave at the other).
DISPLAY_WIDTH_PX = 280           # M1001 VFD is 280x16
FONT_HEIGHT_PX = {1: 8, 2: 16, 3: 32, 10: 16, 11: 16, 12: 16, 14: 16}
# Proportional fonts, so this is a rough mean advance per character.
GLYPH_ASPECT = 0.25
# Scroll rate of the firmware's marquee. This is an estimate - if looping
# restarts early (text jumps back mid-pass) lower it; if there is a pause
# with the display sitting idle between passes, raise it. Or just set
# `scroll_interval` on the service call and skip the estimate entirely.
MARQUEE_SPEED_PX_PER_SEC = 40.0

# Never restart faster than this, whatever the estimate says.
MIN_SCROLL_INTERVAL = 1.0
