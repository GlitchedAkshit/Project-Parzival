import customtkinter as ctk
import theme
from widgets.responsive import on_resize


class StatCard(ctk.CTkFrame):
    """Small titled value card. The value text re-wraps to the card's width
    whenever the window is resized, instead of a fixed wrap length."""

    def __init__(self, master, title, value="-", value_color=None, **kwargs):
        super().__init__(master, fg_color=theme.BG_CARD, corner_radius=theme.RADIUS,
                         border_width=1, border_color=theme.BORDER, **kwargs)

        ctk.CTkLabel(
            self, text=title, font=theme.FONT_HUD, text_color=theme.TEXT_SECONDARY, anchor="w"
        ).pack(anchor="w", padx=12, pady=(10, 0))

        self._value = str(value)
        self._value_label = ctk.CTkLabel(
            self, text=self._value, font=theme.FONT_BODY,
            text_color=value_color or theme.TEXT_PRIMARY, anchor="w",
            wraplength=220, justify="left"
        )
        self._value_label.pack(anchor="w", padx=12, pady=(2, 10), fill="x")

        on_resize(self, lambda w, h: self._value_label.configure(wraplength=max(80, w - 28)))

    def set_value(self, value, color=None):
        value = str(value)
        if len(value) > 240:
            value = value[:237] + "..."
        if value != self._value:      # skip redundant redraws
            self._value = value
            self._value_label.configure(text=value)
        if color:
            self._value_label.configure(text_color=color)
