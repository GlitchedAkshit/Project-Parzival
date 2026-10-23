"""
Real PC control - Windows-focused. Adapted from the AI Vision Assistant
project's system_control.py. Each capability degrades gracefully if an
optional package is missing.
"""

import ctypes
import os
import subprocess
import webbrowser
from datetime import datetime

import pyautogui

try:
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities
    _PYCAW_AVAILABLE = True
except ImportError:
    _PYCAW_AVAILABLE = False


class VolumeControl:
    def __init__(self, step=0.1):
        self.step = step
        self._volume = None

        if not _PYCAW_AVAILABLE:
            print("[system_control] pycaw not installed - volume control disabled.")
            return

        try:
            device = AudioUtilities.GetSpeakers()
            if hasattr(device, "EndpointVolume"):
                # Newer pycaw API
                self._volume = device.EndpointVolume
            else:
                # Older pycaw API
                from pycaw.pycaw import IAudioEndpointVolume
                interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                self._volume = cast(interface, POINTER(IAudioEndpointVolume))
        except Exception as e:
            print(f"[system_control] Volume init failed: {e}")

    def is_ready(self):
        return self._volume is not None

    def up(self):
        if self.is_ready():
            current = self._volume.GetMasterVolumeLevelScalar()
            self._volume.SetMasterVolumeLevelScalar(min(1.0, current + self.step), None)

    def down(self):
        if self.is_ready():
            current = self._volume.GetMasterVolumeLevelScalar()
            self._volume.SetMasterVolumeLevelScalar(max(0.0, current - self.step), None)

    def toggle_mute(self):
        if self.is_ready():
            muted = bool(self._volume.GetMute())
            self._volume.SetMute(0 if muted else 1, None)
            return not muted
        return None


_volume = VolumeControl()


def take_screenshot():
    try:
        os.makedirs("screenshots", exist_ok=True)
        filename = datetime.now().strftime("screenshots/screenshot_%Y%m%d_%H%M%S.png")
        pyautogui.screenshot(filename)
        return filename
    except Exception as e:
        print(f"[system_control] Screenshot failed: {e}")
        return None


def lock_pc():
    try:
        ctypes.windll.user32.LockWorkStation()
    except Exception as e:
        print(f"[system_control] Lock failed: {e}")


def open_browser(url="https://www.google.com"):
    try:
        webbrowser.open(url)
    except Exception as e:
        print(f"[system_control] Could not open browser: {e}")


def open_file_explorer():
    try:
        subprocess.Popen("explorer")
    except Exception as e:
        print(f"[system_control] Could not open File Explorer: {e}")


_APPS = {
    "open_notepad": ("notepad.exe", "Opening Notepad."),
    "open_calculator": ("calc.exe", "Opening the calculator."),
    "open_task_manager": ("taskmgr.exe", "Opening Task Manager."),
    "open_settings": ("ms-settings:", "Opening Windows Settings."),
}


def open_app(action):
    """os.startfile goes through the Windows shell, which also handles apps
    that need elevation (Task Manager) and URI targets (ms-settings:)."""
    target, reply = _APPS[action]
    os.startfile(target)
    return reply


_VK_MEDIA_PLAY_PAUSE = 0xB3
_VK_MEDIA_NEXT_TRACK = 0xB0
_VK_MEDIA_PREV_TRACK = 0xB1


def _press_media_key(vk_code):
    try:
        user32 = ctypes.windll.user32
        user32.keybd_event(vk_code, 0, 0x1, 0)
        user32.keybd_event(vk_code, 0, 0x1 | 0x2, 0)
    except Exception as e:
        print(f"[system_control] Media key failed: {e}")


def play_pause():
    _press_media_key(_VK_MEDIA_PLAY_PAUSE)


def next_track():
    _press_media_key(_VK_MEDIA_NEXT_TRACK)


def previous_track():
    _press_media_key(_VK_MEDIA_PREV_TRACK)


def handle(action):
    """Dispatcher used by the intent parser's ('system', action) result.
    Never raises - a failed PC action shouldn't take down the voice loop."""
    try:
        return _dispatch(action)
    except Exception as e:
        print(f"[system_control] '{action}' failed: {e}")
        return "That didn't work, I'm afraid."


def _dispatch(action):
    if action == "screenshot":
        path = take_screenshot()
        return "Screenshot saved." if path else "Couldn't take a screenshot."
    elif action == "lock_pc":
        lock_pc()
        return "Locking your PC."
    elif action == "volume_up":
        _volume.up()
        return "Volume up."
    elif action == "volume_down":
        _volume.down()
        return "Volume down."
    elif action == "mute":
        muted = _volume.toggle_mute()
        return "Muted." if muted else "Unmuted."
    elif action == "open_browser":
        open_browser()
        return "Opening your browser."
    elif action == "open_explorer":
        open_file_explorer()
        return "Opening File Explorer."
    elif action in _APPS:
        return open_app(action)
    elif action == "play_pause":
        play_pause()
        return "Toggling playback."
    elif action == "next_track":
        next_track()
        return "Skipping to the next track."
    elif action == "previous_track":
        previous_track()
        return "Going back a track."
    return "I don't know how to do that yet."
