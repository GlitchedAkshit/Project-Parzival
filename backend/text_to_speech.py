"""
Offline text-to-speech that runs on its own thread, so callers never block
and speech can be cut off mid-sentence (e.g. when you press the hotkey to
interrupt Parzival).

On Windows it drives the built-in SAPI voices directly through comtypes,
which supports instant interruption. Elsewhere it falls back to pyttsx3,
which can only stop between sentences.
"""

import math
import queue
import threading
import time

import config

_SAPI_ASYNC = 1
_SAPI_PURGE = 2
_SAPI_NOT_XML = 16   # speak "<" and "&" literally instead of parsing SAPI XML


class VoiceOutput:
    def __init__(self, enabled=True, rate=None, voice_name=None):
        self.enabled = enabled
        self._rate = rate or config.TTS_RATE
        self._voice_name = (voice_name if voice_name is not None else config.TTS_VOICE) or ""

        self._queue = queue.Queue()
        self._lock = threading.Lock()
        self._pending = 0        # sentences queued or currently being spoken
        self._generation = 0     # bumped by stop(); stale sentences are skipped
        self._thread = None

    # ------------------------------------------------------------------
    def start(self):
        if self.enabled and self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True, name="tts")
            self._thread.start()

    def say(self, text):
        """Queues text to be spoken; returns immediately."""
        if not self.enabled or not text or not text.strip():
            return
        with self._lock:
            self._pending += 1
            generation = self._generation
        self._queue.put((generation, text))

    def speak_blocking(self, text, stop_event=None):
        self.say(text)
        self.wait_until_done(stop_event)

    def is_busy(self):
        return self._pending > 0

    def wait_until_done(self, stop_event=None, timeout=None):
        waited = 0.0
        while self.is_busy():
            if stop_event is not None and stop_event.is_set():
                return False
            if timeout is not None and waited >= timeout:
                return False
            time.sleep(0.05)
            waited += 0.05
        return True

    def stop(self):
        """Silences current speech immediately and drops anything queued."""
        with self._lock:
            self._generation += 1

    def shutdown(self):
        self.stop()
        if self._thread is not None:
            self._queue.put(None)

    # ------------------------------------------------------------------
    def _run(self):
        speak = self._init_sapi() or self._init_pyttsx3()
        if speak is None:
            self.enabled = False

        while True:
            item = self._queue.get()
            if item is None:
                return
            generation, text = item
            try:
                if speak is not None and generation == self._generation:
                    speak(text, generation)
            except Exception as e:
                print(f"[text_to_speech] Speak error: {e}")
            finally:
                with self._lock:
                    self._pending -= 1

    def _init_sapi(self):
        try:
            import comtypes
            import comtypes.client
            comtypes.CoInitialize()
            voice = comtypes.client.CreateObject("SAPI.SpVoice")
        except Exception as e:
            print(f"[text_to_speech] SAPI unavailable ({e}), falling back to pyttsx3")
            return None

        # pyttsx3's words-per-minute -> SAPI's -10..10 rate scale
        voice.Rate = max(-10, min(10, round(math.log(self._rate / 156.63) / math.log(1.11))))

        if self._voice_name:
            voices = voice.GetVoices()
            for i in range(voices.Count):
                token = voices.Item(i)
                if self._voice_name.lower() in token.GetDescription().lower():
                    voice.Voice = token
                    break
            else:
                print(f"[text_to_speech] No voice matching '{self._voice_name}', using default")

        def speak(text, generation):
            voice.Speak(text, _SAPI_ASYNC | _SAPI_NOT_XML)
            while not voice.WaitUntilDone(50):
                if generation != self._generation:
                    voice.Pause()    # silences the audio instantly...
                    voice.Speak("", _SAPI_ASYNC | _SAPI_PURGE)   # ...then drop the rest (slower)
                    voice.Resume()
                    return

        return speak

    def _init_pyttsx3(self):
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", self._rate)
            if self._voice_name:
                for v in engine.getProperty("voices"):
                    if self._voice_name.lower() in v.name.lower():
                        engine.setProperty("voice", v.id)
                        break
        except Exception as e:
            print(f"[text_to_speech] Could not initialize TTS: {e}")
            return None

        def speak(text, generation):
            engine.say(text)
            engine.runAndWait()

        return speak
