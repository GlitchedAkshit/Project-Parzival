import threading

import customtkinter as ctk

import system_control
import theme
from widgets.responsive import on_resize

_MIN_BUTTON_WIDTH = 200


class SystemPage(ctk.CTkFrame):
    """Direct buttons for real PC control - the same actions Parzival can
    trigger by voice, available here for quick manual use/testing. Actions
    run on a worker thread (a screenshot takes long enough to hitch the UI)
    and report back what happened."""

    ACTIONS = [
        ("Screenshot", "screenshot"),
        ("Lock PC", "lock_pc"),
        ("Open Browser", "open_browser"),
        ("Open File Explorer", "open_explorer"),
        ("Volume Up", "volume_up"),
        ("Volume Down", "volume_down"),
        ("Toggle Mute", "mute"),
        ("Play / Pause", "play_pause"),
        ("Next Track", "next_track"),
        ("Previous Track", "previous_track"),
    ]

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._columns = 2
        self._result = None

        ctk.CTkLabel(
            self, text="System Control", font=theme.FONT_TITLE, text_color=theme.TEXT_PRIMARY
        ).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            self, text="Real actions on this PC, same as Parzival can trigger by voice.",
            font=theme.FONT_SMALL, text_color=theme.TEXT_SECONDARY
        ).pack(anchor="w", pady=(0, 16))

        self._grid = ctk.CTkFrame(self, fg_color=theme.BG_CARD, corner_radius=theme.RADIUS,
                                  border_width=1, border_color=theme.BORDER)
        self._grid.pack(fill="x")

        self._buttons = [
            ctk.CTkButton(self._grid, text=label, height=40, command=lambda a=action: self._run(a),
                          fg_color=theme.BG_SIDEBAR, hover_color=theme.BORDER, font=theme.FONT_BODY)
            for label, action in self.ACTIONS
        ]
        self._layout()

        self._status = ctk.CTkLabel(self, text="", font=theme.FONT_SMALL, text_color=theme.TEXT_SECONDARY,
                                    anchor="w", justify="left")
        self._status.pack(anchor="w", pady=(10, 0))

        on_resize(self, self._on_resize)

    def _on_resize(self, width, height):
        columns = max(1, min(4, int(width // _MIN_BUTTON_WIDTH)))
        if columns != self._columns:
            self._columns = columns
            self._layout()

    def _layout(self):
        for col in range(4):
            self._grid.grid_columnconfigure(col, weight=1 if col < self._columns else 0,
                                            uniform="btn" if col < self._columns else "")
        for i, btn in enumerate(self._buttons):
            btn.grid(row=i // self._columns, column=i % self._columns, sticky="ew", padx=10, pady=8)

    def _run(self, action):
        self._status.configure(text="Working...", text_color=theme.TEXT_SECONDARY)

        def work():
            if action == "screenshot":
                path = system_control.take_screenshot()
                self._result = f"Screenshot saved to {path}" if path else "Couldn't take a screenshot."
            else:
                self._result = system_control.handle(action)

        threading.Thread(target=work, daemon=True).start()

    def refresh(self, core, state):
        if self._result is not None:   # hand the worker's result to the GUI thread
            self._status.configure(text=self._result, text_color=theme.ACCENT_GREEN)
            self._result = None
