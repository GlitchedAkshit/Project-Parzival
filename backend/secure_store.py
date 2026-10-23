"""
Encrypts secrets (the Home Assistant token) at rest with Windows DPAPI.

DPAPI ties the ciphertext to your Windows user account: the value saved in
settings.json can only be decrypted by you, on this PC - copying the file
elsewhere (or another user on this PC reading it) yields nothing usable.
On other platforms the value is stored as-is, with a console warning.
"""

import base64
import ctypes
import sys
from ctypes import wintypes

_ENTROPY = b"Parzival/HomeAssistant/v1"   # extra salt so other apps' DPAPI blobs can't be swapped in
_PREFIX = "dpapi:"


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data):
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte))), buf


def _call(func, data):
    src, _keep = _blob(data)
    entropy, _keep2 = _blob(_ENTROPY)
    out = _Blob()
    CRYPTPROTECT_UI_FORBIDDEN = 0x1
    if not func(ctypes.byref(src), None, ctypes.byref(entropy), None, None,
                CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out)):
        raise OSError(ctypes.get_last_error() or "DPAPI call failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def available():
    return sys.platform == "win32"


def protect(secret):
    """str -> 'dpapi:<base64>' (or the plain string where DPAPI is unavailable)."""
    if not secret:
        return ""
    if not available():
        print("[secure_store] DPAPI unavailable on this platform - secret stored unencrypted")
        return secret
    crypt = ctypes.windll.crypt32.CryptProtectData
    return _PREFIX + base64.b64encode(_call(crypt, secret.encode("utf-8"))).decode("ascii")


def unprotect(value):
    """Reverses protect(). Plain (legacy) values are returned unchanged."""
    if not value or not str(value).startswith(_PREFIX):
        return value or ""
    crypt = ctypes.windll.crypt32.CryptUnprotectData
    return _call(crypt, base64.b64decode(value[len(_PREFIX):])).decode("utf-8")


def is_protected(value):
    return isinstance(value, str) and value.startswith(_PREFIX)
