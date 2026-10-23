import time
from tkinter import messagebox

import customtkinter as ctk
import theme
from llm_client import clean_reply


class HistoryPage(ctk.CTkFrame):
    """Browse Parzival's full persisted conversation memory (memory.json),
    not just the current session's transcript.

    Only redraws when the memory actually changed - the old version wiped
    and re-inserted the whole history ~7 times a second, which flickered
    and made it impossible to scroll."""

    def __init__(self, master, get_core, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._get_core = get_core
        self._seen = None

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            header, text="History", font=theme.FONT_TITLE, text_color=theme.TEXT_PRIMARY
        ).pack(side="left")

        ctk.CTkButton(
            header, text="Clear Memory", command=self._clear_memory, width=120,
            fg_color=theme.ACCENT_RED, hover_color=theme.ACCENT_RED_HOVER
        ).pack(side="right")

        self._count_label = ctk.CTkLabel(header, text="", font=theme.FONT_HUD, text_color=theme.TEXT_SECONDARY)
        self._count_label.pack(side="right", padx=12)

        box = self._box = ctk.CTkTextbox(
            self, fg_color=theme.BG_CARD, corner_radius=theme.RADIUS, border_width=1,
            border_color=theme.BORDER, font=theme.FONT_BODY, text_color=theme.TEXT_PRIMARY, wrap="word",
            **theme.SCROLLBAR
        )
        box.pack(fill="both", expand=True)
        box.tag_config("date", foreground=theme.ACCENT_CYAN_DIM, spacing1=14, spacing3=4)
        box.tag_config("user", foreground=theme.ACCENT_GOLD, spacing1=6)
        box.tag_config("bot", foreground=theme.ACCENT_CYAN, spacing1=6)
        box.tag_config("time", foreground=theme.TEXT_MUTED)
        box.tag_config("body", spacing3=2, lmargin1=2, lmargin2=2)
        box.configure(state="disabled")

    def _clear_memory(self):
        if messagebox.askyesno("Clear memory",
                               "Delete Parzival's entire conversation memory? This can't be undone.",
                               parent=self.winfo_toplevel()):
            self._get_core().memory.clear()

    def refresh(self, core, state):
        key = (id(core.memory), core.memory.revision)
        if key == self._seen:
            return
        self._seen = key

        history = core.memory.get_full_history()
        self._count_label.configure(text=f"{len(history)} MESSAGES")

        box = self._box
        box.configure(state="normal")
        box.delete("1.0", "end")

        if not history:
            box.insert("end", "No conversation history yet.", "time")
        else:
            last_day = None
            for entry in history:
                ts = entry.get("ts")
                local = time.localtime(ts) if ts else None
                day = time.strftime("%A, %d %B %Y", local) if local else "Unknown date"
                if day != last_day:
                    box.insert("end", day.upper() + "\n", "date")
                    last_day = day
                is_user = entry["role"] == "user"
                box.insert("end", "You" if is_user else "Parzival", "user" if is_user else "bot")
                if local:
                    box.insert("end", "  " + time.strftime("%H:%M", local), "time")
                text = entry["content"] if is_user else clean_reply(entry["content"])
                box.insert("end", "\n" + text + "\n", "body")

        box.configure(state="disabled")
        box.see("end")
