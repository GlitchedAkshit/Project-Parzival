"""
Persists conversation history to a JSON file so Parzival remembers context
across restarts, and hands back a rolling window sized to fit the LLM's
context comfortably (full history is kept on disk; only the recent slice
is sent to the model each turn).
"""

import json
import os
import threading
import time

import config


class ConversationMemory:
    def __init__(self, path=None, max_messages=None):
        self.path = path or config.MEMORY_FILE
        self.max_messages = max_messages or config.MAX_HISTORY_MESSAGES
        self._lock = threading.Lock()
        self._messages = self._load()
        self.revision = 0   # bumped on every change so the History page knows to redraw

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save(self):
        self.revision += 1
        try:
            tmp_path = self.path + ".tmp"
            with open(tmp_path, "w") as f:
                json.dump(self._messages, f, indent=2)
            os.replace(tmp_path, self.path)
        except Exception as e:
            print(f"[memory] Could not save memory: {e}")

    def add(self, role, content):
        with self._lock:
            self._messages.append({"role": role, "content": content, "ts": time.time()})
            # Keep a bit more on disk than we send to the LLM, as a light history buffer
            self._messages = self._messages[-(self.max_messages * 4):]
            self._save()

    def get_context(self):
        with self._lock:
            recent = self._messages[-self.max_messages:]
            return [{"role": m["role"], "content": m["content"]} for m in recent]

    def get_full_history(self):
        with self._lock:
            return list(self._messages)

    def clear(self):
        with self._lock:
            self._messages = []
            self._save()
