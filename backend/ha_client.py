"""
Thin REST client for a locally-running Home Assistant instance
(https://www.home-assistant.io). This is what lets Parzival control REAL
devices - your TV, smart plugs, lights, AC, speakers - instead of only the
simulated devices in device_controller.py.

Setup required before this works (see README):
    1. Home Assistant running (Docker container on localhost:8123)
    2. A Long-Lived Access Token generated in HA
    3. HA_URL / HA_TOKEN set in Settings (the token is stored encrypted)

Security: the token is only ever sent to Home Assistant on this PC
(localhost) or over HTTPS. A plain-http URL pointing at another machine is
refused, because the token would cross your Wi-Fi unencrypted.
"""

import ipaddress
from urllib.parse import urlparse

import requests

import config
from llm_client import fast_local_url

# Domain preference when a spoken name matches several entities
# ("tv" matches both media_player.living_room_tv and remote.living_room_tv)
_DOMAIN_PRIORITY = ["media_player", "light", "switch", "fan", "climate", "lock", "cover", "remote"]
_TV_WORDS = {"tv", "television", "the tv", "telly", "my tv"}


def insecure_url_reason(url):
    """Returns why `url` is unsafe for sending the token, or None if it's fine."""
    parsed = urlparse(url)
    if parsed.scheme == "https":
        return None
    host = (parsed.hostname or "").lower()
    if host in ("localhost",):
        return None
    try:
        if ipaddress.ip_address(host).is_loopback:
            return None
    except ValueError:
        pass
    if getattr(config, "HA_ALLOW_INSECURE_LAN", False):
        return None
    return (f"Home Assistant at {url} uses plain http on another machine - the access token "
            f"would cross your network unencrypted. Use an https:// URL (or run it on this PC).")


class HomeAssistantClient:
    def __init__(self, base_url=None, token=None):
        self.base_url = fast_local_url((base_url or config.HA_URL).rstrip("/"))
        self.token = token or config.HA_TOKEN
        self.error = insecure_url_reason(self.base_url)
        self._headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _usable(self):
        return bool(self.token) and self.error is None

    def is_available(self):
        if not self._usable():
            return False
        try:
            r = requests.get(f"{self.base_url}/api/", headers=self._headers, timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def get_states(self):
        """Returns a list of every entity and its current state."""
        if not self._usable():
            return []
        try:
            r = requests.get(f"{self.base_url}/api/states", headers=self._headers, timeout=5)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"[ha_client] Could not fetch states: {e}")
            return []

    def call_service(self, domain, service, entity_id, extra=None):
        """
        E.g. call_service('light', 'turn_on', 'light.living_room',
        {'brightness_pct': 50}). Domains/services follow Home Assistant's
        own naming conventions. Returns True on success.
        """
        if not self._usable():
            return False
        payload = {"entity_id": entity_id}
        if extra:
            payload.update(extra)

        try:
            r = requests.post(
                f"{self.base_url}/api/services/{domain}/{service}",
                headers=self._headers, json=payload, timeout=8,
            )
            r.raise_for_status()
            return True
        except Exception as e:
            print(f"[ha_client] Service call failed ({domain}.{service} on {entity_id}): {e}")
            return False

    def find_entity_by_name(self, spoken_name, domain_filter=None):
        """
        Fuzzy-matches a spoken device name (e.g. "living room light")
        against Home Assistant's friendly names, since voice input won't
        match entity_ids exactly. "tv" / "television" also finds a TV
        whose name doesn't contain the word.
        """
        spoken = spoken_name.lower().strip()
        domains = [domain_filter] if isinstance(domain_filter, str) else domain_filter
        exact, partial, tvs = [], [], []

        for state in self.get_states():
            domain = state["entity_id"].split(".")[0]
            if domains and domain not in domains:
                continue
            attrs = state.get("attributes", {})
            friendly = attrs.get("friendly_name", "").lower()
            if spoken == friendly:
                exact.append(state)
            elif spoken and friendly and (spoken in friendly or friendly in spoken):
                partial.append(state)
            if domain == "media_player" and attrs.get("device_class") in (None, "tv"):
                tvs.append(state)

        def rank(state):
            domain = state["entity_id"].split(".")[0]
            return _DOMAIN_PRIORITY.index(domain) if domain in _DOMAIN_PRIORITY else len(_DOMAIN_PRIORITY)

        for group in (exact, partial):
            if group:
                return sorted(group, key=rank)[0]
        if spoken in _TV_WORDS and tvs:
            return tvs[0]
        return None

    # ------------------------------------------------------------------
    # Config flows - used to pair new devices (e.g. an Android TV) from
    # Parzival's Smart home panel. Requires an admin user's token.
    # ------------------------------------------------------------------
    def start_flow(self, handler):
        r = requests.post(f"{self.base_url}/api/config/config_entries/flow", headers=self._headers,
                          json={"handler": handler, "show_advanced_options": False}, timeout=30)
        r.raise_for_status()
        return r.json()

    def flow_step(self, flow_id, data):
        r = requests.post(f"{self.base_url}/api/config/config_entries/flow/{flow_id}",
                          headers=self._headers, json=data, timeout=60)
        r.raise_for_status()
        return r.json()

    def abort_flow(self, flow_id):
        try:
            requests.delete(f"{self.base_url}/api/config/config_entries/flow/{flow_id}",
                            headers=self._headers, timeout=10)
        except Exception:
            pass
