"""
Short earcons, generated in code so there are no audio files to ship:
a rising two-note chime when Parzival starts listening, and a falling one
when it gives up / you cancel. Much faster than the old spoken "Yes?",
and it doesn't talk over the start of your command.
"""

import numpy as np

_RATE = 44100


def _tone(freqs, note_seconds=0.07, volume=0.15):
    notes = []
    for freq in freqs:
        t = np.arange(int(_RATE * note_seconds)) / _RATE
        # 8ms fade-in / 20ms fade-out so the notes don't click
        envelope = np.minimum(1.0, np.minimum(t / 0.008, (note_seconds - t) / 0.02))
        notes.append(np.sin(2 * np.pi * freq * t) * envelope)
    return (np.concatenate(notes) * volume).astype(np.float32)


_START = _tone([660, 990])
_END = _tone([880, 587])


def _play(samples):
    try:
        import sounddevice as sd
        sd.play(samples, _RATE)   # non-blocking
    except Exception as e:
        print(f"[sounds] Could not play chime: {e}")


def play_start():
    _play(_START)


def play_end():
    _play(_END)
