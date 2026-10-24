"""
Real device control via Home Assistant, exposed with the same shape as
device_controller.DeviceController's data and interface, so both the
Devices page and assistant_core.py can treat real and simulated devices
almost interchangeably.

Supported Home Assistant domains: light, switch (smart plugs), fan, lock,
climate (AC / thermostat), media_player (TVs, speakers, Chromecast) - with
the matching remote entity used for TV keys and app launching.

Network calls never happen on the GUI thread: poll() runs on a background
thread (see ParzivalCore._ha_loop) and caches both "is HA reachable?" and
the device list. is_available()/get_all() just read that cache.
"""

import concurrent.futures
import socket
import threading

from ha_client import HomeAssistantClient

_SUPPORTED_DOMAINS = ("light", "switch", "fan", "lock", "climate", "media_player")

# media_player supported_features bits (homeassistant.components.media_player.MediaPlayerEntityFeature)
F_PAUSE, F_VOLUME_SET, F_VOLUME_MUTE = 1, 4, 8
F_PREVIOUS, F_NEXT, F_TURN_ON, F_TURN_OFF = 16, 32, 128, 256
F_PLAY_MEDIA, F_VOLUME_STEP, F_SELECT_SOURCE, F_PLAY = 512, 1024, 2048, 16384

# Apps that can be launched on an Android / Google TV. Deep links follow
# Home Assistant's Android TV Remote documentation; package names launch
# the app directly.
TV_APPS = {
    "youtube": ("YouTube", "https://www.youtube.com"),
    "netflix": ("Netflix", "https://www.netflix.com/title"),
    "prime video": ("Prime Video", "https://app.primevideo.com"),
    "amazon prime": ("Prime Video", "https://app.primevideo.com"),
    "spotify": ("Spotify", "com.spotify.tv.android"),
    "play store": ("Play Store", "com.android.vending"),
    "settings": ("Settings", "com.android.tv.settings"),
}

TV_APP_CHIPS = ["YouTube", "Netflix", "Prime Video", "Spotify"]

TV_KEYS = {"home": "HOME", "back": "BACK", "channel_up": "CHANNEL_UP", "channel_down": "CHANNEL_DOWN"}
_OFF_STATES = ("off", "standby", "unavailable", "unknown")


class HADeviceController:
    def __init__(self):
        self.client = HomeAssistantClient()
        self._lock = threading.Lock()
        self._available = False
        self._last_devices = {}
        self.revision = 0
        self.refresh_requested = threading.Event()

    # ------------------------------------------------------------------
    def is_configured(self):
        return bool(self.client.token)

    def is_available(self):
        return self._available

    @property
    def security_error(self):
        return self.client.error

    def poll(self):
        """Blocking network refresh - call from a background thread only."""
        available = self.is_configured() and self.client.is_available()
        devices = self._fetch_all() if available else {}
        with self._lock:
            if available != self._available or devices != self._last_devices:
                self.revision += 1
            self._available = available
            self._last_devices = devices

    def get_all(self):
        with self._lock:
            return {name: dict(d) for name, d in self._last_devices.items()}

    # ------------------------------------------------------------------
    def _fetch_all(self):
        """
        Returns entities normalized into the same shape the simulated
        DeviceController uses (type/on/brightness/temperature/locked), plus
        a richer shape for TVs and speakers.
        """
        states = self.client.get_states()
        remotes = {s["entity_id"].split(".", 1)[1]: s["entity_id"]
                   for s in states if s["entity_id"].startswith("remote.")}
        devices = {}

        for state in states:
            entity_id = state["entity_id"]
            domain, object_id = entity_id.split(".", 1)

            if domain not in _SUPPORTED_DOMAINS:
                continue

            attrs = state.get("attributes", {})
            name = attrs.get("friendly_name", entity_id)

            if domain == "light":
                brightness_raw = attrs.get("brightness") or 0
                devices[name] = {
                    "type": "light",
                    "on": state["state"] == "on",
                    "brightness": round(brightness_raw / 255 * 100),
                    "entity_id": entity_id,
                }
            elif domain in ("switch", "fan"):
                devices[name] = {
                    "type": "fan" if domain == "fan" else "switch",
                    "on": state["state"] == "on",
                    "entity_id": entity_id,
                }
            elif domain == "lock":
                devices[name] = {
                    "type": "lock",
                    "locked": state["state"] == "locked",
                    "entity_id": entity_id,
                }
            elif domain == "climate":
                devices[name] = {
                    "type": "thermostat",
                    "on": state["state"] not in ("off", "unavailable"),
                    "temperature": attrs.get("temperature", 70),
                    "min": attrs.get("min_temp", 50),
                    "max": attrs.get("max_temp", 90),
                    "unit": "C" if (attrs.get("max_temp") or 90) < 45 else "F",
                    "entity_id": entity_id,
                }
            elif domain == "media_player":
                volume = attrs.get("volume_level")
                apps = TV_APP_CHIPS
                devices[name] = {
                    "type": "speaker" if attrs.get("device_class") in ("speaker", "receiver") else "tv",
                    "on": state["state"] not in _OFF_STATES,
                    "available": state["state"] != "unavailable",
                    "state": state["state"],
                    "volume": round(volume * 100) if isinstance(volume, (int, float)) else None,
                    "muted": bool(attrs.get("is_volume_muted")),
                    "source": attrs.get("app_name") or attrs.get("source") or "",
                    "title": attrs.get("media_title") or "",
                    "sources": list(attrs.get("source_list") or [])[:24],
                    "apps": apps if object_id in remotes else [],
                    "features": int(attrs.get("supported_features") or 0),
                    "remote": remotes.get(object_id),
                    "entity_id": entity_id,
                }

        return devices

    # ------------------------------------------------------------------
    # Voice
    # ------------------------------------------------------------------
    def handle(self, args):
        """Called by the intent parser's ('device', args) result."""
        action = args["action"]
        spoken_name = args.get("device", "")

        domain_filter = "lock" if action in ("lock", "unlock") else None
        match = self.client.find_entity_by_name(spoken_name, domain_filter)

        if match is None:
            return f"I couldn't find a device called {spoken_name}."

        entity_id = match["entity_id"]
        domain = entity_id.split(".")[0]
        friendly = match.get("attributes", {}).get("friendly_name", spoken_name)
        reply = f"I can't do that with the {friendly}."
        ok = True

        if action in ("on", "off") and domain in ("light", "switch", "fan", "media_player", "climate", "remote"):
            ok = self.client.call_service(domain, "turn_on" if action == "on" else "turn_off", entity_id)
            reply = f"Turning {action} the {friendly}."
        elif action == "set" and domain == "climate":
            ok = self.client.call_service(domain, "set_temperature", entity_id, {"temperature": args["value"]})
            reply = f"Setting {friendly} to {args['value']} degrees."
        elif action == "set" and domain == "light":
            pct = max(0, min(100, args["value"]))
            ok = self.client.call_service(domain, "turn_on", entity_id, {"brightness_pct": pct})
            reply = f"Setting {friendly} brightness to {pct} percent."
        elif action == "set" and domain == "media_player":
            return self.handle_tv({"action": "volume_set", "value": args["value"], "device": spoken_name})
        elif action == "lock" and domain == "lock":
            ok = self.client.call_service(domain, "lock", entity_id)
            reply = f"Locking the {friendly}."
        elif action == "unlock" and domain == "lock":
            ok = self.client.call_service(domain, "unlock", entity_id)
            reply = f"Unlocking the {friendly}."

        self.refresh_requested.set()
        return reply if ok else f"The {friendly} didn't respond."

    def handle_tv(self, args):
        """('tv', args) intents: volume, mute, playback, apps, remote keys."""
        match = self.client.find_entity_by_name(args.get("device") or "tv", "media_player")
        if match is None:
            return "I don't see a TV in Home Assistant yet. Open Smart home and choose Add a TV."
        entity_id = match["entity_id"]
        name = match.get("attributes", {}).get("friendly_name", "TV")
        device = self._last_devices.get(name) or {"entity_id": entity_id, "remote": None, "sources": []}
        action = args["action"]

        if action == "app":
            return self._launch_app(device, name, args.get("app", ""))
        reply, ok = self._tv_action(device, action, args.get("value"))
        self.refresh_requested.set()
        return reply.format(name=name) if ok else f"The {name} didn't respond."

    def _tv_action(self, device, action, value=None):
        entity_id, remote = device["entity_id"], device.get("remote")
        call = self.client.call_service
        if action == "volume_up":
            return "Turning the {name} up.", call("media_player", "volume_up", entity_id)
        if action == "volume_down":
            return "Turning the {name} down.", call("media_player", "volume_down", entity_id)
        if action == "volume_set":
            level = max(0, min(100, int(value or 0)))
            return f"Setting the {{name}} volume to {level}.", call("media_player", "volume_set", entity_id, {"volume_level": level / 100})
        if action in ("mute", "unmute"):
            return ("Muting the {name}." if action == "mute" else "Unmuting the {name}."), \
                call("media_player", "volume_mute", entity_id, {"is_volume_muted": action == "mute"})
        if action == "play_pause":
            return "Done.", call("media_player", "media_play_pause", entity_id)
        if action == "next":
            return "Skipping ahead.", call("media_player", "media_next_track", entity_id)
        if action == "previous":
            return "Going back.", call("media_player", "media_previous_track", entity_id)
        if action in TV_KEYS:
            if not remote:
                return "The {name} doesn't accept remote keys.", True
            return "Done.", call("remote", "send_command", remote, {"command": TV_KEYS[action]})
        return "I can't do that with the {name}.", True

    def _launch_app(self, device, name, spoken_app):
        spoken = spoken_app.lower().strip()
        for source in device.get("sources") or []:
            if spoken and (spoken in source.lower() or source.lower() in spoken):
                ok = self.client.call_service("media_player", "select_source", device["entity_id"], {"source": source})
                return f"Opening {source} on the {name}." if ok else f"The {name} didn't respond."
        app = next((v for k, v in TV_APPS.items() if k in spoken or spoken in k), None) if spoken else None
        if app is None:
            return f"I don't know how to open {spoken_app} on the TV yet."
        label, link = app
        if device.get("remote"):
            ok = self.client.call_service("remote", "turn_on", device["remote"], {"activity": link})
        else:
            ok = self.client.call_service("media_player", "play_media", device["entity_id"],
                                          {"media_content_type": "url" if link.startswith("http") else "app",
                                           "media_content_id": link})
        self.refresh_requested.set()
        return f"Opening {label} on the {name}." if ok else f"The {name} didn't respond."

    # ------------------------------------------------------------------
    # GUI
    # ------------------------------------------------------------------
    def set_device_gui(self, name, updates):
        """Called (on a worker thread) when a control changes - looks up the
        real entity_id from the cached device list, since the GUI only
        knows the friendly display name."""
        device = self._last_devices.get(name)
        if not device:
            return

        entity_id = device["entity_id"]
        domain = entity_id.split(".")[0]

        if domain == "media_player":
            if "on" in updates:
                self.client.call_service(domain, "turn_on" if updates["on"] else "turn_off", entity_id)
            elif "volume" in updates:
                self._tv_action(device, "volume_set", updates["volume"])
            elif "muted" in updates:
                self._tv_action(device, "mute" if updates["muted"] else "unmute")
            elif "command" in updates:
                self._tv_action(device, updates["command"])
            elif "app" in updates:
                self._launch_app(device, name, str(updates["app"]))
        elif "on" in updates:
            service = "turn_on" if updates["on"] else "turn_off"
            self.client.call_service(domain, service, entity_id)
        elif "locked" in updates:
            service = "lock" if updates["locked"] else "unlock"
            self.client.call_service(domain, service, entity_id)
        elif "temperature" in updates:
            self.client.call_service(domain, "set_temperature", entity_id,
                                     {"temperature": updates["temperature"]})
        elif "brightness" in updates:
            pct = max(0, min(100, updates["brightness"]))
            self.client.call_service(domain, "turn_on", entity_id, {"brightness_pct": pct})

        self.refresh_requested.set()

    # ------------------------------------------------------------------
    # Pairing a new Android / Google TV (Home Assistant's encrypted
    # "Android TV Remote" protocol: the TV shows a code you type in)
    # ------------------------------------------------------------------
    def start_tv_pairing(self, host):
        flow = self.client.start_flow("androidtv_remote")
        try:
            summary = _summarize_flow(self.client.flow_step(flow["flow_id"], {"host": host}))
        except Exception:
            self.client.abort_flow(flow["flow_id"])
            raise
        if summary["status"] == "error":
            self.client.abort_flow(flow["flow_id"])   # don't leave a half-finished setup in HA
            summary.pop("flow_id", None)
        return summary

    def finish_tv_pairing(self, flow_id, pin):
        result = _summarize_flow(self.client.flow_step(flow_id, {"pin": pin.strip().upper()}))
        if result["status"] == "paired":
            self.refresh_requested.set()
        return result

    def cancel_tv_pairing(self, flow_id):
        self.client.abort_flow(flow_id)


_FLOW_ERRORS = {
    "cannot_connect": "Couldn't reach a TV at that address. Is it switched on and on the same Wi-Fi?",
    "invalid_auth": "That code didn't match. Check the code on the TV and try again.",
    "already_configured": "That TV is already connected.",
    "unknown": "The TV refused the connection. Try again.",
}


def _summarize_flow(result):
    """Turns a Home Assistant config-flow step into something the UI can show."""
    kind = result.get("type")
    errors = result.get("errors") or {}
    if kind == "create_entry":
        return {"status": "paired", "name": result.get("title", "TV")}
    if kind == "abort":
        reason = result.get("reason", "unknown")
        return {"status": "done" if reason == "already_configured" else "error",
                "message": _FLOW_ERRORS.get(reason, f"Pairing stopped: {reason}")}
    if kind == "form" and result.get("step_id") == "pair":
        msg = _FLOW_ERRORS.get(errors.get("base", ""), "") if errors else ""
        return {"status": "need_pin", "flow_id": result["flow_id"], "message": msg,
                "name": (result.get("description_placeholders") or {}).get("name", "your TV")}
    if kind == "form":
        return {"status": "error", "flow_id": result.get("flow_id"),
                "message": _FLOW_ERRORS.get(errors.get("base", ""), "Home Assistant needs more information.")}
    return {"status": "error", "message": f"Unexpected response from Home Assistant ({kind})."}


def _tv_name(ip):
    """The name you gave the TV (e.g. "BRAVIA VU31"), from its built-in
    Chromecast's read-only device-info endpoint; falls back to reverse DNS."""
    try:
        import requests
        r = requests.get(f"http://{ip}:8008/setup/eureka_info", params={"params": "name"}, timeout=1.5)
        name = r.json().get("name")
        if name:
            return str(name)[:60]
    except Exception:
        pass
    try:
        return socket.gethostbyaddr(ip)[0]
    except OSError:
        return ""


def discover_android_tvs(timeout=0.6):
    """Finds devices on this PC's local /24 network that accept Android TV
    Remote connections (TCP 6466) - the same check the Google TV phone app
    makes. Only touches your own subnet."""
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("192.0.2.1", 9))          # no packet is sent; picks the LAN interface
        local_ip = probe.getsockname()[0]
        probe.close()
    except OSError:
        return []
    prefix = local_ip.rsplit(".", 1)[0]

    def check(i):
        ip = f"{prefix}.{i}"
        s = socket.socket()
        s.settimeout(timeout)
        try:
            s.connect((ip, 6466))
            return {"host": ip, "name": _tv_name(ip)}
        except OSError:
            return None
        finally:
            s.close()

    with concurrent.futures.ThreadPoolExecutor(64) as pool:
        return [r for r in pool.map(check, range(1, 255)) if r and r["host"] != local_ip]
