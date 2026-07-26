import ctypes
import re
from ctypes import wintypes

user32 = ctypes.windll.user32

# PotPlayer responds to WM_USER (1024) with a query code in wParam and
# returns the value directly from SendMessage. Verified against
# https://github.com/ld3l/PotPlayerControl (JNAMessageConst.java / JNAPotPlayer.java).
WM_QUERY = 1024
GET_TOTAL_TIME = 20482      # duration, milliseconds
GET_CURRENT_TIME = 20484    # playback position, milliseconds
GET_PLAY_STATUS = 20486     # -1 stopped, 1 paused, 2 playing

STATUS_STOPPED = -1
STATUS_PAUSED = 1
STATUS_PLAYING = 2

user32.SendMessageW.restype = ctypes.c_longlong
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

_EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

_TITLE_SUFFIX_RE = re.compile(r"\s*-\s*PotPlayer.*$", re.IGNORECASE)


def find_window():
    found = []

    def cb(hwnd, lparam):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                if "PotPlayer" in buf.value:
                    found.append((hwnd, buf.value))
        return True

    user32.EnumWindows(_EnumWindowsProc(cb), 0)
    return found[0] if found else None


def _query(hwnd, code):
    return user32.SendMessageW(hwnd, WM_QUERY, code, 0)


def get_state():
    """Return current PotPlayer playback state, or None if not playing anything."""
    win = find_window()
    if not win:
        return None
    hwnd, title = win

    status = _query(hwnd, GET_PLAY_STATUS)
    if status not in (STATUS_PLAYING, STATUS_PAUSED):
        return None

    total_ms = _query(hwnd, GET_TOTAL_TIME)
    current_ms = _query(hwnd, GET_CURRENT_TIME)
    filename = _TITLE_SUFFIX_RE.sub("", title).strip()

    return {
        "filename": filename,
        "playing": status == STATUS_PLAYING,
        "total_ms": total_ms,
        "current_ms": current_ms,
    }


if __name__ == "__main__":
    import time

    print("Polling PotPlayer state, Ctrl+C to stop...")
    while True:
        print(get_state())
        time.sleep(2)
