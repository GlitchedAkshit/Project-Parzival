import time

import customtkinter as ctk

import config
import theme
from widgets.icons import icon
from widgets.orb import CoreOrb
from widgets.responsive import on_resize
from widgets.stat_card import StatCard


def _pretty_hotkey(spec):
    return "+".join(p.strip().capitalize() for p in str(spec).split("+"))


class DashboardPage(ctk.CTkFrame):
    """Animated status core + live conversation transcript + controls for
    voice activation (wake word on/off, push-to-talk, stop) + a typed
    command box. Lays itself out side-by-side on wide windows and stacked
    on narrow ones."""

    def __init__(self, master, get_core, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._get_core = get_core
        self._stacked = None
        self._seen_core = None
        self._seen_version = None
        self._last_entry_id = 0
        self._live_index = None
        self._live_key = None
        self._action_mode = None

        self._build_log_card()
        self._build_status_panel()

        on_resize(self, self._apply_layout)
        self._apply_layout(900, 600)

    # ==================================================================
    # Construction
    # ==================================================================
    def _build_log_card(self):
        card = self._log_card = ctk.CTkFrame(self, fg_color=theme.BG_CARD, corner_radius=theme.RADIUS,
                                             border_width=1, border_color=theme.BORDER)
        card.grid_rowconfigure(1, weight=1)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card, text="CONVERSATION LOG", font=theme.FONT_HUD, text_color=theme.ACCENT_CYAN
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 4))

        box = self._box = ctk.CTkTextbox(
            card, fg_color=theme.BG_SECONDARY, corner_radius=theme.RADIUS,
            font=theme.FONT_BODY, text_color=theme.TEXT_PRIMARY, wrap="word", **theme.SCROLLBAR,
        )
        box.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 8))
        box.tag_config("who_user", foreground=theme.ACCENT_GOLD, spacing1=10)
        box.tag_config("who_bot", foreground=theme.ACCENT_CYAN, spacing1=10)
        box.tag_config("time", foreground=theme.TEXT_MUTED)
        box.tag_config("body", foreground=theme.TEXT_PRIMARY, spacing3=4, lmargin1=2, lmargin2=2)
        box.tag_config("live", foreground=theme.TEXT_SECONDARY, spacing3=4, lmargin1=2, lmargin2=2)
        box.configure(state="disabled")

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 14))
        row.grid_columnconfigure(0, weight=1)

        self._input = ctk.CTkEntry(row, placeholder_text="Type a command instead of speaking...",
                                   height=36, font=theme.FONT_BODY)
        self._input.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._input.bind("<Return>", lambda e: self._submit_text())

        send_icon = icon(theme.ICONS["send"], theme.BG_PRIMARY, 16)
        ctk.CTkButton(
            row, text="" if send_icon else "SEND", image=send_icon, width=44 if send_icon else 70,
            height=36, command=self._submit_text, fg_color=theme.ACCENT_CYAN,
            hover_color=theme.ACCENT_CYAN_HOVER, text_color=theme.BG_PRIMARY, font=theme.FONT_HUD,
        ).grid(row=0, column=1)

    def _build_status_panel(self):
        panel = self._panel = ctk.CTkFrame(self, fg_color="transparent")
        panel.grid_columnconfigure(0, weight=1)

        card = self._orb_card = ctk.CTkFrame(panel, fg_color=theme.BG_CARD, corner_radius=theme.RADIUS,
                                             border_width=1, border_color=theme.BORDER)
        card.grid(row=0, column=0, sticky="ew")

        self._orb = CoreOrb(card, size=170, level_source=lambda: self._get_core().mic_level())

        info = self._info = ctk.CTkFrame(card, fg_color="transparent")

        self._status_text = ctk.CTkLabel(info, text="INITIALIZING", font=(theme.FONT_HUD[0], 14, "bold"),
                                         text_color=theme.TEXT_SECONDARY)
        self._status_text.pack(pady=(0, 2))

        self._hint = ctk.CTkLabel(info, text="", font=theme.FONT_SMALL, text_color=theme.TEXT_SECONDARY)
        self._hint.pack(pady=(0, 10))

        self._action_btn = ctk.CTkButton(info, text="", height=36, width=170, font=theme.FONT_HUD,
                                         command=self._on_action)
        self._action_btn.pack(pady=(0, 10))

        self._wake_switch = ctk.CTkSwitch(info, text="Wake word", font=theme.FONT_SMALL,
                                          text_color=theme.TEXT_SECONDARY, progress_color=theme.ACCENT_CYAN,
                                          command=self._on_wake_toggle)
        self._wake_switch.pack(pady=(0, 10))

        chips = ctk.CTkFrame(info, fg_color="transparent")
        chips.pack(pady=(0, 6))
        self._chips = {}
        for key in ("MIC", "LLM", "HOME"):
            label = ctk.CTkLabel(chips, text=f"● {key}", font=theme.FONT_HUD,
                                 text_color=theme.TEXT_MUTED)
            label.pack(side="left", padx=6)
            self._chips[key] = label

        self._error_label = ctk.CTkLabel(info, text="", font=theme.FONT_SMALL, text_color=theme.ACCENT_GOLD,
                                         wraplength=230, justify="center")
        self._error_label.pack(pady=(0, 4))

        self.card_heard = StatCard(panel, "LAST HEARD")
        self.card_reply = StatCard(panel, "LAST REPLY")

    # ==================================================================
    # Responsive layout
    # ==================================================================
    def _apply_layout(self, width, height):
        stacked = width < theme.STACK_DASHBOARD_BELOW
        show_cards = not stacked and height >= 560

        if stacked != self._stacked:
            self._stacked = stacked
            for w in (self._log_card, self._panel, self._orb, self._info):
                w.grid_forget()
            for i in range(2):
                self.grid_columnconfigure(i, weight=0, minsize=0)
                self.grid_rowconfigure(i, weight=0)
                self._orb_card.grid_columnconfigure(i, weight=0)

            if stacked:
                self.grid_columnconfigure(0, weight=1)
                self.grid_rowconfigure(1, weight=1)
                self._panel.grid(row=0, column=0, sticky="ew", pady=(0, 12))
                self._log_card.grid(row=1, column=0, sticky="nsew")
                self._orb_card.grid_columnconfigure(1, weight=1)
                self._orb.resize(120)
                self._orb.grid(row=0, column=0, padx=(16, 8), pady=12)
                self._info.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=12)
            else:
                self.grid_columnconfigure(0, weight=1)
                self.grid_columnconfigure(1, weight=0, minsize=270)
                self.grid_rowconfigure(0, weight=1)
                self._log_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
                self._panel.grid(row=0, column=1, sticky="nsew")
                self._orb_card.grid_columnconfigure(0, weight=1)
                self._orb.resize(170)
                self._orb.grid(row=0, column=0, pady=(18, 8))
                self._info.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))

        if show_cards:
            self.card_heard.grid(row=1, column=0, sticky="ew", pady=(10, 0))
            self.card_reply.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        else:
            self.card_heard.grid_forget()
            self.card_reply.grid_forget()

    # ==================================================================
    # User actions
    # ==================================================================
    def _submit_text(self):
        text = self._input.get().strip()
        if text:
            self._get_core().submit_text_command(text)
            self._input.delete(0, "end")

    def _on_action(self):
        core = self._get_core()
        if self._action_mode == "stop":
            core.interrupt()
        elif self._action_mode in ("talk", "cancel"):
            core.activate()

    def _on_wake_toggle(self):
        self._get_core().set_wake_enabled(bool(self._wake_switch.get()))

    def focus_input(self):
        self._input.focus_set()

    def set_visible(self, visible):
        self._orb.set_visible(visible)

    # ==================================================================
    # Refresh (called by the app's tick only when the state changed)
    # ==================================================================
    def refresh(self, core, state):
        if core is self._seen_core and state["version"] == self._seen_version:
            return   # nothing changed since the last frame - skip all redraw work
        self._seen_version = state["version"]
        if core is not self._seen_core:
            self._seen_core = core
            self._reset_transcript()

        status = state["status"]
        color = theme.STATUS_COLORS.get(status, theme.ACCENT_CYAN_DIM)
        self._orb.set_status(status)
        self._status_text.configure(text=theme.STATUS_LABELS.get(status, status.upper()), text_color=color)

        self._refresh_controls(state)
        self._refresh_chips(state)

        self.card_heard.set_value(state.get("last_heard") or "-")
        self.card_reply.set_value(state.get("last_reply") or "-")

        self._refresh_transcript(state)

    def _refresh_controls(self, state):
        status = state["status"]
        hotkey = _pretty_hotkey(state["hotkey"]) if not state.get("hotkey_error") else None

        if status == "loading":
            mode, text, fg, hover, tc = "loading", "LOADING...", theme.BG_SECONDARY, theme.BG_SECONDARY, theme.TEXT_SECONDARY
        elif status == "listening":
            mode, text, fg, hover, tc = "cancel", "CANCEL", theme.BG_SECONDARY, theme.BORDER, theme.ACCENT_CYAN
        elif status in ("thinking", "speaking"):
            mode, text, fg, hover, tc = "stop", "STOP", theme.ACCENT_RED, theme.ACCENT_RED_HOVER, theme.BG_PRIMARY
        else:
            mode, text, fg, hover, tc = "talk", "TALK", theme.ACCENT_CYAN, theme.ACCENT_CYAN_HOVER, theme.BG_PRIMARY

        if mode != self._action_mode:
            self._action_mode = mode
            glyph = {"talk": theme.ICONS["mic"], "stop": theme.ICONS["stop"]}.get(mode)
            self._action_btn.configure(
                text=f" {text}" if glyph else text, image=icon(glyph, tc, 16) if glyph else None,
                fg_color=fg, hover_color=hover, text_color=tc,
                state="disabled" if mode == "loading" else "normal",
            )

        wake_word = (state.get("wake_phrases") or [None])[0]
        voice_ok = state.get("mic_ready")
        if not voice_ok and status != "loading":
            hint = "Voice unavailable · type below"
        elif state["wake_enabled"] and state.get("wake_phrases"):
            hint = f'Say "{str(config.WAKE_WORD).title()}"' + (f" or press {hotkey}" if hotkey else "")
        elif hotkey:
            hint = f"Press {hotkey} or click Talk"
        else:
            hint = "Click Talk to speak"
        if status == "listening":
            hint = "Go ahead, I'm listening..."
        elif status == "speaking":
            hint = "Press Esc or Stop to interrupt"
        self._hint.configure(text=hint)

        if bool(self._wake_switch.get()) != bool(state["wake_enabled"]):
            self._wake_switch.select() if state["wake_enabled"] else self._wake_switch.deselect()
        self._wake_switch.configure(state="normal" if wake_word else "disabled")

        problems = []
        if state.get("voice_error"):
            problems.append(state["voice_error"])
        if state.get("hotkey_error"):
            problems.append(f"Hotkey: {state['hotkey_error']}")
        if state.get("llm_status") == "offline":
            problems.append("Ollama isn't running - chat is offline, commands still work.")
        elif state.get("llm_status") == "missing-model":
            problems.append(f"Model not found - run: ollama pull {config.OLLAMA_MODEL}")
        if state.get("notice") and not problems:
            problems.append(state["notice"])
        self._error_label.configure(text="\n".join(problems[:2]))

    def _refresh_chips(self, state):
        mic = theme.ACCENT_GREEN if state.get("mic_ready") else (
            theme.TEXT_MUTED if state["status"] == "loading" else theme.ACCENT_RED)
        llm = {"ready": theme.ACCENT_GREEN, "checking": theme.ACCENT_GOLD}.get(
            state.get("llm_status"), theme.ACCENT_RED)
        home = {"connected": theme.ACCENT_GREEN, "unreachable": theme.ACCENT_RED}.get(
            state.get("ha_status"), theme.TEXT_MUTED)
        for key, color in (("MIC", mic), ("LLM", llm), ("HOME", home)):
            self._chips[key].configure(text_color=color)

    # ------------------------------------------------------------------
    # Transcript: appended incrementally (the old version re-rendered the
    # whole log, and stopped updating entirely after 50 messages)
    # ------------------------------------------------------------------
    def _reset_transcript(self):
        box = self._box
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.configure(state="disabled")
        self._last_entry_id = 0
        self._live_index = None
        self._live_key = None

    def _refresh_transcript(self, state):
        new_entries = [e for e in state["transcript"] if e["id"] > self._last_entry_id]
        live_key = (state["status"], state.get("partial", ""), state.get("reply_draft", ""),
                    bool(state["transcript"]))
        if not new_entries and live_key == self._live_key:
            return

        box = self._box
        at_bottom = box.yview()[1] >= 0.995
        box.configure(state="normal")

        if self._live_index is not None:
            # "end-1c", not "end": deleting through Tk's final newline makes
            # Tk eat the newline *before* the range, gluing entries together.
            box.delete(self._live_index, "end-1c")
            self._live_index = None

        for entry in new_entries:
            self._insert_entry(entry["role"], entry["text"], entry.get("ts"))
            self._last_entry_id = entry["id"]

        self._live_index = box.index("end-1c")
        self._live_key = live_key
        self._insert_live(state)

        box.configure(state="disabled")
        if at_bottom or new_entries:
            box.see("end")

    def _insert_entry(self, role, text, ts=None, live=False):
        box = self._box
        who = "YOU" if role == "user" else "PARZIVAL"
        box.insert("end", who, "who_user" if role == "user" else "who_bot")
        if ts:
            box.insert("end", "  " + time.strftime("%H:%M", time.localtime(ts)), "time")
        box.insert("end", "\n" + text + "\n", "live" if live else "body")

    def _insert_live(self, state):
        status = state["status"]
        partial = state.get("partial", "")
        draft = state.get("reply_draft", "")

        if status == "listening":
            self._insert_entry("user", (partial + " ▍") if partial else "Listening...", live=True)
        elif draft:
            self._insert_entry("assistant", draft + " ▍", live=True)
        elif status == "thinking":
            self._insert_entry("assistant", "Thinking...", live=True)
        elif not state["transcript"] and status == "idle":
            self._box.insert("end", "No messages yet. Say the wake word, press the hotkey, "
                                    "or type a command below.\n", "live")
