"""
Rule-based intent parser. Checked BEFORE the LLM, so deterministic
commands (device control, PC actions, reminders) are fast and reliable
instead of depending on a language model to consistently produce
structured output. Anything that doesn't match a known pattern falls
through to the LLM for open-ended conversation.

All matching is on whole words, so "clock" doesn't trigger the door lock
and "commute" doesn't mute the volume. Spoken numbers ("seventy two",
"half an hour") are converted to digits first, because Vosk transcribes
numbers as words.
"""

import re
import time

DEVICE_PATTERN = re.compile(
    r"\b(lights?|lamps?|thermostat|temperature|lock|unlock|door|fan|plug)\b"
)

SYSTEM_KEYWORDS = {
    "screenshot": ["screenshot", "screen shot", "take a screenshot"],
    "lock_pc": ["lock my pc", "lock the pc", "lock the computer", "lock my computer", "lock my laptop"],
    "volume_up": ["volume up", "turn up the volume", "increase volume", "increase the volume", "louder"],
    "volume_down": ["volume down", "turn down the volume", "decrease volume", "decrease the volume", "quieter"],
    "mute": ["mute", "unmute", "mute the volume"],
    "open_browser": ["open browser", "open chrome", "open the browser", "open edge"],
    "open_explorer": ["open file explorer", "open explorer", "open my files"],
    "open_notepad": ["open notepad"],
    "open_calculator": ["open calculator", "open the calculator"],
    "open_task_manager": ["open task manager", "open the task manager"],
    "open_settings": ["open settings", "open windows settings", "open the settings"],
    "play_pause": ["play music", "pause music", "play pause", "pause", "resume music",
                   "stop music", "stop the music", "resume the music",
                   "turn off the music", "turn off music", "turn on the music", "turn on music"],
    "next_track": ["next song", "next track", "skip song", "skip track", "skip this song"],
    "previous_track": ["previous song", "previous track", "go back a song", "last song"],
}

# Said on their own while Parzival is listening = "never mind, go back to standby"
CANCEL_PHRASES = {
    "cancel", "never mind", "nevermind", "stop", "forget it", "nothing",
    "no thanks", "no thank you", "go to sleep", "that's all", "that is all",
    "stop listening", "be quiet", "shut up", "quiet",
}

_SYSTEM_PATTERNS = [
    (action, re.compile(r"\b(" + "|".join(re.escape(p) for p in phrases) + r")\b"))
    for action, phrases in SYSTEM_KEYWORDS.items()
]

# ---------------------------------------------------------------------------
# Spoken numbers -> digits
# ---------------------------------------------------------------------------
_UNITS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * (i + 2) for i, w in enumerate(
    "twenty thirty forty fifty sixty seventy eighty ninety".split())}


def words_to_numbers(text):
    """'set it to seventy two' -> 'set it to 72'; 'in half an hour' -> 'in 30 minutes'."""
    text = re.sub(r"\bhalf an hour\b", "30 minutes", text)
    text = re.sub(r"\b(?:a|an) (second|minute|hour)\b", r"1 \1", text)

    words = text.split()
    out = []
    i = 0
    while i < len(words):
        if words[i] not in _UNITS and words[i] not in _TENS:
            out.append(words[i])
            i += 1
            continue
        value, j = 0, i
        while j < len(words):
            w = words[j]
            if w in _TENS and value % 100 == 0:
                value += _TENS[w]
            elif w in _UNITS and value % 10 == 0:
                value += _UNITS[w]
            elif w == "hundred" and 0 < value < 10:
                value *= 100
            elif w == "and" and value >= 100 and j + 1 < len(words) and (
                    words[j + 1] in _UNITS or words[j + 1] in _TENS):
                pass
            else:
                break
            j += 1
        out.append(str(value))
        i = j
    return " ".join(out)


# ---------------------------------------------------------------------------
# Reminders & tasks
# ---------------------------------------------------------------------------
_UNIT_SECONDS = {"second": 1, "sec": 1, "minute": 60, "min": 60, "hour": 3600, "hr": 3600}
_DURATION = r"(?P<n>\d+) (?P<unit>seconds?|secs?|minutes?|mins?|hours?|hrs?)"

_REMINDER_PATTERNS = [
    re.compile(r"\bremind me (?:to )?(?P<text>.+?) in " + _DURATION + r"\b"),
    re.compile(r"\bremind me in " + _DURATION + r" (?:to |that |about )?(?P<text>.+)"),
    re.compile(r"\bset (?:a |an )?(?:reminder|timer|alarm) (?:for|in) " + _DURATION + r"(?: (?:to|that|for|about) (?P<text>.+))?"),
]
_TASK_ADD_PATTERNS = [
    re.compile(r"\badd (?P<text>.+?) to (?:my |the )?(?:tasks?|to ?do(?: list)?|list|task list)\b"),
    re.compile(r"\b(?:add|create|make) (?:a |an )?(?:new )?(?:task|to ?do)(?: to| called| for)? (?P<text>.+)"),
    re.compile(r"\bremind me to (?P<text>.+)"),
]
_TASK_LIST = re.compile(
    r"\b(?:what(?:'s| is| are)|read|list|show)(?: me)? (?:on )?(?:my|the) (?:tasks?|to ?do(?: list)?|task list|list|reminders)\b"
)


# ---------------------------------------------------------------------------
# TV (via Home Assistant). Only phrases that mention the TV are routed here,
# so "mute" alone still mutes the PC and "pause" still pauses PC media.
# ---------------------------------------------------------------------------
_TV = r"(?:the |my )?(?:tv|television|telly)"
_TV_PATTERNS = [
    ("app", re.compile(r"\b(?:open|launch|start|put on|play|switch to)\s+(?P<app>.+?)\s+(?:on|in)\s+" + _TV + r"\b")),
    ("volume_set", re.compile(r"\b(?:set\s+)?(?:the\s+)?(?:tv|television)\s+volume\s+(?:to\s+)?(?P<n>\d+)")),
    ("volume_set", re.compile(r"\bset\s+(?:the\s+)?volume\s+(?:on|of)\s+" + _TV + r"\s+to\s+(?P<n>\d+)")),
    ("volume_up", re.compile(r"\b(?:tv|television)\s+volume\s+up\b|\bturn\s+(?:up\s+" + _TV + r"|" + _TV + r"\s+up)\b"
                             r"|\b(?:louder|volume up)\s+on\s+" + _TV + r"\b")),
    ("volume_down", re.compile(r"\b(?:tv|television)\s+volume\s+down\b|\bturn\s+(?:down\s+" + _TV + r"|" + _TV + r"\s+down)\b"
                               r"|\b(?:quieter|volume down)\s+on\s+" + _TV + r"\b")),
    ("unmute", re.compile(r"\bunmute\s+" + _TV + r"\b")),
    ("mute", re.compile(r"\bmute\s+" + _TV + r"\b")),
    ("play_pause", re.compile(r"\b(?:pause|play|resume)\s+(?:it\s+)?(?:on\s+)?" + _TV + r"\b")),
    ("next", re.compile(r"\bnext\s+(?:episode\s+|video\s+|track\s+|song\s+)?on\s+" + _TV + r"\b")),
    ("previous", re.compile(r"\bprevious\s+(?:episode\s+|video\s+|track\s+|song\s+)?on\s+" + _TV + r"\b")),
    ("channel_up", re.compile(r"\b(?:next|change the)\s+channel\b|\bchannel\s+up\b")),
    ("channel_down", re.compile(r"\bprevious\s+channel\b|\bchannel\s+down\b")),
    ("home", re.compile(r"\b(?:go\s+)?home\s+(?:screen\s+)?on\s+" + _TV + r"\b|\b(?:tv|television)\s+home\b")),
    ("back", re.compile(r"\b(?:go\s+)?back\s+on\s+" + _TV + r"\b")),
]


def _tv_intent(lowered):
    for action, pattern in _TV_PATTERNS:
        match = pattern.search(lowered)
        if not match:
            continue
        args = {"action": action, "device": "tv"}
        if action == "app":
            args["app"] = match.group("app").strip()
        elif action == "volume_set":
            args["value"] = int(match.group("n"))
        return ("tv", args)
    return None


def _duration_seconds(match):
    unit = match.group("unit").rstrip("s")
    return int(match.group("n")) * _UNIT_SECONDS.get(unit, 60)


def parse_intent(text):
    """
    Returns (action, args) if the text matches a known command, or None if
    it should go to the LLM as open-ended conversation.
    """
    lowered = re.sub(r"[^\w\s']", " ", text.lower())   # drop punctuation from typed input
    lowered = re.sub(r"\s+", " ", lowered).strip()
    lowered = words_to_numbers(lowered)

    if lowered in CANCEL_PHRASES:
        return ("cancel", None)

    # Reminders/tasks first: "remind me to turn off the lights in 10 minutes"
    # must not switch the lights off right now.
    for pattern in _REMINDER_PATTERNS:
        match = pattern.search(lowered)
        if match:
            seconds = _duration_seconds(match)
            what = (match.groupdict().get("text") or "").strip() or "your timer is done"
            return ("reminder", {"text": what, "seconds": seconds, "due": time.time() + seconds})

    if _TASK_LIST.search(lowered):
        return ("task_list", None)

    for pattern in _TASK_ADD_PATTERNS:
        match = pattern.search(lowered)
        if match and match.group("text").strip():
            return ("task_add", {"text": match.group("text").strip()})

    if re.search(r"\bwhat('?s| is) the time\b|\bwhat time is it\b|\btell me the time\b", lowered):
        return ("time", None)

    if re.search(r"\bwhat('?s| is) (the|today'?s) date\b|\bwhat day is (it|today)\b", lowered):
        return ("date", None)

    tv = _tv_intent(lowered)
    if tv:
        return tv

    for action, pattern in _SYSTEM_PATTERNS:
        if pattern.search(lowered):
            return ("system", action)

    # "turn on/off X" is always a device command, even when speech
    # recognition garbles the device name ("living room life") - the device
    # controller fuzzy-matches the name, which beats sending it to the LLM.
    turn_on = re.search(r"\b(?:turn|switch) on (?:the )?(.+)", lowered)
    turn_off = re.search(r"\b(?:turn|switch) off (?:the )?(.+)", lowered)
    # "turn the kitchen light on"
    turn_x = re.search(r"\b(?:turn|switch) (?:the )?(.+?) (on|off)\b", lowered)

    if turn_on:
        return ("device", {"action": "on", "device": turn_on.group(1).strip()})

    if turn_off:
        return ("device", {"action": "off", "device": turn_off.group(1).strip()})

    if turn_x:
        return ("device", {"action": turn_x.group(2), "device": turn_x.group(1).strip()})

    if DEVICE_PATTERN.search(lowered):
        set_value = re.search(r"\bset (the )?(.+?) to (\d+)", lowered)
        unlock = re.search(r"\bunlock\b", lowered)
        lock = re.search(r"\block\b", lowered)

        if set_value:
            device_name = set_value.group(2).strip()
            value = int(set_value.group(3))
            return ("device", {"action": "set", "device": device_name, "value": value})

        if unlock:
            return ("device", {"action": "unlock", "device": "front door"})

        if lock:
            return ("device", {"action": "lock", "device": "front door"})

    return None
