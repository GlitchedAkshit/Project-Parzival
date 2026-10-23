"""
Wake-word detection ("voice activation").

Vosk's small English model has a fixed vocabulary and "parzival" isn't in
it - a full-vocabulary recognizer hears it as "party will" or "portable",
so the old `"parzival" in transcript` check could never fire. Instead this
detector runs a recognizer restricted to a tiny grammar: in-vocabulary
sound-alikes of the wake word plus "[unk]" (anything else). With only a
handful of choices the decoder is cheap on CPU, rarely false-triggers, and
reports the wake word from partial results ~0.5s after you say it.

It also remembers the last few seconds of audio, so "Parzival, turn on the
light" works as one sentence: detect() hands back the audio that came
*after* the wake word, which the command recognizer then transcribes.
"""

import collections
import itertools
import json

from vosk import KaldiRecognizer

# In-vocabulary words that sound like the wake word (checked against
# vosk-model-small-en-us-0.15). Used when the wake word itself is unknown.
BUILTIN_ALIASES = {
    "parzival": ["percival", "parsifal", "perceval"],
    "parcival": ["percival", "parsifal", "perceval"],
}


class WakeWordDetector:
    def __init__(self, model, sample_rate, wake_word, extra_aliases=(), buffer_seconds=4.0):
        self._model = model
        self._sample_rate = sample_rate
        self._buffer_max = int(buffer_seconds * sample_rate)

        self.phrases = self._build_phrases(wake_word, extra_aliases)
        if not self.phrases:
            raise ValueError(
                f'The wake word "{wake_word}" isn\'t in the speech model\'s vocabulary. '
                f"Choose another word, or add a sound-alike under WAKE_WORD_ALIASES in Settings."
            )
        self._phrase_tokens = [p.split() for p in self.phrases]
        self._grammar = json.dumps(self.phrases + ["[unk]"])
        self.reset()

    # ------------------------------------------------------------------
    def _known(self, word):
        return self._model.vosk_model_find_word(word) >= 0

    def _build_phrases(self, wake_word, extra_aliases):
        """'hey parzival' -> ['hey percival', 'hey parsifal', 'hey perceval']"""
        options = []
        for word in wake_word.lower().split():
            choices = [word] if self._known(word) else BUILTIN_ALIASES.get(word, [])
            choices = [c for c in choices if self._known(c)]
            if not choices:
                options = []
                break
            options.append(choices)

        phrases = [" ".join(combo) for combo in itertools.product(*options)][:12] if options else []

        for alias in extra_aliases:
            alias = str(alias).lower().strip()
            if alias and all(self._known(w) for w in alias.split()) and alias not in phrases:
                phrases.append(alias)
            elif alias:
                print(f"[wake_word] Alias '{alias}' has words the model doesn't know - ignored")
        return phrases

    # ------------------------------------------------------------------
    def reset(self):
        """Start fresh (call after a command finishes). Word timestamps
        from Vosk count from the recognizer's creation, so the sample
        counter resets alongside it."""
        self._rec = KaldiRecognizer(self._model, self._sample_rate, self._grammar)
        self._rec.SetWords(True)
        self._rec.SetPartialWords(True)
        self._samples_fed = 0
        self._buffer = collections.deque()  # (first_sample_index, pcm_bytes)

    def detect(self, chunk):
        """Feed one chunk of 16-bit mono PCM. Returns None normally, or the
        bytes of audio recorded after the wake word once it's heard."""
        self._buffer.append((self._samples_fed, chunk))
        self._samples_fed += len(chunk) // 2
        while self._buffer and self._samples_fed - self._buffer[0][0] > self._buffer_max:
            self._buffer.popleft()

        if self._rec.AcceptWaveform(chunk):
            words = json.loads(self._rec.Result()).get("result", [])
        else:
            words = json.loads(self._rec.PartialResult()).get("partial_result", [])

        end_time = self._find_wake_end(words)
        if end_time is None:
            return None

        remainder = self._audio_after(end_time)
        self.reset()
        return remainder

    def strip_wake_word(self, text):
        """Removes a leading wake word the command recognizer may have
        caught, e.g. 'percival what time is it' -> 'what time is it'."""
        words = text.split()
        for tokens in self._phrase_tokens:
            if words[:len(tokens)] == tokens:
                return " ".join(words[len(tokens):])
        return text

    # ------------------------------------------------------------------
    def _find_wake_end(self, words):
        spoken = [w.get("word", "") for w in words]
        for tokens in self._phrase_tokens:
            n = len(tokens)
            for i in range(len(spoken) - n + 1):
                if spoken[i:i + n] == tokens:
                    return float(words[i + n - 1].get("end", 0.0))
        return None

    def _audio_after(self, seconds):
        cut = int(seconds * self._sample_rate)
        out = bytearray()
        for start, data in self._buffer:
            end = start + len(data) // 2
            if end <= cut:
                continue
            out += data[max(0, cut - start) * 2:]
        return bytes(out)
