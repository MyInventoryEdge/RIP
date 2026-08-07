"""Process-local source-change tracking with fail-safe full-scan fallback.

The tracker is an optimization only. It never creates evidence or replaces the
governed full-content baseline. Any unsupported, unhealthy, overflowed, or
changed state requires the caller to perform a complete SHA-256 verification.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path


if os.name == "nt":
    import ctypes
    from ctypes import wintypes


_FILE_LIST_DIRECTORY = 0x0001
_FILE_SHARE_READ = 0x00000001
_FILE_SHARE_WRITE = 0x00000002
_FILE_SHARE_DELETE = 0x00000004
_OPEN_EXISTING = 3
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_NOTIFY_FILTER = 0x00000001 | 0x00000002 | 0x00000004 | 0x00000008 | 0x00000010 | 0x00000020 | 0x00000100
_ERROR_OPERATION_ABORTED = 995
_WATCH_BUFFER_BYTES = 64 * 1024


class SourceChangeTracker:
    """Watch one repository subtree without reading or modifying its contents."""

    def __init__(self, repository: Path) -> None:
        if os.name != "nt":
            raise OSError("native source change tracking is unavailable on this platform")
        self.repository = repository.resolve()
        self._lock = threading.Lock()
        self._changed_paths: set[str] = set()
        self._healthy = True
        self._closed = False
        self._ready = threading.Event()
        self._handle = _open_directory_handle(self.repository)
        self._thread = threading.Thread(target=self._watch, name="rip-source-watch", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=2):
            self.close()
            raise OSError("native source change tracker did not start")

    @property
    def healthy(self) -> bool:
        with self._lock:
            return self._healthy and not self._closed

    @property
    def changed(self) -> bool:
        with self._lock:
            return bool(self._changed_paths) or not self._healthy or self._closed

    @property
    def changed_paths(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._changed_paths, key=str.casefold))

    def close(self) -> None:
        if os.name != "nt":
            return
        with self._lock:
            if self._closed:
                return
            self._closed = True
            handle = self._handle
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CancelIoEx(wintypes.HANDLE(handle), None)
        kernel32.CloseHandle(wintypes.HANDLE(handle))
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=2)

    def _watch(self) -> None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        buffer = ctypes.create_string_buffer(_WATCH_BUFFER_BYTES)
        returned = wintypes.DWORD()
        self._ready.set()
        while True:
            ok = kernel32.ReadDirectoryChangesW(
                wintypes.HANDLE(self._handle),
                ctypes.byref(buffer),
                _WATCH_BUFFER_BYTES,
                True,
                _NOTIFY_FILTER,
                ctypes.byref(returned),
                None,
                None,
            )
            if not ok:
                error = ctypes.get_last_error()
                with self._lock:
                    closed = self._closed
                    if not closed and error != _ERROR_OPERATION_ABORTED:
                        self._healthy = False
                return
            if returned.value == 0:
                with self._lock:
                    self._healthy = False
                return
            paths = _parse_notifications(buffer.raw[: returned.value])
            if not paths:
                with self._lock:
                    self._healthy = False
                return
            for path in paths:
                with self._lock:
                    self._changed_paths.add(path)


def start_source_change_tracker(repository: Path) -> SourceChangeTracker | None:
    """Return a native tracker or None; callers must full-scan on None."""
    if os.name != "nt":
        return None
    try:
        return SourceChangeTracker(repository)
    except OSError:
        return None


def _open_directory_handle(repository: Path) -> int:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    kernel32.CreateFileW.restype = wintypes.HANDLE
    handle = kernel32.CreateFileW(
        str(repository),
        _FILE_LIST_DIRECTORY,
        _FILE_SHARE_READ | _FILE_SHARE_WRITE | _FILE_SHARE_DELETE,
        None,
        _OPEN_EXISTING,
        _FILE_FLAG_BACKUP_SEMANTICS,
        None,
    )
    invalid = ctypes.c_void_p(-1).value
    if handle in (None, invalid):
        raise OSError(ctypes.get_last_error(), "unable to start native source change tracking")
    return int(handle)


def _parse_notifications(data: bytes) -> tuple[str, ...]:
    paths: list[str] = []
    offset = 0
    while offset + 12 <= len(data):
        next_offset = int.from_bytes(data[offset : offset + 4], "little")
        name_length = int.from_bytes(data[offset + 8 : offset + 12], "little")
        name_end = offset + 12 + name_length
        if name_end > len(data) or name_length % 2:
            return ()
        paths.append(data[offset + 12 : name_end].decode("utf-16-le").replace("\\", "/"))
        if next_offset == 0:
            break
        offset += next_offset
    return tuple(paths)
