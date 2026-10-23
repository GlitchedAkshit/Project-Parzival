import customtkinter as ctk

import config
import settings
import theme
from hotkey import parse_hotkey
from settings_schema import SECTIONS


class SettingsPage(ctk.CTkFrame):
    def __init__(self, master, on_restart_core=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._on_restart_core = on_restart_core
        self._widgets = {}
        self._restarting = False

        ctk.CTkLabel(
            self, text="Settings", font=theme.FONT_TITLE, text_color=theme.TEXT_PRIMARY
        ).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            self, text="Saved to settings.json. Voice and model changes apply after a restart (button below).",
            font=theme.FONT_SMALL, text_color=theme.TEXT_SECONDARY
        ).pack(anchor="w", pady=(0, 12))

        # Buttons first (packed at the bottom) so they never scroll out of view
        button_row = ctk.CTkFrame(self, fg_color="transparent")
        button_row.pack(side="bottom", fill="x", pady=(12, 0))

        ctk.CTkButton(
            button_row, text="Save", command=self._save, width=100,
            fg_color=theme.ACCENT_GREEN, hover_color="#00a844", text_color=theme.BG_PRIMARY
        ).pack(side="left", padx=(0, 8))

        self._restart_btn = ctk.CTkButton(
            button_row, text="Save & Restart Parzival", command=self._save_and_restart,
            fg_color=theme.ACCENT_GOLD, hover_color=theme.ACCENT_GOLD_HOVER, text_color=theme.BG_PRIMARY
        )
        self._restart_btn.pack(side="left")

        self._status_label = ctk.CTkLabel(
            button_row, text="", font=theme.FONT_SMALL, text_color=theme.TEXT_SECONDARY
        )
        self._status_label.pack(side="left", padx=12)

        scroll = ctk.CTkScrollableFrame(self, fg_color=theme.BG_CARD, corner_radius=theme.RADIUS,
                                        border_width=1, border_color=theme.BORDER, **theme.SCROLLBAR)
        scroll.pack(fill="both", expand=True)
        scroll.grid_columnconfigure(0, weight=1)

        existing = settings.load()
        row = 0
        for title, fields in SECTIONS:
            ctk.CTkLabel(scroll, text=title, font=theme.FONT_HUD, text_color=theme.ACCENT_CYAN).grid(
                row=row, column=0, columnspan=2, sticky="w", padx=14, pady=(14 if row else 8, 4))
            row += 1
            for key, label, kind in fields:
                value = existing.get(key, getattr(config, key, ""))
                ctk.CTkLabel(scroll, text=label, font=theme.FONT_BODY, text_color=theme.TEXT_PRIMARY,
                             anchor="w", justify="left").grid(row=row, column=0, sticky="ew", padx=14, pady=5)
                widget = self._make_input(scroll, kind, value)
                widget.grid(row=row, column=1, sticky="e", padx=14, pady=5)
                self._widgets[key] = (kind, widget)
                row += 1

    def _make_input(self, parent, kind, value):
        if kind == "bool":
            switch = ctk.CTkSwitch(parent, text="", progress_color=theme.ACCENT_CYAN, width=48)
            if value in (True, "true", "True", 1):
                switch.select()
            return switch

        if kind == "secret":
            frame = ctk.CTkFrame(parent, fg_color="transparent")
            entry = ctk.CTkEntry(frame, width=200, show="*")
            entry.insert(0, str(value or ""))
            entry.pack(side="left")
            ctk.CTkButton(frame, text="Show", width=54, fg_color=theme.BG_SIDEBAR, hover_color=theme.BORDER,
                          command=lambda: entry.configure(show="" if entry.cget("show") else "*")
                          ).pack(side="left", padx=(6, 0))
            frame.entry = entry
            return frame

        entry = ctk.CTkEntry(parent, width=260 if kind in ("text", "list") else 120)
        if kind == "list":
            value = ", ".join(value) if isinstance(value, (list, tuple)) else str(value or "")
        entry.insert(0, str(value))
        return entry

    def _collect_values(self):
        parsed = {}
        for key, (kind, widget) in self._widgets.items():
            if kind == "bool":
                parsed[key] = bool(widget.get())
                continue
            raw = (widget.entry if kind == "secret" else widget).get().strip()
            try:
                if kind == "int":
                    parsed[key] = int(raw)
                elif kind == "float":
                    parsed[key] = float(raw)
                elif kind == "list":
                    parsed[key] = [v.strip().lower() for v in raw.split(",") if v.strip()]
                else:
                    parsed[key] = raw
            except ValueError:
                self._show(f"'{raw}' isn't a valid number for {key}", theme.ACCENT_RED)
                return None

        if not parsed["WAKE_WORD"]:
            self._show("The wake word can't be empty", theme.ACCENT_RED)
            return None
        parsed["WAKE_WORD"] = parsed["WAKE_WORD"].lower()
        try:
            parse_hotkey(parsed["HOTKEY"])
        except ValueError as e:
            self._show(f"Hotkey: {e}", theme.ACCENT_RED)
            return None
        return parsed

    def _show(self, text, color):
        self._status_label.configure(text=text, text_color=color)

    def _save(self):
        values = self._collect_values()
        if values is None:
            return False
        try:
            settings.save(values)
        except OSError as e:
            self._show(f"Couldn't write settings.json: {e}", theme.ACCENT_RED)
            return False
        self._show("Saved.", theme.ACCENT_GREEN)
        return True

    def _save_and_restart(self):
        if self._restarting or not self._save():
            return
        if self._on_restart_core:
            self._restarting = True
            self._restart_btn.configure(state="disabled")
            self._show("Restarting Parzival...", theme.ACCENT_GOLD)
            self._on_restart_core(self._on_restarted)

    def _on_restarted(self):
        """Called on the GUI thread once the new core is running."""
        self._restarting = False
        self._restart_btn.configure(state="normal")
        self._show("Saved and restarted.", theme.ACCENT_GREEN)

    def refresh(self, core, state):
        pass
