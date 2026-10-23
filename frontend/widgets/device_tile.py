import time

import customtkinter as ctk
import theme


class DeviceTile(ctk.CTkFrame):
    """
    A single smart-home device: name, a status line, and a toggle switch
    (light/switch/fan/lock) and/or a slider (thermostat / light brightness).
    on_change(device_name, updates_dict) is called when the user interacts.

    refresh() keeps the controls in sync with changes made elsewhere (e.g.
    "turn on the kitchen light" by voice flips this tile's switch), without
    re-triggering on_change. Slider drags are debounced so dragging doesn't
    write devices.json / call Home Assistant dozens of times a second.
    """

    _SLIDER_DEBOUNCE_MS = 250
    _HOLD_SECONDS = 1.5   # ignore stale refreshes right after the user changes something

    def __init__(self, master, name, device, on_change, **kwargs):
        super().__init__(master, fg_color=theme.BG_CARD, corner_radius=theme.RADIUS,
                         border_width=1, border_color=theme.BORDER, **kwargs)
        self.name = name
        self.device = device
        self.on_change = on_change
        self._switch = None
        self._slider = None
        self._slider_job = None
        self._touched_at = 0.0

        ctk.CTkLabel(
            self, text=name.title(), font=theme.FONT_HEADING, text_color=theme.TEXT_PRIMARY,
            anchor="w"
        ).pack(anchor="w", fill="x", padx=14, pady=(12, 2))

        self._status_label = ctk.CTkLabel(
            self, text="", font=theme.FONT_SMALL, text_color=theme.TEXT_SECONDARY, anchor="w"
        )
        self._status_label.pack(anchor="w", padx=14)

        self._build_control()
        self.refresh(device, force=True)

    def _build_control(self):
        dtype = self.device["type"]

        if dtype in ("light", "fan", "switch"):
            self._switch = ctk.CTkSwitch(
                self, text="", command=self._on_switch, progress_color=theme.ACCENT_GOLD,
            )
            self._switch.pack(anchor="w", padx=14, pady=(6, 12 if dtype != "light" else 4))

        if dtype == "light":
            self._slider_key, low, high = "brightness", 0, 100
        elif dtype == "thermostat":
            self._slider_key, low, high = "temperature", 50, 90
        else:
            self._slider_key = None

        if self._slider_key:
            self._slider = ctk.CTkSlider(
                self, from_=low, to=high, number_of_steps=high - low, command=self._on_slider,
                progress_color=theme.ACCENT_GOLD, button_color=theme.TEXT_PRIMARY,
            )
            self._slider.pack(fill="x", padx=14, pady=(6, 14))

        if dtype == "lock":
            self._switch = ctk.CTkSwitch(
                self, text="Unlocked", command=self._on_lock_switch,
                progress_color=theme.ACCENT_RED, text_color=theme.TEXT_SECONDARY,
            )
            self._switch.pack(anchor="w", padx=14, pady=(6, 12))

    # ------------------------------------------------------------------
    def _touch(self):
        self._touched_at = time.time()

    def _on_switch(self):
        self._touch()
        on = bool(self._switch.get())
        self.device = dict(self.device, on=on)
        self._update_status()
        self.on_change(self.name, {"on": on})

    def _on_lock_switch(self):
        self._touch()
        locked = not bool(self._switch.get())
        self.device = dict(self.device, locked=locked)
        self._update_status()
        self.on_change(self.name, {"locked": locked})

    def _on_slider(self, value):
        self._touch()
        self.device = dict(self.device, **{self._slider_key: int(value)})
        self._update_status()
        if self._slider_job is not None:
            self.after_cancel(self._slider_job)
        self._slider_job = self.after(self._SLIDER_DEBOUNCE_MS, self._commit_slider)

    def _commit_slider(self):
        self._slider_job = None
        self._touch()
        self.on_change(self.name, {self._slider_key: int(self._slider.get())})

    # ------------------------------------------------------------------
    def refresh(self, device, force=False):
        if not force and (self._slider_job is not None
                          or time.time() - self._touched_at < self._HOLD_SECONDS):
            return   # the user is mid-interaction; don't yank the control back
        if not force and device == self.device:
            return
        self.device = device

        if self._switch is not None:
            checked = (not device.get("locked", True)) if device["type"] == "lock" else device.get("on", False)
            if bool(self._switch.get()) != bool(checked):
                self._switch.select() if checked else self._switch.deselect()

        if self._slider is not None:
            value = device.get(self._slider_key)
            if value is not None and int(self._slider.get()) != int(value):
                self._slider.set(value)

        self._update_status()

    def _update_status(self):
        device = self.device
        dtype = device["type"]

        if dtype == "light":
            status = f"{'On' if device.get('on') else 'Off'} · {device.get('brightness', 100)}%"
            color = theme.ACCENT_GOLD if device.get("on") else theme.TEXT_SECONDARY
        elif dtype in ("fan", "switch"):
            status = "On" if device.get("on") else "Off"
            color = theme.ACCENT_GOLD if device.get("on") else theme.TEXT_SECONDARY
        elif dtype == "thermostat":
            status = f"{device.get('temperature', 70)} °F"
            color = theme.TEXT_PRIMARY
        elif dtype == "lock":
            locked = device.get("locked")
            status = "Locked" if locked else "Unlocked"
            color = theme.ACCENT_GREEN if locked else theme.ACCENT_RED
        else:
            status, color = "", theme.TEXT_SECONDARY

        self._status_label.configure(text=status, text_color=color)
