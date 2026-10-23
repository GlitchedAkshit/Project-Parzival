import customtkinter as ctk
import theme
from widgets.device_tile import DeviceTile
from widgets.responsive import on_resize

_MIN_TILE_WIDTH = 230


class DevicesPage(ctk.CTkFrame):
    """
    Grid of devices - toggle/slide directly here, or control the same
    devices by voice; both write to the same state. Prefers real Home
    Assistant devices when reachable, falls back to simulated ones
    automatically otherwise.

    Nothing here touches the network: the core polls Home Assistant on a
    background thread and this page only reads the cached result, so the
    window never freezes waiting on HA. Tiles are created once and then
    updated in place; the grid reflows its column count to the width.
    """

    def __init__(self, master, get_core, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._get_core = get_core
        self._tiles = {}
        self._columns = 3
        self._seen = None

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            header, text="Devices", font=theme.FONT_TITLE, text_color=theme.TEXT_PRIMARY
        ).pack(side="left")

        self._source_label = ctk.CTkLabel(
            header, text="", font=theme.FONT_HUD, text_color=theme.TEXT_SECONDARY
        )
        self._source_label.pack(side="right")

        self._grid = ctk.CTkScrollableFrame(self, fg_color="transparent", **theme.SCROLLBAR)
        self._grid.pack(fill="both", expand=True)

        on_resize(self, self._on_resize)

    def _on_resize(self, width, height):
        columns = max(1, min(4, int(width // _MIN_TILE_WIDTH)))
        if columns != self._columns:
            self._columns = columns
            self._layout_tiles()

    def _on_device_change(self, name, updates):
        self._get_core().set_device(name, updates)

    # ------------------------------------------------------------------
    def refresh(self, core, state):
        key = (id(core), core.devices_revision())
        if key == self._seen:
            return
        self._seen = key

        source, devices = core.get_devices()
        if source == "home-assistant":
            self._source_label.configure(text="CONNECTED TO HOME ASSISTANT", text_color=theme.ACCENT_GREEN)
        elif state.get("ha_status") == "unreachable":
            self._source_label.configure(text="SIMULATED · HOME ASSISTANT UNREACHABLE",
                                         text_color=theme.ACCENT_GOLD)
        else:
            self._source_label.configure(text="SIMULATED", text_color=theme.TEXT_SECONDARY)

        if list(devices) != list(self._tiles):
            self._rebuild(devices)
        else:
            for name, tile in self._tiles.items():
                tile.refresh(devices[name])

    def _rebuild(self, devices):
        for tile in self._tiles.values():
            tile.destroy()
        self._tiles = {name: DeviceTile(self._grid, name, device, self._on_device_change)
                       for name, device in devices.items()}
        self._layout_tiles()

    def _layout_tiles(self):
        for col in range(4):
            self._grid.grid_columnconfigure(col, weight=1 if col < self._columns else 0,
                                            uniform="tiles" if col < self._columns else "")
        for i, tile in enumerate(self._tiles.values()):
            tile.grid(row=i // self._columns, column=i % self._columns, sticky="nsew", padx=6, pady=6)
