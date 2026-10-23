"""
Tasks & reminders: a small JSON-backed to-do list. A task with a `due`
time is a reminder - ParzivalCore checks once a second and announces any
that come due (spoken aloud + shown as a notification).

Voice: "remind me to stretch in 20 minutes", "add buy milk to my tasks",
"what are my tasks". The UI's Tasks panel edits the same store.
"""

import json
import os
import threading
import time
import uuid


class TaskStore:
    def __init__(self, path="tasks.json"):
        self.path = path
        self._lock = threading.Lock()
        self._tasks = self._load()
        self.revision = 0

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    data = json.load(f)
                return data if isinstance(data, list) else []
            except Exception as e:
                print(f"[tasks] Could not read {self.path}: {e}")
        return []

    def _save(self):
        self.revision += 1
        try:
            tmp_path = self.path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._tasks, f, indent=2)
            os.replace(tmp_path, self.path)
        except Exception as e:
            print(f"[tasks] Could not save tasks: {e}")

    # ------------------------------------------------------------------
    def list(self):
        with self._lock:
            return [dict(t) for t in self._tasks]

    def pending(self):
        return [t for t in self.list() if not t["done"]]

    def add(self, text, due=None):
        text = " ".join(str(text).split()).rstrip(".")[:280]
        if not text:
            raise ValueError("A task needs some text")
        task = {
            "id": uuid.uuid4().hex[:10],
            "text": text,
            "done": False,
            "created": time.time(),
            "due": float(due) if due else None,
            "notified": False,
        }
        with self._lock:
            self._tasks.append(task)
            self._save()
        return dict(task)

    def update(self, task_id, **fields):
        with self._lock:
            for task in self._tasks:
                if task["id"] == task_id:
                    if "done" in fields:
                        task["done"] = bool(fields["done"])
                    if "text" in fields and str(fields["text"]).strip():
                        task["text"] = str(fields["text"]).strip()[:280]
                    if "due" in fields:
                        task["due"] = float(fields["due"]) if fields["due"] else None
                        task["notified"] = False
                    self._save()
                    return dict(task)
        raise KeyError(task_id)

    def delete(self, task_id):
        with self._lock:
            before = len(self._tasks)
            self._tasks = [t for t in self._tasks if t["id"] != task_id]
            if len(self._tasks) == before:
                raise KeyError(task_id)
            self._save()

    def clear_completed(self):
        with self._lock:
            self._tasks = [t for t in self._tasks if not t["done"]]
            self._save()

    def pop_due(self, now=None):
        """Returns reminders that just came due, marking them announced."""
        now = now or time.time()
        due = []
        with self._lock:
            for task in self._tasks:
                if task.get("due") and not task["done"] and not task.get("notified") and task["due"] <= now:
                    task["notified"] = True
                    due.append(dict(task))
            if due:
                self._save()
        return due
