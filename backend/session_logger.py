import csv
import os
import threading
from datetime import datetime


class SessionLogger:
    def __init__(self, enabled=True, log_dir="logs"):
        self.enabled = enabled
        self._file = None
        self._writer = None
        self._lock = threading.Lock()   # voice thread and GUI may log at the same time

        if not enabled:
            return

        try:
            os.makedirs(log_dir, exist_ok=True)
            filename = datetime.now().strftime("parzival_%Y%m%d_%H%M%S.csv")
            path = os.path.join(log_dir, filename)
            self._file = open(path, "w", newline="", encoding="utf-8")
            self._writer = csv.writer(self._file)
            self._writer.writerow(["timestamp", "event", "detail"])
            print(f"[session_logger] Logging to {path}")
        except Exception as e:
            print(f"[session_logger] Could not open log: {e}")
            self.enabled = False

    def log(self, event, detail=""):
        if not self.enabled or self._writer is None:
            return
        with self._lock:
            if self._file is None or self._file.closed:
                return
            self._writer.writerow([datetime.now().isoformat(timespec="seconds"), event, detail])
            self._file.flush()

    def close(self):
        with self._lock:
            if self._file:
                self._file.close()
