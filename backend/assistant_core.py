"""
Parzival's core state machine:

    IDLE (waiting for the wake word, the hotkey, the mic button, or typing)
      -> LISTENING (recording your command; live words show up in the UI)
      -> THINKING (rule-based intent parsing, or streaming from the LLM)
      -> SPEAKING (text-to-speech reply - interruptible at any moment)
      -> optional follow-up LISTENING (after a conversational reply, so you
         can answer Parzival's question without saying the wake word again)
      -> back to IDLE

All voice work runs on one background thread (the "voice loop"). The GUI
never blocks on it: activate() / interrupt() / submit_text_command() /
set_wake_enabled() just post events and return immediately, and the GUI
polls get_state() - a cheap snapshot with a `version` number that only
changes when something actually changed, so idle redraws cost nothing.
"""

import json
import queue
import re
import threading
import time
import traceback

import config
import settings
import sounds
import system_control
from device_controller import DeviceController
from ha_device_controller import HADeviceController
from hotkey import GlobalHotkey
from intent_parser import parse_intent
from llm_client import OllamaClient, LLMError, clean_reply
from memory import ConversationMemory
from session_logger import SessionLogger
from tasks import TaskStore
from text_to_speech import VoiceOutput

# Vosk tends to "hear" these in background noise - never treat them as a command.
_FILLER = {"", "the", "a", "huh", "uh", "um", "hmm", "mm", "ah", "oh", "i", "and", "but", "so", "it"}

# End of a sentence followed by whitespace, e.g. 'done. ' or 'really?" '
_SENTENCE_END = re.compile(r"[.!?]+[\"')\]”]*\s+")


def _as_list(value):
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return list(value or [])


class ParzivalCore:
    def __init__(self):
        self._lock = threading.Lock()
        self._state = {
            "status": "loading",     # loading / idle / listening / thinking / speaking
            "partial": "",           # words recognized so far while you're talking
            "reply_draft": "",       # Parzival's reply as the LLM streams it in
            "last_heard": "",
            "last_reply": "",
            "transcript": [],        # [{"id", "role": "user"/"assistant", "text", "ts"}]
            "voice_error": None,     # mic / speech model / wake word problems
            "notice": "",            # one-line hint for the UI
            "wake_enabled": bool(config.WAKE_WORD_ENABLED),
            "wake_phrases": [],
            "hotkey": config.HOTKEY,
            "hotkey_error": None,
            "llm_status": "checking",
            "ha_status": "off",      # off / connected / unreachable
            "mic_ready": False,
            "activity": [],          # [{"id", "ts", "kind", "text"}] what Parzival did, newest last
            "notifications": [],     # [{"id", "ts", "level", "text"}] info / warn / error / reminder
        }
        self._version = 0
        self._entry_id = 0
        self._feed_id = 0

        self._events = queue.Queue()
        self._stop_event = threading.Event()
        self._interrupt = threading.Event()
        self._voice_thread = None
        self._started = False

        self.memory = ConversationMemory(config.MEMORY_FILE, config.MAX_HISTORY_MESSAGES)
        self.ha = HADeviceController()          # real devices, if Home Assistant is reachable
        self.devices = DeviceController(config.DEVICES_FILE)  # simulated fallback
        self.tasks = TaskStore(config.TASKS_FILE)
        self.llm = OllamaClient()
        self.logger = SessionLogger(config.SESSION_LOGGING_ENABLED, config.LOG_DIR)
        self.voice = VoiceOutput(config.TTS_ENABLED)
        self.hotkey = GlobalHotkey(config.HOTKEY, self.activate)

        # Created on the voice thread - loading the Vosk model takes a
        # second or two and used to freeze the window at startup.
        self.speech = None
        self.wake = None

    # ==================================================================
    # Lifecycle
    # ==================================================================
    def start(self):
        if self._started:
            return
        self._started = True
        self.voice.start()

        self._voice_thread = threading.Thread(target=self._voice_loop, daemon=True, name="voice-loop")
        self._voice_thread.start()
        threading.Thread(target=self._ha_loop, daemon=True, name="home-assistant").start()
        threading.Thread(target=self._llm_loop, daemon=True, name="llm-warmup").start()
        threading.Thread(target=self._reminder_loop, daemon=True, name="reminders").start()

        if not self.hotkey.start():
            self._update(hotkey_error=self.hotkey.error)
            self._notify("warn", f"Hotkey unavailable: {self.hotkey.error}")

    def stop(self):
        self._stop_event.set()
        self.interrupt()
        self.ha.refresh_requested.set()   # wake the HA thread so it notices the stop
        self.hotkey.stop()
        if self._voice_thread is not None:
            self._voice_thread.join(timeout=2)
        self.voice.shutdown()
        if self.speech is not None:
            self.speech.stop_stream()
        self.logger.close()

    # ==================================================================
    # Thread-safe API for the GUI / hotkey
    # ==================================================================
    def submit_text_command(self, text):
        """Typed command - processed on the voice thread like a spoken one.
        Cuts off whatever Parzival is currently saying."""
        self.interrupt()
        self._events.put(("text", text))

    def activate(self):
        """Push-to-talk (global hotkey or the mic button). Starts listening
        right away; pressed while listening, it cancels; pressed while
        Parzival is thinking/speaking, it cuts the reply off and listens."""
        if self._state["status"] == "listening":
            self.interrupt()
            return
        self.interrupt()
        self._events.put(("listen", None))

    def interrupt(self):
        """Stop talking / thinking / listening right now."""
        self._interrupt.set()
        self.voice.stop()

    def set_wake_enabled(self, enabled):
        self._update(wake_enabled=bool(enabled))
        try:
            settings.save({"WAKE_WORD_ENABLED": bool(enabled)})
        except Exception as e:
            print(f"[assistant_core] Could not save wake word setting: {e}")

    def clear_transcript(self):
        """Clears this session's on-screen conversation. Long-term memory
        (what the LLM remembers) is kept - see memory.clear() for that."""
        with self._lock:
            self._state["transcript"] = []
            self._state["last_heard"] = self._state["last_reply"] = ""
            self._version += 1

    def clear_notifications(self):
        self._update(notifications=[])

    def get_state(self):
        with self._lock:
            snapshot = dict(self._state)
            snapshot["transcript"] = list(self._state["transcript"])
            snapshot["version"] = self._version
        return snapshot

    @property
    def version(self):
        return self._version

    @property
    def status(self):
        return self._state["status"]

    def mic_level(self):
        speech = self.speech
        return speech.level if speech is not None else 0.0

    # ---- devices (GUI side) -------------------------------------------
    def get_devices(self):
        """Returns ("home-assistant" | "simulated", {name: device}). Never blocks."""
        if self.ha.is_available():
            return "home-assistant", self.ha.get_all()
        return "simulated", self.devices.get_all()

    def devices_revision(self):
        return (self.devices.revision, self.ha.revision, self.ha.is_available())

    def set_device(self, name, updates):
        if self.ha.is_available():
            # Network call - keep it off the GUI thread
            threading.Thread(target=self.ha.set_device_gui, args=(name, updates), daemon=True).start()
        else:
            self.devices.set_device_gui(name, updates)

    # ==================================================================
    # State helpers
    # ==================================================================
    def _update(self, **changes):
        with self._lock:
            changed = False
            for key, value in changes.items():
                if self._state.get(key) != value:
                    self._state[key] = value
                    changed = True
            if changed:
                self._version += 1

    def _push_transcript(self, role, text):
        with self._lock:
            self._entry_id += 1
            self._state["transcript"].append(
                {"id": self._entry_id, "role": role, "text": text, "ts": time.time()}
            )
            self._state["transcript"] = self._state["transcript"][-50:]
            self._state["last_heard" if role == "user" else "last_reply"] = text
            if role == "assistant":
                self._state["reply_draft"] = ""
            self._version += 1

    def _feed(self, key, limit, **entry):
        with self._lock:
            self._feed_id += 1
            items = self._state[key] + [dict(entry, id=self._feed_id, ts=time.time())]
            self._state[key] = items[-limit:]
            self._version += 1

    def _log(self, kind, text):
        """AI activity timeline (shown in the UI's Activity panel)."""
        self._feed("activity", 40, kind=kind, text=text)

    def _notify(self, level, text):
        """System notification. A repeat of the latest one is dropped."""
        latest = self._state["notifications"][-1:]
        if latest and latest[0]["text"] == text:
            return
        self._feed("notifications", 20, level=level, text=text)

    def _set_llm_status(self, status):
        previous = self._state["llm_status"]
        if status != previous:
            if status == "offline":
                self._notify("warn", "Ollama isn't running - conversation is offline, commands still work.")
            elif status == "missing-model":
                self._notify("warn", f"Model '{self.llm.model}' isn't installed - run: ollama pull {self.llm.model}")
            elif status == "ready" and previous != "checking":
                self._notify("info", f"Language model {self.llm.model} is online.")
        self._update(llm_status=status)

    # ==================================================================
    # Background threads
    # ==================================================================
    def _voice_loop(self):
        self._init_voice()

        while not self._stop_event.is_set():
            try:
                event = self._next_event()
                if event is not None:
                    self._handle_event(event)
                    continue

                if self.speech is None:
                    continue
                chunk = self.speech.get_audio_chunk(timeout=0.1)
                if chunk is None or self.wake is None or not self._state["wake_enabled"]:
                    continue

                remainder = self.wake.detect(chunk)
                if remainder is not None:
                    self.logger.log("wake", "")
                    self._log("wake", "Wake word detected")
                    self._session(initial_audio=remainder, by_voice=True)
            except Exception as e:
                traceback.print_exc()
                self._update(notice=f"Recovered from an error: {e}")
                self._finish_session()
                time.sleep(0.2)

    def _init_voice(self):
        try:
            from speech_to_text import SpeechEngine   # imports vosk/sounddevice
            self.speech = SpeechEngine()
            self.speech.start_stream()
        except Exception as e:
            self.speech = None
            message = f"Microphone/speech engine failed to start: {e}"
            print(f"[assistant_core] {message}")
            self._update(status="idle", voice_error=message,
                         notice="Voice input is off - you can still type commands.")
            self._notify("error", "Microphone unavailable - voice input is off. You can still type commands.")
            return

        try:
            from wake_word import WakeWordDetector
            self.wake = WakeWordDetector(
                self.speech.model, self.speech.sample_rate,
                str(config.WAKE_WORD).strip().lower(), _as_list(config.WAKE_WORD_ALIASES),
            )
            self._update(wake_phrases=self.wake.phrases)
            print(f"[assistant_core] Wake word ready - listening for {self.wake.phrases}")
        except Exception as e:
            self.wake = None
            self._update(voice_error=str(e))
            self._notify("warn", str(e))

        self._update(status="idle", mic_ready=True)

    def _next_event(self):
        try:
            if self.speech is None:
                return self._events.get(timeout=0.2)
            return self._events.get_nowait()
        except queue.Empty:
            return None

    def _handle_event(self, event):
        kind, payload = event
        self._interrupt.clear()
        if kind == "text":
            self._session(first_text=payload, by_voice=False)
        elif kind == "listen":
            if self.speech is None:
                self._update(notice="Voice input isn't available - type your command instead.")
                return
            self._log("listen", "Listening (push-to-talk)")
            self._session(by_voice=True)
        elif kind == "announce":
            self._announce(payload)

    def _announce(self, text):
        """Speaks something Parzival brings up on its own (a due reminder)."""
        if self.speech is not None:
            self.speech.set_muted(True)
        self._push_transcript("assistant", text)
        self._say(text)
        self.voice.wait_until_done(self._interrupt)
        self._finish_session()

    def _ha_loop(self):
        while not self._stop_event.is_set():
            if self.ha.security_error:
                status = "insecure"
            elif self.ha.is_configured():
                self.ha.poll()
                status = "connected" if self.ha.is_available() else "unreachable"
            else:
                status = "off"
            previous = self._state["ha_status"]
            if status != previous and status == "insecure":
                self._notify("error", self.ha.security_error)
            if status != previous and status == "connected":
                self._notify("info", "Connected to Home Assistant.")
            elif status != previous and status == "unreachable":
                self._notify("warn", "Home Assistant is unreachable - using simulated devices.")
            self._update(ha_status=status)
            self.ha.refresh_requested.wait(timeout=config.HA_POLL_SECONDS)
            self.ha.refresh_requested.clear()

    def _llm_loop(self):
        """Pre-loads the model so the first question is fast, and keeps
        re-checking (every 20s) until Ollama is up with the model pulled."""
        while not self._stop_event.is_set():
            self._set_llm_status(self.llm.warm_up())
            if self.llm.status == "ready":
                return
            self._stop_event.wait(20)

    # ==================================================================
    # One interaction: listen -> think -> speak (-> follow-up)
    # ==================================================================
    def _session(self, first_text=None, initial_audio=b"", by_voice=True):
        text = first_text
        start_timeout = config.COMMAND_START_TIMEOUT
        chime = by_voice and config.WAKE_CHIME
        try:
            while not self._stop_event.is_set():
                if text is None:
                    if chime:
                        sounds.play_start()
                        chime = False
                    text = self._listen(initial_audio, start_timeout)
                    initial_audio = b""
                    if text is None:
                        break

                wants_follow_up = self._respond(text)
                text = None
                if not (wants_follow_up and by_voice and self.speech is not None
                        and config.FOLLOW_UP_SECONDS > 0):
                    break
                start_timeout = config.FOLLOW_UP_SECONDS
        finally:
            self._finish_session()

    def _finish_session(self):
        self._update(status="idle", partial="", reply_draft="")
        if self.speech is not None:
            self.speech.set_muted(False)
        if self.wake is not None:
            self.wake.reset()

    def _listen(self, initial_audio, start_timeout):
        """Records one command. Returns its text, or None if you said
        nothing / cancelled / something else (typing, hotkey) took over."""
        self.speech.set_muted(False)
        self._update(status="listening", partial="")

        recognizer = self.speech.new_recognizer()
        pending = [initial_audio] if initial_audio else []
        started = last_speech = last_change = time.time()
        last_partial = ""

        while True:
            if self._stop_event.is_set() or self._interrupt.is_set() or not self._events.empty():
                if self._interrupt.is_set():
                    sounds.play_end()
                return None

            now = time.time()
            if now - last_speech > start_timeout:
                sounds.play_end()
                return None
            if now - started > config.MAX_COMMAND_SECONDS:
                return self._clean(json.loads(recognizer.FinalResult()).get("text", "")) or None

            chunk = pending.pop(0) if pending else self.speech.get_audio_chunk(timeout=0.1)
            if chunk is None:
                continue

            if recognizer.AcceptWaveform(chunk):
                text = self._clean(json.loads(recognizer.Result()).get("text", ""))
                if text:
                    return text
                last_partial = ""
                self._update(partial="")
                continue

            partial = json.loads(recognizer.PartialResult()).get("partial", "")
            if partial != last_partial:
                last_partial, last_change = partial, now
                cleaned = self._clean(partial)
                if cleaned:
                    last_speech = now
                self._update(partial=cleaned)
            elif partial and now - last_change > config.SILENCE_TIMEOUT:
                text = self._clean(partial)
                if text:
                    return text

    def _clean(self, text):
        text = text.strip().lower()
        if self.wake is not None:
            text = self.wake.strip_wake_word(text)
        return "" if text in _FILLER else text

    def _respond(self, text):
        """Handles one command. Returns True if Parzival should listen for
        a follow-up afterwards (i.e. it was a conversational reply)."""
        if self.speech is not None:
            self.speech.set_muted(True)   # don't let Parzival hear itself

        intent = parse_intent(text)
        if intent is not None and intent[0] == "cancel":
            sounds.play_end()
            self._log("cancel", "Cancelled")
            return False

        self._push_transcript("user", text)
        self.logger.log("heard", text)
        self._update(status="thinking", partial="", reply_draft="")

        follow_up = False
        try:
            if intent is None:
                reply, follow_up = self._converse(text)
            else:
                reply = self._run_intent(intent)
                self._say(reply)
        except Exception as e:
            traceback.print_exc()
            reply = "Something went wrong on my end."
            self._say(reply)
            print(f"[assistant_core] Command failed: {e}")

        self._push_transcript("assistant", reply)
        self.logger.log("replied", reply)

        self.voice.wait_until_done(self._interrupt)
        if self._interrupt.is_set():
            self.voice.stop()
            self._log("interrupt", "Reply interrupted")
            return False
        time.sleep(0.15)   # let the speaker's echo die down before reopening the mic
        return follow_up

    def _say(self, text):
        if self.voice.enabled and text:
            self.voice.say(text)
            self._update(status="speaking")

    def _converse(self, text):
        """Streams an LLM reply, speaking each sentence as soon as it's
        complete. Returns (reply, succeeded)."""
        history = self.memory.get_context() + [{"role": "user", "content": text}]
        reply = ""
        spoken_upto = 0
        started = time.time()

        try:
            for piece in self.llm.chat_stream(history, self._interrupt):
                reply += piece
                self._update(reply_draft=reply.lstrip(" \"“"))
                for match in _SENTENCE_END.finditer(reply, spoken_upto):
                    end = match.end()
                    self._say(reply[spoken_upto:end].strip(" \"“”\n"))
                    spoken_upto = end
        except LLMError as e:
            self._set_llm_status(self.llm.status)
            message = str(e)
            self._log("error", message)
            self._say(message)
            return message, False

        self._set_llm_status(self.llm.status)
        if not self._interrupt.is_set():
            self._say(reply[spoken_upto:].strip(" \"“”\n"))

        reply = clean_reply(reply)
        if reply:
            self.memory.add("user", text)
            self.memory.add("assistant", reply)
            self._log("reply", f"Answered with {self.llm.model} in {time.time() - started:.1f}s")
        return reply or "...", bool(reply)

    def _run_intent(self, intent):
        action, args = intent
        reply = self._dispatch_intent(action, args)
        self._log(action, reply)
        return reply

    def _dispatch_intent(self, action, args):
        if action == "device":
            if self.ha.is_available():
                return self.ha.handle(args)
            if args.get("device", "").strip() in ("tv", "television", "the tv", "my tv"):
                return self._tv_not_connected()
            return self.devices.handle(args)
        elif action == "tv":
            if not self.ha.is_available():
                return self._tv_not_connected()
            return self.ha.handle_tv(args)
        elif action == "system":
            return system_control.handle(args)
        elif action == "reminder":
            self.tasks.add(args["text"], due=args["due"])
            return f"I'll remind you to {args['text']} in {_describe_seconds(args['seconds'])}."
        elif action == "task_add":
            self.tasks.add(args["text"])
            return f"Added {args['text']} to your tasks."
        elif action == "task_list":
            pending = self.tasks.pending()
            if not pending:
                return "Your task list is empty."
            names = [t["text"] for t in pending[:5]]
            more = f", and {len(pending) - 5} more" if len(pending) > 5 else ""
            count = f"{len(pending)} task{'s' if len(pending) != 1 else ''}"
            return f"You have {count}: " + "; ".join(names) + more + "."
        elif action == "time":
            now = time.localtime()
            return f"It's {int(time.strftime('%I', now))}:{time.strftime('%M %p', now)}."
        elif action == "date":
            now = time.localtime()
            return f"Today is {time.strftime('%A, %B', now)} {now.tm_mday}."

        return "I'm not sure how to do that yet."

    def _tv_not_connected(self):
        if self.ha.security_error:
            return "I won't talk to Home Assistant over an insecure connection. Check its address in Settings."
        if not self.ha.is_configured():
            return "Your TV isn't connected yet. Add your Home Assistant token in Settings first."
        return "I can't reach Home Assistant right now, so the TV is out of reach. Is it running?"

    def _reminder_loop(self):
        while not self._stop_event.wait(1.0):
            for task in self.tasks.pop_due():
                text = f"Reminder: {task['text']}."
                self._notify("reminder", text)
                self._log("reminder", text)
                self._events.put(("announce", text))


def _describe_seconds(seconds):
    for unit, size in (("hour", 3600), ("minute", 60)):
        if seconds >= size and seconds % size == 0:
            n = seconds // size
            return f"{n} {unit}{'s' if n != 1 else ''}"
    if seconds >= 60:
        return f"{seconds // 60} minutes and {seconds % 60} seconds"
    return f"{seconds} second{'s' if seconds != 1 else ''}"
