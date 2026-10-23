"""
Offline speech-to-text via Vosk, streaming from the microphone.

Vosk runs fully locally (no internet, no cloud API) - you just need to
download a model once from https://alphacephei.com/vosk/models and point
config.VOSK_MODEL_PATH at the extracted folder. The "small" English model
(~50MB) is plenty for wake-word + short command recognition.
"""

import math
import os
import queue

import numpy as np
import sounddevice as sd
from vosk import Model, KaldiRecognizer, SetLogLevel

import config

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))

SetLogLevel(-1)  # Vosk's Kaldi logging is very chatty


class SpeechEngine:
    """Wraps a Vosk model + a live microphone stream. Call start_stream()
    once, then repeatedly get_audio_chunk() and feed it to a recognizer
    (see assistant_core.py for the actual recognition loop - this class
    only owns the audio plumbing)."""

    # 0.1s of audio per chunk. Smaller chunks = the recognizer sees speech
    # sooner, which is what makes the wake word and partial transcripts
    # feel instant (the old 0.5s chunks added up to half a second of lag).
    BLOCK_SIZE = 1600

    def __init__(self, model_path=None, sample_rate=None):
        self.sample_rate = sample_rate or config.SAMPLE_RATE

        resolved_path = model_path or config.VOSK_MODEL_PATH
        if not os.path.isabs(resolved_path):
            # Resolve relative to backend/, not the process's CWD, so
            # this works whether you launch from frontend/, backend/, or
            # the project root.
            resolved_path = os.path.join(_BACKEND_DIR, resolved_path)

        if not os.path.isdir(resolved_path):
            raise FileNotFoundError(
                f"Vosk model not found at: {resolved_path}\n"
                f"Download it from https://alphacephei.com/vosk/models and "
                f"place it at backend/models/vosk-model-small-en-us-0.15"
            )

        self.model = Model(resolved_path)
        # Bounded so a stalled consumer can never pile up minutes of audio
        # (~20s max); the oldest audio is dropped first.
        self._audio_queue = queue.Queue(maxsize=200)
        self._stream = None
        self._muted = False
        self.level = 0.0  # 0..1 loudness of the latest chunk, for the UI

    def _callback(self, indata, frames, time_info, status):
        data = bytes(indata)

        samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
        rms = float(np.sqrt(np.mean(samples * samples))) / 32768.0 if samples.size else 0.0
        db = 20 * math.log10(rms + 1e-9)
        self.level = min(1.0, max(0.0, (db + 60) / 45))  # -60 dB -> 0, -15 dB -> 1

        if self._muted:
            return
        try:
            self._audio_queue.put_nowait(data)
        except queue.Full:
            try:
                self._audio_queue.get_nowait()
                self._audio_queue.put_nowait(data)
            except (queue.Empty, queue.Full):
                pass

    def start_stream(self):
        self._stream = sd.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=self.BLOCK_SIZE,
            dtype="int16",
            channels=1,
            callback=self._callback,
            device=config.MIC_DEVICE_INDEX,
        )
        self._stream.start()

    def stop_stream(self):
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                print(f"[speech_to_text] Error closing mic stream: {e}")
            self._stream = None

    def set_muted(self, muted):
        """While muted, mic audio is discarded - used while Parzival is
        speaking so it doesn't hear (and react to) its own voice."""
        self._muted = muted
        if muted:
            self.flush()

    def flush(self):
        while True:
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                return

    def new_recognizer(self, grammar=None):
        if grammar:
            return KaldiRecognizer(self.model, self.sample_rate, grammar)
        return KaldiRecognizer(self.model, self.sample_rate)

    def get_audio_chunk(self, timeout=1.0):
        try:
            return self._audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None
