"""Optional Windows change-time query. Unsupported filesystems fail closed.

FILE_BASIC_INFO.ChangeTime tracks metadata/content changes independently of
LastWriteTime. Python's Windows st_ctime is creation time and is unsuitable.
https://learn.microsoft.com/windows/win32/api/winbase/ns-winbase-file_basic_info
"""
from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache


def change_stamp(path: Path) -> tuple[int, ...] | None:
    """Return native metadata for NTFS/ReFS files, or disable reuse.

    This cache is not a defense against an actor deliberately spoofing native
    change timestamps. All handles are closed, including on query failure.
    """
    if os.name != 'nt':
        return None
    try:
        return _query(path)
    except (OSError, AttributeError):
        return None


@lru_cache(maxsize=1)
def _bindings():
    import ctypes
    from ctypes import wintypes

    class BasicInfo(ctypes.Structure):
        _fields_ = [(name, ctypes.c_longlong) for name in
                    ('creation', 'access', 'write', 'change')] + [('attributes', wintypes.DWORD)]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                       ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    query = kernel.GetFileInformationByHandleEx
    query.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    query.restype = wintypes.BOOL
    volume = kernel.GetVolumeInformationByHandleW
    volume.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD,
                       ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                       wintypes.LPWSTR, wintypes.DWORD]
    volume.restype = wintypes.BOOL
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    return BasicInfo,create,query,volume,close


def _query(path: Path) -> tuple[int, ...] | None:
    import ctypes
    BasicInfo,create,query,volume,close=_bindings()
    # FILE_READ_ATTRIBUTES, share read/write/delete, OPEN_EXISTING,
    # FILE_FLAG_OPEN_REPARSE_POINT: do not dereference the final component.
    handle = create(str(path), 0x80, 7, None, 3, 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        return None
    try:
        fs = ctypes.create_unicode_buffer(32)
        if not volume(handle, None, 0, None, None, None, fs, len(fs)):
            return None
        if fs.value.upper() not in {'NTFS', 'REFS'}:
            return None
        info = BasicInfo()
        if not query(handle, 0, ctypes.byref(info), ctypes.sizeof(info)):
            return None
        if info.change <= 0 or info.attributes & 0x400:  # reparse point
            return None
        return (info.change, info.write, info.attributes)
    finally:
        close(handle)
