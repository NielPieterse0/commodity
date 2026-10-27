"""Protect files against Windows writer/replacement races during Parquet reads.

Windows retains non-write/non-delete-sharing handles for each input and all
ancestor directories through DuckDB's pathname query. Other platforms fail
closed: their independently immutable storage must be integrated and proven
before enabling snapshots. The guard cannot itself attest source truth.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path

from .errors import MarketTruthError


@contextmanager
def protected_table_reads(files: Iterable[Path]) -> Iterator[None]:
    """Keep immutable input identities while the database opens them by path."""
    if os.name != "nt":
        raise MarketTruthError(
            "non-Windows immutable source protection not implemented; "
            "market snapshots fail closed"
        )

    import ctypes
    from ctypes import wintypes

    FILE_SHARE_READ = 0x00000001
    GENERIC_READ = 0x80000000
    OPEN_EXISTING = 3
    FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
    invalid = ctypes.c_void_p(-1).value
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    close_handle = kernel.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL

    class FileTime(ctypes.Structure):
        _fields_ = (
            ("dwLowDateTime", wintypes.DWORD),
            ("dwHighDateTime", wintypes.DWORD),
        )

    class FileInfo(ctypes.Structure):
        _fields_ = (
            ("dwFileAttributes", wintypes.DWORD),
            ("ftCreationTime", FileTime),
            ("ftLastAccessTime", FileTime),
            ("ftLastWriteTime", FileTime),
            ("dwVolumeSerialNumber", wintypes.DWORD),
            ("nFileSizeHigh", wintypes.DWORD),
            ("nFileSizeLow", wintypes.DWORD),
            ("nNumberOfLinks", wintypes.DWORD),
            ("nFileIndexHigh", wintypes.DWORD),
            ("nFileIndexLow", wintypes.DWORD),
        )

    get_info = kernel.GetFileInformationByHandle
    get_info.argtypes = (wintypes.HANDLE, ctypes.POINTER(FileInfo))
    get_info.restype = wintypes.BOOL

    source_paths = [Path(path).absolute() for path in files]
    if not source_paths:
        raise MarketTruthError("empty guarded source set")
    # Lock ancestor directories from outermost to innermost as well: otherwise
    # DuckDB can follow a renamed/replaced parent after original file checks.
    ancestors = sorted(
        {parent for path in source_paths for parent in path.parents},
        key=lambda path: (len(path.parts), str(path).lower()),
    )
    paths_to_guard = [*ancestors, *source_paths]
    handles = []
    try:
        for path in paths_to_guard:
            handle = create_file(
                str(path), GENERIC_READ, FILE_SHARE_READ, None, OPEN_EXISTING,
                FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS, None,
            )
            if handle in (None, invalid):
                raise MarketTruthError(
                    "exclusive-read source protection unavailable: "
                    + str(ctypes.get_last_error())
                )
            handles.append(handle)
            info = FileInfo()
            if not get_info(handle, ctypes.byref(info)):
                raise MarketTruthError("source handle identity unavailable")
            if info.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT:
                raise MarketTruthError("market source or ancestor reparse point prohibited")
        yield
    finally:
        for handle in reversed(handles):
            close_handle(handle)
