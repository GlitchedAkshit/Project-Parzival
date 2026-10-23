# Parzival

A local, offline voice assistant with a holographic "glass" interface: a
wake word and push-to-talk, real conversational AI (via a locally-running
LLM), a smart-home dashboard (simulated, or real devices through Home
Assistant), tasks and spoken reminders, and real PC control. No cloud APIs,
no internet required once set up.

For a full walkthrough of how every part works, see
[HOW_IT_WORKS.md](HOW_IT_WORKS.md).

## One-time setup (outside this project)

**1. Install Ollama** (the local LLM server): https://ollama.com

Then pull the model named in Settings (default in `settings.json`: `llama3.1`):
```bash
ollama pull llama3.1
```
Ollama runs a local server automatically at `http://localhost:11434` — no
API key needed.

**2. Download a Vosk speech model**: https://alphacephei.com/vosk/models

Grab the small English model (`vosk-model-small-en-us-0.15`, ~50MB), unzip
it, and place it at `backend/models/vosk-model-small-en-us-0.15` (or point
`config.VOSK_MODEL_PATH` at wherever you put it).

## Install & run

```bash
pip install -r requirements.txt
python parzival.py
```

`parzival.py` starts the assistant and opens the interface in its own
window (Microsoft Edge WebView2, built into Windows 11). Other ways to run it:

| Command | What it does |
| --- | --- |
| `python parzival.py --browser` | Open the interface in an Edge/Chrome app window instead |
| `python parzival.py --classic` | The original CustomTkinter interface |
| `python parzival.py --server-only` | No window; prints a URL to open in a browser (development) |
| `python parzival.py --quiet` | No spoken replies or chimes (testing) |

## Talking to Parzival

| How | What happens |
| --- | --- |
| Say **"Parzival"** | Chime → Parzival listens for your command |
| Say **"Parzival, turn on the kitchen light"** | One sentence works too — no need to pause after the wake word |
| Press **Ctrl+Alt+P** (anywhere in Windows) | Push-to-talk: listens immediately, no wake word needed |
| Click the **microphone** (or tap the AI core) | Same as the hotkey; click again to cancel |
| Press **Esc** or the stop button while it talks | Cuts Parzival off mid-sentence |
| Say **"never mind"** / **"cancel"** | Goes back to standby |
| Answer a question Parzival asked | After a conversational reply it keeps listening for ~5s |
| Type in the conversation panel | Works with no microphone at all (↑ recalls earlier commands) |

Keyboard: **Ctrl+K** search · **/** focus the command box · **Alt+1…8**
dock items · **Esc** close panel / interrupt.

## What it can do

**Conversation** — anything that isn't a recognized command goes to your
local LLM (Ollama). Replies stream in and are spoken sentence by sentence.
Memory persists across restarts (`memory.json`); search it from the dock.

**Tasks & reminders** — "remind me to stretch in 20 minutes", "remind me in
half an hour to call mom", "set a timer for 5 minutes", "add buy milk to my
tasks", "what are my tasks". Reminders are announced aloud when due.

**Smart home** — "turn on the living room light", "turn off all the
lights", "set the thermostat to seventy two", "lock the front door". The
Smart home panel stays in sync with voice commands both ways. Uses real
Home Assistant devices when `HA_URL`/`HA_TOKEN` are set and reachable,
simulated ones otherwise.

**Your TV** (Android / Google TV, through Home Assistant) — "turn on the
TV", "open YouTube on the TV", "play Netflix on the TV", "mute the TV",
"turn the TV up", "set the TV volume to 20", "pause the TV", "next
channel", "go home on the TV". The Smart home panel has a full remote:
power, volume, playback, Home/Back and one-tap apps.

**PC control** — "take a screenshot", "lock my pc", "volume up", "mute",
"open browser / file explorer / notepad / calculator / task manager /
settings", "play music" / "pause" / "next song", "what time is it",
"what's the date".

## Connecting your TV and other Wi-Fi devices

Parzival controls real devices through **Home Assistant**, which runs on
this PC (Docker container `homeassistant`) and talks to your devices over
your own Wi-Fi — no cloud account needed for the TV.

1. Make sure Home Assistant is running (Docker Desktop → `homeassistant`,
   or `docker start homeassistant`). The Smart home panel says so if not.
2. Switch the TV on, on the **same Wi-Fi** as this PC.
3. In Parzival: **Smart home → Add a TV → Find my TV**, pick it, then type
   the code the TV shows. Done — try "turn off the TV".

Smart plugs, lights, ACs, speakers etc. that you add to Home Assistant
(http://localhost:8123 → Settings → Devices & services) show up in the
Smart home panel and respond to voice automatically.

**If "Find my TV" finds nothing:** on the TV open Settings → Network &
Internet and check it's on the same Wi-Fi with a `192.168.1.x` address. If
it is but still isn't found, the router's *AP / client isolation* (often
on guest networks or one Wi-Fi band) is stopping devices from talking to
each other — turn it off, or connect the TV to the main network.

### Security

- **Pairing is encrypted and local:** the Android TV Remote protocol uses
  TLS with a per-device certificate, confirmed by the code on the TV screen.
- **Home Assistant only listens on this PC** (`127.0.0.1:8123`), so other
  devices on your Wi-Fi can't reach it.
- **The access token is encrypted at rest** with Windows DPAPI — only your
  Windows account on this PC can decrypt it — and is never shown in the UI.
- **No token over plain http:** Parzival refuses to send the token to a
  Home Assistant on another machine unless the address is `https://`.
- Parzival's own interface is local-only and protected by a per-launch key.

## The interface

- **AI core** — a holographic canvas that shows what Parzival is doing:
  calm orbits in standby, a waveform driven by your real mic level while
  listening, a radar sweep while processing, energy pulses while speaking,
  amber when the core connection is lost.
- **Conversation** — streaming replies, copy / run-again actions, live
  transcription of what you're saying.
- **Status bar** — clock, core link, mic, wake word, LLM, Home Assistant,
  and real CPU / memory readings (Win32 API; hidden if unavailable).
- **Dock** — Search & history, Applications, System, Tasks & reminders,
  Smart home, Activity (narrow windows), Settings.
- **Context panels** — current tasks, recent commands, notifications, AI
  activity, connected services.
- Responsive from phone width to ultrawide; keyboard accessible; follows
  Windows' "reduce motion" setting, plus a *Reduce visual effects* switch
  in Settings.

## Project structure

```
parzival.py               # launcher: core + local server + window
web/                      # the glass interface (HTML/CSS/JS, no build step)
├── index.html
├── css/                  # tokens, glass, layout, stage, conversation, views...
└── js/
    ├── main.js           # wires the live event stream into the UI
    ├── api.js, store.js  # server API + tiny observable store
    ├── fx/               # visual effects only: core.js (AI core), waveform,
    │                     #   starfield, pointer light/parallax, springs
    ├── ui/               # status bar, conversation, stage, dock, context, sheet
    └── views/            # search, apps, system, tasks, home, settings
backend/
├── config.py / settings.py / settings_schema.py   # tunables, overrides, editable fields
├── assistant_core.py     # the state machine: wake -> listen -> think -> speak
├── web_server.py         # local HTTP + live events API for the interface
├── wake_word.py          # grammar-restricted wake-word detector
├── hotkey.py             # global push-to-talk hotkey
├── speech_to_text.py     # Vosk + microphone
├── text_to_speech.py     # interruptible SAPI voice output
├── llm_client.py         # streaming Ollama client + persona
├── intent_parser.py      # rule-based commands (checked before the LLM)
├── tasks.py              # tasks & reminders
├── system_metrics.py     # real CPU / memory / uptime
├── device_controller.py, ha_client.py, ha_device_controller.py   # devices
├── system_control.py     # PC actions + app launchers
└── memory.py, session_logger.py, sounds.py
frontend/                 # classic Tk interface; also where your data lives
                          #   (memory.json, devices.json, tasks.json, logs/)
```

## Notes & limitations

- Windows-focused: PC control, the global hotkey, SAPI voices and the
  native window. The interface itself also opens in any modern browser
  via `--server-only` / `--browser`.
- The local server listens on 127.0.0.1 only and requires a random
  per-launch session key, so other apps and web pages can't drive Parzival.
- The small Vosk model doesn't contain the word "parzival", so the
  wake-word detector listens for sound-alikes ("percival", "parsifal",
  "perceval"). Add your own under *Extra sound-alikes* in Settings.
- Without headphones, Parzival mutes its microphone while it speaks; use
  the hotkey / Esc / stop button to interrupt.
- `settings.json` stores your Home Assistant token in plain text. It's in
  `.gitignore` — never commit or share it. The interface never displays it.
