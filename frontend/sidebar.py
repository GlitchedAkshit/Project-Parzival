import customtkinter as ctk
import theme
from widgets.nav_button import NavButton


class Sidebar(ctk.CTkFrame):
    """Nav rail. Collapses to an icon-only strip on narrow windows, and
    shows Parzival's live status + how to activate it at the bottom."""

    PAGES = ["Dashboard", "Devices", "System", "History", "Settings"]

    def __init__(self, master, on_navigate, **kwargs):
        super().__init__(master, width=theme.SIDEBAR_WIDTH, fg_color=theme.BG_SIDEBAR,
                         corner_radius=0, **kwargs)
        self.grid_propagate(False)
        self.pack_propagate(False)

        self._on_navigate = on_navigate
        self._buttons = {}
        self._compact = False
        self._current = None
        self._shown_status = None

        self._header = ctk.CTkFrame(self, fg_color="transparent")
        self._header.pack(fill="x", padx=14, pady=(24, 12))
        self._title = ctk.CTkLabel(
            self._header, text="PARZIVAL", font=(theme.FONT_FAMILY, 22, "bold"),
            text_color=theme.ACCENT_CYAN
        )
        self._title.pack(anchor="w")
        self._subtitle = ctk.CTkLabel(
            self._header, text="local voice assistant", font=theme.FONT_SMALL,
            text_color=theme.TEXT_SECONDARY
        )
        self._subtitle.pack(anchor="w")

        # Thin glowing divider - a small HUD touch
        ctk.CTkFrame(self, height=1, fg_color=theme.ACCENT_CYAN_DIM).pack(
            fill="x", padx=14, pady=(0, 16)
        )

        for page in self.PAGES:
            btn = NavButton(self, text=page, command=lambda p=page: self.select(p))
            btn.pack(fill="x", padx=10, pady=3)
            self._buttons[page] = btn

        # ---- footer: live status ----
        self._footer = ctk.CTkFrame(self, fg_color="transparent")
        self._footer.pack(side="bottom", fill="x", padx=14, pady=16)
        self._status_dot = ctk.CTkLabel(self._footer, text="●", font=(theme.FONT_FAMILY, 14),
                                        text_color=theme.TEXT_SECONDARY, width=14)
        self._status_dot.pack(side="left")
        self._status_label = ctk.CTkLabel(self._footer, text="INITIALIZING", font=theme.FONT_HUD,
                                          text_color=theme.TEXT_SECONDARY)
        self._status_label.pack(side="left", padx=(6, 0))

    def select(self, page):
        if page == self._current:
            return
        self._current = page
        for name, btn in self._buttons.items():
            btn.set_active(name == page)
        self._on_navigate(page)

    def set_status(self, status):
        if status == self._shown_status:
            return
        self._shown_status = status
        color = theme.STATUS_COLORS.get(status, theme.TEXT_SECONDARY)
        self._status_dot.configure(text_color=color)
        self._status_label.configure(text=theme.STATUS_LABELS.get(status, status.upper()),
                                     text_color=color)

    def set_compact(self, compact):
        if compact == self._compact:
            return
        self._compact = compact
        self.configure(width=theme.SIDEBAR_WIDTH_COMPACT if compact else theme.SIDEBAR_WIDTH)
        self._title.configure(text="P" if compact else "PARZIVAL")
        if compact:
            self._subtitle.pack_forget()
            self._status_label.pack_forget()
        else:
            self._subtitle.pack(anchor="w")
            self._status_label.pack(side="left", padx=(6, 0))
        for btn in self._buttons.values():
            btn.set_compact(compact)
