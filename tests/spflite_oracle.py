"""Run editing scenarios in SPFLite3 (Windows) to get reference results.

SPFLite is started on a scratch file with an initial macro (-E %macro) that
issues each step through SPF_Cmd, SAVEs, and writes a log of return codes and
messages. The profile dialog for an unknown file type is answered with
DEFAULT, and the window is closed afterwards - all by window messages, so the
desktop's focus is never taken.

Leaves nothing behind except SPFLite's own state: the temporary macro is
removed by cleanup().
"""
import ctypes
import os
import shutil
import subprocess
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

SPFLITE = Path(os.environ.get("SPFLITE_EXE", r"C:\apps\SPFLite\SPFLite3.exe"))
MACRO_DIR = Path(os.environ.get("SPFLITE_MACROS",
                                Path.home() / "Documents" / "SPFLite" / "MACROS"))
MACRO_NAME = "zzIsfpedRegTest"

user32 = ctypes.WinDLL("user32", use_last_error=True) if os.name == "nt" else None
if user32:
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    user32.EnumChildWindows.argtypes = [wintypes.HWND, WNDENUMPROC, wintypes.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

WM_SYSCOMMAND, SC_CLOSE, BM_CLICK = 0x0112, 0xF060, 0x00F5


def available():
    return os.name == "nt" and SPFLITE.is_file() and MACRO_DIR.is_dir()


def _text(hwnd):
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def _windows(pid):
    found = []

    def cb(hwnd, _):
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found


def _click_default_profile(pid):
    """Answer 'No profile currently exists for file-type ...' with DEFAULT."""
    for hwnd in _windows(pid):
        if _text(hwnd) == "Create new Profile":
            buttons = []

            def cb(child, _):
                if _text(child) == "DEFAULT":
                    buttons.append(child)
                return True
            user32.EnumChildWindows(hwnd, WNDENUMPROC(cb), 0)
            for b in buttons[:1]:
                user32.PostMessageW(b, BM_CLICK, 0, 0)
                return True
    return False


def _close(proc):
    for hwnd in _windows(proc.pid):
        user32.PostMessageW(hwnd, WM_SYSCOMMAND, SC_CLOSE, 0)
    try:
        proc.wait(5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def _q(s):
    return '"' + s.replace('"', '""') + '"'


def to_commands(steps):
    """Steps (see cases.py) -> SPFLite primary commands."""
    commands = []
    for kind, value in steps:
        if kind == "P":
            commands.append(value)
        else:
            # One LINE per line command, bottom-up so line numbers stay valid
            for line in sorted(value, reverse=True):
                commands.append(f"LINE '{value[line]}' .{line}")
    return commands


def run(lines, steps, timeout=25):
    """Return (saved lines, [(rc, command, message)])."""
    work = Path(tempfile.mkdtemp(prefix="spfreg"))
    data, log = work / "case.txt", work / "case.log"
    data.write_text("\n".join(lines) + "\n", encoding="utf-8")
    commands = to_commands(steps)
    body = [f"' {MACRO_NAME}.macro - temporary isfped regression oracle (auto-generated)",
            'uses "FILE"', "dim r as string"]
    for c in commands:
        body.append(f"SPF_Cmd({_q(c)})")
        body.append(f'r = r + str$(Get_RC) + $TAB + {_q(c)} + $TAB + Get_Msg$ + $CRLF')
    body += ['SPF_Cmd("SAVE")', f"FILE_Save({_q(str(log))}, r)", "halt"]
    (MACRO_DIR / f"{MACRO_NAME}.macro").write_text("\r\n".join(body) + "\r\n",
                                                    encoding="latin-1")
    proc = subprocess.Popen([str(SPFLITE), "-E", f"%{MACRO_NAME}", str(data)],
                            cwd=str(SPFLITE.parent))
    try:
        try:
            deadline = time.time() + timeout
            while not log.exists() and time.time() < deadline:
                time.sleep(0.2)
                _click_default_profile(proc.pid)
            time.sleep(0.3)
            if not log.exists():
                raise RuntimeError("SPFLite did not finish the macro")
        finally:
            _close(proc)
        out = data.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
        if out.endswith("\n"):
            out = out[:-1]
        entries = []
        for row in log.read_text(errors="replace").splitlines():
            rc, cmd, msg = (row.split("\t") + ["", ""])[:3]
            entries.append((int(rc.strip() or 0), cmd, msg))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return out.split("\n"), entries


def cleanup():
    (MACRO_DIR / f"{MACRO_NAME}.macro").unlink(missing_ok=True)
