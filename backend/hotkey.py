"""
System-wide push-to-talk hotkey ("voice invocation" without the wake word).

Uses the Win32 RegisterHotKey API through ctypes, so it needs no extra
packages and no admin rights, and works while Parzival's window is
minimized or another app has focus.
"""

import ctypes
import sys
import threading
from ctypes import wintypes

_MODIFIERS = {"alt": 0x1, "ctrl": 0x2, "control": 0x2, "shift": 0x4, "win": 0x8}
_MOD_NOREPEAT = 0x4000
_WM_HOTKEY = 0x0312
_WM_QUIT = 0x0012
_HOTKEY_ID = 1


def parse_hotkey(spec):
    """'ctrl+alt+p' -> (modifier_flags, virtual_key_code). Raises ValueError."""
    parts = [p.strip().lower() for p in str(spec).split("+") if p.strip()]
    if not parts:
        raise ValueError("Hotkey is empty")

    modifiers = 0
    for part in parts[:-1]:
        if part not in _MODIFIERS:
            raise ValueError(f"Unknown modifier '{part}' (use ctrl, alt, shift, win)")
        modifiers |= _MODIFIERS[part]

    key = parts[-1]
    if len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    elif key == "space":
        vk = 0x20
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x70 + int(key[1:]) - 1
    else:
        raise ValueError(f"Unsupported key '{key}' (use a-z, 0-9, f1-f24 or space)")

    if modifiers == 0 and not key.startswith("f"):
        raise ValueError("Add at least one modifier (e.g. ctrl+alt+p) so normal typing isn't hijacked")
    return modifiers, vk


class GlobalHotkey:
    def __init__(self, spec, callback):
        self.spec = spec
        self.error = None
        self._callback = callback
        self._thread = None
        self._thread_id = None
        self._ready = threading.Event()

    def start(self):
        if not sys.platform.startswith("win"):
            self.error = "Global hotkeys are only supported on Windows"
            return False
        try:
            self._modifiers, self._vk = parse_hotkey(self.spec)
        except ValueError as e:
            self.error = str(e)
            return False

        self._thread = threading.Thread(target=self._run, daemon=True, name="hotkey")
        self._thread.start()
        self._ready.wait(timeout=2)
        return self.error is None

    def stop(self):
        if self._thread is not None and self._thread.is_alive() and self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, _WM_QUIT, 0, 0)
            self._thread.join(timeout=1)

    def _run(self):
        user32 = ctypes.windll.user32
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()

        if not user32.RegisterHotKey(None, _HOTKEY_ID, self._modifiers | _MOD_NOREPEAT, self._vk):
            self.error = f"{self.spec} is already in use by another app - pick a different hotkey"
            self._ready.set()
            return
        self._ready.set()

        msg = wintypes.MSG()
        try:
            # GetMessageW returns 0 on WM_QUIT (sent by stop()) and -1 on error
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == _WM_HOTKEY:
                    try:
                        self._callback()
                    except Exception as e:
                        print(f"[hotkey] Callback error: {e}")
        finally:
            user32.UnregisterHotKey(None, _HOTKEY_ID)
