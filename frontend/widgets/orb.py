"""
Animated circular HUD indicator - concentric rotating arcs whose speed and
color reflect Parzival's current status, plus a ring that pulses with your
voice while Parzival is listening.

Smoothness notes:
  * Shapes are created ONCE and only their angle/color/coords are updated
    each frame via itemconfigure()/coords() - deleting and recreating every
    frame is what caused the old flicker.
  * Motion is time-based (degrees per second x elapsed time), so the
    rotation stays even when a frame arrives late instead of stuttering.
  * Colors cross-fade between states instead of snapping.
  * The animation idles at a low rate while the orb isn't visible, and
    stops completely when the widget is destroyed (no TclError spam).
"""

import math
import time
import tkinter as tk

import theme

_FRAME_MS = 33          # ~30 fps
_HIDDEN_FRAME_MS = 250

# status -> (rotation speed in degrees/second, color)
_STYLES = {
    "loading": (45, theme.TEXT_SECONDARY),
    "idle": (14, theme.ACCENT_CYAN_DIM),
    "listening": (70, theme.ACCENT_CYAN),
    "thinking": (120, theme.ACCENT_GOLD),
    "speaking": (85, theme.ACCENT_GREEN),
    "error": (0, theme.ACCENT_RED),
}


def _rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(c)))) for c in rgb)


def _mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


class CoreOrb(tk.Canvas):
    def __init__(self, master, size=180, level_source=None, bg=theme.BG_CARD, **kwargs):
        super().__init__(master, width=size, height=size, bg=bg, highlightthickness=0, **kwargs)
        self._bg_rgb = _rgb(bg)
        self._level_source = level_source   # callable returning mic level 0..1
        self._status = "loading"
        self._visible = True
        self._angle = 0.0
        self._level = 0.0
        self._color = _rgb(_STYLES["loading"][1])
        self._last_colors = None
        self._last_time = time.perf_counter()
        self._job = None

        self._build(size)
        self.bind("<Destroy>", self._on_destroy, add="+")
        self._job = self.after(_FRAME_MS, self._tick)

    # ------------------------------------------------------------------
    def _build(self, size):
        self.delete("all")
        self.size = size
        c = size / 2
        self._center = c
        self._r_outer = size / 2 - max(6, size * 0.055)
        self._r_inner = self._r_outer - max(12, size * 0.12)
        self._r_core = self._r_inner * 0.42
        w_outer = max(2, round(size / 60))

        self._pulse_id = self.create_oval(c, c, c, c, outline="", width=2)
        self._outer_ids = [
            self.create_arc(c - self._r_outer, c - self._r_outer, c + self._r_outer, c + self._r_outer,
                            start=i * 180, extent=100, style="arc", width=w_outer)
            for i in range(2)
        ]
        self._inner_ids = [
            self.create_arc(c - self._r_inner, c - self._r_inner, c + self._r_inner, c + self._r_inner,
                            start=i * 60, extent=30, style="arc", width=max(1, w_outer - 1))
            for i in range(6)
        ]
        self._center_id = self.create_oval(c - 4, c - 4, c + 4, c + 4, outline="")
        self._last_colors = None

    def resize(self, size):
        size = int(size)
        if size != self.size:
            self.configure(width=size, height=size)
            self._build(size)

    def set_status(self, status):
        self._status = status

    def set_visible(self, visible):
        self._visible = visible

    # ------------------------------------------------------------------
    def _tick(self):
        self._job = None
        now = time.perf_counter()
        dt = min(0.1, now - self._last_time)
        self._last_time = now

        if self._visible:
            try:
                self._draw(now, dt)
            except tk.TclError:
                return
        self._job = self.after(_FRAME_MS if self._visible else _HIDDEN_FRAME_MS, self._tick)

    def _draw(self, now, dt):
        speed, target_hex = _STYLES.get(self._status, _STYLES["idle"])
        self._angle = (self._angle + speed * dt) % 360
        self._color = _mix(self._color, _rgb(target_hex), min(1.0, dt * 6))

        raw_level = 0.0
        if self._status == "listening" and self._level_source is not None:
            raw_level = self._level_source()
        # quick attack, slower release - reads like a VU meter
        rate = 18 if raw_level > self._level else 5
        self._level += (raw_level - self._level) * min(1.0, dt * rate)

        color = _hex(self._color)
        pulse_color = _hex(_mix(self._bg_rgb, self._color, 0.25 + 0.5 * self._level))
        if (color, pulse_color) != self._last_colors:
            for item in self._outer_ids + self._inner_ids:
                self.itemconfigure(item, outline=color)
            self.itemconfigure(self._center_id, fill=color)
            self.itemconfigure(self._pulse_id, outline=pulse_color)
            self._last_colors = (color, pulse_color)

        self.itemconfigure(self._outer_ids[0], start=self._angle)
        self.itemconfigure(self._outer_ids[1], start=self._angle + 180)
        inner_start = (-self._angle * 1.6) % 360
        for i, item in enumerate(self._inner_ids):
            self.itemconfigure(item, start=inner_start + i * 60)

        c = self._center
        # Center dot "breathes" gently; voice ring grows with mic level
        dot = 4 + 1.5 * math.sin(now * 2.2) + 6 * self._level
        self.coords(self._center_id, c - dot, c - dot, c + dot, c + dot)
        ring = self._r_core + (self._r_inner - self._r_core - 4) * self._level
        self.coords(self._pulse_id, c - ring, c - ring, c + ring, c + ring)

    def _on_destroy(self, event):
        if event.widget is self and self._job is not None:
            try:
                self.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None

    def stop(self):
        self._visible = False
