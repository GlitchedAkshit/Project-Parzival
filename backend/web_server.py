"""
Local HTTP + Server-Sent-Events bridge between ParzivalCore and the glass
web UI (web/). The core stays exactly as it is - this module only adapts
its thread-safe API to JSON:

    GET  /api/events?token=..     live stream: state / level / metrics / devices / tasks / memory
    GET  /api/state               one snapshot
    POST /api/command             {"text"}  typed command
    POST /api/activate            push-to-talk (same as the hotkey)
    POST /api/interrupt           stop talking / thinking / listening
    POST /api/wake                {"enabled"}
    POST /api/transcript/clear    clear this session's conversation log
    POST /api/notifications/clear
    GET  /api/devices             POST /api/devices  {"name", "updates"}
    GET  /api/tasks               POST /api/tasks {"text", "due"}
    POST /api/tasks/update        {"id", ...fields}   POST /api/tasks/delete {"id"}
    POST /api/tasks/clear-completed
    GET  /api/history             POST /api/history/clear
    GET  /api/search?q=
    POST /api/system              {"action"}
    GET  /api/settings            POST /api/settings {"values", "restart"}

Security: binds to 127.0.0.1 only, checks the Host header (blocks DNS
rebinding), and every /api call must carry the random per-launch token
(X-Parzival-Token header, or ?token= for the event stream). A web page in
your browser therefore can't drive Parzival or read your conversations.
The Home Assistant token is never sent to the UI.
"""

import ipaddress
import json
import mimetypes
import os
import re
import secrets
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

import requests

import config
import settings
import settings_schema
import system_control
from ha_device_controller import discover_android_tvs
from system_metrics import SystemMetrics

_EVENT_HZ = 30
_MAX_BODY = 1_000_000

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("font/woff2", ".woff2")


class CoreHolder:
    """Owns the running ParzivalCore and swaps in a fresh one on restart
    (new settings), so connected UIs keep working across restarts."""

    def __init__(self, factory):
        self._factory = factory
        self.core = factory()
        self.core.start()
        self.restarting = False

    def restart(self):
        if self.restarting:
            return
        self.restarting = True

        def work():
            try:
                self.core.stop()
                settings.apply_overrides(verbose=False)
                new = self._factory()
                new.start()
                self.core = new
            except Exception:
                traceback.print_exc()
            finally:
                self.restarting = False

        threading.Thread(target=work, daemon=True, name="core-restart").start()

    def stop(self):
        self.core.stop()


class _MetricsSampler:
    """One shared sampler (CPU % is a delta between samples, so every
    client must see the same series)."""

    def __init__(self, interval=1.5):
        self._metrics = SystemMetrics()
        self.latest = self._metrics.sample()
        self._interval = interval
        threading.Thread(target=self._run, daemon=True, name="metrics").start()

    def _run(self):
        while True:
            time.sleep(self._interval)
            self.latest = self._metrics.sample()


def _services(core, state):
    """'Connected services' panel data - all of it real, from config/state."""
    voice_name = config.TTS_VOICE or "System default"
    return [
        {"id": "mic", "name": "Microphone", "status": "ok" if state["mic_ready"] else
            ("pending" if state["status"] == "loading" else "error"),
         "detail": "Listening for audio" if state["mic_ready"] else (state.get("voice_error") or "Starting...")},
        {"id": "wake", "name": "Wake word", "status": "ok" if state["wake_enabled"] and state["wake_phrases"] else "off",
         "detail": (f'"{str(config.WAKE_WORD).title()}"' if state["wake_phrases"] else "Unavailable")
                   + ("" if state["wake_enabled"] else " - paused")},
        {"id": "stt", "name": "Speech recognition", "status": "ok" if state["mic_ready"] else "off",
         "detail": "Vosk " + os.path.basename(str(config.VOSK_MODEL_PATH))},
        {"id": "llm", "name": "Language model", "status": {"ready": "ok", "checking": "pending"}.get(state["llm_status"], "error"),
         "detail": f"Ollama · {config.OLLAMA_MODEL}" + {"offline": " · offline", "missing-model": " · not installed",
                                                            "checking": " · loading"}.get(state["llm_status"], "")},
        {"id": "tts", "name": "Voice output", "status": "ok" if core.voice.enabled else "off",
         "detail": voice_name if core.voice.enabled else "Disabled"},
        {"id": "home", "name": "Home Assistant",
         "status": {"connected": "ok", "unreachable": "error", "insecure": "error"}.get(state["ha_status"], "off"),
         "detail": {"connected": "Connected · local · token encrypted",
                    "unreachable": "Unreachable · simulated devices",
                    "insecure": "Blocked: insecure address (needs https)"}.get(
             state["ha_status"], "Not configured · simulated devices")},
        {"id": "hotkey", "name": "Push-to-talk hotkey", "status": "error" if state.get("hotkey_error") else "ok",
         "detail": state.get("hotkey_error") or "+".join(p.capitalize() for p in str(state["hotkey"]).split("+"))},
    ]


def _public_state(holder, include_transcript=True):
    core = holder.core
    state = core.get_state()
    state["core_id"] = id(core)
    state["restarting"] = holder.restarting
    state["wake_word"] = str(config.WAKE_WORD)
    state["llm_model"] = config.OLLAMA_MODEL
    state["services"] = _services(core, state)
    if not include_transcript:
        state.pop("transcript", None)
    return state


class WebServer:
    def __init__(self, holder, static_dir, host="127.0.0.1", port=0, token=None):
        self.holder = holder
        self.static_dir = os.path.abspath(static_dir)
        self.token = token or secrets.token_urlsafe(24)
        self.metrics = _MetricsSampler()
        self.clients = 0
        self.last_client_seen = time.time()
        self._stopping = threading.Event()

        server = self
        handler = type("Handler", (_Handler,), {"server_ref": server})
        self.httpd = ThreadingHTTPServer((host, port), handler)
        self.httpd.daemon_threads = True
        self.host, self.port = self.httpd.server_address[:2]

    @property
    def url(self):
        return f"http://{self.host}:{self.port}/"

    def start(self):
        threading.Thread(target=self.httpd.serve_forever, daemon=True, name="web-server").start()
        return self.url

    def stop(self):
        self._stopping.set()
        self.httpd.shutdown()
        self.httpd.server_close()


class _Handler(BaseHTTPRequestHandler):
    server_ref = None          # set per-server via type()
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):   # keep the console quiet
        pass

    # ------------------------------------------------------------------
    # Plumbing
    # ------------------------------------------------------------------
    @property
    def srv(self):
        return self.server_ref

    @property
    def core(self):
        return self.srv.holder.core

    def _host_ok(self):
        host = (self.headers.get("Host") or "").lower()
        return host in (f"127.0.0.1:{self.srv.port}", f"localhost:{self.srv.port}")

    def _token_ok(self, query):
        supplied = self.headers.get("X-Parzival-Token") or (query.get("token") or [""])[0]
        return secrets.compare_digest(supplied, self.srv.token)

    def _send(self, status, body=b"", content_type="application/json", extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, payload, status=200):
        self._send(status, json.dumps(payload).encode("utf-8"))

    def _error(self, status, message):
        self._json({"error": message}, status)

    def _read_body(self):
        """Always drain the request body - even for endpoints that ignore it.
        With HTTP/1.1 keep-alive, unread body bytes would otherwise be parsed
        as the start of the *next* request on the connection, silently
        breaking it (e.g. every second click on the mic button)."""
        length = int(self.headers.get("Content-Length") or 0)
        if length > _MAX_BODY:
            self.close_connection = True
            raise ValueError("Request too large")
        self._raw_body = self.rfile.read(length) if length else b""

    def _body(self):
        data = json.loads(self._raw_body or b"{}")
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object")
        return data

    # ------------------------------------------------------------------
    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def _dispatch(self, method):
        try:
            self._read_body()
        except ValueError as e:
            return self._error(413, str(e))
        if not self._host_ok():
            return self._error(403, "Forbidden host")
        parsed = urlparse(self.path)
        path, query = parsed.path, parse_qs(parsed.query)

        if not path.startswith("/api/"):
            return self._static(path) if method == "GET" else self._error(405, "Method not allowed")
        if not self._token_ok(query):
            return self._error(401, "Missing or invalid session token")

        route = _ROUTES.get((method, path))
        if route is None:
            return self._error(404, "Unknown endpoint")
        try:
            route(self, query)
        except (ValueError, KeyError) as e:
            self._error(400, str(e) or "Bad request")
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            traceback.print_exc()
            self._error(500, f"Internal error: {e}")

    def _static(self, path):
        rel = unquote(path).lstrip("/") or "index.html"
        full = os.path.abspath(os.path.join(self.srv.static_dir, rel))
        if not full.startswith(self.srv.static_dir + os.sep) or not os.path.isfile(full):
            return self._error(404, "Not found")
        with open(full, "rb") as f:
            body = f.read()
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        self._send(200, body, ctype, {"Cache-Control": "no-cache"})

    # ------------------------------------------------------------------
    # Live event stream
    # ------------------------------------------------------------------
    def r_events(self, query):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        srv = self.srv
        srv.clients += 1
        last = {"core": None, "version": None, "tx": None, "devices": None, "tasks": None,
                "memory": None, "metrics": 0.0, "ping": time.time()}

        def send(event, data):
            self.wfile.write(f"event: {event}\ndata: {json.dumps(data)}\n\n".encode("utf-8"))

        try:
            while not srv._stopping.is_set():
                holder = srv.holder
                core = holder.core
                now = time.time()
                srv.last_client_seen = now

                version = (core.version, holder.restarting)
                if core is not last["core"] or version != last["version"]:
                    state = _public_state(holder)
                    tx = state["transcript"]
                    tx_key = (len(tx), tx[-1]["id"] if tx else 0)
                    if tx_key == last["tx"] and core is last["core"]:
                        state.pop("transcript")      # unchanged - don't resend 50 messages per token
                    last["tx"] = tx_key
                    send("state", state)
                    last["version"] = version

                if core.status == "listening":
                    send("level", {"level": round(core.mic_level(), 3)})

                dev_rev = (id(core), core.devices_revision())
                if dev_rev != last["devices"]:
                    source, devices = core.get_devices()
                    send("devices", {"source": source, "devices": devices})
                    last["devices"] = dev_rev

                task_rev = (id(core), core.tasks.revision)
                if task_rev != last["tasks"]:
                    send("tasks", {"tasks": core.tasks.list()})
                    last["tasks"] = task_rev

                mem_rev = (id(core), core.memory.revision)
                if mem_rev != last["memory"]:
                    send("memory", {"revision": core.memory.revision, "count": len(core.memory.get_full_history())})
                    last["memory"] = mem_rev

                if now - last["metrics"] >= 1.5:
                    send("metrics", srv.metrics.latest)
                    last["metrics"] = now

                if now - last["ping"] >= 15:
                    self.wfile.write(b": ping\n\n")
                    last["ping"] = now

                self.wfile.flush()
                last["core"] = core
                time.sleep(1 / _EVENT_HZ)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            srv.clients -= 1
            srv.last_client_seen = time.time()
        self.close_connection = True

    # ------------------------------------------------------------------
    # Assistant
    # ------------------------------------------------------------------
    def r_state(self, query):
        self._json(_public_state(self.srv.holder))

    def r_command(self, query):
        text = str(self._body().get("text", "")).strip()
        if not text:
            raise ValueError("Empty command")
        self.core.submit_text_command(text[:2000])
        self._json({"ok": True})

    def r_activate(self, query):
        self.core.activate()
        self._json({"ok": True})

    def r_interrupt(self, query):
        self.core.interrupt()
        self._json({"ok": True})

    def r_wake(self, query):
        self.core.set_wake_enabled(bool(self._body().get("enabled")))
        self._json({"ok": True})

    def r_transcript_clear(self, query):
        self.core.clear_transcript()
        self._json({"ok": True})

    def r_notifications_clear(self, query):
        self.core.clear_notifications()
        self._json({"ok": True})

    # ------------------------------------------------------------------
    # Devices
    # ------------------------------------------------------------------
    def r_devices(self, query):
        source, devices = self.core.get_devices()
        self._json({"source": source, "devices": devices})

    def r_devices_set(self, query):
        body = self._body()
        name, updates = body.get("name"), body.get("updates")
        if not isinstance(updates, dict):
            raise ValueError("updates must be an object")
        allowed = {k: updates[k] for k in ("on", "locked", "brightness", "temperature",
                                           "volume", "muted", "command", "app") if k in updates}
        if not allowed:
            raise ValueError("Nothing to update")
        _, devices = self.core.get_devices()
        if name not in devices:
            raise KeyError(f"No device called {name}")
        self.core.set_device(name, allowed)
        self._json({"ok": True})

    # ------------------------------------------------------------------
    # Pairing a TV through Home Assistant
    # ------------------------------------------------------------------
    def _require_ha(self):
        if not self.core.ha.is_available():
            raise ValueError(self.core.ha.security_error or "Home Assistant isn't reachable - start it first.")

    def r_ha_discover(self, query):
        self._require_ha()
        self._json({"tvs": discover_android_tvs()})

    def r_ha_pair(self, query):
        self._require_ha()
        host = str(self._body().get("host", "")).strip()
        try:
            if not ipaddress.ip_address(host).is_private:
                raise ValueError
        except ValueError:
            raise ValueError("Enter the TV's local IP address, e.g. 192.168.1.20")
        try:
            self._json(self.core.ha.start_tv_pairing(host))
        except requests.RequestException as e:
            self._json({"status": "error", "message": f"Home Assistant couldn't start pairing: {e}"}, 502)

    def r_ha_pair_pin(self, query):
        body = self._body()
        flow_id, pin = str(body.get("flow_id", "")), str(body.get("pin", "")).strip()
        if not re.fullmatch(r"[A-Za-z0-9]{4,8}", pin) or not re.fullmatch(r"[0-9A-Za-z]{8,64}", flow_id):
            raise ValueError("Enter the code exactly as shown on the TV")
        try:
            self._json(self.core.ha.finish_tv_pairing(flow_id, pin))
        except requests.RequestException as e:
            self._json({"status": "error", "message": f"Pairing failed: {e}"}, 502)

    def r_ha_pair_cancel(self, query):
        flow_id = str(self._body().get("flow_id", ""))
        if re.fullmatch(r"[0-9A-Za-z]{8,64}", flow_id):
            self.core.ha.cancel_tv_pairing(flow_id)
        self._json({"ok": True})

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------
    def r_tasks(self, query):
        self._json({"tasks": self.core.tasks.list()})

    def r_tasks_add(self, query):
        body = self._body()
        task = self.core.tasks.add(body.get("text", ""), due=body.get("due"))
        self._json({"task": task})

    def r_tasks_update(self, query):
        body = self._body()
        task_id = body.pop("id", None)
        fields = {k: body[k] for k in ("done", "text", "due") if k in body}
        self._json({"task": self.core.tasks.update(task_id, **fields)})

    def r_tasks_delete(self, query):
        self.core.tasks.delete(self._body().get("id"))
        self._json({"ok": True})

    def r_tasks_clear_completed(self, query):
        self.core.tasks.clear_completed()
        self._json({"ok": True})

    # ------------------------------------------------------------------
    # History & search
    # ------------------------------------------------------------------
    def r_history(self, query):
        self._json({"history": self.core.memory.get_full_history()})

    def r_history_clear(self, query):
        self.core.memory.clear()
        self._json({"ok": True})

    def r_search(self, query):
        q = (query.get("q") or [""])[0].strip().lower()
        if not q:
            return self._json({"query": "", "messages": [], "tasks": []})
        messages = [m for m in self.core.memory.get_full_history() if q in m.get("content", "").lower()]
        seen = {(m["role"], m["content"]) for m in messages}
        for entry in self.core.get_state()["transcript"]:   # this session, incl. commands
            if q in entry["text"].lower() and (entry["role"], entry["text"]) not in seen:
                messages.append({"role": entry["role"], "content": entry["text"], "ts": entry["ts"]})
        messages.sort(key=lambda m: m.get("ts") or 0, reverse=True)
        tasks = [t for t in self.core.tasks.list() if q in t["text"].lower()]
        self._json({"query": q, "messages": messages[:100], "tasks": tasks})

    # ------------------------------------------------------------------
    # System actions (same ones Parzival runs by voice)
    # ------------------------------------------------------------------
    _SYSTEM_ACTIONS = {"screenshot", "lock_pc", "volume_up", "volume_down", "mute", "open_browser",
                       "open_explorer", "open_notepad", "open_calculator", "open_task_manager",
                       "open_settings", "play_pause", "next_track", "previous_track"}

    def r_system(self, query):
        action = self._body().get("action")
        if action not in self._SYSTEM_ACTIONS:
            raise ValueError(f"Unknown action {action}")
        if action == "screenshot":
            path = system_control.take_screenshot()
            message = f"Screenshot saved to {os.path.abspath(path)}" if path else "Couldn't take a screenshot."
            return self._json({"ok": bool(path), "message": message})
        message = system_control.handle(action)
        self._json({"ok": "didn't work" not in message, "message": message})

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------
    def r_settings(self, query):
        stored = settings.load()
        sections = []
        for title, fields in settings_schema.SECTIONS:
            items = []
            for key, label, kind in fields:
                value = stored.get(key, settings.DEFAULTS.get(key, ""))
                item = {"key": key, "label": label, "kind": kind}
                if kind == "secret":
                    item["value"] = ""
                    item["has_value"] = bool(value)       # never send the token itself
                else:
                    item["value"] = value
                items.append(item)
            sections.append({"title": title, "fields": items})
        self._json({"sections": sections})

    def r_settings_save(self, query):
        body = self._body()
        values, error = settings_schema.parse(body.get("values") or {})
        if error:
            return self._json({"ok": False, "error": error}, 400)
        settings.save(values)
        if body.get("restart"):
            self.srv.holder.restart()
        self._json({"ok": True, "restarting": bool(body.get("restart"))})


_ROUTES = {
    ("GET", "/api/events"): _Handler.r_events,
    ("GET", "/api/state"): _Handler.r_state,
    ("POST", "/api/command"): _Handler.r_command,
    ("POST", "/api/activate"): _Handler.r_activate,
    ("POST", "/api/interrupt"): _Handler.r_interrupt,
    ("POST", "/api/wake"): _Handler.r_wake,
    ("POST", "/api/transcript/clear"): _Handler.r_transcript_clear,
    ("POST", "/api/notifications/clear"): _Handler.r_notifications_clear,
    ("GET", "/api/devices"): _Handler.r_devices,
    ("POST", "/api/devices"): _Handler.r_devices_set,
    ("POST", "/api/ha/discover-tvs"): _Handler.r_ha_discover,
    ("POST", "/api/ha/pair"): _Handler.r_ha_pair,
    ("POST", "/api/ha/pair/pin"): _Handler.r_ha_pair_pin,
    ("POST", "/api/ha/pair/cancel"): _Handler.r_ha_pair_cancel,
    ("GET", "/api/tasks"): _Handler.r_tasks,
    ("POST", "/api/tasks"): _Handler.r_tasks_add,
    ("POST", "/api/tasks/update"): _Handler.r_tasks_update,
    ("POST", "/api/tasks/delete"): _Handler.r_tasks_delete,
    ("POST", "/api/tasks/clear-completed"): _Handler.r_tasks_clear_completed,
    ("GET", "/api/history"): _Handler.r_history,
    ("POST", "/api/history/clear"): _Handler.r_history_clear,
    ("GET", "/api/search"): _Handler.r_search,
    ("POST", "/api/system"): _Handler.r_system,
    ("GET", "/api/settings"): _Handler.r_settings,
    ("POST", "/api/settings"): _Handler.r_settings_save,
}
