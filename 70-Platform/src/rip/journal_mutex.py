"""The sole Windows process-wide serializer for Journal Authority publication."""
from __future__ import annotations
import ctypes,hashlib
from contextlib import contextmanager
from .platform_keys import AUTHORITY_ID
_K=ctypes.windll.kernel32; _WAIT_OBJECT_0=0;_WAIT_ABANDONED=0x80;_WAIT_TIMEOUT=0x102
@contextmanager
def journal_authority_lock(timeout_ms:int=10000):
 name="Global\\RIP.JournalAuthority."+hashlib.sha256(AUTHORITY_ID.encode()).hexdigest()
 handle=_K.CreateMutexW(None,False,name)
 if not handle: raise OSError("journal mutex creation failed")
 result=_K.WaitForSingleObject(handle,timeout_ms)
 if result==_WAIT_TIMEOUT: _K.CloseHandle(handle);raise TimeoutError("journal authority lock acquisition timed out")
 if result not in (_WAIT_OBJECT_0,_WAIT_ABANDONED): _K.CloseHandle(handle);raise OSError("journal authority lock acquisition failed")
 try: yield result==_WAIT_ABANDONED
 finally: _K.ReleaseMutex(handle);_K.CloseHandle(handle)
