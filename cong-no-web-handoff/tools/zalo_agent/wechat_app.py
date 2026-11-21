"""WECHAT-01: WeChat trên máy Zalo có đang chạy và đang đăng nhập không, cho `status.json` và máy canh.

Đọc được DB và khóa ảnh ngay cả khi WeChat đã tắt hay chờ đăng nhập (22/11/2026: WeChat tắt từ khoảng 03:48 tới 06:10 mà
`processors.wechat` vẫn ổn), nên phải nhìn chính app. Chỉ ĐỌC danh sách tiến trình và lớp cửa sổ của Windows (ctypes, stdlib):
không đụng giao diện, không bật lớp trợ năng của WeChat, không đọc bộ nhớ hay tiêu đề cửa sổ.

Đo trên máy thật 22/11/2026 (WeChat 4.2):
- Tiến trình chính là `Weixin.exe` có cha không phải `Weixin.exe` (các tiến trình con `--type=…` có cha là tiến trình chính).
- Đã đăng nhập: tiến trình chính có cửa sổ ẩn lớp `Qt…WxTrayIconMessageWindowClass` (biểu tượng khay) và có tiến trình con
  `Weixin.exe` (wxutility, wxocr, wxpublic, xplayer); cả hai còn nguyên khi cửa sổ chính thu xuống khay.
- Màn đăng nhập ("Confirm on Phone"): chỉ cửa sổ cỡ 294×387, không cửa sổ khay, không tiến trình con `Weixin.exe`.
- Không có `Weixin.exe` chính mà có `WeixinUpdate.exe`: đang chờ cập nhật (06:07 ngày 22/11).

Nhiều bản WeChat cùng chạy thì chỉ cần một bản đã đăng nhập là `logged_in`.
"""
from __future__ import annotations

import ctypes
import sys

LOGGED_IN, LOGIN, CLOSED, UPDATE, UNKNOWN = "logged_in", "login", "closed", "update", "unknown"
STATES = (LOGGED_IN, LOGIN, CLOSED, UPDATE, UNKNOWN)
MAIN_EXE, UPDATE_EXE = "weixin.exe", "weixinupdate.exe"
TRAY_SUFFIX = "WxTrayIconMessageWindowClass"   # tiền tố Qt đổi theo phiên bản (Qt51514…), phần đuôi là của WeChat


def classify(processes: list[tuple[int, int, str]], windows: list[tuple[int, str]]) -> str:
    """`processes`: (pid, pid cha, tên exe), `windows`: (pid, lớp cửa sổ) của các cửa sổ cấp trên cùng. Trả một mã trong STATES."""
    weixin = {pid for pid, _, name in processes if name.lower() == MAIN_EXE}
    mains = {pid for pid, parent, name in processes if name.lower() == MAIN_EXE and parent not in weixin}
    if not mains:
        return UPDATE if any(name.lower() == UPDATE_EXE for _, _, name in processes) else CLOSED
    helpers = {parent for _, parent, name in processes if name.lower() == MAIN_EXE and parent in mains}
    trays = {pid for pid, cls in windows if pid in mains and cls.endswith(TRAY_SUFFIX)}
    return LOGGED_IN if helpers | trays else LOGIN


def state() -> str:
    """Trạng thái hiện tại; không đọc được (không phải Windows, API lỗi) thì `unknown`, không bao giờ ném."""
    if sys.platform != "win32":
        return UNKNOWN
    try:
        processes = list_processes()
        mains = {pid for pid, parent, name in processes if name.lower() == MAIN_EXE}
        return classify(processes, list_windows(mains))
    except Exception:   # noqa: BLE001  (máy canh cần một mã, không cần chi tiết lỗi)
        return UNKNOWN


def list_processes() -> list[tuple[int, int, str]]:
    """(pid, pid cha, tên exe) của mọi tiến trình, qua Toolhelp32 (không cần quyền đọc tiến trình khác)."""
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel.Process32FirstW.argtypes = kernel.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(Entry))
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    snap = kernel.CreateToolhelp32Snapshot(0x2, 0)   # TH32CS_SNAPPROCESS
    if not snap or snap == wintypes.HANDLE(-1).value:
        raise OSError(ctypes.get_last_error(), "CreateToolhelp32Snapshot")
    try:
        entry = Entry()
        entry.dwSize = ctypes.sizeof(Entry)
        found = []
        more = kernel.Process32FirstW(snap, ctypes.byref(entry))
        while more:
            found.append((entry.th32ProcessID, entry.th32ParentProcessID, entry.szExeFile))
            more = kernel.Process32NextW(snap, ctypes.byref(entry))
        return found
    finally:
        kernel.CloseHandle(snap)


def list_windows(pids: set[int]) -> list[tuple[int, str]]:
    """(pid, lớp cửa sổ) của các cửa sổ cấp trên cùng thuộc `pids`, kể cả cửa sổ ẩn. Không đọc tiêu đề (có thể là tên nhóm)."""
    from ctypes import wintypes

    if not pids:
        return []
    user = ctypes.WinDLL("user32", use_last_error=True)
    found: list[tuple[int, str]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids:
            name = ctypes.create_unicode_buffer(256)
            user.GetClassNameW(hwnd, name, 256)
            found.append((pid.value, name.value))
        return True

    user.EnumWindows(visit, 0)
    return found
