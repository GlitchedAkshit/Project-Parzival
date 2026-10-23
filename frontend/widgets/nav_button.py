import customtkinter as ctk
import theme
from widgets.icons import icon


class NavButton(ctk.CTkButton):
    """Sidebar entry: icon + label, or icon only when the sidebar is compact."""

    def __init__(self, master, text, command, **kwargs):
        self._label = text
        self._active = False
        self._compact = False
        glyph = theme.ICONS.get(text)
        self._icons = {
            False: icon(glyph, theme.TEXT_SECONDARY) if glyph else None,
            True: icon(glyph, theme.ACCENT_GOLD) if glyph else None,
        }
        super().__init__(
            master, text=f"  {text}", command=command, anchor="w",
            image=self._icons[False], compound="left",
            corner_radius=theme.RADIUS, fg_color="transparent",
            hover_color=theme.BG_CARD, text_color=theme.TEXT_SECONDARY,
            font=theme.FONT_BODY, height=42, **kwargs,
        )

    def set_active(self, active):
        self._active = active
        self.configure(
            fg_color=theme.BG_CARD if active else "transparent",
            text_color=theme.ACCENT_GOLD if active else theme.TEXT_SECONDARY,
            image=self._icons[active],
        )

    def set_compact(self, compact):
        if compact == self._compact or self._icons[False] is None:
            return
        self._compact = compact
        self.configure(text="" if compact else f"  {self._label}",
                       anchor="center" if compact else "w")
