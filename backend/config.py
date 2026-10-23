# ==========================
# Wake word / voice activation
# ==========================
WAKE_WORD = "parzival"
WAKE_WORD_ENABLED = True  # False = only the hotkey / mic button can activate Parzival

# The small Vosk model doesn't know the word "parzival" (it hears it as
# "party will" or "portable"), so the wake-word detector listens for
# in-vocabulary sound-alikes instead. Built-in aliases for "parzival" live
# in wake_word.py; add your own here if it misses you, e.g. ["parse a ball"].
WAKE_WORD_ALIASES = []

WAKE_CHIME = True         # short beep when Parzival starts listening

# Global push-to-talk hotkey (works even when the window isn't focused).
# Modifiers: ctrl, alt, shift, win. Keys: a-z, 0-9, f1-f12, space.
HOTKEY = "ctrl+alt+p"

# Download a model from https://alphacephei.com/vosk/models and point this
# at the extracted folder, e.g. "models/vosk-model-small-en-us-0.15"
VOSK_MODEL_PATH = "models/vosk-model-small-en-us-0.15"

SAMPLE_RATE = 16000
MIC_DEVICE_INDEX = None   # None = system default microphone

SILENCE_TIMEOUT = 1.5     # seconds of silence before a command is considered finished
MAX_COMMAND_SECONDS = 10  # hard cap on how long a single command can run
COMMAND_START_TIMEOUT = 5 # give up if you don't start speaking within this many seconds
FOLLOW_UP_SECONDS = 5     # after a conversational reply, listen this long for a follow-up (0 = off)

# ==========================
# Text-to-speech
# ==========================
TTS_ENABLED = True
TTS_RATE = 175
TTS_VOICE = ""            # part of a voice name, e.g. "Zira" or "David" ("" = system default)

# ==========================
# LLM (Ollama - fully local, no cloud API)
# ==========================
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "llama3.2"
OLLAMA_TIMEOUT = 60          # max wait for the first words (cold model loads can be slow)
OLLAMA_KEEP_ALIVE = "30m"   # keep the model loaded in RAM between questions (faster replies)
MAX_HISTORY_MESSAGES = 20   # rolling context window sent to the LLM each turn

# ==========================
# Storage (relative paths resolve against the frontend/ folder)
# ==========================
MEMORY_FILE = "memory.json"
DEVICES_FILE = "devices.json"
TASKS_FILE = "tasks.json"
LOG_DIR = "logs"
SESSION_LOGGING_ENABLED = True

# ==========================
# Home Assistant (real device control)
# ==========================
# Set these in settings.json, NOT here - HA_TOKEN is a secret credential
# and should never be committed to git.
HA_URL = "http://localhost:8123"
HA_TOKEN = ""
HA_POLL_SECONDS = 5         # how often device state is refreshed in the background
HA_ALLOW_INSECURE_LAN = False  # never send the token over plain http to another machine
