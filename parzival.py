"""
Parzival launcher - starts the voice assistant core and opens the
holographic glass interface in its own window.

    python parzival.py               normal start (native window via pywebview)
    python parzival.py --browser     open in an Edge/Chrome app window instead
    python parzival.py --classic     the original CustomTkinter interface

Developer options:
    --server-only     no window; print the URL (open it in any browser)
    --port N          fixed port instead of a random free one
    --data-dir DIR    folder for memory.json / devices.json / tasks.json / logs
    --quiet           no spoken replies or chimes (handy while testing)
    --debug           pywebview developer tools
"""

import argparse
import ctypes
import os
import runpy
import shutil
import subprocess
import sys
import time
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(ROOT, "backend")
WEB_DIR = os.path.join(ROOT, "web")
DEFAULT_DATA_DIR = os.path.join(ROOT, "frontend")   # where your memory/devices/logs already live


def _parse_args():
    p = argparse.ArgumentParser(description="Parzival voice assistant")
    p.add_argument("--browser", action="store_true", help="use an Edge/Chrome app window instead of pywebview")
    p.add_argument("--classic", action="store_true", help="run the original Tk interface")
    p.add_argument("--server-only", action="store_true", help="don't open a window; print the URL")
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--data-dir", default=DEFAULT_DATA_DIR)
    p.add_argument("--quiet", action="store_true", help="disable speech output and chimes")
    p.add_argument("--debug", action="store_true")
    return p.parse_args()


def main():
    args = _parse_args()

    if args.classic:
        sys.argv = [os.path.join(ROOT, "frontend", "app.py")]
        runpy.run_path(sys.argv[0], run_name="__main__")
        return

    data_dir = os.path.abspath(args.data_dir)
    os.makedirs(data_dir, exist_ok=True)
    os.chdir(data_dir)
    sys.path.insert(0, BACKEND_DIR)

    import settings
    settings.apply_overrides()
    import config
    if args.quiet:
        config.TTS_ENABLED = False
        config.WAKE_CHIME = False

    from assistant_core import ParzivalCore
    from web_server import CoreHolder, WebServer

    holder = CoreHolder(ParzivalCore)
    server = WebServer(holder, WEB_DIR, port=args.port)
    server.start()
    # The token travels in the URL fragment, which is never sent over HTTP.
    app_url = f"{server.url}#token={server.token}"

    try:
        if args.server_only:
            print(f"\n  Parzival UI: {app_url}\n  (Ctrl+C to stop)\n", flush=True)
            while True:
                time.sleep(1)
        elif args.browser or not _run_webview(app_url, data_dir, args.debug):
            _run_app_window(app_url, data_dir, server)
    except KeyboardInterrupt:
        pass
    finally:
        holder.stop()
        server.stop()


# ----------------------------------------------------------------------
def _run_webview(url, data_dir, debug):
    try:
        import webview
    except ImportError:
        print("[parzival] pywebview isn't installed - opening an Edge app window instead.")
        return False

    window = webview.create_window(
        "Parzival", url, width=1480, height=920, min_size=(420, 640),
        background_color="#030508", text_select=True,
    )
    window.events.shown += lambda: _style_title_bar(window)
    webview.start(private_mode=False, storage_path=os.path.join(data_dir, ".webview"), debug=debug)
    return True


def _style_title_bar(window):
    """Windows 11: dark title bar tinted to match the UI's background."""
    try:
        hwnd = int(window.native.Handle.ToInt64())
        dwm = ctypes.windll.dwmapi

        def set_attr(attr, value):
            v = ctypes.c_int(value)
            dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))

        set_attr(20, 1)            # DWMWA_USE_IMMERSIVE_DARK_MODE
        set_attr(35, 0x00080503)   # DWMWA_CAPTION_COLOR  (#030508, COLORREF is 0x00BBGGRR)
        set_attr(34, 0x002E2410)   # DWMWA_BORDER_COLOR   (#10242e)
        set_attr(36, 0x00FFF0DC)   # DWMWA_TEXT_COLOR     (#dcf0ff)
    except Exception as e:
        print(f"[parzival] Couldn't style the title bar: {e}")


def _find_app_browser():
    candidates = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    found = [c for c in candidates if os.path.isfile(c)]
    return found[0] if found else shutil.which("msedge") or shutil.which("chrome")


def _run_app_window(url, data_dir, server):
    browser = _find_app_browser()
    if browser:
        subprocess.Popen([browser, f"--app={url}", "--window-size=1480,920", "--no-first-run",
                          f"--user-data-dir={os.path.join(data_dir, '.app-window')}"])
    else:
        webbrowser.open(url)

    # Keep running while the window is connected; exit once it's closed.
    started = time.time()
    while True:
        time.sleep(1)
        if server.clients == 0:
            idle = time.time() - server.last_client_seen
            if (server.last_client_seen > started and idle > 5) or time.time() - started > 60 and idle > 60:
                return


if __name__ == "__main__":
    main()
