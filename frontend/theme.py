"""Jarvis-inspired dark HUD theme: near-black background, glowing cyan
accents, monospace HUD labels."""

BG_PRIMARY = "#05070a"
BG_SECONDARY = "#0a0e14"
BG_CARD = "#0d1219"
BG_CARD_HOVER = "#121a24"
BG_SIDEBAR = "#070a0f"

ACCENT_CYAN = "#00d9ff"
ACCENT_CYAN_HOVER = "#00a8cc"
ACCENT_CYAN_DIM = "#0a5a6e"
ACCENT_GREEN = "#00e676"
ACCENT_RED = "#ff5252"
ACCENT_RED_HOVER = "#c62828"
ACCENT_GOLD = "#ffb300"
ACCENT_GOLD_HOVER = "#b8942c"
ACCENT_PURPLE = "#a074c4"

TEXT_PRIMARY = "#e8f6ff"
TEXT_SECONDARY = "#5c7a8a"
TEXT_MUTED = "#3b5260"
BORDER = "#132029"

# Subtle scrollbars (CTk's default grey bar is loud on this dark theme)
SCROLLBAR = {"scrollbar_button_color": BORDER, "scrollbar_button_hover_color": "#24404f"}

FONT_FAMILY = "Segoe UI"
FONT_TITLE = (FONT_FAMILY, 20, "bold")
FONT_HEADING = (FONT_FAMILY, 15, "bold")
FONT_BODY = (FONT_FAMILY, 13)
FONT_SMALL = (FONT_FAMILY, 11)
FONT_MONO = ("Consolas", 12)
FONT_HUD = ("Consolas", 11, "bold")   # uppercase, technical-feeling labels

RADIUS = 8
PAD = 14
SIDEBAR_WIDTH = 210
SIDEBAR_WIDTH_COMPACT = 64

# Layout breakpoints (logical pixels, before Windows display scaling)
COMPACT_SIDEBAR_BELOW = 980   # window width
STACK_DASHBOARD_BELOW = 720   # dashboard content width

STATUS_COLORS = {
    "loading": TEXT_SECONDARY,
    "idle": ACCENT_CYAN_DIM,
    "listening": ACCENT_CYAN,
    "thinking": ACCENT_GOLD,
    "speaking": ACCENT_GREEN,
    "error": ACCENT_RED,
}

STATUS_LABELS = {
    "loading": "INITIALIZING",
    "idle": "STANDBY",
    "listening": "LISTENING",
    "thinking": "THINKING",
    "speaking": "SPEAKING",
    "error": "ERROR",
}

# Segoe MDL2 Assets glyphs (ships with Windows 10/11), see widgets/icons.py
ICONS = {
    "Dashboard": "",
    "Devices": "",
    "System": "",
    "History": "",
    "Settings": "",
    "mic": "",
    "stop": "",
    "send": "",
}
