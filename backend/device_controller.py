"""
Manages a JSON-backed set of SIMULATED smart-home devices. There's no real
hardware behind this - it's a persistent state store that both voice
commands and the GUI's Devices page read/write, so toggling a light by
voice updates the dashboard live, and vice versa.

Voice commands run on Parzival's background thread while the GUI runs on
the main thread, so every read/write goes through a lock, and `revision`
increments on each change so the GUI knows when to redraw.
"""

import difflib
import json
import os
import threading

DEFAULT_DEVICES = {
    "living room light": {"type": "light", "on": False, "brightness": 100},
    "bedroom light": {"type": "light", "on": False, "brightness": 100},
    "kitchen light": {"type": "light", "on": False, "brightness": 100},
    "thermostat": {"type": "thermostat", "temperature": 70},
    "front door": {"type": "lock", "locked": True},
    "fan": {"type": "fan", "on": False, "speed": 1},
}

_FILLER_WORDS = {"the", "all", "my", "of", "please", "in", "a"}


class DeviceController:
    def __init__(self, path="devices.json"):
        self.path = path
        self._lock = threading.RLock()
        self.devices = self._load()
        self.revision = 0

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    return json.load(f)
            except Exception:
                pass
        return json.loads(json.dumps(DEFAULT_DEVICES))  # deep copy

    def _save(self):
        self.revision += 1
        try:
            tmp_path = self.path + ".tmp"
            with open(tmp_path, "w") as f:
                json.dump(self.devices, f, indent=2)
            os.replace(tmp_path, self.path)
        except Exception as e:
            print(f"[device_controller] Could not save devices: {e}")

    def _match_devices(self, name):
        """Returns a list of device keys. 'lights' / 'all the lights' /
        'kitchen lights' address every matching light at once."""
        name = (name or "").strip().lower()
        if name in self.devices:
            return [name]

        words = [w for w in name.split() if w not in _FILLER_WORDS]
        if words and words[-1] in ("lights", "lamps"):
            room = " ".join(words[:-1])
            return [k for k, d in self.devices.items()
                    if d["type"] == "light" and (not room or room in k)]

        cleaned = " ".join(words)
        singular = cleaned[:-1] if cleaned.endswith("s") else cleaned
        for candidate in (cleaned, singular):
            for key in self.devices:
                if candidate and (candidate in key or key in candidate):
                    return [key]

        # Speech recognition slips ("living room life" -> "living room light")
        return difflib.get_close_matches(cleaned, list(self.devices), n=1, cutoff=0.75)

    def get_all(self):
        with self._lock:
            return json.loads(json.dumps(self.devices))

    def handle(self, args):
        """Called by the intent parser's ('device', args) result."""
        with self._lock:
            names = self._match_devices(args.get("device", ""))
            if not names:
                return f"I don't have a device called {args.get('device', 'that')}."

            if len(names) > 1:
                replies = [self._apply(n, args) for n in names]
                if all(r.startswith(("Turning", "Setting")) for r in replies):
                    verb = {"on": "on", "off": "off"}.get(args["action"])
                    if verb:
                        return f"Turning {verb} {len(names)} lights."
                    return f"Setting {len(names)} lights to {args.get('value')} percent."
                return " ".join(replies)

            return self._apply(names[0], args)

    def _apply(self, device_name, args):
        action = args["action"]
        device = self.devices[device_name]

        if action == "on" and device["type"] in ("light", "fan"):
            device["on"] = True
            self._save()
            return f"Turning on the {device_name}."

        if action == "off" and device["type"] in ("light", "fan"):
            device["on"] = False
            self._save()
            return f"Turning off the {device_name}."

        if action == "set" and device["type"] == "thermostat":
            device["temperature"] = max(50, min(90, args["value"]))
            self._save()
            return f"Setting the thermostat to {device['temperature']} degrees."

        if action == "set" and device["type"] == "light":
            device["brightness"] = max(0, min(100, args["value"]))
            device["on"] = device["brightness"] > 0
            self._save()
            return f"Setting the {device_name} brightness to {device['brightness']} percent."

        if action == "lock" and device["type"] == "lock":
            device["locked"] = True
            self._save()
            return f"The {device_name} is locked."

        if action == "unlock" and device["type"] == "lock":
            device["locked"] = False
            self._save()
            return f"The {device_name} is unlocked."

        return f"I can't do that with the {device_name}."

    def set_device_gui(self, device_name, updates):
        """Called directly by the GUI (a toggle switch or slider), bypassing voice."""
        with self._lock:
            if device_name in self.devices:
                self.devices[device_name].update(updates)
                self._save()
