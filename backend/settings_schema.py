"""
The editable settings, shared by both UIs (the glass web UI and the classic
Tk window): field list, input kinds, and validation.
"""

from hotkey import parse_hotkey

# (key, label, kind) grouped into sections. kind: text / int / float / bool / list / secret
SECTIONS = [
    ("VOICE ACTIVATION", [
        ("WAKE_WORD", "Wake word", "text"),
        ("WAKE_WORD_ENABLED", "Listen for the wake word", "bool"),
        ("WAKE_WORD_ALIASES", "Extra sound-alikes (comma separated)", "list"),
        ("HOTKEY", "Push-to-talk hotkey (e.g. ctrl+alt+p)", "text"),
        ("WAKE_CHIME", "Chime when listening starts", "bool"),
        ("FOLLOW_UP_SECONDS", "Listen for a follow-up after replies (seconds, 0 = off)", "float"),
    ]),
    ("LISTENING", [
        ("COMMAND_START_TIMEOUT", "Give up if you don't speak within (seconds)", "float"),
        ("SILENCE_TIMEOUT", "Silence before a command ends (seconds)", "float"),
        ("MAX_COMMAND_SECONDS", "Max command length (seconds)", "int"),
    ]),
    ("VOICE OUTPUT", [
        ("TTS_ENABLED", "Spoken replies", "bool"),
        ("TTS_RATE", "Speech rate (words per minute)", "int"),
        ("TTS_VOICE", "Voice (part of the name, e.g. Zira or David)", "text"),
    ]),
    ("CONVERSATION", [
        ("OLLAMA_MODEL", "Ollama model name (e.g. llama3.1)", "text"),
        ("MAX_HISTORY_MESSAGES", "Conversation memory window (messages)", "int"),
    ]),
    ("SMART HOME", [
        ("HA_URL", "Home Assistant URL", "text"),
        ("HA_TOKEN", "Home Assistant long-lived access token", "secret"),
    ]),
    ("LOGGING", [
        ("SESSION_LOGGING_ENABLED", "Log each session to CSV", "bool"),
    ]),
]

FIELDS = {key: kind for _, fields in SECTIONS for key, _, kind in fields}


def parse(raw):
    """Coerces raw form values (strings / bools) into typed settings.
    Returns (values, error_message). Secret fields left blank are omitted,
    which keeps the stored value."""
    values = {}
    for key, kind in FIELDS.items():
        if key not in raw:
            continue
        value = raw[key]
        try:
            if kind == "bool":
                values[key] = value if isinstance(value, bool) else str(value).strip().lower() in ("1", "true", "yes", "on")
            elif kind == "int":
                values[key] = int(str(value).strip())
            elif kind == "float":
                values[key] = float(str(value).strip())
            elif kind == "list":
                items = value if isinstance(value, list) else str(value).split(",")
                values[key] = [str(v).strip().lower() for v in items if str(v).strip()]
            elif kind == "secret":
                if str(value).strip():
                    values[key] = str(value).strip()
            else:
                values[key] = str(value).strip()
        except ValueError:
            return None, f"'{value}' isn't a valid number for {key}"

    if "WAKE_WORD" in values:
        if not values["WAKE_WORD"]:
            return None, "The wake word can't be empty"
        values["WAKE_WORD"] = values["WAKE_WORD"].lower()
    if "HOTKEY" in values:
        try:
            parse_hotkey(values["HOTKEY"])
        except ValueError as e:
            return None, f"Hotkey: {e}"
    for key in ("MAX_HISTORY_MESSAGES", "TTS_RATE", "MAX_COMMAND_SECONDS"):
        if key in values and values[key] <= 0:
            return None, f"{key} must be greater than zero"
    return values, None
