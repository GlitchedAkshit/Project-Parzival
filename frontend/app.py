import os
import sys
import threading
import traceback

import customtkinter as ctk

_FRONTEND_DIR = os.path.dirname(os.path.abspath(__file__))
# memory.json, devices.json, logs/ and screenshots/ live next to this file,
# no matter which folder you launch the app from.
os.chdir(_FRONTEND_DIR)
sys.path.insert(0, os.path.abspath(os.path.join(_FRONTEND_DIR, "..", "backend")))

import settings
settings.apply_overrides()

import theme
from sidebar import Sidebar
from dashboard import DashboardPage
from devices_page import DevicesPage
from system_page import SystemPage
from history_page import HistoryPage
from settings_page import SettingsPage
from assistant_core import ParzivalCore
from widgets.responsive import on_resize

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

_TICK_MS = 50   # state polling; cheap because pages skip work when nothing changed


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Parzival")
        self.geometry("1200x720")
        self.minsize(720, 520)
        self.configure(fg_color=theme.BG_PRIMARY)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # The core loads the speech model on its own thread, so the window
        # shows up immediately (status: INITIALIZING) instead of freezing.
        self.core = ParzivalCore()
        self.core.start()

        self._state = None
        self._state_core = None
        self._state_version = None
        self._current = None
        self._pending_core = None
        self._reported_errors = set()

        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)

        get_core = lambda: self.core   # pages always reach the *current* core, even after a restart
        self._pages = {
            "Dashboard": DashboardPage(self._content, get_core),
            "Devices": DevicesPage(self._content, get_core),
            "System": SystemPage(self._content),
            "History": HistoryPage(self._content, get_core),
            "Settings": SettingsPage(self._content, on_restart_core=self._restart_core),
        }
        for page in self._pages.values():
            page.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.sidebar = Sidebar(self, on_navigate=self._show_page)
        self.sidebar.grid(row=0, column=0, sticky="nsw")
        self.sidebar.select("Dashboard")

        on_resize(self, self._on_window_resize)
        self.bind("<Escape>", lambda e: self.core.interrupt())

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(_TICK_MS, self._tick)

    # ------------------------------------------------------------------
    def _on_window_resize(self, width, height):
        compact = width < theme.COMPACT_SIDEBAR_BELOW
        self.sidebar.set_compact(compact)
        pad = 12 if compact else 20
        self._content.grid_configure(padx=pad, pady=pad)

    def _show_page(self, name):
        page = self._pages.get(name)
        if page is None:
            return
        if self._current and hasattr(self._pages[self._current], "set_visible"):
            self._pages[self._current].set_visible(False)
        self._current = name
        page.lift()
        if hasattr(page, "set_visible"):
            page.set_visible(True)
        if name == "Dashboard":
            page.focus_input()
        self._refresh_visible()

    def _restart_core(self, on_done=None):
        """Stops the old core and starts a fresh one (with the new
        settings) on a background thread; _tick swaps it in when ready.
        Pages are kept - the old version destroyed and rebuilt them while
        a button callback was still running, which crashed the app."""
        old = self.core

        def work():
            new = None
            try:
                old.stop()
                new = ParzivalCore()
                new.start()
            except Exception:
                traceback.print_exc()
            self._pending_core = (new, on_done)

        threading.Thread(target=work, daemon=True, name="restart").start()

    # ------------------------------------------------------------------
    def _tick(self):
        # Reschedule FIRST: an exception in a page's refresh used to kill
        # this loop for good, leaving the UI frozen on stale data.
        self.after(_TICK_MS, self._tick)
        try:
            if self._pending_core is not None:
                new, on_done = self._pending_core
                self._pending_core = None
                if new is not None:
                    self.core = new
                if on_done:
                    on_done()
            self._refresh_visible()
        except Exception as e:
            key = (type(e).__name__, str(e))
            if key not in self._reported_errors:   # log each distinct error once, not 20x/second
                self._reported_errors.add(key)
                traceback.print_exc()

    def _refresh_visible(self):
        core = self.core
        if core is not self._state_core or core.version != self._state_version:
            self._state = core.get_state()
            self._state_core = core
            self._state_version = self._state["version"]
            self.sidebar.set_status(self._state["status"])
        if self._current:
            # Only the visible page refreshes; hidden pages catch up when shown.
            self._pages[self._current].refresh(core, self._state)

    def _on_close(self):
        self.withdraw()   # disappear instantly; shutdown finishes behind the scenes
        try:
            self.core.stop()
        except Exception:
            traceback.print_exc()
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
