import customtkinter as ctk
import theme


class NavButton(ctk.CTkButton):
    def __init__(self, master, text, command, **kwargs):
        super().__init__(
            master, text=f"  {text}", command=command, anchor="w",
            corner_radius=theme.RADIUS, fg_color="transparent",
            hover_color=theme.BG_CARD, text_color=theme.TEXT_SECONDARY,
            font=theme.FONT_BODY, height=42, **kwargs,
        )

    def set_active(self, active):
        if active:
            self.configure(fg_color=theme.BG_CARD, text_color=theme.ACCENT_CYAN)
        else:
            self.configure(fg_color="transparent", text_color=theme.TEXT_SECONDARY)
