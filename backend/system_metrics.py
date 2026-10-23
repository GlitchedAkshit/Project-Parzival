"""
Real CPU / memory / uptime readings via the Win32 API (ctypes), so no extra
packages are needed. On other platforms every value is None and the UI
hides the metric - Parzival never shows made-up numbers.
"""

import ctypes
import sys
import time
from ctypes import wintypes


class _FILETIME(ctypes.Structure):
    _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]

    def value(self):
        return (self.high << 32) | self.low


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


class SystemMetrics:
    def __init__(self):
        self.available = sys.platform == "win32"
        self._prev = self._cpu_times() if self.available else None

    def _cpu_times(self):
        idle, kernel, user = _FILETIME(), _FILETIME(), _FILETIME()
        if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
            return None
        return idle.value(), kernel.value(), user.value()

    def sample(self):
        """Returns {"cpu": %, "memory": %, ...}. CPU is the average load
        since the previous call, so call it at a steady interval."""
        reading = {"cpu": None, "memory": None, "memory_used_gb": None,
                   "memory_total_gb": None, "uptime": None, "ts": time.time()}
        if not self.available:
            return reading

        try:
            now = self._cpu_times()
            if now and self._prev:
                d_idle, d_kernel, d_user = (a - b for a, b in zip(now, self._prev))
                busy_total = d_kernel + d_user   # kernel time includes idle time
                if busy_total > 0:
                    reading["cpu"] = round(max(0.0, min(100.0, 100.0 * (1 - d_idle / busy_total))), 1)
            self._prev = now

            mem = _MEMORYSTATUSEX()
            mem.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)):
                total = mem.ullTotalPhys / 1024 ** 3
                reading["memory"] = int(mem.dwMemoryLoad)
                reading["memory_total_gb"] = round(total, 1)
                reading["memory_used_gb"] = round(total - mem.ullAvailPhys / 1024 ** 3, 1)

            get_ticks = ctypes.windll.kernel32.GetTickCount64
            get_ticks.restype = ctypes.c_ulonglong
            reading["uptime"] = int(get_ticks() / 1000)
        except Exception as e:
            print(f"[system_metrics] Could not read metrics: {e}")
        return reading
