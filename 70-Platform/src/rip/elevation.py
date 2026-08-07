"""Fail-closed Windows elevation contract for the operator desktop."""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

_TOKEN_QUERY = 0x0008
_TOKEN_ELEVATION = 20
_TOKEN_INTEGRITY_LEVEL = 25
_SECURITY_MANDATORY_HIGH_RID = 0x3000


class _TokenElevation(ctypes.Structure):
    _fields_ = (("TokenIsElevated", wintypes.DWORD),)


class _SidAndAttributes(ctypes.Structure):
    _fields_ = (("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD))


class _TokenMandatoryLabel(ctypes.Structure):
    _fields_ = (("Label", _SidAndAttributes),)


def elevation_failure_reason() -> str | None:
    """Return a concise reason unless the current Windows token is elevated High."""
    if os.name != "nt":
        return "RIP requires an elevated Windows Administrator process."
    token = wintypes.HANDLE()
    advapi = ctypes.windll.advapi32
    kernel = ctypes.windll.kernel32
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    advapi.OpenProcessToken.argtypes = (wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE))
    advapi.OpenProcessToken.restype = wintypes.BOOL
    advapi.GetTokenInformation.argtypes = (wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
    advapi.GetTokenInformation.restype = wintypes.BOOL
    advapi.GetSidSubAuthorityCount.argtypes = (ctypes.c_void_p,)
    advapi.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
    advapi.GetSidSubAuthority.argtypes = (ctypes.c_void_p, ctypes.c_ubyte)
    advapi.GetSidSubAuthority.restype = ctypes.POINTER(wintypes.DWORD)
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), _TOKEN_QUERY, ctypes.byref(token)):
        return "RIP could not verify the Windows elevation token."
    try:
        elevation = _TokenElevation()
        returned = wintypes.DWORD()
        if not advapi.GetTokenInformation(token, _TOKEN_ELEVATION, ctypes.byref(elevation), ctypes.sizeof(elevation), ctypes.byref(returned)):
            return "RIP could not verify the Windows elevation token."
        if not elevation.TokenIsElevated:
            return "RIP must run as Administrator. Approve the Windows UAC prompt, then reopen RIP."
        size = wintypes.DWORD()
        advapi.GetTokenInformation(token, _TOKEN_INTEGRITY_LEVEL, None, 0, ctypes.byref(size))
        if not size.value:
            return "RIP could not verify the elevated token integrity."
        buffer = ctypes.create_string_buffer(size.value)
        if not advapi.GetTokenInformation(token, _TOKEN_INTEGRITY_LEVEL, buffer, size.value, ctypes.byref(returned)):
            return "RIP could not verify the elevated token integrity."
        label = ctypes.cast(buffer, ctypes.POINTER(_TokenMandatoryLabel)).contents
        count = advapi.GetSidSubAuthorityCount(label.Label.Sid)
        if not count:
            return "RIP could not verify the elevated token integrity."
        rid = advapi.GetSidSubAuthority(label.Label.Sid, count.contents.value - 1)
        if not rid or rid.contents.value < _SECURITY_MANDATORY_HIGH_RID:
            return "RIP requires a High-integrity Administrator process. Approve the Windows UAC prompt, then reopen RIP."
        return None
    finally:
        kernel.CloseHandle(token)
