"""
Loads optional overrides from settings.json on top of config.py's
defaults. Call settings.apply_overrides() once, before any other module
reads config values (and again after saving, so changes take effect).

Secrets (HA_TOKEN) are stored encrypted with Windows DPAPI - see
secure_store.py. A plain-text token left over from older versions is
encrypted automatically the next time settings are loaded.
"""

import json
import os
import config
import secure_store

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_BACKEND_DIR, ".."))
SETTINGS_PATH = os.path.join(_PROJECT_ROOT, "settings.json")

# Encrypted at rest, never echoed to the console, never sent to the UI.
SECRET_KEYS = {"HA_TOKEN"}

# config.py's own defaults, captured before any override is applied, so the
# settings form never mistakes a runtime-only change (e.g. --quiet) for a saved one.
DEFAULTS = {k: getattr(config, k) for k in dir(config) if k.isupper()}


def load():
    """Returns the raw contents of settings.json (or {} if missing/broken).
    Secret values are returned in their stored (encrypted) form."""
    if not os.path.exists(SETTINGS_PATH):
        return {}
    try:
        with open(SETTINGS_PATH) as f:
            return json.load(f)
    except Exception as e:
        print(f"[settings] Could not read settings.json: {e}")
        return {}


def _write(data):
    tmp_path = SETTINGS_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, SETTINGS_PATH)  # atomic: never leaves a half-written file


def save(values):
    """Merges `values` into settings.json (keys you didn't pass are kept),
    encrypting secrets, and applies them to config immediately."""
    data = load()
    for key, value in values.items():
        if key in SECRET_KEYS and value and not secure_store.is_protected(value):
            value = secure_store.protect(value)
        data[key] = value
    _write(data)
    apply_overrides(verbose=False)


def _migrate_plaintext_secrets(data):
    changed = False
    for key in SECRET_KEYS:
        value = data.get(key)
        if value and not secure_store.is_protected(value) and secure_store.available():
            data[key] = secure_store.protect(value)
            changed = True
    if changed:
        _write(data)
        print("[settings] Encrypted the stored Home Assistant token (Windows DPAPI)")
    return data


def apply_overrides(verbose=True):
    data = _migrate_plaintext_secrets(load())
    for key, value in data.items():
        attr = key.upper()
        if not hasattr(config, attr):
            if verbose:
                print(f"[settings] Unknown setting '{key}' ignored")
            continue
        if attr in SECRET_KEYS:
            try:
                value = secure_store.unprotect(value)
            except OSError as e:
                print(f"[settings] Couldn't decrypt {attr} (saved by another Windows user?): {e}")
                value = ""
        setattr(config, attr, value)
        if verbose:
            shown = "********" if attr in SECRET_KEYS and value else value
            print(f"[settings] Overriding config.{attr} = {shown}")
