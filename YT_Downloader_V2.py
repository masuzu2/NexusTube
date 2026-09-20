"""
NexusTube — Modern YouTube & Multi-Platform Music Suite v3.0.0
Design system: Dark OLED · Dynamic Accent · Modern Cards · ui-ux-pro-max
Author: by herlove
Repo: https://github.com/masuzu2/NexusTube
"""

VERSION     = "3.4.0"
GITHUB_REPO = "masuzu2/NexusTube"

# Sentry DSN for crash reporting (opt-in only). Leave empty to disable entirely.
# ผู้ใช้สามารถกำหนด DSN ของตัวเองได้ที่นี่
SENTRY_DSN = ""  # e.g. "https://xxxx@oxxxx.ingest.sentry.io/xxxx"

import base64
import hashlib
import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

# ── Exception Hierarchy: Expected vs Unexpected Errors (Task 4) ─────────────
class NexusTubeError(Exception):
    """Base exception for all NexusTube application errors."""
    pass

class ExpectedNexusError(NexusTubeError):
    """Anticipated operational errors (e.g. network timeout, deleted video, geo-block).
    These should update task status cleanly and NOT trigger fatal crash popups."""
    def __init__(self, message, user_message=None):
        super().__init__(message)
        self.user_message = user_message or message

class NetworkError(ExpectedNexusError):
    """Network connection drop, DNS failure, or server timeout."""
    pass

class DownloadUnavailableError(ExpectedNexusError):
    """Video is private, deleted, requires age confirmation/login, or blocked."""
    pass

class FormatNotSupportedError(ExpectedNexusError):
    """Requested format or DRM stream cannot be downloaded."""
    pass

class ExternalToolError(NexusTubeError):
    """External CLI tool (yt-dlp, ffmpeg, ffprobe) failed after retries."""
    def __init__(self, cmd, returncode, stdout, stderr, user_message=None):
        cmd_str = " ".join(cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        msg = f"External tool failed (code {returncode}): {cmd_str}\n{stderr.strip() if stderr else ''}"
        super().__init__(msg)
        self.cmd = cmd
        self.returncode = returncode
        self.stdout = stdout or ""
        self.stderr = stderr or ""
        self.user_message = user_message or f"Tool failed with code {returncode}: {stderr.strip()[:120] if stderr else ''}"


# ── Bulletproof Safeguard: Streams, Logging & Environment Guard (Task 1) ─────
_GLOBAL_LOG_DIR = None
_GLOBAL_LOG_FILE = None
_GLOBAL_CRASH_FILE = None

class _SafeStream:
    """Safe fallback stream when running under --noconsole (windowed) mode.
    Guarantees write/flush/isatty never fail or raise AttributeError."""
    def __init__(self, log_path=None, original=None):
        self._log_path = log_path
        self._original = original
        self.encoding = "utf-8"
        self.errors = "replace"

    def write(self, s):
        if not s:
            return 0
        written = False
        if self._original is not None:
            try:
                self._original.write(s)
                written = True
            except Exception:
                pass
        if self._log_path:
            try:
                with open(self._log_path, "a", encoding="utf-8", errors="replace") as f:
                    f.write(s)
                written = True
            except Exception:
                pass
        return len(s)

    def writelines(self, lines):
        for line in lines:
            self.write(line)

    def flush(self):
        if self._original is not None:
            try:
                self._original.flush()
            except Exception:
                pass

    def isatty(self):
        return False

    def readable(self):
        return False

    def writable(self):
        return True

    def seekable(self):
        return False

    def fileno(self):
        raise OSError("SafeStream has no fileno")

    def close(self):
        pass


def open_log_folder():
    """Opens the directory containing NexusTube logs in system file manager."""
    global _GLOBAL_LOG_DIR
    if _GLOBAL_LOG_DIR and os.path.isdir(_GLOBAL_LOG_DIR):
        try:
            if sys.platform == "win32":
                os.startfile(_GLOBAL_LOG_DIR)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", _GLOBAL_LOG_DIR])
            else:
                subprocess.Popen(["xdg-open", _GLOBAL_LOG_DIR])
        except Exception:
            pass


def _init_bulletproof_runtime():
    global _GLOBAL_LOG_DIR, _GLOBAL_LOG_FILE, _GLOBAL_CRASH_FILE
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        _GLOBAL_LOG_DIR = os.path.join(appdata, "NexusTube", "logs")
    else:
        _GLOBAL_LOG_DIR = os.path.join(os.path.expanduser("~"), ".nexustube", "logs")

    try:
        os.makedirs(_GLOBAL_LOG_DIR, exist_ok=True)
        _GLOBAL_LOG_FILE = os.path.join(_GLOBAL_LOG_DIR, "runtime.log")
        _GLOBAL_CRASH_FILE = os.path.join(_GLOBAL_LOG_DIR, "crash.log")
    except Exception:
        _GLOBAL_LOG_FILE = None
        _GLOBAL_CRASH_FILE = None

    if sys.stdout is None or not hasattr(sys.stdout, "write"):
        sys.stdout = _SafeStream(_GLOBAL_LOG_FILE, None)
    elif hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if sys.stderr is None or not hasattr(sys.stderr, "write"):
        sys.stderr = _SafeStream(_GLOBAL_LOG_FILE, None)
    elif hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if sys.stdin is None:
        sys.stdin = io.StringIO()

    # Windows DLL directories
    meipass = getattr(sys, "_MEIPASS", None)
    exe_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
    for d in [meipass, exe_dir]:
        if d and os.path.isdir(d) and hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(d)
            except Exception:
                pass

    # Ensure PATH has NexusTube bin directories immediately
    try:
        bin_dirs = [
            os.path.join(exe_dir, "bin"),
            os.path.join(appdata, "NexusTube", "bin") if appdata else "",
            os.path.join(appdata, "NexusTube") if appdata else "",
            os.path.join(appdata, "YTDownloaderPro") if appdata else "",
        ]
        curr_path = os.environ.get("PATH", "")
        new_bins = [b for b in bin_dirs if b and os.path.isdir(b) and b not in curr_path]
        if new_bins:
            os.environ["PATH"] = os.pathsep.join(new_bins) + os.pathsep + curr_path
    except Exception:
        pass

    # Task 1.1: Global unhandled exception hook for main thread
    def _safe_excepthook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, (KeyboardInterrupt, SystemExit, ExpectedNexusError)):
            return
        import traceback as tb
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        msg = "".join(tb.format_exception(exc_type, exc_value, exc_tb))
        report = f"\n[FATAL UNHANDLED EXCEPTION — {timestamp}]\n{msg}\n"
        try:
            sys.stderr.write(report)
        except Exception:
            pass
        try:
            if _GLOBAL_CRASH_FILE:
                with open(_GLOBAL_CRASH_FILE, "a", encoding="utf-8") as cf:
                    cf.write(report)
        except Exception:
            pass
        try:
            import ctypes
            res = ctypes.windll.user32.MessageBoxW(
                0,
                f"NexusTube encountered an unexpected error:\n\n{exc_type.__name__}: {exc_value}\n\nLog saved to:\n{_GLOBAL_CRASH_FILE or _GLOBAL_LOG_FILE}\n\nWould you like to open the log folder?",
                "NexusTube Error",
                0x14  # MB_YESNO | MB_ICONERROR
            )
            if res == 6:  # IDYES
                open_log_folder()
        except Exception:
            pass

    sys.excepthook = _safe_excepthook

    # Task 1.1: Global threading exception hook for background threads
    def _safe_thread_excepthook(args):
        exc_type = args.exc_type
        exc_value = args.exc_value
        exc_tb = args.exc_traceback
        thread = args.thread
        thread_name = getattr(thread, "name", "Thread")

        if issubclass(exc_type, (KeyboardInterrupt, SystemExit, ExpectedNexusError)):
            return

        import traceback as tb
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        msg = "".join(tb.format_exception(exc_type, exc_value, exc_tb))
        report = f"\n[BACKGROUND THREAD EXCEPTION in '{thread_name}' — {timestamp}]\n{msg}\n"
        try:
            sys.stderr.write(report)
        except Exception:
            pass
        try:
            if _GLOBAL_CRASH_FILE:
                with open(_GLOBAL_CRASH_FILE, "a", encoding="utf-8") as cf:
                    cf.write(report)
        except Exception:
            pass
        # Note: Do NOT show modal dialog or kill the app on background thread error!
        # The main app UI continues running reliably.

    if hasattr(threading, "excepthook"):
        threading.excepthook = _safe_thread_excepthook

_init_bulletproof_runtime()


# ── Task 4: Expected Error Classification ────────────────────────────────────
def classify_download_error(stderr_or_msg: str) -> ExpectedNexusError | None:
    """
    Classifies external tool error output into domain-specific ExpectedNexusError subclasses.
    Expected errors should NOT crash the app or trigger fatal modal popups.
    """
    if not stderr_or_msg:
        return None
    msg_str = str(stderr_or_msg)
    msg_lower = msg_str.lower()

    # 1. Video unavailable / deleted / private / age-restricted / geoblocked
    if any(p in msg_lower for p in [
        "video unavailable", "this video has been removed", "private video",
        "sign in to confirm your age", "account associated with this video has been terminated",
        "not available in your country", "uploader has not made this video available",
        "this live event has ended", "premieres in", "members-only content",
        "copyright claim", "who has blocked it"
    ]):
        return DownloadUnavailableError(
            msg_str,
            "วิดีโอนี้ไม่พร้อมใช้งาน (ถูกลบ, เป็นส่วนตัว, ติดจำกัดอายุ หรือถูกบล็อกลิขสิทธิ์/ภูมิภาค)"
        )

    # 2. Network drop, DNS timeout, connection reset, rate limiting
    if any(p in msg_lower for p in [
        "incompleteread", "connection reset", "connection refused",
        "timed out", "timeout", "temporary failure in name resolution",
        "network is unreachable", "remotedisconnected", "http error 429",
        "too many requests", "unable to download webpage", "ssl: cert",
        "name or service not known", "getaddrinfo failed", "errno 10054",
        "errno 10060", "read timed out", "connection aborted",
        "http error 403", "forbidden"
    ]):
        return NetworkError(
            msg_str,
            "เกิดปัญหาการเชื่อมต่อเครือข่าย หรือเซิร์ฟเวอร์ปฏิเสธการเชื่อมต่อชั่วคราว (Rate Limit)"
        )

    # 3. Format or DRM issues
    if any(p in msg_lower for p in [
        "requested format is not available", "drm protected",
        "this format is not available", "unsupported url",
        "no video formats found", "no suitable format found"
    ]):
        return FormatNotSupportedError(
            msg_str,
            "รูปแบบไฟล์ที่เลือกไม่รองรับ หรือคอนเทนต์นี้ติดการป้องกันลิขสิทธิ์ (DRM)"
        )

    return None


# ── Task 2: Centralized External Tool Runner ────────────────────────────────
def run_external_tool(
    cmd: list[str],
    *,
    timeout: float | None = None,
    retries: int = 1,
    retry_backoff: float = 2.0,
    label: str = "",
    check: bool = True,
    capture_output: bool = True,
    text: bool = True,
    encoding: str = "utf-8",
    errors: str = "replace",
    **kwargs
) -> subprocess.CompletedProcess:
    """
    Centralized executor for external CLI tools (yt-dlp, ffmpeg, ffprobe).
    - Logs full command + label before running
    - Captures stdout/stderr safely
    - Automatically retries with exponential backoff on transient errors
    - Raises ExternalToolError or classified ExpectedNexusError when retries exhausted if check=True
    """
    if isinstance(cmd, (str, bytes)):
        cmd = [str(cmd)]
    else:
        cmd = [str(c) for c in cmd]

    if not label and cmd:
        label = os.path.basename(cmd[0])

    # Ensure CREATE_NO_WINDOW on Windows to prevent console flashing
    if sys.platform == "win32" and "creationflags" not in kwargs:
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    cmd_display = " ".join(f'"{c}"' if " " in c else c for c in cmd)
    tag = f"[{label}] " if label else ""
    log_msg = f"[ExternalTool] {tag}Executing: {cmd_display}\n"
    try:
        sys.stderr.write(log_msg)
    except Exception:
        pass

    last_proc = None
    last_error = None

    for attempt in range(1, max(1, retries) + 1):
        try:
            res = subprocess.run(
                cmd,
                capture_output=capture_output,
                text=text,
                encoding=encoding,
                errors=errors,
                timeout=timeout,
                **kwargs
            )
            last_proc = res

            if res.returncode == 0:
                return res

            err_sample = (res.stderr or res.stdout or "").strip()[:200]
            fail_log = f"[ExternalTool] {tag}Attempt {attempt}/{retries} exited with code {res.returncode}: {err_sample}\n"
            try:
                sys.stderr.write(fail_log)
            except Exception:
                pass

            # Non-retryable condition: e.g. input file missing or command syntax error
            if res.returncode in (127, 2) and "No such file" in err_sample:
                break

            if attempt < retries:
                time.sleep(retry_backoff * attempt)

        except FileNotFoundError as fnf:
            last_error = fnf
            try:
                sys.stderr.write(f"[ExternalTool] {tag}Executable not found: {cmd[0]}\n")
            except Exception:
                pass
            break  # Cannot retry missing binary
        except subprocess.TimeoutExpired as te:
            last_error = te
            try:
                sys.stderr.write(f"[ExternalTool] {tag}Attempt {attempt}/{retries} timed out after {timeout}s\n")
            except Exception:
                pass
            if attempt < retries:
                time.sleep(retry_backoff * attempt)
        except Exception as ex:
            last_error = ex
            try:
                sys.stderr.write(f"[ExternalTool] {tag}Attempt {attempt}/{retries} error: {ex}\n")
            except Exception:
                pass
            if attempt < retries:
                time.sleep(retry_backoff * attempt)

    # When execution fails
    if last_proc is not None and last_proc.returncode != 0:
        if check:
            classified = classify_download_error(last_proc.stderr or last_proc.stdout or "")
            if classified:
                raise classified
            raise ExternalToolError(
                cmd=cmd,
                returncode=last_proc.returncode,
                stdout=last_proc.stdout,
                stderr=last_proc.stderr,
                user_message=f"{label or cmd[0]} failed (exit code {last_proc.returncode})"
            )
        return last_proc

    if last_error is not None:
        if check:
            raise ExternalToolError(
                cmd=cmd,
                returncode=-1,
                stdout="",
                stderr=str(last_error),
                user_message=f"{label or cmd[0]} failed to execute: {last_error}"
            )
        return subprocess.CompletedProcess(args=cmd, returncode=-1, stdout="", stderr=str(last_error))

    return last_proc or subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

# ── Fix: _tkinter DLL initialization ─────────────────────────────────────────
# PyInstaller runtime hook ต้องการ TCL_LIBRARY / TK_LIBRARY ชี้ไปที่ถูกที่
# ก่อน import tkinter เสมอ (ทั้งบน _MEIPASS และ dev environment)
def _fix_tcltk_paths():
    meipass = getattr(sys, "_MEIPASS", None)
    search_roots = [meipass] if meipass else []
    search_roots += [os.path.dirname(sys.executable)]

    candidates_tcl = ["tcl8.6", os.path.join("tcl", "tcl8.6"), "_tcl_data"]
    candidates_tk  = ["tk8.6",  os.path.join("tcl", "tk8.6"),  "_tk_data"]

    for root in search_roots:
        if not root:
            continue
        for c in candidates_tcl:
            p = os.path.join(root, c)
            if os.path.isdir(p):
                os.environ.setdefault("TCL_LIBRARY", p)
                break
        for c in candidates_tk:
            p = os.path.join(root, c)
            if os.path.isdir(p):
                os.environ.setdefault("TK_LIBRARY", p)
                break
        if "TCL_LIBRARY" in os.environ and "TK_LIBRARY" in os.environ:
            break

_fix_tcltk_paths()
# ─────────────────────────────────────────────────────────────────────────────

import tkinter as tk
import traceback

# ── Task 1.2: Tkinter Callback Exception Hook ────────────────────────────────
def _safe_tk_report_callback_exception(self, exc_type, exc_value, exc_tb):
    """
    Overrides tk.Tk.report_callback_exception to capture exceptions occurring inside
    widget callbacks or Tkinter event loop without swallowing them or crashing silently.
    """
    if issubclass(exc_type, (KeyboardInterrupt, SystemExit, ExpectedNexusError)):
        return

    import traceback as tb
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    msg = "".join(tb.format_exception(exc_type, exc_value, exc_tb))
    report = f"\n[TKINTER CALLBACK EXCEPTION — {timestamp}]\n{msg}\n"

    try:
        sys.stderr.write(report)
    except Exception:
        pass
    try:
        if _GLOBAL_CRASH_FILE:
            with open(_GLOBAL_CRASH_FILE, "a", encoding="utf-8") as cf:
                cf.write(report)
    except Exception:
        pass
    try:
        import ctypes
        res = ctypes.windll.user32.MessageBoxW(
            0,
            f"An unexpected UI callback error occurred:\n\n{exc_type.__name__}: {exc_value}\n\nThe application will attempt to continue running.\n\nWould you like to open the log folder?",
            "NexusTube UI Notice",
            0x14  # MB_YESNO | MB_ICONWARNING
        )
        if res == 6:  # IDYES
            open_log_folder()
    except Exception:
        pass

tk.Tk.report_callback_exception = _safe_tk_report_callback_exception

from concurrent.futures import ThreadPoolExecutor
from tkinter import filedialog, messagebox


try:
    import ctypes
    from ctypes import wintypes
except ImportError:
    ctypes = None
    wintypes = None


def _setup_safe_font_loading():
    """
    Windows GDI Font Redirection Hook.
    Intercepts AddFontResourceExW and AddFontResourceExA so CustomTkinter fonts
    originating in temporary directories (e.g. PyInstaller _MEIPASS) are copied to and
    loaded from %LOCALAPPDATA%\\NexusTube\\fonts. This prevents Windows GDI from locking
    files in _MEIPASS, completely eliminating the 'Failed to remove temporary directory' warning.
    """
    if sys.platform != "win32" or not ctypes:
        return
    try:
        gdi32 = ctypes.windll.gdi32
        orig_add_w = gdi32.AddFontResourceExW
        orig_add_a = getattr(gdi32, "AddFontResourceExA", None)
        meipass = getattr(sys, "_MEIPASS", None)
        temp_dir = tempfile.gettempdir()
        _loaded_fonts = []

        def _get_long_path(p):
            if not p or not isinstance(p, str):
                return ""
            try:
                buf = ctypes.create_unicode_buffer(1024)
                if ctypes.windll.kernel32.GetLongPathNameW(p, buf, 1024):
                    return buf.value
            except Exception:
                pass
            return p

        def _get_short_path(p):
            if not p or not isinstance(p, str):
                return ""
            try:
                buf = ctypes.create_unicode_buffer(1024)
                if ctypes.windll.kernel32.GetShortPathNameW(p, buf, 1024):
                    return buf.value
            except Exception:
                pass
            return p

        def _extract_path(arg):
            if not arg:
                return None
            if isinstance(arg, str):
                return arg
            if isinstance(arg, bytes):
                try:
                    return arg.decode("utf-8", errors="replace")
                except Exception:
                    return None
            obj = getattr(arg, "_obj", None)
            if obj is not None:
                val = getattr(obj, "value", None)
                if isinstance(val, (str, bytes)):
                    return _extract_path(val)
            val = getattr(arg, "value", None)
            if isinstance(val, (str, bytes)):
                return _extract_path(val)
            return None

        def _is_temp_or_meipass(raw_path):
            if not raw_path or not isinstance(raw_path, str):
                return False
            p_lower = raw_path.lower().replace("/", "\\")
            if "\\_mei" in p_lower or "/_mei" in p_lower or "_mei" in p_lower:
                return True
            if "customtkinter" in p_lower and (".ttf" in p_lower or ".otf" in p_lower or "roboto" in p_lower or "shape" in p_lower):
                return True
            check_dirs = [temp_dir, os.environ.get("TEMP"), os.environ.get("TMP"), meipass]
            for td in check_dirs:
                if not td:
                    continue
                for cand in (td, _get_long_path(td), _get_short_path(td)):
                    if cand:
                        cand_norm = cand.lower().replace("/", "\\")
                        if cand_norm in p_lower:
                            return True
            return False

        def _get_persistent_font_path(raw_path):
            if not raw_path or not isinstance(raw_path, str):
                return None
            if not _is_temp_or_meipass(raw_path):
                return None
            local_appdata = (
                os.environ.get("LOCALAPPDATA")
                or os.environ.get("APPDATA")
                or os.path.expanduser("~")
            )
            persistent_dir = os.path.join(local_appdata, "NexusTube", "fonts")
            try:
                os.makedirs(persistent_dir, exist_ok=True)
                dest = os.path.join(persistent_dir, os.path.basename(raw_path))
                if not os.path.exists(dest) or (os.path.exists(raw_path) and os.path.getsize(dest) != os.path.getsize(raw_path)):
                    shutil.copy2(raw_path, dest)
                return dest
            except Exception:
                return None

        def hooked_add_w(byref_buf, flags=0x10, pdv=0):
            raw_path = _extract_path(byref_buf)
            if raw_path and _is_temp_or_meipass(raw_path):
                p_path = _get_persistent_font_path(raw_path)
                if p_path:
                    _loaded_fonts.append((p_path, flags, True))
                    if isinstance(byref_buf, str):
                        return orig_add_w(p_path, flags, pdv)
                    new_buf = ctypes.create_unicode_buffer(p_path)
                    return orig_add_w(ctypes.byref(new_buf), flags, pdv)
            if raw_path:
                _loaded_fonts.append((raw_path, flags, True))
            return orig_add_w(byref_buf, flags, pdv)

        def hooked_add_a(byref_buf, flags=0x10, pdv=0):
            raw_path = _extract_path(byref_buf)
            if raw_path and _is_temp_or_meipass(raw_path):
                p_path = _get_persistent_font_path(raw_path)
                if p_path:
                    _loaded_fonts.append((p_path, flags, False))
                    if isinstance(byref_buf, (str, bytes)):
                        enc = p_path.encode("utf-8", errors="replace")
                        return orig_add_a(enc, flags, pdv)
                    new_buf = ctypes.create_string_buffer(p_path.encode("utf-8", errors="replace"))
                    return orig_add_a(ctypes.byref(new_buf), flags, pdv)
            if raw_path:
                _loaded_fonts.append((raw_path, flags, False))
            return orig_add_a(byref_buf, flags, pdv)

        gdi32.AddFontResourceExW = hooked_add_w
        if orig_add_a:
            gdi32.AddFontResourceExA = hooked_add_a

        import atexit

        def _cleanup_fonts():
            for fpath, flags, is_wide in list(_loaded_fonts):
                try:
                    if is_wide:
                        buf = ctypes.create_unicode_buffer(fpath)
                        gdi32.RemoveFontResourceExW(ctypes.byref(buf), flags, 0)
                    else:
                        buf = ctypes.create_string_buffer(fpath.encode("utf-8", errors="replace"))
                        gdi32.RemoveFontResourceExA(ctypes.byref(buf), flags, 0)
                except Exception:
                    pass
            _loaded_fonts.clear()

        atexit.register(_cleanup_fonts)
    except Exception:
        pass


_setup_safe_font_loading()

import customtkinter as ctk

# Additional protection: ensure customtkinter FontManager directly uses persistent paths
try:
    from customtkinter.windows.widgets.font import font_manager as _ctk_fm
    _orig_win_load_font = _ctk_fm.FontManager.windows_load_font
    @classmethod
    def _safe_win_load_font(cls, font_path, private=True, enumerable=False):
        local_appdata = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
        p_dir = os.path.join(local_appdata, "NexusTube", "fonts")
        if isinstance(font_path, str):
            p_lower = font_path.lower().replace("/", "\\")
            if "\\_mei" in p_lower or "/_mei" in p_lower or "_mei" in p_lower or "customtkinter" in p_lower:
                try:
                    os.makedirs(p_dir, exist_ok=True)
                    dest = os.path.join(p_dir, os.path.basename(font_path))
                    if not os.path.exists(dest) or (os.path.exists(font_path) and os.path.getsize(dest) != os.path.getsize(font_path)):
                        shutil.copy2(font_path, dest)
                    font_path = dest
                except Exception:
                    pass
        return _orig_win_load_font(font_path, private=private, enumerable=enumerable)
    _ctk_fm.FontManager.windows_load_font = _safe_win_load_font
except Exception:
    pass
import requests
from PIL import Image

try:
    import mutagen
except ImportError:
    mutagen = None

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

# ── Feature 5: Sentry Crash Reporting (optional dependency) ──────────────────
# sentry_sdk ไม่จำเป็นต้องติดตั้ง — ถ้าไม่มีจะ fallback อย่างเงียบๆ
try:
    import sentry_sdk
    from sentry_sdk import capture_exception as _sentry_capture
    SENTRY_AVAILABLE = True
except ImportError:
    sentry_sdk = None
    _sentry_capture = None
    SENTRY_AVAILABLE = False

from nexus_audio import (
    EQ_PRESETS,
    clean_music_title,
    convert_audio_file,
    detect_platform_url,
    export_m3u8_playlist,
    fetch_lyrics,
    format_lrc,
    generate_ffmpeg_eq_filter,
    get_active_lyric_index,
    parse_lrc,
    parse_music_metadata,
    resolve_multiplatform_url,
    safe_http_get,
    safe_json_response,
    tag_audio_file,
)
from nexus_discord import DiscordRPC
from nexus_hotkeys_tray import GlobalMediaHotkeys, SystemTrayIcon

__all__ = [
    "clean_music_title",
    "parse_lrc",
    "format_lrc",
    "get_active_lyric_index",
    "fetch_lyrics",
    "parse_music_metadata",
    "EQ_PRESETS",
    "generate_ffmpeg_eq_filter",
    "detect_platform_url",
    "resolve_multiplatform_url",
    "tag_audio_file",
    "convert_audio_file",
    "export_m3u8_playlist",
    "safe_http_get",
    "safe_json_response",
    "is_valid_binary",
    "is_webview2_available",
    "setup_crash_handler",
    "NexusBridgeAPI",
    "DiscordRPC",
    "GlobalMediaHotkeys",
    "SystemTrayIcon",
    "run_app",
]


def setup_crash_handler():
    """
    Installs global exception hooks for main thread and background worker threads.
    Logs diagnostics to %APPDATA%/YTDownloaderPro/crash.log and current directory.
    Pops up native Windows error alert on critical failures.
    """
    def _handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, (KeyboardInterrupt, SystemExit, ExpectedNexusError)):
            return

        tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        appdata_base = os.getenv("APPDATA") or os.path.expanduser("~")
        appdata_dir = (
            os.path.join(appdata_base, "NexusTube", "logs")
            if sys.platform == "win32"
            else os.path.join(appdata_base, ".NexusTube", "logs")
        )
        crash_log_file = os.path.join(appdata_dir, "crash.log")
        crash_report = (
            f"==================== NEXUSTUBE CRASH REPORT ====================\n"
            f"Timestamp : {timestamp}\n"
            f"Version   : {VERSION}\n"
            f"Platform  : {sys.platform} ({platform.platform() if hasattr(platform, 'platform') else 'unknown'})\n"
            f"Python    : {sys.version}\n"
            f"Executable: {getattr(sys, 'executable', 'unknown')} (frozen={getattr(sys, 'frozen', False)})\n"
            f"Exception : {exc_type.__name__}: {exc_value}\n"
            f"Traceback :\n{tb_text}\n"
            f"=================================================================\n\n"
        )

        try:
            os.makedirs(appdata_dir, exist_ok=True)
            with open(crash_log_file, "a", encoding="utf-8") as f:
                f.write(crash_report)
        except Exception:
            pass

        try:
            with open("nexus_crash.log", "a", encoding="utf-8") as f:
                f.write(crash_report)
        except Exception:
            pass

        try:
            sys.stderr.write(crash_report)
        except Exception:
            pass

        # Only display modal popup if the crash happened on the main GUI thread
        is_main = (threading.current_thread() is threading.main_thread())
        if sys.platform == "win32" and is_main:
            try:
                import ctypes
                summary = (
                    f"NexusTube encountered an unexpected error:\n\n"
                    f"{exc_type.__name__}: {exc_value}\n\n"
                    f"A detailed crash log has been saved to:\n{crash_log_file}\n\n"
                    f"Would you like to open the log folder?"
                )
                res = ctypes.windll.user32.MessageBoxW(0, summary, "NexusTube Crash Handler", 0x14)
                if res == 6:
                    open_log_folder()
            except Exception:
                pass

    sys.excepthook = _handle_exception
    if hasattr(threading, "excepthook"):
        def _thread_excepthook(args):
            _handle_exception(args.exc_type, args.exc_value, args.exc_traceback)
        threading.excepthook = _thread_excepthook

    tk.Tk.report_callback_exception = _safe_tk_report_callback_exception


def init_sentry(config: dict):
    """
    Initialize Sentry SDK for opt-in crash telemetry.
    Safe to call even if sentry_sdk is not installed.
    - config: app config dict (must contain 'telemetry_enabled' key)
    - Requires SENTRY_DSN to be set at module level
    - Sends: platform, VERSION, exception type+message, anonymized traceback
    - NEVER sends: file paths, URLs, user data, download history
    """
    if not SENTRY_AVAILABLE:
        return  # sentry_sdk not installed, silently skip
    if not SENTRY_DSN:
        return  # DSN not configured, silently skip
    if not config.get("telemetry_enabled", False):
        return  # user has not opted in
    try:
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            release=f"nexustube@{VERSION}",
            environment="production" if getattr(sys, "frozen", False) else "development",
            traces_sample_rate=0.0,      # ปิด performance monitoring
            profiles_sample_rate=0.0,    # ปิด profiling
            send_default_pii=False,      # ห้ามส่ง PII เด็ดขาด
            max_breadcrumbs=20,
            before_send=_sentry_before_send,
        )
        sentry_sdk.set_tag("platform", sys.platform)
        sentry_sdk.set_tag("frozen", str(getattr(sys, "frozen", False)))
        sentry_sdk.set_tag("version", VERSION)
        print(f"[NexusTube] Sentry telemetry initialized (release={VERSION})")
    except Exception as e:
        print(f"[NexusTube] Sentry init failed (non-critical): {e}")


def _sentry_before_send(event, hint):
    """
    Sentry before_send hook: strip any sensitive data before the event is sent.
    Removes file paths, URLs, and any stack frame locals that might contain user data.
    """
    # ลบ locals ทั้งหมดจาก stack frames เพื่อป้องกันการรั่วข้อมูล
    try:
        for exc in event.get("exception", {}).get("values", []):
            for frame in exc.get("stacktrace", {}).get("frames", []):
                frame.pop("vars", None)        # ลบ local variables
                frame.pop("pre_context", None)
                frame.pop("post_context", None)
    except Exception:
        pass
    # ลบ breadcrumbs ที่อาจมี URL หรือ path
    try:
        event.get("breadcrumbs", {}).get("values", []).clear()
    except Exception:
        pass
    return event


try:
    from plyer import notification
except ImportError:
    notification = None

def show_notify(title, msg):
    if notification:
        try:
            notification.notify(title=title, message=msg, app_name="NexusTube", timeout=5)
        except Exception:
            pass

def time_to_seconds(t_str):
    """Parse HH:MM:SS, MM:SS, SS, or float seconds string into float seconds."""
    if not t_str:
        return 0.0
    s = str(t_str).strip()
    try:
        if ":" in s:
            parts = s.split(":")
            if len(parts) == 3:
                return max(0.0, float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2]))
            elif len(parts) == 2:
                return max(0.0, float(parts[0]) * 60 + float(parts[1]))
        return max(0.0, float(s))
    except Exception:
        return 0.0

def seconds_to_time(sec):
    """Format float or integer seconds to HH:MM:SS string."""
    sec = max(0.0, float(sec))
    isec = int(sec)
    h = isec // 3600
    m = (isec % 3600) // 60
    s = isec % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def sanitize_filename(name):
    """Strip characters illegal in Windows/POSIX filenames while keeping Unicode text."""
    if not name:
        return "track"
    cleaned = re.sub(r'[\\/*?:"<>|]', "", str(name))
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned[:120] if cleaned else "track"

def is_valid_binary(filepath, min_size=1000):
    """Checks if a file exists, is non-empty, and possesses valid executable headers."""
    if not filepath or not os.path.isfile(filepath):
        return False
    try:
        size = os.path.getsize(filepath)
        if size < min_size:
            return False
        if sys.platform == "win32" and filepath.lower().endswith(".exe"):
            with open(filepath, "rb") as f:
                header = f.read(2)
                if header != b"MZ":
                    return False
        return True
    except Exception:
        return False

def is_webview2_available():
    """
    Checks if Microsoft Edge WebView2 runtime is operable on Windows.
    Returns True on macOS / Linux / other platforms.
    """
    if sys.platform != "win32":
        return True
    try:
        import winreg
        def check_reg(hive, subkey):
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    pv, _ = winreg.QueryValueEx(key, "pv")
                    return bool(pv and pv != "0.0.0.0" and pv != "0")
            except Exception:
                return False

        keys = [
            r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
            r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
            r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{2CD8A007-E189-409D-A2C8-9AF4EF3C72AA}",
            r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{2CD8A007-E189-409D-A2C8-9AF4EF3C72AA}",
            r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{0D50BFEC-CD6A-4F9A-964C-C7416E3ACB10}",
            r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{0D50BFEC-CD6A-4F9A-964C-C7416E3ACB10}",
            r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{65C35B14-6C1D-4122-AC46-7148CC9D6497}",
            r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{65C35B14-6C1D-4122-AC46-7148CC9D6497}",
        ]
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for k in keys:
                if check_reg(hive, k):
                    return True
    except Exception:
        pass

    try:
        import webview.platforms.winforms as winforms
        if hasattr(winforms, "_is_chromium"):
            return bool(winforms._is_chromium())
    except Exception:
        pass
    return False

def get_binary_path(appdata_dir, name, exe_ext=""):
    """Find binary executable across all locations or fallback to system PATH."""
    try:
        from nexus_doctor import find_binary
        found = find_binary(name)
        if found:
            return found
    except Exception:
        pass

    appdata_file = os.path.join(appdata_dir, f"{name}{exe_ext}")
    if os.path.exists(appdata_file):
        if is_valid_binary(appdata_file):
            return appdata_file
        else:
            try:
                os.remove(appdata_file)
            except Exception:
                pass

    sys_found = shutil.which(f"{name}{exe_ext}") or shutil.which(name)
    if sys_found and is_valid_binary(sys_found):
        return sys_found
    return appdata_file

# ── Design Tokens ─────────────────────────────────────────────────────────────
BG        = "#0A0A16"   # Deep OLED Black
SIDEBAR   = "#06060F"   # Pitch Black Sidebar
SURFACE   = "#13132B"   # Elevated card background
SURFACE2  = "#1D1D3A"   # Secondary elevation (inputs, inner cards)
BORDER    = "#282846"   # Soft borders
PRIMARY   = "#4F46E5"   # Vibrant Indigo
PRIMARY_HV= "#4338CA"
TEXT      = "#F8FAFC"   # Crisp White text
MUTED     = "#8B9BB4"   # High legibility muted text
ERROR     = "#EF4444"   # Red
WARN      = "#F59E0B"   # Amber
SUCCESS   = "#22C55E"   # Neon Green

# Available Theme Accents
ACCENT_PALETTE = {
    "Green":  {"color": "#22C55E", "hover": "#16A34A"},
    "Indigo": {"color": "#6366F1", "hover": "#4F46E5"},
    "Pink":   {"color": "#EC4899", "hover": "#DB2777"},
    "Cyan":   {"color": "#06B6D4", "hover": "#0891B2"},
    "Amber":  {"color": "#F59E0B", "hover": "#D97706"},
    "Purple": {"color": "#A855F7", "hover": "#9333EA"},
}

FONT_H   = ("Segoe UI", 24, "bold")
FONT_MD  = ("Segoe UI", 15, "bold")
FONT_SM  = ("Segoe UI", 12)
FONT_XS  = ("Segoe UI", 10)
FONT_MONO= ("Consolas", 10)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── Complete Bilingual Localization (EN / TH) ────────────────────────────────
LOCALES = {
    "Search": {"en": "Search", "th": "ค้นหา"},
    "Queue": {"en": "Queue", "th": "คิวโหลด"},
    "Library": {"en": "Library", "th": "คลังเพลง"},
    "Settings": {"en": "Settings", "th": "ตั้งค่า"},
    "Search & Download": {"en": "Search & Download", "th": "ค้นหาและดาวน์โหลด"},
    "Search_Sub": {"en": "Search YouTube or paste video / playlist link", "th": "ค้นหาจาก YouTube หรือวางลิงก์วิดีโอ/เพลย์ลิสต์"},
    "Paste": {"en": "📋 Paste", "th": "📋 วางลิงก์"},
    "SearchBtn": {"en": "🔍 Search", "th": "🔍 ค้นหา"},
    "+ Add URL": {"en": "+ Add URL", "th": "+ เพิ่ม URL"},
    "Import TXT": {"en": "📄 Import TXT", "th": "📄 นำเข้า TXT"},
    "Results": {"en": "Results", "th": "ผลการค้นหา"},
    "No results found.": {"en": "No results found.", "th": "ไม่พบผลลัพธ์"},
    "Searching...": {"en": "Searching YouTube...", "th": "กำลังค้นหาจาก YouTube..."},
    "Resolving URL...": {"en": "Resolving video details...", "th": "กำลังดึงข้อมูลวิดีโอ..."},
    "Download": {"en": "Download", "th": "ดาวน์โหลด"},
    "Download Queue": {"en": "Download Queue", "th": "คิวการดาวน์โหลด"},
    "Queue_Sub": {"en": "Track active downloads with real-time speed & ETA", "th": "ติดตามสถานะการดาวน์โหลด ความเร็ว และเวลาที่เหลือ"},
    "Clear Finished": {"en": "🗑️ Clear Finished", "th": "🗑️ ล้างที่เสร็จแล้ว"},
    "Open Downloads Folder": {"en": "📂 Open Folder", "th": "📂 เปิดโฟลเดอร์"},
    "No active downloads": {"en": "No active downloads in queue.", "th": "ยังไม่มีรายการในคิวโหลด"},
    "Refresh": {"en": "🔄 Refresh", "th": "🔄 รีเฟรช"},
    "Search Library...": {"en": "🔍 Filter library songs or artists...", "th": "🔍 ค้นหาเพลงหรือศิลปินในคลัง..."},
    "No files downloaded yet.": {"en": "No files downloaded yet.", "th": "ยังไม่มีไฟล์ที่ดาวน์โหลด"},
    "Trim": {"en": "✂️ Trim", "th": "✂️ ตัดเสียง"},
    "Play": {"en": "▶ Play", "th": "▶ เล่น"},
    "Play in App": {"en": "▶ Play", "th": "▶ เล่นในแอป"},
    "Show in Folder": {"en": "📂 Folder", "th": "📂 ที่เก็บไฟล์"},
    "Delete": {"en": "🗑️ Delete", "th": "🗑️ ลบ"},
    "DeleteConfirm": {"en": "Are you sure you want to permanently delete:\n", "th": "คุณแน่ใจหรือไม่ว่าต้องการลบไฟล์นี้ถาวร:\n"},
    "Settings_Title": {"en": "Settings & Preferences", "th": "ตั้งค่าและปรับแต่ง"},
    "Settings_Sub": {"en": "Configure download formats, engine behavior, and UI", "th": "ตั้งค่ารูปแบบการดาวน์โหลด ระบบ และหน้าตาแอป"},
    "Default Format": {"en": "Default Download Format", "th": "รูปแบบการดาวน์โหลดเริ่มต้น"},
    "Download Options": {"en": "Download Options", "th": "ตัวเลือกการดาวน์โหลดเพิ่มเติม"},
    "Theme Accent Color": {"en": "Theme Accent Color", "th": "สีธีมหลัก (Accent Color)"},
    "Language": {"en": "Language", "th": "ภาษา (Language)"},
    "Output Folder": {"en": "Output Folder", "th": "โฟลเดอร์บันทึกไฟล์"},
    "Browse": {"en": "Browse", "th": "เลือกโฟลเดอร์"},
    "Engines Status": {"en": "Self-Healing Engine Status", "th": "สถานะระบบเครื่องมือและตัวช่วยดาวน์โหลด"},
    "Update Engines Now": {"en": "🔄 Update Engines Now", "th": "🔄 ตรวจสอบและอัปเดตเครื่องมือ"},
    "Audio  —  MP3 320kbps (Extreme)": {"en": "Audio  —  MP3 320kbps (Extreme CBR)", "th": "เสียง  —  MP3 320kbps (ชัดสูงสุด CBR)"},
    "Audio  —  M4A / AAC (Source Quality)": {"en": "Audio  —  M4A / AAC (Source Quality, No Loss)", "th": "เสียง  —  M4A / AAC (คุณภาพแท้จากต้นฉบับ ไม่ลดทอน)"},
    "Audio  —  FLAC (Lossless)": {"en": "Audio  —  FLAC (Lossless Audio)", "th": "เสียง  —  FLAC (Lossless คุณภาพสูงสุด)"},
    "Video  —  MP4 (Best Available / 4K)": {"en": "Video  —  MP4 (Best Available / up to 4K)", "th": "วิดีโอ  —  MP4 (ชัดที่สุด / สูงสุด 4K)"},
    "Video  —  MP4 (1080p Full HD)": {"en": "Video  —  MP4 (1080p Full HD)", "th": "วิดีโอ  —  MP4 (1080p Full HD คมชัดสูง)"},
    "Video  —  MP4 (720p HD)": {"en": "Video  —  MP4 (720p HD)", "th": "วิดีโอ  —  MP4 (720p HD มาตรฐาน)"},
    "Embed thumbnail / album art": {"en": "Embed thumbnail & album cover art", "th": "ฝังรูปภาพหน้าปกและอัลบั้มอาร์ต"},
    "Embed metadata & artist info": {"en": "Embed ID3 tags & artist metadata", "th": "ฝังแท็กข้อมูลเพลง ศิลปิน อัลบั้ม"},
    "Embed lyrics / subtitles": {"en": "Embed lyrics / subtitles (English/Thai)", "th": "ฝังเนื้อเพลงและคำบรรยาย (English/Thai)"},
    "SponsorBlock": {"en": "SponsorBlock (Auto-skip sponsors)", "th": "SponsorBlock (ตัดท่อนโฆษณา/สปอนเซอร์อัตโนมัติ)"},
    "Volume Normalization": {"en": "Audio Volume Normalization", "th": "ปรับระดับความดังเสียงให้เท่ากันอัตโนมัติ"},
    "Smart Playlist": {"en": "Smart Playlist Selector", "th": "เลือกดาวน์โหลดจากเพลย์ลิสต์"},
    "Select All": {"en": "✓ Select All", "th": "✓ เลือกทั้งหมด"},
    "Deselect All": {"en": "✗ Deselect All", "th": "✗ ยกเลิกทั้งหมด"},
    "Download Selected": {"en": "Download Selected", "th": "ดาวน์โหลดที่เลือก"},
    "Cancel": {"en": "🛑 Cancel", "th": "🛑 ยกเลิก"},
    "Retry": {"en": "🔄 Retry", "th": "🔄 ลองใหม่"},
    "Waiting…": {"en": "Waiting in queue…", "th": "กำลังรอคิว…"},
    "Starting…": {"en": "Starting engine…", "th": "กำลังเริ่มดาวน์โหลด…"},
    "Processing…": {"en": "Processing audio / tags…", "th": "กำลังประมวลผลไฟล์และแท็ก…"},
    "Complete ✓": {"en": "Complete ✓", "th": "ดาวน์โหลดเสร็จสมบูรณ์ ✓"},
    "Cancelled": {"en": "Cancelled 🛑", "th": "ยกเลิกแล้ว 🛑"},
    "Failed ✗": {"en": "Failed ✗", "th": "ดาวน์โหลดไม่สำเร็จ ✗"},
    "Trimmer_Title": {"en": "✂️ Audio Trimmer & Ringtone Maker", "th": "✂️ เครื่องมือตัดเสียงและทำเสียงเรียกเข้า"},
    "Start Time": {"en": "Start Time (HH:MM:SS or SS)", "th": "เวลาเริ่มต้น (HH:MM:SS หรือ วินาที)"},
    "End Time": {"en": "End Time (HH:MM:SS or SS)", "th": "เวลาสิ้นสุด (HH:MM:SS หรือ วินาที)"},
    "Preview Slice": {"en": "🔊 Preview Slice", "th": "🔊 ฟังตัวอย่าง"},
    "Stop Preview": {"en": "⏹ Stop", "th": "⏹ หยุด"},
    "Trim Now": {"en": "✂️ Trim & Save", "th": "✂️ ตัดและบันทึก"},
    "Repeat": {"en": "Repeat", "th": "เล่นซ้ำ"},
    "Shuffle": {"en": "Shuffle", "th": "สุ่มเพลง"},
    "Lyrics": {"en": "🎤 Lyrics", "th": "🎤 เนื้อเพลง"},
    "Synchronized Lyrics": {"en": "🎤 Synchronized Lyrics & Karaoke", "th": "🎤 คาราโอเกะและเนื้อเพลงสด"},
    "Equalizer": {"en": "🎛️ Equalizer", "th": "🎛️ อีควอไลเซอร์"},
    "Audio Equalizer & Presets": {"en": "🎛️ Audio Equalizer & DSP Presets", "th": "🎛️ ปรับแต่งเสียง & พรีเซ็ต EQ"},
    "EQ Preset": {"en": "Preset:", "th": "พรีเซ็ตเสียง:"},
    "Reset EQ": {"en": "Reset to Flat", "th": "รีเซ็ตค่าเดิม"},
    "Bass (60Hz)": {"en": "Sub Bass (60 Hz)", "th": "เสียงเบสลึก (60 Hz)"},
    "Low-Mid (250Hz)": {"en": "Low Mid (250 Hz)", "th": "เสียงกลางต่ำ (250 Hz)"},
    "Mid (1kHz)": {"en": "Midrange (1 kHz)", "th": "เสียงกลาง/ร้อง (1 kHz)"},
    "High-Mid (4kHz)": {"en": "High Mid (4 kHz)", "th": "เสียงกลางสูง (4 kHz)"},
    "Treble (12kHz)": {"en": "Treble (12 kHz)", "th": "เสียงแหลม (12 kHz)"},
    "Save .LRC": {"en": "💾 Save .LRC", "th": "💾 บันทึก .LRC"},
    "LRC Saved": {"en": "LRC lyrics saved successfully!", "th": "บันทึกไฟล์เนื้อเพลง .LRC เรียบร้อยแล้ว!"},
    "No Lyrics Found": {"en": "No synchronized lyrics found for this song.", "th": "ไม่พบเนื้อเพลงสำหรับเพลงนี้"},
    "Searching Lyrics...": {"en": "Searching lyrics...", "th": "กำลังค้นหาเนื้อเพลง..."},
    "Search Lyrics": {"en": "🔍 Search", "th": "🔍 ค้นหา"},
    "Import to Queue": {"en": "📥 Import to Queue", "th": "📥 เพิ่มเข้าคิวโหลด"},
    "Universal Playlist": {"en": "Universal Multi-Platform Playlist", "th": "เพลย์ลิสต์เพลงหลายแพลตฟอร์ม"},
    "Visualizer": {"en": "Audio Visualizer", "th": "แถบคลื่นเสียง"},
    "Speed": {"en": "Speed", "th": "ความเร็ว"},
    "ETA": {"en": "ETA", "th": "เวลาที่เหลือ"},
    "Downloading": {"en": "Downloading", "th": "กำลังดาวน์โหลด"},
    "Processing Tags…": {"en": "Processing Tags…", "th": "กำลังประมวลผลแท็ก…"},
    "Folder": {"en": "Folder", "th": "เปิดโฟลเดอร์"},
    "MENU": {"en": "Navigation", "th": "เมนูหลัก"},
    "STUDIO_TOOLS": {"en": "Studio Tools", "th": "เครื่องมือสตูดิโอ"},
    "Open": {"en": "Open", "th": "เปิด"},
    "Total Downloads": {"en": "Total Downloads", "th": "งานทั้งหมด"},
    "Active": {"en": "Active", "th": "กำลังทำงาน"},
    "Completed": {"en": "Completed", "th": "เสร็จสมบูรณ์"},
    "Search_Hero": {"en": "Download Ultra High-Res Audio & 4K Video", "th": "ดาวน์โหลดเพลงเสียงระดับสตูดิโอ & วิดีโอ 4K"},
    "Reveal in Explorer": {"en": "Reveal in Explorer", "th": "เปิดในโฟลเดอร์"},
    "Edit LRC": {"en": "Edit LRC", "th": "แก้ไข .LRC"},
    "View Synced": {"en": "View Synced", "th": "ดูเนื้อเพลงสด"},
    "Auto-Fetch": {"en": "Auto-Fetch", "th": "ค้นหาอัตโนมัติ"},
    "Sort: Recent": {"en": "Sort: Recent", "th": "เรียง: ล่าสุด"},
    "Sort: Title": {"en": "Sort: Title", "th": "เรียง: ชื่อเพลง"},
    "Sort: Artist": {"en": "Sort: Artist", "th": "เรียง: ศิลปิน"},
    "Sort: Duration": {"en": "Sort: Duration", "th": "เรียง: ความยาว"},
    "Sort: File Size": {"en": "Sort: File Size", "th": "เรียง: ขนาดไฟล์"},
    "Delete File?": {"en": "Delete File?", "th": "ลบไฟล์นี้?"},
    "Delete Permanently": {"en": "Delete Permanently", "th": "ลบไฟล์ถาวร"},
    "Tracks Selected": {"en": "tracks selected", "th": "เพลงที่เลือก"},
    "Tracks Found": {"en": "tracks found", "th": "เพลงที่พบ"},
    "Engines: Ready": {"en": "Engines: Ready", "th": "เครื่องมือ: พร้อมใช้งาน"},
    "Engines: Missing/Updating": {"en": "Engines: Missing/Updating", "th": "เครื่องมือ: กำลังอัปเดต..."},
    "Table View": {"en": "Table View", "th": "มุมมองตาราง"},
    "Grid View": {"en": "Grid View", "th": "มุมมองการ์ด"},
    "Favorites": {"en": "Favorites", "th": "เพลงโปรด"},
    "Favorites Only": {"en": "❤️ Favorites Only", "th": "❤️ เฉพาะเพลงโปรด"},
    "Play All": {"en": "▶ Play All", "th": "▶ เล่นทั้งหมด"},
    "Shuffle All": {"en": "🔀 Shuffle All", "th": "🔀 สุ่มทั้งหมด"},
    "Sleep Timer": {"en": "🌙 Sleep Timer", "th": "🌙 ตั้งเวลาปิดเพลง"},
    "Sleep Timer Off": {"en": "Timer Off", "th": "ปิดตัวตั้งเวลา"},
    "Keyboard Shortcuts": {"en": "Keyboard Shortcuts", "th": "คีย์ลัดแป้นพิมพ์"},
    "Convert Audio": {"en": "Studio Audio Converter", "th": "แปลงไฟล์เสียงสตูดิโอ"},
    "Convert Now": {"en": "Convert Now", "th": "เริ่มแปลงไฟล์"},
    "Pre-Amp": {"en": "Pre-Amp Gain", "th": "ระดับขยาย Pre-Amp"},
    "Bass Boost Knob": {"en": "Sub-Bass Exciter", "th": "เพิ่มพลังเสียงเบสลึก"},
    "3D Surround": {"en": "3D Spatial Surround", "th": "มิติเสียงโอบล้อม 3D"},
    "Trending Vibes": {"en": "Trending Vibes & Discovery", "th": "แนวเพลงยอดนิยม & ค้นหาด่วน"},
    "Recent Searches": {"en": "Recent Searches", "th": "การค้นหาล่าสุด"},
    "Fullscreen Karaoke": {"en": "Fullscreen Karaoke", "th": "คาราโอเกะเต็มจอ"},
    "Copy Lyrics": {"en": "📋 Copy Lyrics", "th": "📋 คัดลอกเนื้อเพลง"},
    "Lyrics Copied": {"en": "Lyrics copied to clipboard!", "th": "คัดลอกเนื้อเพลงแล้ว!"},
    "Export M3U8": {"en": "Export Playlist (.M3U8)", "th": "ส่งออกเพลย์ลิสต์ (.M3U8)"},
    "Playlist Exported": {"en": "Playlist exported successfully!", "th": "ส่งออกเพลย์ลิสต์สำเร็จแล้ว!"},
    "Cancel All": {"en": "🛑 Cancel All", "th": "🛑 ยกเลิกทั้งหมด"},
    "Playback Speed": {"en": "Playback Speed", "th": "ความเร็วการเล่น"},
    "Target Format": {"en": "Target Format", "th": "รูปแบบปลายทาง"},
    "Target Bitrate": {"en": "Bitrate", "th": "บิตเรต"},
    "Normalize Audio": {"en": "Normalize Audio (EBU R128)", "th": "ปรับระดับเสียงให้เท่ากัน (EBU R128)"},
}

def _btn(parent, text, cmd, fg=None, hv=None, width=120, height=36, corner_radius=8, **kw):
    return ctk.CTkButton(
        parent, text=text, command=cmd,
        fg_color=fg or PRIMARY, hover_color=hv or PRIMARY_HV,
        font=FONT_SM, corner_radius=corner_radius, width=width, height=height, **kw
    )

def _label(parent, text, font=FONT_SM, color=TEXT, **kw):
    return ctk.CTkLabel(parent, text=text, font=font, text_color=color, **kw)


# ── Metadata & Audio Inspection Helper ─────────────────────────────────────────
def get_media_info(filepath):
    info = {
        "title": os.path.basename(filepath).rsplit(".", 1)[0],
        "artist": "Local Audio",
        "album": "NexusTube",
        "genre": "Music",
        "year": "",
        "lyrics": "",
        "duration": 0,
        "size_bytes": 0,
        "cover_image": None,
    }
    try:
        if os.path.exists(filepath):
            info["size_bytes"] = os.path.getsize(filepath)
    except Exception:
        pass

    if mutagen and os.path.exists(filepath):
        try:
            mf = mutagen.File(filepath)
            if mf:
                if hasattr(mf, "info") and hasattr(mf.info, "length"):
                    info["duration"] = int(mf.info.length)
                if hasattr(mf, "tags") and mf.tags:
                    for tag in ("TIT2", "title", "\xa9nam"):
                        if tag in mf.tags:
                            val = mf.tags[tag]
                            info["title"] = str(val[0] if isinstance(val, list) else val)
                            break
                    for tag in ("TPE1", "artist", "\xa9ART"):
                        if tag in mf.tags:
                            val = mf.tags[tag]
                            info["artist"] = str(val[0] if isinstance(val, list) else val)
                            break
                    for tag in ("TALB", "album", "\xa9alb"):
                        if tag in mf.tags:
                            val = mf.tags[tag]
                            info["album"] = str(val[0] if isinstance(val, list) else val)
                            break
                    for tag in ("TDRC", "TYER", "date", "\xa9day"):
                        if tag in mf.tags:
                            val = mf.tags[tag]
                            info["year"] = str(val[0] if isinstance(val, list) else val)
                            break
                    # Lyrics extraction
                    if hasattr(mf.tags, "getall"):
                        for u in mf.tags.getall("USLT"):
                            if u.text:
                                info["lyrics"] = str(u.text)
                                break
                    if not info["lyrics"]:
                        for l_tag in ("\xa9lyr", "LYRICS", "lyrics"):
                            if l_tag in mf.tags:
                                val = mf.tags[l_tag]
                                info["lyrics"] = str(val[0] if isinstance(val, list) else val)
                                break
                    # Cover art extraction (with explicit in-memory copy)
                    if hasattr(mf.tags, "getall"):
                        for pic in mf.tags.getall("APIC"):
                            if pic.data:
                                try:
                                    with Image.open(io.BytesIO(pic.data)) as im:
                                        info["cover_image"] = im.copy()
                                    break
                                except Exception:
                                    pass
                    if not info["cover_image"] and "covr" in mf.tags:
                        covr = mf.tags["covr"]
                        if covr:
                            try:
                                with Image.open(io.BytesIO(bytes(covr[0]))) as im:
                                    info["cover_image"] = im.copy()
                            except Exception:
                                pass
                    if not info["cover_image"] and hasattr(mf, "pictures") and mf.pictures:
                        try:
                            with Image.open(io.BytesIO(mf.pictures[0].data)) as im:
                                info["cover_image"] = im.copy()
                        except Exception:
                            pass
        except Exception:
            if filepath.lower().endswith(".mp3"):
                try:
                    from mutagen.id3 import ID3
                    id3 = ID3(filepath)
                    if "TIT2" in id3: info["title"] = str(id3["TIT2"])
                    if "TPE1" in id3: info["artist"] = str(id3["TPE1"])
                    if "TALB" in id3: info["album"] = str(id3["TALB"])
                    if "TDRC" in id3: info["year"] = str(id3["TDRC"])
                    for u in id3.getall("USLT"):
                        if u.text:
                            info["lyrics"] = str(u.text)
                            break
                    for pic in id3.getall("APIC"):
                        if pic.data:
                            try:
                                with Image.open(io.BytesIO(pic.data)) as im:
                                    info["cover_image"] = im.copy()
                                break
                            except Exception:
                                pass
                except Exception:
                    pass

    if filepath.lower().endswith(".wav"):
        try:
            import wave
            with wave.open(filepath, "rb") as wf:
                info["duration"] = int(wf.getnframes() / float(wf.getframerate()))
        except Exception:
            pass

    if info["duration"] <= 0 and filepath and os.path.exists(filepath):
        # Fallback to ffprobe for files lacking metadata or video formats
        ffprobe = None
        try:
            from nexus_doctor import find_binary
            ffprobe = find_binary("ffprobe")
        except Exception:
            pass
        if not ffprobe:
            ffprobe = shutil.which("ffprobe") or (
                os.path.join(os.getenv("APPDATA") or "", "NexusTube", "bin", "ffprobe.exe")
                if sys.platform == "win32" else None
            )
        if ffprobe and os.path.exists(ffprobe):
            try:
                res = run_external_tool(
                    [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", filepath],
                    label="ffprobe duration", check=False
                )
                if res.returncode == 0 and res.stdout.strip():
                    info["duration"] = int(float(res.stdout.strip()))
            except Exception:
                pass

    return info


# ── In-App Audio Player Controller ────────────────────────────────────────────
class AudioPlayer:
    """Robust in-app audio player engine powered by pygame.mixer.music with FFmpeg fallback decoding, Equalizer DSP, and Synced Lyrics."""
    def __init__(self, ffmpeg_bin=None):
        self.current_path = None
        self.raw_filepath = None
        self.info = {}
        self.is_playing = False
        self.is_paused = False
        self.seek_offset = 0.0
        self.volume = 0.85
        self.is_muted = False
        self.repeat_mode = "off"   # "off", "all", "one"
        self.is_shuffle = False
        self.playback_speed = 1.0
        self._initialized = False
        self.ffmpeg = ffmpeg_bin
        self._temp_pcm_files = []

        # Equalizer DSP State
        self.current_eq_preset = "Flat"
        self.current_eq_bands = {"bass": 0.0, "low_mid": 0.0, "mid": 0.0, "high_mid": 0.0, "treble": 0.0}
        self.dsp_effects = {"preamp": 0.0, "bass_boost": 0.0, "surround": False}
        self.normalize_audio = False
        self.lyrics_data = {"synced": [], "synced_raw": "", "plain": "", "source": "none"}

        self._init_mixer()

    def _init_mixer(self):
        if not PYGAME_AVAILABLE:
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
            pygame.mixer.music.set_volume(self.volume)
            self._initialized = True
        except Exception as e:
            print(f"[AudioPlayer] Mixer init failed: {e}")

    def _transcode_to_wav(self, filepath, eq_filter=None):
        """Transcode unsupported formats (M4A, AAC, OPUS, WEBM) or apply EQ filter and speed to a temporary PCM WAV file."""
        ffmpeg = self.ffmpeg
        if not ffmpeg or not os.path.exists(ffmpeg):
            try:
                from nexus_doctor import find_binary
                ffmpeg = find_binary("ffmpeg")
            except Exception:
                ffmpeg = None
            if not ffmpeg:
                ffmpeg = shutil.which("ffmpeg") or (
                    os.path.join(os.getenv("APPDATA") or "", "NexusTube", "bin", "ffmpeg.exe")
                    if sys.platform == "win32" else None
                )
        if not ffmpeg or not os.path.exists(ffmpeg):
            return None

        cache_dir = os.path.join(tempfile.gettempdir(), "nexustube_cache")
        os.makedirs(cache_dir, exist_ok=True)
        self._cleanup_cache(max_files=10)

        if eq_filter is None:
            eq_filter = generate_ffmpeg_eq_filter(
                self.current_eq_bands,
                preamp=self.dsp_effects.get("preamp", 0.0),
                bass_boost=self.dsp_effects.get("bass_boost", 0.0),
                surround=self.dsp_effects.get("surround", False),
                normalize=getattr(self, "normalize_audio", False),
            )
        filters_list = []
        if eq_filter:
            filters_list.append(eq_filter)
        speed = getattr(self, "playback_speed", 1.0)
        if abs(speed - 1.0) > 0.01:
            filters_list.append(f"atempo={speed:.2f}")
        active_filter = ",".join(filters_list)

        sig = f"{filepath}::{active_filter}"
        h = hashlib.md5(sig.encode("utf-8", errors="ignore")).hexdigest()
        out_wav = os.path.join(cache_dir, f"audio_{h}.wav")
        if os.path.exists(out_wav) and os.path.getsize(out_wav) > 1000:
            return out_wav
        try:
            cmd = [
                ffmpeg, "-y", "-i", filepath,
                "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2"
            ]
            if active_filter:
                cmd += ["-af", active_filter]
            cmd.append(out_wav)
            run_external_tool(cmd, label="ffmpeg transcode to wav", check=True)
            if os.path.exists(out_wav):
                self._temp_pcm_files.append(out_wav)
                return out_wav
        except Exception as e:
            print(f"[AudioPlayer] Transcode error: {e}")
        return None

    def _cleanup_cache(self, max_files=10):
        """Evicts old PCM WAV files from cache directory to conserve disk space."""
        try:
            cache_dir = os.path.join(tempfile.gettempdir(), "nexustube_cache")
            if not os.path.exists(cache_dir):
                return
            files = [
                os.path.join(cache_dir, f) for f in os.listdir(cache_dir)
                if (f.startswith("audio_") or f.startswith("stream_")) and f.endswith(".wav")
            ]
            if len(files) > max_files:
                files.sort(key=lambda x: os.path.getmtime(x))
                for f in files[:-max_files]:
                    try:
                        os.remove(f)
                    except Exception:
                        pass
        except Exception:
            pass

    def cleanup(self):
        """Stops playback, unloads mixer, and removes session temporary PCM files."""
        self.stop()
        try:
            for p in list(self._temp_pcm_files):
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
            self._temp_pcm_files.clear()
        except Exception:
            pass
        # Fully release the pygame audio device / SDL mixer subsystem. Leaving
        # it initialized keeps its native DLLs (SDL2.dll, libmpg123, etc.)
        # loaded in the process, which on a PyInstaller --onefile build can
        # still be holding a handle when the bootloader tries to delete its
        # temp _MEI extraction folder on exit, causing a
        # "Failed to remove temporary directory" warning.
        if PYGAME_AVAILABLE:
            try:
                if pygame.mixer.get_init():
                    try:
                        pygame.mixer.music.stop()
                    except Exception:
                        pass
                    try:
                        if hasattr(pygame.mixer.music, "unload"):
                            pygame.mixer.music.unload()
                    except Exception:
                        pass
                    pygame.mixer.quit()
            except Exception:
                pass
            try:
                if pygame.get_init():
                    pygame.quit()
            except Exception:
                pass


    def load_and_play(self, filepath, start_time=0.0):
        if not self._initialized:
            self._init_mixer()
        if not self._initialized:
            return False

        if not filepath or not os.path.exists(filepath):
            return False

        self.stop()
        loaded = False
        eq_filter = generate_ffmpeg_eq_filter(
            self.current_eq_bands,
            preamp=self.dsp_effects.get("preamp", 0.0),
            bass_boost=self.dsp_effects.get("bass_boost", 0.0),
            surround=self.dsp_effects.get("surround", False),
            normalize=getattr(self, "normalize_audio", False),
        )

        speed = getattr(self, "playback_speed", 1.0)
        has_speed_mod = abs(speed - 1.0) > 0.01

        # If EQ, DSP filter, or normalization is active, or playback speed is modified, route through ffmpeg filtergraph
        if eq_filter or has_speed_mod or getattr(self, "normalize_audio", False):
            wav_path = self._transcode_to_wav(filepath, eq_filter=eq_filter)
            if wav_path and os.path.exists(wav_path):
                try:
                    pygame.mixer.music.load(wav_path)
                    loaded = True
                except Exception as eq_err:
                    print(f"[AudioPlayer] EQ load error: {eq_err}")

        if not loaded:
            try:
                pygame.mixer.music.load(filepath)
                loaded = True
            except Exception as direct_err:
                # Fallback to FFmpeg PCM transcoding for M4A, AAC, Opus, etc.
                wav_path = self._transcode_to_wav(filepath, eq_filter=eq_filter)
                if wav_path and os.path.exists(wav_path):
                    try:
                        pygame.mixer.music.load(wav_path)
                        loaded = True
                    except Exception as wav_err:
                        print(f"[AudioPlayer] Converted WAV load error: {wav_err}")
                else:
                    print(f"[AudioPlayer] Load error: {direct_err}")

        if not loaded:
            return False

        try:
            start_time = max(0.0, float(start_time))
            if start_time > 0:
                try:
                    pygame.mixer.music.play(start=start_time)
                except Exception:
                    pygame.mixer.music.play()
            else:
                pygame.mixer.music.play()

            self.current_path = filepath
            self.raw_filepath = filepath
            self.info = get_media_info(filepath)
            self.is_playing = True
            self.is_paused = False
            self.seek_offset = start_time

            # Pre-cache lyrics for current song
            self._cache_lyrics_async(filepath)
            return True
        except Exception as e:
            print(f"[AudioPlayer] Play error: {e}")
            return False

    def _cache_lyrics_async(self, filepath):
        def _fetch():
            try:
                t = self.info.get("title", "")
                a = self.info.get("artist", "")
                d = self.info.get("duration", 0)
                self.lyrics_data = fetch_lyrics(t, a, duration=d, file_path=filepath)
            except Exception:
                pass
        threading.Thread(target=_fetch, daemon=True).start()

    def set_eq_preset(self, preset_name):
        """Applies a preset from EQ_PRESETS, updating sliders and live playback."""
        if preset_name in EQ_PRESETS:
            self.current_eq_preset = preset_name
            p = EQ_PRESETS[preset_name]
            self.current_eq_bands = {k: float(p.get(k, 0)) for k in ("bass", "low_mid", "mid", "high_mid", "treble")}
            if self.current_path and (self.is_playing or self.is_paused):
                pos = self.get_pos()
                was_paused = self.is_paused
                self.load_and_play(self.current_path, start_time=pos)
                if was_paused:
                    self.toggle_play_pause()

    def set_eq_bands(self, bands):
        """Sets custom 5-band EQ values (dB) and re-filters live playback."""
        self.current_eq_bands = {k: float(bands.get(k, 0)) for k in ("bass", "low_mid", "mid", "high_mid", "treble")}
        self.current_eq_preset = "Custom"
        if self.current_path and (self.is_playing or self.is_paused):
            pos = self.get_pos()
            was_paused = self.is_paused
            self.load_and_play(self.current_path, start_time=pos)
            if was_paused:
                self.toggle_play_pause()

    def set_dsp_effects(self, effects):
        """Sets preamp gain, dynamic bass boost exciter, and 3D surround simulation."""
        if not isinstance(effects, dict):
            return self.dsp_effects
        if "preamp" in effects:
            try:
                self.dsp_effects["preamp"] = max(-12.0, min(12.0, float(effects["preamp"])))
            except Exception:
                pass
        if "bass_boost" in effects:
            try:
                self.dsp_effects["bass_boost"] = max(0.0, min(100.0, float(effects["bass_boost"])))
            except Exception:
                pass
        if "surround" in effects:
            self.dsp_effects["surround"] = bool(effects["surround"])

        if self.current_path and (self.is_playing or self.is_paused):
            pos = self.get_pos()
            was_paused = self.is_paused
            self.load_and_play(self.current_path, start_time=pos)
            if was_paused:
                self.toggle_play_pause()
        return self.dsp_effects

    def set_normalization(self, enabled):
        """Toggles dynamic loudness normalization (dynaudnorm) and updates live playback."""
        self.normalize_audio = bool(enabled)
        target = getattr(self, "raw_filepath", None) or self.current_path
        if target and (self.is_playing or self.is_paused):
            pos = self.get_pos()
            was_paused = self.is_paused
            self.load_and_play(target, start_time=pos)
            if was_paused:
                self.pause()
        return self.normalize_audio

    def toggle_play_pause(self):
        if not self.is_playing and not self.is_paused:
            if self.current_path:
                return self.load_and_play(self.current_path, self.seek_offset)
            return False

        if self.is_paused:
            try:
                pygame.mixer.music.unpause()
                self.is_paused = False
                self.is_playing = True
                return True
            except Exception:
                return False
        else:
            try:
                pygame.mixer.music.pause()
                self.is_paused = True
                self.is_playing = False
                return True
            except Exception:
                return False

    def pause(self):
        """Explicitly pauses playback without toggling."""
        if not self._initialized:
            return False
        if self.is_playing and not self.is_paused:
            try:
                pygame.mixer.music.pause()
                self.is_paused = True
                self.is_playing = False
                return True
            except Exception:
                return False
        return True

    def resume(self):
        """Explicitly resumes playback without toggling."""
        if not self._initialized:
            return False
        if self.is_paused:
            try:
                pygame.mixer.music.unpause()
                self.is_paused = False
                self.is_playing = True
                return True
            except Exception:
                return False
        elif not self.is_playing and self.current_path:
            return self.load_and_play(self.current_path, self.seek_offset)
        return True

    def set_speed(self, speed):
        """Sets playback speed multiplier [0.5, 2.0] and re-filters live playback."""
        try:
            sp = max(0.5, min(2.0, float(speed)))
        except Exception:
            sp = 1.0
        self.playback_speed = sp
        if self.current_path and (self.is_playing or self.is_paused):
            pos = self.get_pos()
            was_paused = self.is_paused
            self.load_and_play(self.current_path, start_time=pos)
            if was_paused:
                self.pause()
        return self.playback_speed

    def seek(self, target_seconds):
        if not self.current_path or not self._initialized:
            return
        try:
            target_seconds = max(0.0, float(target_seconds))
            try:
                pygame.mixer.music.play(start=target_seconds)
            except Exception:
                self.load_and_play(self.current_path, start_time=target_seconds)
                return
            self.seek_offset = target_seconds
            self.is_playing = True
            self.is_paused = False
        except Exception as e:
            print(f"[AudioPlayer] Seek error: {e}")

    def stop(self):
        if not self._initialized:
            return
        try:
            pygame.mixer.music.stop()
            if hasattr(pygame.mixer.music, "unload"):
                pygame.mixer.music.unload()
        except Exception:
            pass
        self.is_playing = False
        self.is_paused = False
        self.seek_offset = 0.0

    def set_volume(self, val):
        self.volume = max(0.0, min(1.0, float(val)))
        if self.volume > 0 and self.is_muted:
            self.is_muted = False
        if not self.is_muted and self._initialized:
            try:
                pygame.mixer.music.set_volume(self.volume)
            except Exception:
                pass

    def toggle_mute(self):
        if not self._initialized:
            return False
        if self.is_muted:
            self.is_muted = False
            try:
                pygame.mixer.music.set_volume(self.volume)
            except Exception:
                pass
            return False
        else:
            self.is_muted = True
            try:
                pygame.mixer.music.set_volume(0.0)
            except Exception:
                pass
            return True

    def toggle_repeat(self):
        modes = ["off", "all", "one"]
        idx = modes.index(self.repeat_mode) if self.repeat_mode in modes else 0
        self.repeat_mode = modes[(idx + 1) % len(modes)]
        return self.repeat_mode

    def toggle_shuffle(self):
        self.is_shuffle = not self.is_shuffle
        return self.is_shuffle

    def get_pos(self):
        if not self.is_playing and not self.is_paused:
            return 0.0
        if not self._initialized:
            return 0.0
        try:
            ms = pygame.mixer.music.get_pos()
            if ms < 0:
                return self.seek_offset
            dur = self.info.get("duration", 0)
            cur = self.seek_offset + (ms / 1000.0)
            if dur > 0 and cur > dur:
                return float(dur)
            return cur
        except Exception:
            return self.seek_offset


# ── Sleek Animated Audio Visualizer ───────────────────────────────────────────
class AudioVisualizer(ctk.CTkCanvas):
    """
    Sleek, animated audio frequency spectrum visualizer with smooth easing,
    organic rhythm simulation, and dynamic theme-accent reactive styling.
    Reuses persistent canvas items for zero-flicker 60fps animation.
    """
    def __init__(self, parent, width=88, height=26, num_bars=14, color="#22C55E", bg=SIDEBAR):
        super().__init__(parent, width=width, height=height, bg=bg, highlightthickness=0)
        self.w = width
        self.h = height
        self.num_bars = num_bars
        self.color = color
        self.heights = [2.0] * num_bars
        self.targets = [2.0] * num_bars
        self._bar_items = []

        spacing = 2
        bar_w = max(2.0, (self.w - (self.num_bars - 1) * spacing) / float(self.num_bars))
        for i in range(num_bars):
            x0 = i * (bar_w + spacing)
            y1 = self.h - 1.0
            y0 = y1 - 2.0
            item = self.create_rectangle(x0, y0, x0 + bar_w, y1, fill=self.color, outline="")
            self._bar_items.append(item)

        self.update_bars(False)

    def set_color(self, color):
        self.color = color
        for item in self._bar_items:
            try:
                self.itemconfig(item, fill=color)
            except Exception:
                pass

    def update_bars(self, is_playing, volume=0.85, bass_boost=0.0):
        import random
        spacing = 2
        bar_w = max(2.0, (self.w - (self.num_bars - 1) * spacing) / float(self.num_bars))
        max_h = self.h - 3.0
        vol_scale = max(0.2, min(1.0, float(volume)))

        for i in range(self.num_bars):
            if is_playing:
                if random.random() < 0.45:
                    weight = 1.25 if i < 4 else (1.0 if i < 9 else 0.85)
                    boost = 1.0 + max(0.0, float(bass_boost) / 15.0) if i < 4 else 1.0
                    target = random.uniform(4.0, max_h) * weight * boost * vol_scale
                    self.targets[i] = min(max_h, max(3.0, target))
                self.heights[i] += (self.targets[i] - self.heights[i]) * 0.45
            else:
                self.heights[i] = max(2.0, self.heights[i] * 0.72)

            x0 = i * (bar_w + spacing)
            y1 = self.h - 1.0
            y0 = max(1.0, y1 - self.heights[i])
            if i < len(self._bar_items):
                try:
                    self.coords(self._bar_items[i], x0, y0, x0 + bar_w, y1)
                except Exception:
                    pass


# ── Main Application ──────────────────────────────────────────────────────────
class App(ctk.CTk):
    def __init__(self, check_updates=True, is_fallback=False):
        super().__init__()
        self.is_fallback = is_fallback
        if is_fallback:
            self.title("NexusTube — YouTube Music & Video Downloader (Compatibility Mode)")
        else:
            self.title("NexusTube — YouTube Music & Video Downloader")
        self.geometry("960x680")
        self.minsize(800, 580)
        self.configure(fg_color=BG)

        self.is_win = sys.platform == "win32"
        self.is_mac = sys.platform == "darwin"
        self.exe_ext = ".exe" if self.is_win else ""

        if getattr(sys, "frozen", False):
            base_dir = sys._MEIPASS
            self._exe_path = sys.executable
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self._exe_path = None

        icon_path = os.path.join(base_dir, "NexusTube by herlove.ico")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(base_dir, "icon.ico")
        if os.path.exists(icon_path) and self.is_win:
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        # AppData and Storage Configuration
        appdata_base = os.getenv("APPDATA") or os.path.expanduser("~")
        self.appdata_dir = (
            os.path.join(appdata_base, "YTDownloaderPro")
            if self.is_win
            else os.path.join(appdata_base, ".NexusTube")
        )
        try:
            os.makedirs(self.appdata_dir, exist_ok=True)
        except Exception:
            self.appdata_dir = os.path.join(tempfile.gettempdir(), "NexusTube")
            try:
                os.makedirs(self.appdata_dir, exist_ok=True)
            except Exception:
                pass

        self.config_path = os.path.join(self.appdata_dir, "config.json")
        self.config = {
            "accent": "#22C55E",
            "lang": "th",
            "format": "mp3_320",
            "embed_thumb": True,
            "embed_meta": True,
            "embed_lyrics": False,
            "sponsorblock": "sponsor",
            "normalize": False,
            "eq_preset": "Flat",
            "eq_bands": {"bass": 0.0, "low_mid": 0.0, "mid": 0.0, "high_mid": 0.0, "treble": 0.0},
            "outdir": os.path.join(os.path.expanduser("~"), "Downloads", "NexusTube"),
        }
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self.config.update(loaded)
        except Exception:
            pass

        self.accent_color = self.config.get("accent", "#22C55E")
        self.accent_hv    = "#16A34A"
        for name, meta in ACCENT_PALETTE.items():
            if meta["color"].lower() == self.accent_color.lower():
                self.accent_hv = meta["hover"]
                break

        self.lang = self.config.get("lang", "th")
        self.ffmpeg = get_binary_path(self.appdata_dir, "ffmpeg", self.exe_ext)
        self.ffprobe= get_binary_path(self.appdata_dir, "ffprobe", self.exe_ext)
        self.ffplay = get_binary_path(self.appdata_dir, "ffplay", self.exe_ext)
        self.ytdlp  = get_binary_path(self.appdata_dir, "yt-dlp", self.exe_ext)

        self._default_outdir = self.config.get("outdir") or os.path.join(os.path.expanduser("~"), "Downloads", "NexusTube")
        try:
            os.makedirs(self._default_outdir, exist_ok=True)
        except Exception:
            fallback_dir = os.path.join(os.path.expanduser("~"), "Downloads")
            try:
                os.makedirs(fallback_dir, exist_ok=True)
                self._default_outdir = fallback_dir
            except Exception:
                self._default_outdir = tempfile.gettempdir()

        # Thread pool and state managers
        self.executor = ThreadPoolExecutor(max_workers=5)
        self.player = AudioPlayer(ffmpeg_bin=self.ffmpeg)

        # Load saved EQ preset or custom bands
        if self.config.get("eq_preset") in EQ_PRESETS:
            self.player.set_eq_preset(self.config["eq_preset"])
        elif "eq_bands" in self.config:
            self.player.set_eq_bands(self.config["eq_bands"])

        self.active_tasks = {}       # task_id -> {proc, cancelled, card, stat, prog, title, url}
        self.thumb_cache = {}        # url -> CTkImage
        self.library_items = []      # list of file paths in library

        self.lyrics_window = None
        self.eq_window = None
        self._current_lyrics = []
        self._last_lyric_idx = -1

        self._pending_update_url = None
        self._pending_update_ver = None
        self._engine_busy = False
        self._ytdlp_ver_str = "Checking..."
        self._seeking = False
        self._is_destroyed = False
        self._poll_after_id = None
        self._eq_debounce_timer = None

        # Build UI layout
        self._build_ui()

        # Start self-healing engine check and app update check
        if check_updates:
            threading.Thread(target=self._check_engine, daemon=True).start()
            threading.Thread(target=self._check_app_update, daemon=True).start()

        # Start Player position polling loop
        self._poll_player()

    def t(self, key):
        return LOCALES.get(key, {}).get(self.lang, key)

    def safe_after(self, delay, fn):
        if getattr(self, "_is_destroyed", False):
            return None
        try:
            if self.winfo_exists():
                return self.after(delay, fn)
        except Exception:
            pass
        return None

    def destroy(self):
        self._is_destroyed = True
        if hasattr(self, "_poll_after_id") and self._poll_after_id:
            try:
                self.after_cancel(self._poll_after_id)
            except Exception:
                pass
        if hasattr(self, "_eq_debounce_timer") and self._eq_debounce_timer:
            try:
                self.after_cancel(self._eq_debounce_timer)
            except Exception:
                pass
        if hasattr(self, "player") and self.player:
            try:
                self.player.cleanup()
            except Exception:
                pass
        if hasattr(self, "executor") and self.executor:
            try:
                self.executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
        try:
            for tid, task in list(getattr(self, "active_tasks", {}).items()):
                proc = task.get("proc")
                if proc and proc.poll() is None:
                    try:
                        proc.terminate()
                    except Exception:
                        pass
        except Exception:
            pass
        super().destroy()

    def _save_config(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # ── UI Construction ───────────────────────────────────────────────────────
    def _build_ui(self):
        # 1. Left Sidebar
        self.sidebar = ctk.CTkFrame(self, width=210, fg_color=SIDEBAR, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Logo Area
        logo_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        logo_frame.pack(fill="x", pady=(24, 10), padx=18)
        self.logo_title = _label(logo_frame, "▶  NexusTube", font=FONT_H, color=self.accent_color)
        self.logo_title.pack(anchor="w")
        _label(logo_frame, "Music Downloader", font=FONT_XS, color=MUTED).pack(anchor="w")
        _label(logo_frame, "by herlove", font=FONT_XS, color=PRIMARY).pack(anchor="w", pady=(2, 0))
        _label(logo_frame, f"v{VERSION}", font=FONT_XS, color=MUTED).pack(anchor="w")
        if getattr(self, "is_fallback", False):
            _label(logo_frame, "⚠️ Compatibility Mode", font=FONT_XS, color=WARN).pack(anchor="w", pady=(2, 0))

        # Update Banner
        self._update_banner = ctk.CTkFrame(logo_frame, fg_color="#1a3a1a", corner_radius=6)
        self._update_btn = ctk.CTkButton(
            self._update_banner, text="🔄 Update Available!",
            font=("Segoe UI", 10, "bold"), text_color=self.accent_color,
            fg_color="transparent", hover_color="#1e4a1e",
            height=26, command=self._do_app_update,
        )
        self._update_btn.pack(padx=4, pady=2)

        ctk.CTkFrame(self.sidebar, fg_color=BORDER, height=1).pack(fill="x", padx=12, pady=10)

        # Navigation Buttons
        self._active_tab = tk.StringVar(value="search")
        self._nav_btns = {}
        nav_specs = [
            ("Search", "search", "🔍"),
            ("Queue", "queue", "📥"),
            ("Library", "library", "🎵"),
            ("Settings", "settings", "⚙️"),
        ]
        for key, tab_id, icon in nav_specs:
            btn = ctk.CTkButton(
                self.sidebar, text=f"  {icon}  {self.t(key)}", anchor="w",
                font=FONT_SM, corner_radius=8,
                fg_color="transparent", hover_color=SURFACE2,
                text_color=TEXT, height=42,
                command=lambda k=tab_id: self._switch_tab(k),
            )
            btn.pack(fill="x", padx=10, pady=3)
            self._nav_btns[tab_id] = (btn, key, icon)

        ctk.CTkFrame(self.sidebar, fg_color="transparent").pack(expand=True)
        ctk.CTkFrame(self.sidebar, fg_color=BORDER, height=1).pack(fill="x", padx=12, pady=6)

        # Engine Health Status in Sidebar
        self.engine_dot = _label(self.sidebar, "● Engine: Initializing…", font=FONT_XS, color=WARN)
        self.engine_dot.pack(padx=14, pady=(4, 4), anchor="w")

        self.status_var = tk.StringVar(value="Ready")
        ctk.CTkLabel(self.sidebar, textvariable=self.status_var, font=FONT_XS, text_color=MUTED, wraplength=180).pack(padx=14, pady=(0, 16), anchor="w")

        # 2. Right Content Area (Pages + Docked Player Bar)
        self.right_area = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.right_area.pack(side="left", fill="both", expand=True)

        # Docked Bottom Player Bar
        self._build_player_bar(self.right_area)

        # Pages Container
        self.pages_container = ctk.CTkFrame(self.right_area, fg_color=BG, corner_radius=0)
        self.pages_container.pack(side="top", fill="both", expand=True)

        self._pages = {
            "search":   self._build_search_page(self.pages_container),
            "queue":    self._build_queue_page(self.pages_container),
            "library":  self._build_library_page(self.pages_container),
            "settings": self._build_settings_page(self.pages_container),
        }
        self._switch_tab("search")

    # ── Docked Music Player Bar ───────────────────────────────────────────────
    def _build_player_bar(self, parent):
        self.player_bar = ctk.CTkFrame(parent, height=72, fg_color=SIDEBAR, corner_radius=0, border_width=1, border_color=BORDER)
        self.player_bar.pack(side="bottom", fill="x")
        self.player_bar.pack_propagate(False)

        # Left: Album Artwork + Title + Artist
        left_box = ctk.CTkFrame(self.player_bar, fg_color="transparent", width=250)
        left_box.pack(side="left", fill="y", padx=16)
        left_box.pack_propagate(False)

        self.bar_thumb_lbl = ctk.CTkLabel(left_box, text="🎵", font=("Segoe UI", 18), width=48, height=48, fg_color=SURFACE, corner_radius=6)
        self.bar_thumb_lbl.pack(side="left", pady=12)

        meta_box = ctk.CTkFrame(left_box, fg_color="transparent")
        meta_box.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=12)
        self.bar_title_lbl = _label(meta_box, "No track playing", font=("Segoe UI", 12, "bold"), anchor="w")
        self.bar_title_lbl.pack(fill="x")
        self.bar_artist_lbl= _label(meta_box, "NexusTube Player", font=FONT_XS, color=MUTED, anchor="w")
        self.bar_artist_lbl.pack(fill="x")

        # Center: Playback Controls + Seek Slider
        center_box = ctk.CTkFrame(self.player_bar, fg_color="transparent")
        center_box.pack(side="left", fill="both", expand=True, padx=10, pady=6)

        # Controls Row
        ctrl_row = ctk.CTkFrame(center_box, fg_color="transparent")
        ctrl_row.pack()

        self.bar_shuffle_btn = _btn(ctrl_row, "🔀", self._toggle_shuffle_ui, fg="transparent", hv=SURFACE2, width=32, height=30)
        self.bar_shuffle_btn.pack(side="left", padx=3)
        self.bar_shuffle_btn.configure(text_color=MUTED)

        _btn(ctrl_row, "⏮", self._play_prev_song, fg="transparent", hv=SURFACE2, width=32, height=30).pack(side="left", padx=3)
        self.bar_play_btn = _btn(ctrl_row, "▶", self._toggle_play_pause, fg=self.accent_color, hv=self.accent_hv, width=38, height=32, corner_radius=16)
        self.bar_play_btn.pack(side="left", padx=5)
        _btn(ctrl_row, "⏹", self._stop_player, fg="transparent", hv=SURFACE2, width=32, height=30).pack(side="left", padx=3)
        _btn(ctrl_row, "⏭", self._play_next_song, fg="transparent", hv=SURFACE2, width=32, height=30).pack(side="left", padx=3)

        self.bar_repeat_btn = _btn(ctrl_row, "🔁", self._toggle_repeat_ui, fg="transparent", hv=SURFACE2, width=32, height=30)
        self.bar_repeat_btn.pack(side="left", padx=3)
        self.bar_repeat_btn.configure(text_color=MUTED)

        # Dynamic Audio Visualizer
        self.visualizer = AudioVisualizer(ctrl_row, width=86, height=24, num_bars=14, color=self.accent_color)
        self.visualizer.pack(side="left", padx=(8, 2))

        # Seek Slider Row
        seek_row = ctk.CTkFrame(center_box, fg_color="transparent")
        seek_row.pack(fill="x", padx=10)

        self.bar_time_cur = _label(seek_row, "00:00", font=FONT_XS, color=MUTED, width=40)
        self.bar_time_cur.pack(side="left")

        self.bar_seek_slider = ctk.CTkSlider(
            seek_row, from_=0, to=100, number_of_steps=1000,
            progress_color=self.accent_color, button_color=TEXT,
            button_hover_color=self.accent_color, height=12,
            command=self._on_seek_change,
        )
        self.bar_seek_slider.pack(side="left", fill="x", expand=True, padx=8)
        self.bar_seek_slider.set(0)
        self.bar_seek_slider.bind("<ButtonPress-1>", lambda e: setattr(self, "_seeking", True))
        self.bar_seek_slider.bind("<ButtonRelease-1>", self._on_seek_release)

        self.bar_time_total = _label(seek_row, "00:00", font=FONT_XS, color=MUTED, width=40)
        self.bar_time_total.pack(side="right")

        # Right: Lyrics + Equalizer + Volume Slider + External Player Button
        right_box = ctk.CTkFrame(self.player_bar, fg_color="transparent", width=250)
        right_box.pack(side="right", fill="y", padx=14)
        right_box.pack_propagate(False)

        self.bar_lyrics_btn = _btn(right_box, "🎤", self._open_lyrics_window, fg="transparent", hv=SURFACE2, width=32, height=30)
        self.bar_lyrics_btn.pack(side="left", padx=2, pady=20)

        self.bar_eq_btn = _btn(right_box, "🎛️", self._open_eq_window, fg="transparent", hv=SURFACE2, width=32, height=30)
        self.bar_eq_btn.pack(side="left", padx=2, pady=20)

        self.mute_btn = _btn(right_box, "🔊", self._toggle_mute, fg="transparent", hv=SURFACE2, width=32, height=30)
        self.mute_btn.pack(side="left", padx=2, pady=20)

        self.vol_slider = ctk.CTkSlider(
            right_box, from_=0, to=1, number_of_steps=100,
            progress_color=PRIMARY, button_color=TEXT,
            button_hover_color=PRIMARY_HV, width=70, height=12,
            command=lambda v: self.player.set_volume(v),
        )
        self.vol_slider.pack(side="left", padx=4, pady=20)
        self.vol_slider.set(self.player.volume)

        _btn(right_box, "↗", self._open_current_in_external, fg="transparent", hv=SURFACE2, width=30, height=30).pack(side="left", padx=2, pady=20)

    # ── Player Operations ─────────────────────────────────────────────────────
    def _play_track(self, filepath):
        if not filepath or not os.path.exists(filepath):
            return
        if filepath.endswith(".mp4"):
            # Launch video in default system player or open
            try:
                if self.is_win: os.startfile(filepath)
                elif self.is_mac: subprocess.call(["open", filepath])
                else: subprocess.call(["xdg-open", filepath])
            except Exception as e:
                messagebox.showerror("Play Error", str(e))
            return

        ok = self.player.load_and_play(filepath)
        if ok:
            title = self.player.info.get("title") or os.path.basename(filepath)
            artist = self.player.info.get("artist") or "NexusTube"
            dur = self.player.info.get("duration") or 0
            self.bar_title_lbl.configure(text=title[:32] + ("…" if len(title) > 32 else ""))
            self.bar_artist_lbl.configure(text=artist[:32])
            self.bar_play_btn.configure(text="⏸")
            self.bar_time_total.configure(text=f"{dur // 60:02d}:{dur % 60:02d}")
            self.bar_seek_slider.configure(to=max(1, dur))
            self.bar_seek_slider.set(0)

            # Cover Image
            cover = self.player.info.get("cover_image")
            if cover:
                try:
                    ctk_img = ctk.CTkImage(light_image=cover, dark_image=cover, size=(48, 48))
                    self.bar_thumb_lbl.configure(image=ctk_img, text="")
                except Exception:
                    self.bar_thumb_lbl.configure(image=None, text="🎵")
            else:
                self.bar_thumb_lbl.configure(image=None, text="🎵")

            # Update lyrics window if open
            if self.lyrics_window and self.lyrics_window.winfo_exists():
                self._load_current_track_lyrics()

    def _toggle_play_pause(self):
        if self.player.is_playing:
            self.player.toggle_play_pause()
            self.bar_play_btn.configure(text="▶")
        elif self.player.is_paused:
            self.player.toggle_play_pause()
            self.bar_play_btn.configure(text="⏸")
        else:
            if self.library_items:
                self._play_track(self.library_items[0])

    def _stop_player(self):
        self.player.stop()
        self.bar_play_btn.configure(text="▶")
        self.bar_seek_slider.set(0)
        self.bar_time_cur.configure(text="00:00")

    def _toggle_shuffle_ui(self):
        is_shuf = self.player.toggle_shuffle()
        self.bar_shuffle_btn.configure(
            text_color=self.accent_color if is_shuf else MUTED,
            fg_color=SURFACE2 if is_shuf else "transparent",
        )

    def _toggle_repeat_ui(self):
        mode = self.player.toggle_repeat()
        if mode == "one":
            self.bar_repeat_btn.configure(text="🔂", text_color=self.accent_color, fg_color=SURFACE2)
        elif mode == "all":
            self.bar_repeat_btn.configure(text="🔁", text_color=self.accent_color, fg_color=SURFACE2)
        else:
            self.bar_repeat_btn.configure(text="🔁", text_color=MUTED, fg_color="transparent")

    def _play_next_song(self):
        if not self.library_items:
            return
        if getattr(self.player, "is_shuffle", False) and len(self.library_items) > 1:
            import random
            choices = [p for p in self.library_items if p != self.player.current_path]
            nxt_track = random.choice(choices if choices else self.library_items)
            self._play_track(nxt_track)
            return

        cur = self.player.current_path
        if cur in self.library_items:
            idx = self.library_items.index(cur)
            if idx == len(self.library_items) - 1 and getattr(self.player, "repeat_mode", "off") == "off":
                self._stop_player()
                return
            nxt = (idx + 1) % len(self.library_items)
            self._play_track(self.library_items[nxt])
        else:
            self._play_track(self.library_items[0])

    def _play_prev_song(self):
        if not self.library_items:
            return
        cur = self.player.current_path
        if cur in self.library_items:
            idx = self.library_items.index(cur)
            prev = (idx - 1) % len(self.library_items)
            self._play_track(self.library_items[prev])
        else:
            self._play_track(self.library_items[0])

    def _toggle_mute(self):
        muted = self.player.toggle_mute()
        self.mute_btn.configure(text="🔇" if muted else "🔊")

    def _open_current_in_external(self):
        if self.player.current_path and os.path.exists(self.player.current_path):
            try:
                if self.is_win: os.startfile(self.player.current_path)
                elif self.is_mac: subprocess.call(["open", self.player.current_path])
                else: subprocess.call(["xdg-open", self.player.current_path])
            except Exception:
                pass

    def _on_seek_change(self, val):
        cur_sec = int(val)
        self.bar_time_cur.configure(text=f"{cur_sec // 60:02d}:{cur_sec % 60:02d}")

    def _on_seek_release(self, event):
        self._seeking = False
        val = self.bar_seek_slider.get()
        self.player.seek(val)

    def _poll_player(self):
        if getattr(self, "_is_destroyed", False):
            return
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return

        is_play = self.player.is_playing

        # Animate frequency visualizer
        if hasattr(self, "visualizer"):
            bass_b = self.player.current_eq_bands.get("bass", 0.0)
            self.visualizer.update_bars(is_play, volume=self.player.volume, bass_boost=bass_b)

        if is_play and not self._seeking:
            pos = self.player.get_pos()
            self.bar_seek_slider.set(pos)
            cur_sec = int(pos)
            self.bar_time_cur.configure(text=f"{cur_sec // 60:02d}:{cur_sec % 60:02d}")

            # Highlight & auto-scroll synchronized lyrics
            if self.lyrics_window and self.lyrics_window.winfo_exists():
                self._sync_lyrics_display(pos)

            dur = self.player.info.get("duration", 0)
            if dur > 0 and pos >= dur:
                if getattr(self.player, "repeat_mode", "off") == "one":
                    self.player.load_and_play(self.player.current_path, 0.0)
                else:
                    self._play_next_song()

        if not getattr(self, "_is_destroyed", False):
            self._poll_after_id = self.safe_after(100, self._poll_player)

    # ── Synchronized Lyrics & Karaoke Studio ──────────────────────────────────
    def _open_lyrics_window(self):
        if self.lyrics_window and self.lyrics_window.winfo_exists():
            self.lyrics_window.lift()
            self.lyrics_window.focus()
            return

        top = ctk.CTkToplevel(self)
        self.lyrics_window = top
        top.title(self.t("Synchronized Lyrics"))
        top.geometry("520x640")
        top.minsize(440, 500)
        top.configure(fg_color=BG)

        # Header card
        hdr_card = ctk.CTkFrame(top, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        hdr_card.pack(fill="x", padx=16, pady=12)

        hdr_row = ctk.CTkFrame(hdr_card, fg_color="transparent")
        hdr_row.pack(fill="x", padx=14, pady=12)

        cur_title = self.player.info.get("title") or "No track playing"
        cur_artist = self.player.info.get("artist") or "NexusTube"

        self.lyr_thumb_lbl = ctk.CTkLabel(hdr_row, text="🎵", font=("Segoe UI", 20), width=54, height=54, fg_color=SURFACE2, corner_radius=8)
        self.lyr_thumb_lbl.pack(side="left", padx=(0, 12))
        cover = self.player.info.get("cover_image")
        if cover:
            try:
                ctk_cover = ctk.CTkImage(light_image=cover, dark_image=cover, size=(54, 54))
                self.lyr_thumb_lbl.configure(image=ctk_cover, text="")
            except Exception:
                pass

        info_box = ctk.CTkFrame(hdr_row, fg_color="transparent")
        info_box.pack(side="left", fill="both", expand=True)

        self.lyr_title_lbl = _label(info_box, cur_title[:45], font=("Segoe UI", 14, "bold"), anchor="w")
        self.lyr_title_lbl.pack(anchor="w")
        self.lyr_artist_lbl = _label(info_box, cur_artist[:45], font=FONT_XS, color=MUTED, anchor="w")
        self.lyr_artist_lbl.pack(anchor="w", pady=(2, 4))
        self.lyr_source_lbl = _label(info_box, "Source: Checking…", font=("Segoe UI", 9), color=PRIMARY, anchor="w")
        self.lyr_source_lbl.pack(anchor="w")

        # Search & Save row
        act_row = ctk.CTkFrame(hdr_card, fg_color="transparent")
        act_row.pack(fill="x", padx=14, pady=(0, 12))

        self.lyr_search_ent = ctk.CTkEntry(act_row, placeholder_text="Song Title / Artist for lyrics...", font=FONT_XS, fg_color=SURFACE2, height=32, corner_radius=8)
        self.lyr_search_ent.pack(side="left", fill="x", expand=True, padx=(0, 8))
        clean_q = f"{cur_artist} - {cur_title}".replace("Local Audio - ", "").replace("NexusTube - ", "")
        self.lyr_search_ent.insert(0, clean_q)
        self.lyr_search_ent.bind("<Return>", lambda e: self._search_manual_lyrics())

        _btn(act_row, self.t("Search Lyrics"), self._search_manual_lyrics, fg=SURFACE2, hv=PRIMARY, width=70, height=32, corner_radius=8).pack(side="left", padx=(0, 6))
        _btn(act_row, self.t("Save .LRC"), self._save_active_lrc, fg=self.accent_color, hv=self.accent_hv, width=85, height=32, corner_radius=8).pack(side="left")

        # Scrollable lyrics area
        self.lyr_scroll = ctk.CTkScrollableFrame(top, fg_color=BG, scrollbar_button_color=SURFACE2)
        self.lyr_scroll.pack(fill="both", expand=True, padx=16, pady=(0, 14))

        self.lyr_line_widgets = []
        self._last_lyric_idx = -1
        self._load_current_track_lyrics()

    def _load_current_track_lyrics(self):
        if not self.lyrics_window or not self.lyrics_window.winfo_exists():
            return
        cur_title = self.player.info.get("title") or "No track playing"
        cur_artist = self.player.info.get("artist") or "NexusTube"
        self.lyr_title_lbl.configure(text=cur_title[:45])
        self.lyr_artist_lbl.configure(text=cur_artist[:45])
        cover = self.player.info.get("cover_image")
        if cover:
            try:
                ctk_cover = ctk.CTkImage(light_image=cover, dark_image=cover, size=(54, 54))
                self.lyr_thumb_lbl.configure(image=ctk_cover, text="")
            except Exception:
                self.lyr_thumb_lbl.configure(image=None, text="🎵")
        else:
            self.lyr_thumb_lbl.configure(image=None, text="🎵")

        self.lyr_source_lbl.configure(text=self.t("Searching Lyrics..."), text_color=WARN)

        def _worker():
            lyrics_data = fetch_lyrics(cur_title, cur_artist, self.player.info.get("duration"), file_path=self.player.current_path)
            self.safe_after(0, lambda: self._render_lyrics_data(lyrics_data))

        threading.Thread(target=_worker, daemon=True).start()

    def _search_manual_lyrics(self):
        q = self.lyr_search_ent.get().strip()
        if not q:
            return
        self.lyr_source_lbl.configure(text=self.t("Searching Lyrics..."), text_color=WARN)
        def _worker():
            lyrics_data = fetch_lyrics(q, "", self.player.info.get("duration"), file_path=self.player.current_path)
            self.safe_after(0, lambda: self._render_lyrics_data(lyrics_data))
        threading.Thread(target=_worker, daemon=True).start()

    def _render_lyrics_data(self, lyrics_data):
        if not self.lyrics_window or not self.lyrics_window.winfo_exists():
            return
        for w in self.lyr_scroll.winfo_children():
            w.destroy()

        self.player.lyrics_data = lyrics_data
        synced = lyrics_data.get("synced", [])
        self._current_lyrics = synced
        self.lyr_line_widgets = []
        self._last_lyric_idx = -1

        src = lyrics_data.get("source", "none")
        src_label = "● Synchronized (LRCLIB)" if "lrclib" in src else ("● Local .LRC" if src == "local_lrc" else ("● Embedded Tags" if src == "embedded" else "● Plain Text"))
        self.lyr_source_lbl.configure(text=src_label, text_color=self.accent_color if synced else WARN)

        if not synced:
            plain = lyrics_data.get("plain", "")
            if plain:
                for line in plain.splitlines():
                    if line.strip():
                        _label(self.lyr_scroll, line.strip(), font=("Segoe UI", 12), color=TEXT).pack(anchor="w", pady=4, padx=12)
            else:
                _label(self.lyr_scroll, self.t("No Lyrics Found"), color=MUTED).pack(pady=40)
            return

        for sec, text in synced:
            row = ctk.CTkFrame(self.lyr_scroll, fg_color="transparent", corner_radius=8)
            row.pack(fill="x", pady=2, padx=4)

            # Timestamp badge
            m, s = int(sec) // 60, int(sec) % 60
            badge = _label(row, f"{m:02d}:{s:02d}", font=("Consolas", 10), color=MUTED, width=46)
            badge.pack(side="left", padx=(4, 8), pady=4)

            # Text label
            lbl = _label(row, text if text else "♪ ♪ ♪", font=("Segoe UI", 13), color=MUTED, anchor="w")
            lbl.pack(side="left", fill="x", expand=True, pady=4)

            # Click to seek
            def _seek_here(target=sec):
                self.player.seek(target)
                self.bar_seek_slider.set(target)

            row.bind("<Button-1>", lambda e, t=sec: _seek_here(t))
            lbl.bind("<Button-1>", lambda e, t=sec: _seek_here(t))
            badge.bind("<Button-1>", lambda e, t=sec: _seek_here(t))

            self.lyr_line_widgets.append((sec, lbl, row))

    def _sync_lyrics_display(self, cur_seconds):
        if not self.lyr_line_widgets:
            return
        idx = get_active_lyric_index(self._current_lyrics, cur_seconds)
        if idx == self._last_lyric_idx:
            return

        # Restore old line
        if 0 <= self._last_lyric_idx < len(self.lyr_line_widgets):
            _, old_lbl, old_row = self.lyr_line_widgets[self._last_lyric_idx]
            old_row.configure(fg_color="transparent")
            old_lbl.configure(text_color=MUTED, font=("Segoe UI", 13))

        # Highlight new line
        if 0 <= idx < len(self.lyr_line_widgets):
            _, new_lbl, new_row = self.lyr_line_widgets[idx]
            new_row.configure(fg_color=SURFACE2)
            new_lbl.configure(text_color=self.accent_color, font=("Segoe UI", 14, "bold"))

            # Auto-scroll so active line is near top/center
            try:
                total = len(self.lyr_line_widgets)
                fraction = max(0.0, min(1.0, (idx - 1) / float(total)))
                self.lyr_scroll._parent_canvas.yview_moveto(fraction)
            except Exception:
                pass

        self._last_lyric_idx = idx

    def _save_active_lrc(self):
        if not self.player.current_path or not self.player.lyrics_data.get("synced_raw"):
            messagebox.showinfo("LRC", "No synchronized lyrics available to save.")
            return
        base = os.path.splitext(self.player.current_path)[0]
        lrc_path = f"{base}.lrc"
        try:
            with open(lrc_path, "w", encoding="utf-8") as f:
                f.write(self.player.lyrics_data["synced_raw"])
            show_notify("Lyrics Saved", f"Saved: {os.path.basename(lrc_path)}")
            messagebox.showinfo("LRC Saved", f"{self.t('LRC Saved')}\n{lrc_path}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # ── Audio Equalizer & DSP Presets Studio ──────────────────────────────────
    def _open_eq_window(self):
        if self.eq_window and self.eq_window.winfo_exists():
            self.eq_window.lift()
            self.eq_window.focus()
            return

        top = ctk.CTkToplevel(self)
        self.eq_window = top
        top.title(self.t("Audio Equalizer & Presets"))
        top.geometry("480x560")
        top.resizable(False, False)
        top.configure(fg_color=BG)

        card = ctk.CTkFrame(top, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        card.pack(fill="both", expand=True, padx=18, pady=18)

        _label(card, self.t("Audio Equalizer & Presets"), font=FONT_MD, color=self.accent_color).pack(anchor="w", padx=16, pady=(16, 4))
        _label(card, "Studio 5-Band DSP Equalizer with real-time FFmpeg audio acceleration", font=FONT_XS, color=MUTED).pack(anchor="w", padx=16, pady=(0, 14))

        # Preset option row
        p_row = ctk.CTkFrame(card, fg_color="transparent")
        p_row.pack(fill="x", padx=16, pady=(0, 16))

        _label(p_row, self.t("EQ Preset"), font=FONT_SM).pack(side="left", padx=(0, 10))

        preset_names = list(EQ_PRESETS.keys())
        self.eq_preset_var = tk.StringVar(value=getattr(self.player, "current_eq_preset", "Flat"))
        self.eq_menu = ctk.CTkOptionMenu(
            p_row, values=preset_names, variable=self.eq_preset_var,
            command=self._on_eq_preset_selected,
            fg_color=PRIMARY, button_color=PRIMARY_HV,
            font=FONT_SM, width=170, height=34
        )
        self.eq_menu.pack(side="left")

        _btn(p_row, self.t("Reset EQ"), self._reset_eq_to_flat, fg=SURFACE2, hv=BORDER, width=95, height=34, corner_radius=8).pack(side="right")

        ctk.CTkFrame(card, fg_color=BORDER, height=1).pack(fill="x", padx=16, pady=(0, 16))

        # 5 Bands
        bands_spec = [
            ("bass", "Bass (60Hz)", "Sub-bass & kick punch"),
            ("low_mid", "Low-Mid (250Hz)", "Warmth & bass body"),
            ("mid", "Mid (1kHz)", "Vocal clarity & presence"),
            ("high_mid", "High-Mid (4kHz)", "Attack, guitars & brass"),
            ("treble", "Treble (12kHz)", "Air, brilliance & cymbals"),
        ]
        self.eq_sliders = {}
        self.eq_val_lbls = {}

        cur_bands = getattr(self.player, "current_eq_bands", {})

        for b_key, loc_k, desc in bands_spec:
            b_row = ctk.CTkFrame(card, fg_color="transparent")
            b_row.pack(fill="x", padx=16, pady=6)

            left_col = ctk.CTkFrame(b_row, fg_color="transparent", width=140)
            left_col.pack(side="left")
            left_col.pack_propagate(False)
            _label(left_col, self.t(loc_k), font=("Segoe UI", 11, "bold"), anchor="w").pack(anchor="w")
            _label(left_col, desc, font=("Segoe UI", 9), color=MUTED, anchor="w").pack(anchor="w")

            val = cur_bands.get(b_key, 0.0)
            lbl = _label(b_row, f"{val:+.1f} dB", font=("Consolas", 10, "bold"), color=self.accent_color, width=65)
            lbl.pack(side="right")
            self.eq_val_lbls[b_key] = lbl

            sld = ctk.CTkSlider(
                b_row, from_=-12, to=12, number_of_steps=48,
                progress_color=self.accent_color, button_color=TEXT, button_hover_color=self.accent_color,
                height=14,
                command=lambda v, k=b_key: self._on_eq_slider_change(k, v)
            )
            sld.set(val)
            sld.pack(side="left", fill="x", expand=True, padx=10)
            self.eq_sliders[b_key] = sld

    def _on_eq_slider_change(self, band, val):
        val = round(float(val), 1)
        if band in self.eq_val_lbls:
            self.eq_val_lbls[band].configure(text=f"{val:+.1f} dB")
        self.player.current_eq_bands[band] = val
        self.player.current_eq_preset = "Custom"
        if hasattr(self, "eq_preset_var"):
            self.eq_preset_var.set("Custom")

        # Debounce the heavy audio filter re-generation and disk write
        if hasattr(self, "_eq_debounce_timer") and self._eq_debounce_timer:
            try:
                self.after_cancel(self._eq_debounce_timer)
            except Exception:
                pass
        self._eq_debounce_timer = self.safe_after(220, self._apply_debounced_eq)

    def _apply_debounced_eq(self):
        if getattr(self, "_is_destroyed", False):
            return
        self.player.set_eq_bands(self.player.current_eq_bands)
        self.config["eq_preset"] = "Custom"
        self.config["eq_bands"] = self.player.current_eq_bands
        self._save_config()

    def _on_eq_preset_selected(self, preset_name):
        self.player.set_eq_preset(preset_name)
        for b_key, sld in getattr(self, "eq_sliders", {}).items():
            val = self.player.current_eq_bands.get(b_key, 0.0)
            sld.set(val)
            if b_key in self.eq_val_lbls:
                self.eq_val_lbls[b_key].configure(text=f"{val:+.1f} dB")
        self.config["eq_preset"] = preset_name
        self.config["eq_bands"] = self.player.current_eq_bands
        self._save_config()

    def _reset_eq_to_flat(self):
        self._on_eq_preset_selected("Flat")
        if hasattr(self, "eq_preset_var"):
            self.eq_preset_var.set("Flat")

    # ── Tab Navigation ────────────────────────────────────────────────────────
    def _switch_tab(self, key):
        self._active_tab.set(key)
        for k, page in self._pages.items():
            if k == key:
                page.pack(fill="both", expand=True)
            else:
                page.pack_forget()

        for k, (btn, loc_key, icon) in self._nav_btns.items():
            is_act = (k == key)
            btn.configure(
                fg_color=SURFACE2 if is_act else "transparent",
                text_color=self.accent_color if is_act else TEXT,
                text=f"  {icon}  {self.t(loc_key)}",
            )
        if key == "library":
            self._refresh_library()
        elif key == "queue":
            self._update_queue_stats()

    # ── Page 1: Search & Download ─────────────────────────────────────────────
    def _build_search_page(self, parent):
        page = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)

        # Header
        hdr = ctk.CTkFrame(page, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(20, 10))
        self.lbl_search_title = _label(hdr, self.t("Search & Download"), font=FONT_H)
        self.lbl_search_title.pack(anchor="w")
        self.lbl_search_sub = _label(hdr, self.t("Search_Sub"), font=FONT_XS, color=MUTED)
        self.lbl_search_sub.pack(anchor="w")

        # Search & Action Input Card
        card = ctk.CTkFrame(page, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        card.pack(fill="x", padx=24, pady=(0, 12))

        row1 = ctk.CTkFrame(card, fg_color="transparent")
        row1.pack(fill="x", padx=16, pady=12)

        self.search_entry = ctk.CTkEntry(
            row1, placeholder_text="YouTube URL, Shorts, Playlist, or Song Title...",
            font=FONT_SM, corner_radius=20,
            fg_color=SURFACE2, border_color=BORDER, border_width=1, text_color=TEXT,
            placeholder_text_color=MUTED, height=44,
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.search_entry.bind("<Return>", lambda e: self._handle_search_action())

        _btn(row1, self.t("Paste"), self._paste_and_search, fg=SURFACE2, hv=BORDER, width=82, height=36, corner_radius=18).pack(side="left", padx=(0, 6))
        _btn(row1, self.t("SearchBtn"), self._handle_search_action, fg=PRIMARY, hv=PRIMARY_HV, width=84, height=36, corner_radius=18).pack(side="left", padx=(0, 6))
        _btn(row1, self.t("+ Add URL"), self._quick_add, fg=self.accent_color, hv=self.accent_hv, width=86, height=36, corner_radius=18).pack(side="left", padx=(0, 6))
        _btn(row1, self.t("Import TXT"), self._import_txt, fg=SURFACE2, hv=BORDER, width=96, height=36, corner_radius=18).pack(side="left")

        # Quick Format Preset Bar
        preset_row = ctk.CTkFrame(card, fg_color="transparent")
        preset_row.pack(fill="x", padx=16, pady=(0, 12))
        _label(preset_row, "Format:", font=FONT_XS, color=MUTED).pack(side="left", padx=(4, 10))

        self.quick_fmt_var = tk.StringVar(value=self.config.get("format", "mp3_320"))
        fmts = [
            ("🎵 MP3 320k", "mp3_320"),
            ("🎶 M4A Source", "m4a_best"),
            ("🎬 MP4 1080p", "mp4_1080"),
            ("✨ MP4 Max", "mp4_best"),
        ]
        for label, val in fmts:
            ctk.CTkRadioButton(
                preset_row, text=label, variable=self.quick_fmt_var, value=val,
                font=FONT_XS, fg_color=self.accent_color, hover_color=self.accent_hv,
            ).pack(side="left", padx=8)

        # Results Label & Scrollable Area
        self.lbl_results_header = _label(page, self.t("Results"), font=FONT_MD, color=MUTED)
        self.lbl_results_header.pack(anchor="w", padx=26, pady=(4, 4))

        self.results_scroll = ctk.CTkScrollableFrame(
            page, fg_color=BG,
            scrollbar_button_color=SURFACE2, scrollbar_button_hover_color=PRIMARY,
        )
        self.results_scroll.pack(fill="both", expand=True, padx=16, pady=(0, 10))
        return page

    def _paste_and_search(self):
        try:
            txt = self.clipboard_get().strip()
            if txt:
                self.search_entry.delete(0, "end")
                self.search_entry.insert(0, txt)
                self._handle_search_action()
        except Exception:
            pass

    def _import_txt(self):
        filepath = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if not filepath:
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                urls = [line.strip() for line in f if line.strip() and "http" in line]
            if urls:
                for url in urls:
                    self.add_to_queue(url, url)
                show_notify("Batch Import", f"Added {len(urls)} videos to queue.")
                self._switch_tab("queue")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _handle_search_action(self):
        q = self.search_entry.get().strip()
        if not q:
            return

        for w in self.results_scroll.winfo_children():
            w.destroy()

        # Check if query is a URL
        is_url = ("http://" in q or "https://" in q or "youtu.be/" in q or "youtube.com/" in q or "spotify.com" in q or "music.apple.com" in q or "soundcloud.com" in q)

        loading_card = ctk.CTkFrame(self.results_scroll, fg_color=SURFACE, corner_radius=10)
        loading_card.pack(fill="x", pady=6, padx=6)
        _label(loading_card, self.t("Resolving URL..." if is_url else "Searching..."), color=MUTED).pack(pady=16)

        if is_url:
            threading.Thread(target=self._resolve_url_thread, args=(q,), daemon=True).start()
        else:
            threading.Thread(target=self._search_thread, args=(q,), daemon=True).start()

    def _resolve_url_thread(self, url):
        while self._engine_busy:
            time.sleep(0.5)

        platform, p_type, ident = detect_platform_url(url)
        if platform in ("spotify", "apple_music", "soundcloud"):
            self.safe_after(0, lambda: self.status_var.set(f"Resolving {platform.capitalize()} {p_type}…"))
            res_data = resolve_multiplatform_url(url, ytdlp_bin=self.ytdlp)
            tracks = res_data.get("tracks", [])
            if tracks:
                if len(tracks) > 1 or p_type in ("playlist", "album"):
                    self.safe_after(0, lambda: self._show_multiplatform_selector(res_data))
                    self.safe_after(0, lambda: self._render_results([]))
                    self.safe_after(0, lambda: self.status_var.set("Ready"))
                    return
                else:
                    # Single track: search YouTube Music / YouTube
                    track = tracks[0]
                    sq = track.get("search_query") or track.get("title")
                    self._search_thread(sq)
                    return

        if "list=" in url:
            # YouTube Playlist URL
            self.safe_after(0, lambda: self._fetch_playlist(url))
            return

        try:
            ytdlp_bin = self.ytdlp if (self.ytdlp and os.path.exists(self.ytdlp)) else (shutil.which("yt-dlp") or self.ytdlp)
            cmd = [ytdlp_bin, "--dump-json", "--no-playlist", "--no-warnings", url]
            proc = run_external_tool(cmd, label="yt-dlp resolve URL", check=False)
            if proc.returncode == 0 and proc.stdout.strip():
                item = json.loads(proc.stdout.strip().split("\n")[0])
                self.safe_after(0, lambda: self._render_featured_result(item, url))
            else:
                classified = classify_download_error(proc.stderr or "")
                err_text = classified.user_message if classified else "URL not found or unavailable"
                self.safe_after(0, lambda msg=err_text: self.status_var.set(msg))
                self.safe_after(0, lambda: self._render_results([]))
        except Exception as e:
            classified = classify_download_error(str(e))
            err_msg = classified.user_message if classified else str(e)
            self.safe_after(0, lambda err=err_msg: self.status_var.set(f"URL Resolution error: {err}"))
            self.safe_after(0, lambda: self._render_results([]))

    def _search_thread(self, q):
        while self._engine_busy:
            time.sleep(0.5)
        try:
            ytdlp_bin = self.ytdlp if (self.ytdlp and os.path.exists(self.ytdlp)) else (shutil.which("yt-dlp") or self.ytdlp)
            proc = subprocess.Popen(
                [ytdlp_bin, f"ytsearch10:{q}", "--dump-json",
                 "--no-playlist", "--flat-playlist", "--no-warnings"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if self.is_win else 0
            )
            results = []
            for line in proc.stdout:
                try:
                    results.append(json.loads(line.decode("utf-8", errors="replace")))
                except Exception:
                    pass
            proc.wait()
            self.safe_after(0, lambda: self._render_results(results))
        except Exception as e:
            err_msg = str(e)
            self.safe_after(0, lambda err=err_msg: self.status_var.set(f"Search error: {err}"))

    def _render_featured_result(self, item, fallback_url):
        for w in self.results_scroll.winfo_children():
            w.destroy()

        title    = item.get("title", "Unknown Title")
        uploader = item.get("uploader") or item.get("channel", "YouTube")
        dur      = time_to_seconds(item.get("duration") or 0)
        url      = item.get("webpage_url") or fallback_url
        thumb_url= item.get("thumbnail", "")
        mins, secs = int(dur) // 60, int(dur) % 60

        card = ctk.CTkFrame(self.results_scroll, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=PRIMARY)
        card.pack(fill="x", pady=8, padx=6)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=16)

        # Thumbnail Label
        thumb_lbl = ctk.CTkLabel(inner, text="🎬", font=("Segoe UI", 24), width=120, height=68, fg_color=SURFACE2, corner_radius=8)
        thumb_lbl.pack(side="left", padx=(0, 16))
        if thumb_url:
            self._load_thumbnail_async(thumb_url, thumb_lbl, (120, 68))

        info = ctk.CTkFrame(inner, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True)

        _label(info, title[:80] + ("…" if len(title) > 80 else ""), font=("Segoe UI", 14, "bold"), anchor="w").pack(anchor="w")
        _label(info, f"{uploader}  ·  Duration: {mins}:{secs:02d}", font=FONT_XS, color=MUTED, anchor="w").pack(anchor="w", pady=(4, 8))

        btn_row = ctk.CTkFrame(info, fg_color="transparent")
        btn_row.pack(anchor="w")

        _btn(btn_row, "🎵 MP3 320k", lambda: self.add_to_queue(url, title, override_fmt="mp3_320"), fg=self.accent_color, hv=self.accent_hv, width=96, height=32, corner_radius=16).pack(side="left", padx=(0, 8))
        _btn(btn_row, "🎶 M4A", lambda: self.add_to_queue(url, title, override_fmt="m4a_best"), fg=PRIMARY, hv=PRIMARY_HV, width=76, height=32, corner_radius=16).pack(side="left", padx=(0, 8))
        _btn(btn_row, "🎬 MP4 1080p", lambda: self.add_to_queue(url, title, override_fmt="mp4_1080"), fg=SURFACE2, hv=BORDER, width=96, height=32, corner_radius=16).pack(side="left")

    def _render_results(self, results):
        for w in self.results_scroll.winfo_children():
            w.destroy()

        if not results:
            _label(self.results_scroll, self.t("No results found."), color=MUTED).pack(pady=30)
            return

        for item in results:
            title    = item.get("title", "Unknown Title")
            uploader = item.get("uploader", "")
            dur      = time_to_seconds(item.get("duration") or 0)
            url      = item.get("webpage_url") or item.get("url") or ("https://youtube.com/watch?v=" + item.get("id", ""))
            thumb_url= item.get("thumbnail", "")
            if not thumb_url and "thumbnails" in item and item["thumbnails"]:
                thumb_url = item["thumbnails"][0].get("url", "")

            mins, secs = int(dur) // 60, int(dur) % 60

            card = ctk.CTkFrame(self.results_scroll, fg_color=SURFACE, corner_radius=12, border_width=1, border_color=BORDER)
            card.pack(fill="x", pady=4, padx=6)

            thumb_lbl = ctk.CTkLabel(card, text="🎵", font=("Segoe UI", 16), width=90, height=52, fg_color=SURFACE2, corner_radius=6)
            thumb_lbl.pack(side="left", padx=10, pady=8)
            if thumb_url:
                self._load_thumbnail_async(thumb_url, thumb_lbl, (90, 52))

            info = ctk.CTkFrame(card, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True, padx=8, pady=8)

            _label(info, title[:65] + ("…" if len(title) > 65 else ""), font=FONT_SM, anchor="w").pack(anchor="w")
            _label(info, f"{uploader}  ·  {mins}:{secs:02d}", font=FONT_XS, color=MUTED, anchor="w").pack(anchor="w", pady=(2, 0))

            btn_box = ctk.CTkFrame(card, fg_color="transparent")
            btn_box.pack(side="right", padx=12, pady=8)

            _btn(btn_box, "🎵 MP3", lambda u=url, t=title: self.add_to_queue(u, t, override_fmt="mp3_320"), fg=self.accent_color, hv=self.accent_hv, width=68, height=30, corner_radius=15).pack(side="left", padx=4)
            _btn(btn_box, "🎬 MP4", lambda u=url, t=title: self.add_to_queue(u, t, override_fmt="mp4_1080"), fg=PRIMARY, hv=PRIMARY_HV, width=68, height=30, corner_radius=15).pack(side="left", padx=4)

    def _load_thumbnail_async(self, thumb_url, label_widget, size):
        if thumb_url in self.thumb_cache:
            try:
                label_widget.configure(image=self.thumb_cache[thumb_url], text="")
            except Exception:
                pass
            return

        def _fetch():
            try:
                r = safe_http_get(thumb_url, timeout=5, max_retries=2)
                if r and r.status_code == 200:
                    with Image.open(io.BytesIO(r.content)) as raw_img:
                        img = raw_img.copy()
                    ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=size)
                    self.thumb_cache[thumb_url] = ctk_img
                    self.safe_after(0, lambda: label_widget.configure(image=ctk_img, text=""))
            except Exception:
                pass

        self.executor.submit(_fetch)

    def _quick_add(self):
        url = self.search_entry.get().strip()
        if not url:
            return
        platform, p_type, ident = detect_platform_url(url)
        if platform in ("spotify", "apple_music", "soundcloud") or ("list=" in url or "playlist" in url):
            plat_name = platform.capitalize() if platform != "youtube" else "Playlist"
            if messagebox.askyesno("Smart Playlist", f"{plat_name} link detected! Would you like to preview & select tracks to download?"):
                self._handle_search_action()
                return
        self.search_entry.delete(0, "end")
        self.add_to_queue(url, url)

    # ── Smart Playlist Dialog (Revamped) ───────────────────────────────────────
    def _fetch_playlist(self, url):
        self.safe_after(0, lambda: self.status_var.set("Fetching playlist info..."))
        try:
            ytdlp_bin = self.ytdlp if (self.ytdlp and os.path.exists(self.ytdlp)) else (shutil.which("yt-dlp") or self.ytdlp)
            cmd = [ytdlp_bin, "--flat-playlist", "--dump-json", "--no-warnings", url]
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if self.is_win else 0
            )
            items = []
            for line in proc.stdout:
                try:
                    items.append(json.loads(line.decode("utf-8", errors="replace")))
                except Exception:
                    pass
            proc.wait()
            self.safe_after(0, lambda: self._show_playlist_selector(items))
            self.safe_after(0, lambda: self.status_var.set("Ready"))
        except Exception as e:
            err_msg = str(e)
            self.safe_after(0, lambda err=err_msg: self.status_var.set(f"Playlist error: {err}"))

    def _show_playlist_selector(self, items):
        if not items:
            messagebox.showinfo("Playlist", "No videos found in this playlist.")
            return

        top = ctk.CTkToplevel(self)
        top.title(self.t("Smart Playlist"))
        top.geometry("560x650")
        top.configure(fg_color=BG)
        top.attributes("-topmost", True)

        hdr = ctk.CTkFrame(top, fg_color=SURFACE, corner_radius=12)
        hdr.pack(fill="x", padx=16, pady=12)
        _label(hdr, f"📑  {self.t('Smart Playlist')}", font=FONT_MD, color=self.accent_color).pack(anchor="w", padx=14, pady=(12, 4))
        _label(hdr, f"Found {len(items)} tracks in playlist. Choose which ones to download:", font=FONT_XS, color=MUTED).pack(anchor="w", padx=14, pady=(0, 10))

        # Filter and Selection Row
        act_row = ctk.CTkFrame(hdr, fg_color="transparent")
        act_row.pack(fill="x", padx=14, pady=(0, 12))

        filter_ent = ctk.CTkEntry(act_row, placeholder_text="Filter tracks by title...", font=FONT_XS, fg_color=SURFACE2, height=32)
        filter_ent.pack(side="left", fill="x", expand=True, padx=(0, 10))

        vars_list = []  # [(var, checkbox_widget, url, title, duration)]

        _btn(act_row, self.t("Select All"), lambda: [v.set(True) for v, *_ in vars_list], fg=PRIMARY, width=80, height=32).pack(side="left", padx=4)
        _btn(act_row, self.t("Deselect All"), lambda: [v.set(False) for v, *_ in vars_list], fg=SURFACE2, width=80, height=32).pack(side="left")

        # Scrollable List of Checkboxes
        scroll = ctk.CTkScrollableFrame(top, fg_color=BG, scrollbar_button_color=SURFACE2)
        scroll.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        for idx, item in enumerate(items, 1):
            var = tk.BooleanVar(value=True)
            title = item.get("title", f"Track {idx}")
            dur = item.get("duration") or 0
            time_str = f" ({dur // 60}:{dur % 60:02d})" if dur else ""
            url = item.get("url") or ("https://youtube.com/watch?v=" + item.get("id", ""))

            cb = ctk.CTkCheckBox(
                scroll, text=f"{idx:02d}. {title[:55]}{time_str}",
                variable=var, font=FONT_SM, text_color=TEXT,
                fg_color=self.accent_color, hover_color=self.accent_hv,
            )
            cb.pack(anchor="w", pady=4, padx=6)
            vars_list.append((var, cb, url, title))

        def _on_filter(event):
            kw = filter_ent.get().strip().lower()
            for v, cb, u, t in vars_list:
                if not kw or kw in t.lower():
                    cb.pack(anchor="w", pady=4, padx=6)
                else:
                    cb.pack_forget()

        filter_ent.bind("<KeyRelease>", _on_filter)

        # Bottom Bar: Track numbering checkbox + Download Action
        bot = ctk.CTkFrame(top, fg_color=SURFACE, corner_radius=12)
        bot.pack(fill="x", padx=16, pady=(0, 14))

        numbering_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            bot, text="Prefix track numbers (01, 02...)",
            variable=numbering_var, font=FONT_XS, fg_color=self.accent_color,
        ).pack(side="left", padx=14, pady=12)

        def do_dl():
            top.destroy()
            selected = [(url, title) for var, cb, url, title in vars_list if var.get()]
            prefix = numbering_var.get()
            for idx, (url, title) in enumerate(selected, 1):
                clean_title = f"{idx:02d} - {title}" if prefix else title
                self.add_to_queue(url, clean_title)
            show_notify("Playlist Added", f"Added {len(selected)} tracks to queue.")
            self._switch_tab("queue")

        _btn(bot, self.t("Download Selected"), do_dl, fg=self.accent_color, hv=self.accent_hv, width=150, height=36).pack(side="right", padx=14, pady=12)

    # ── Universal Multi-Platform Playlist Dialog ──────────────────────────────
    def _show_multiplatform_selector(self, data):
        tracks = data.get("tracks", [])
        if not tracks:
            messagebox.showinfo("Universal Playlist", "No tracks found in playlist.")
            return

        top = ctk.CTkToplevel(self)
        top.title(self.t("Universal Playlist"))
        top.geometry("600x680")
        top.configure(fg_color=BG)
        top.attributes("-topmost", True)

        hdr = ctk.CTkFrame(top, fg_color=SURFACE, corner_radius=12)
        hdr.pack(fill="x", padx=16, pady=12)

        platform_badges = {
            "spotify": "🟢 Spotify",
            "apple_music": "🍎 Apple Music",
            "soundcloud": "🟠 SoundCloud",
            "youtube": "🔴 YouTube",
        }
        plat_str = platform_badges.get(data.get("platform"), "🌐 Web Playlist")

        _label(hdr, f"{plat_str}  ·  {data.get('title')}", font=FONT_MD, color=self.accent_color).pack(anchor="w", padx=14, pady=(12, 4))
        _label(hdr, f"{data.get('artist', '')}  ·  Found {len(tracks)} tracks. Choose which ones to import:", font=FONT_XS, color=MUTED).pack(anchor="w", padx=14, pady=(0, 10))

        # Filter & Selection Control Bar
        ctrl_bar = ctk.CTkFrame(hdr, fg_color="transparent")
        ctrl_bar.pack(fill="x", padx=14, pady=(0, 12))

        filter_ent = ctk.CTkEntry(ctrl_bar, placeholder_text="Filter tracks...", font=FONT_XS, fg_color=SURFACE2, height=32)
        filter_ent.pack(side="left", fill="x", expand=True, padx=(0, 8))

        track_vars = []  # [(var, checkbox, track_item)]

        def _select_all():
            for v, cb, _ in track_vars:
                if cb.winfo_ismapped():
                    v.set(True)

        def _deselect_all():
            for v, cb, _ in track_vars:
                if cb.winfo_ismapped():
                    v.set(False)

        _btn(ctrl_bar, self.t("Select All"), _select_all, fg=PRIMARY, width=80, height=32).pack(side="left", padx=4)
        _btn(ctrl_bar, self.t("Deselect All"), _deselect_all, fg=SURFACE2, width=80, height=32).pack(side="left")

        # Scrollable list of tracks
        scroll = ctk.CTkScrollableFrame(top, fg_color=BG, scrollbar_button_color=SURFACE2)
        scroll.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        for idx, trk in enumerate(tracks, 1):
            var = tk.BooleanVar(value=True)
            t_name = trk.get("title", f"Track {idx}")
            t_art = trk.get("artist", "")
            time_str = f" ({int(trk.get('duration', 0)) // 60}:{int(trk.get('duration', 0)) % 60:02d})" if trk.get("duration") else ""

            cb = ctk.CTkCheckBox(
                scroll, text=f"{idx:02d}. {t_name} — {t_art}{time_str}",
                variable=var, font=FONT_SM, text_color=TEXT,
                fg_color=self.accent_color, hover_color=self.accent_hv,
            )
            cb.pack(anchor="w", padx=10, pady=4)
            track_vars.append((var, cb, trk))

        def _filter_cb(e=None):
            kw = filter_ent.get().strip().lower()
            for v, cb, trk in track_vars:
                txt = f"{trk.get('title', '')} {trk.get('artist', '')}".lower()
                if not kw or kw in txt:
                    cb.pack(anchor="w", padx=10, pady=4)
                else:
                    cb.pack_forget()

        filter_ent.bind("<KeyRelease>", _filter_cb)

        # Bottom Bar: Track Numbering + Queue button
        bot = ctk.CTkFrame(top, fg_color=SURFACE, corner_radius=12)
        bot.pack(fill="x", padx=16, pady=(0, 14))

        numbering_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            bot, text="Prefix track numbers (01, 02...)",
            variable=numbering_var, font=FONT_XS, fg_color=self.accent_color,
        ).pack(side="left", padx=14, pady=12)

        def _do_import():
            top.destroy()
            selected = [trk for var, cb, trk in track_vars if var.get()]
            prefix = numbering_var.get()
            fmt = self.quick_fmt_var.get()

            for idx, trk in enumerate(selected, 1):
                raw_t = trk.get('title', f"Track {idx}")
                clean_t = f"{idx:02d} - {raw_t}" if prefix else raw_t
                direct_url = trk.get("url")
                sq = trk.get("search_query") or f"{trk.get('artist', '')} - {raw_t}".strip()

                if direct_url and ("youtube" in direct_url or "youtu.be" in direct_url or "soundcloud" in direct_url):
                    item_url = direct_url
                else:
                    item_url = f"ytsearch1:{sq}"

                trk_meta = {
                    "title": raw_t,
                    "artist": trk.get("artist") or data.get("artist") or "Unknown Artist",
                    "album": trk.get("album") or data.get("title") or "NexusTube Downloads",
                    "track_num": idx,
                    "thumbnail": trk.get("thumbnail") or data.get("thumbnail"),
                }
                self.add_to_queue(item_url, title=clean_t, override_fmt=fmt, metadata=trk_meta)

            show_notify("Universal Import", f"Queued {len(selected)} tracks for download.")
            self._switch_tab("queue")

        _btn(bot, self.t("Import to Queue"), _do_import, fg=self.accent_color, hv=self.accent_hv, width=150, height=36).pack(side="right", padx=14, pady=12)

    # ── Page 2: Download Queue ────────────────────────────────────────────────
    def _build_queue_page(self, parent):
        page = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)

        # Header
        hdr = ctk.CTkFrame(page, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(20, 10))

        left_hdr = ctk.CTkFrame(hdr, fg_color="transparent")
        left_hdr.pack(side="left")
        self.lbl_queue_title = _label(left_hdr, self.t("Download Queue"), font=FONT_H)
        self.lbl_queue_title.pack(anchor="w")
        self.lbl_queue_sub = _label(left_hdr, self.t("Queue_Sub"), font=FONT_XS, color=MUTED)
        self.lbl_queue_sub.pack(anchor="w")

        right_hdr = ctk.CTkFrame(hdr, fg_color="transparent")
        right_hdr.pack(side="right")
        _btn(right_hdr, self.t("Open Downloads Folder"), self._open_downloads_folder, fg=SURFACE2, hv=BORDER, width=130).pack(side="right", padx=(6, 0))
        _btn(right_hdr, self.t("Clear Finished"), self._clear_finished_queue, fg=SURFACE2, hv=BORDER, width=120).pack(side="right")

        self.queue_scroll = ctk.CTkScrollableFrame(
            page, fg_color=BG,
            scrollbar_button_color=SURFACE2, scrollbar_button_hover_color=PRIMARY,
        )
        self.queue_scroll.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        return page

    def _update_queue_stats(self):
        active = sum(1 for t in self.active_tasks.values() if t.get("status") == "downloading")
        self.lbl_queue_sub.configure(text=f"{active} active downloads in progress" if active else self.t("Queue_Sub"))

    def _open_downloads_folder(self):
        outdir = os.path.abspath(self.out_var.get())
        os.makedirs(outdir, exist_ok=True)
        try:
            if self.is_win: os.startfile(outdir)
            elif self.is_mac: subprocess.call(["open", outdir])
            else: subprocess.call(["xdg-open", outdir])
        except Exception:
            pass

    def _clear_finished_queue(self):
        to_remove = []
        for tid, task in self.active_tasks.items():
            if task.get("status") in ("completed", "cancelled", "failed"):
                try:
                    task["card"].destroy()
                except Exception:
                    pass
                to_remove.append(tid)
        for tid in to_remove:
            self.active_tasks.pop(tid, None)

    def _get_cookie_args(self):
        """คืน yt-dlp cookie arguments ตาม config ที่ตั้งไว้ (สำหรับ App Tkinter worker)
        Priority: custom file > browser extraction.
        คืน list ว่างถ้าไม่มี cookie ที่กำหนดไว้"""
        args = []
        cookie_file   = self.config.get("cookie_file")
        cookie_source = self.config.get("cookie_source")
        if cookie_file and os.path.isfile(cookie_file):
            args = ["--cookies", cookie_file]
        elif cookie_source and cookie_source in (
            "chrome", "firefox", "edge", "brave", "opera", "safari", "chromium"
        ):
            args = ["--cookies-from-browser", cookie_source]
        return args

    def add_to_queue(self, url, title="", override_fmt=None, metadata=None):
        task_id = f"task_{int(time.time() * 1000)}_{len(self.active_tasks)}"

        card = ctk.CTkFrame(self.queue_scroll, fg_color=SURFACE, corner_radius=12, border_width=1, border_color=BORDER)
        card.pack(fill="x", pady=5, padx=6)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(10, 4))

        display_title = (title or url)[:72]
        lbl = _label(top, display_title, font=FONT_SM, anchor="w")
        lbl.pack(side="left", fill="x", expand=True)

        stat = _label(top, self.t("Waiting…"), font=FONT_XS, color=MUTED)
        stat.pack(side="right")

        prog = ctk.CTkProgressBar(card, mode="determinate", fg_color=SURFACE2, progress_color=PRIMARY, corner_radius=4, height=6)
        prog.pack(fill="x", padx=16, pady=(0, 6))
        prog.set(0)

        # Bottom Action and Details Row
        bot = ctk.CTkFrame(card, fg_color="transparent")
        bot.pack(fill="x", padx=16, pady=(0, 10))

        details_lbl = _label(bot, "Preparing…", font=FONT_XS, color=MUTED)
        details_lbl.pack(side="left")

        actions_frame = ctk.CTkFrame(bot, fg_color="transparent")
        actions_frame.pack(side="right")

        cancel_btn = _btn(actions_frame, self.t("Cancel"), lambda tid=task_id: self._cancel_task(tid), fg=SURFACE2, hv=ERROR, width=65, height=26, corner_radius=13)
        cancel_btn.pack(side="right")

        task_data = {
            "id": task_id,
            "url": url,
            "title": title,
            "override_fmt": override_fmt,
            "metadata": metadata or {},
            "card": card,
            "lbl": lbl,
            "stat": stat,
            "prog": prog,
            "details_lbl": details_lbl,
            "actions_frame": actions_frame,
            "cancel_btn": cancel_btn,
            "proc": None,
            "cancelled": False,
            "status": "waiting",
            "out_file": None,
        }
        self.active_tasks[task_id] = task_data
        self.executor.submit(self._download_worker, task_data)

    def _cancel_task(self, task_id):
        task = self.active_tasks.get(task_id)
        if not task:
            return
        task["cancelled"] = True
        proc = task.get("proc")
        if proc:
            try:
                proc.terminate()
                proc.kill()
            except Exception:
                pass
        task["status"] = "cancelled"
        task["stat"].configure(text=self.t("Cancelled"), text_color=WARN)
        task["card"].configure(border_color=WARN)
        task["cancel_btn"].pack_forget()

    def _download_worker(self, task):
        def ui(fn):
            self.safe_after(0, fn)

        while self._engine_busy:
            if task["cancelled"]:
                return
            ui(lambda: task["stat"].configure(text="Waiting for engine…", text_color=WARN))
            time.sleep(1)

        if task["cancelled"]:
            return

        task["status"] = "downloading"
        ui(lambda: task["stat"].configure(text=self.t("Starting…"), text_color=PRIMARY))
        ui(lambda: task["card"].configure(border_color=PRIMARY))

        fmt_choice = task.get("override_fmt") or self.type_var.get()
        outdir = os.path.abspath(self.out_var.get() or os.path.join(os.path.expanduser("~"), "Downloads", "NexusTube"))
        
        # Self-healing output directory verification & fallback
        try:
            os.makedirs(outdir, exist_ok=True)
            probe = os.path.join(outdir, f".write_test_{int(time.time()*1000)}.tmp")
            with open(probe, "w") as fp:
                fp.write("ok")
            os.remove(probe)
        except Exception as perm_err:
            fallback_dir = os.path.join(os.path.expanduser("~"), "Downloads")
            try:
                os.makedirs(fallback_dir, exist_ok=True)
                outdir = fallback_dir
                ui(lambda: task["details_lbl"].configure(text="Output unwritable; redirected to Downloads."))
            except Exception:
                pass

        ffmpeg_dir = os.path.dirname(self.ffmpeg) if (self.ffmpeg and is_valid_binary(self.ffmpeg)) else ""
        ytdlp_bin = self.ytdlp if (self.ytdlp and is_valid_binary(self.ytdlp)) else (shutil.which("yt-dlp") or self.ytdlp)

        if not is_valid_binary(ytdlp_bin):
            task["status"] = "failed"
            ui(lambda: [
                task["stat"].configure(text="Engine Missing", text_color=ERROR),
                task["card"].configure(border_color=ERROR),
                task["details_lbl"].configure(text="yt-dlp engine not found. Connect to internet to download."),
                task["cancel_btn"].pack_forget(),
                _btn(task["actions_frame"], self.t("Retry"), lambda: self.add_to_queue(task["url"], task["title"]), fg=SURFACE2, hv=PRIMARY, width=65, height=26, corner_radius=13).pack(side="right")
            ])
            return

        # Output template with custom title preservation (e.g. track numbering)
        if task.get("title") and task["title"] != task["url"] and not task["title"].startswith("http"):
            safe_t = sanitize_filename(task["title"])
            out_template = os.path.join(outdir, f"{safe_t}.%(ext)s")
        else:
            out_template = os.path.join(outdir, "%(title)s.%(ext)s")

        # Construct yt-dlp arguments
        cmd = [
            ytdlp_bin, "--newline", "--no-warnings", "--windows-filenames",
            "--retries", "5", "--fragment-retries", "10", "--socket-timeout", "30",
            "-o", out_template,
        ]
        if ffmpeg_dir:
            cmd += ["--ffmpeg-location", ffmpeg_dir]

        # Inject browser cookies หากมีการกำหนดค่า (เปิดใช้สำหรับ age-restricted / members-only)
        cmd += self._get_cookie_args()

        has_ffmpeg = bool(ffmpeg_dir or shutil.which("ffmpeg"))
        # Options
        if self.sponsor_var.get() and has_ffmpeg:
            cmd += ["--sponsorblock-remove", "sponsor,selfpromo"]
        if self.meta_var.get() and has_ffmpeg:
            cmd += ["--embed-metadata"]
        if self.thumb_var.get() and has_ffmpeg:
            cmd += ["--embed-thumbnail"]
        if self.lyrics_var.get() and has_ffmpeg:
            cmd += ["--write-subs", "--sub-langs", "en.*,th.*", "--embed-subs"]

        # Format Configuration
        if fmt_choice == "mp3_320":
            cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "320K"]
        elif fmt_choice == "m4a_best":
            cmd += ["-x", "--audio-format", "m4a", "--audio-quality", "0"]
        elif fmt_choice == "flac":
            cmd += ["-x", "--audio-format", "flac", "--audio-quality", "0"]
        elif fmt_choice == "mp4_1080":
            cmd += ["-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best", "--merge-output-format", "mp4"]
        elif fmt_choice == "mp4_720":
            cmd += ["-f", "bestvideo[height<=720]+bestaudio/best[height<=720]/best", "--merge-output-format", "mp4"]
        else:  # mp4_best
            cmd += ["-f", "bestvideo+bestaudio/best", "--merge-output-format", "mp4"]

        # Audio Normalization if enabled
        if self.norm_var.get() and has_ffmpeg:
            if fmt_choice in ("mp3_320", "m4a_best", "flac"):
                cmd += ["--postprocessor-args", "ExtractAudio:-filter:a loudnorm=I=-14:LRA=11:TP=-1.5"]
            else:
                cmd += ["--postprocessor-args", "Merger:-filter:a loudnorm=I=-14:LRA=11:TP=-1.5"]

        cmd.append(task["url"])

        ansi = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        pct_regex   = re.compile(r"(\d+\.?\d*)%")
        speed_regex = re.compile(r"at\s+([~0-9\.]+\s*\w+/s)")
        eta_regex   = re.compile(r"ETA\s+(\d+:\d+(?::\d+)?)")
        dest_file   = None

        max_download_attempts = 3
        download_succeeded = False
        last_error_msg = None

        for dl_attempt in range(1, max_download_attempts + 1):
            if task["cancelled"]:
                ui(lambda: [
                    task["stat"].configure(text=self.t("Cancelled"), text_color=WARN),
                    task["card"].configure(border_color=WARN),
                    task["cancel_btn"].pack_forget()
                ])
                return

            last_output_lines = []
            try:
                # Task 2: Standardized logging for external streaming tool
                cmd_str = " ".join(f'"{c}"' if " " in c else c for c in cmd)
                try:
                    sys.stderr.write(f"[Worker] Starting download (attempt {dl_attempt}/{max_download_attempts}): {cmd_str}\n")
                except Exception:
                    pass

                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if self.is_win else 0
                )
                task["proc"] = proc

                for raw in proc.stdout:
                    if task["cancelled"]:
                        break
                    line = ansi.sub("", raw.decode("utf-8", errors="replace")).strip()
                    if line:
                        last_output_lines.append(line)
                        if len(last_output_lines) > 20:
                            last_output_lines.pop(0)

                    # Detect output file
                    if os.path.isabs(line) and os.path.exists(line):
                        dest_file = line
                        task["out_file"] = dest_file
                    elif "Destination:" in line:
                        d = line.split("Destination:", 1)[-1].strip()
                        if not d.endswith(".part") and not d.endswith(".ytdl"):
                            dest_file = d
                            task["out_file"] = dest_file
                    elif "already been downloaded" in line:
                        m = re.search(r'\[download\]\s+(.*?)\s+has already been downloaded', line)
                        if m:
                            dest_file = m.group(1).strip()
                            task["out_file"] = dest_file
                    elif "Merging formats into" in line:
                        m_dest = line.split('Merging formats into "', 1)[-1].rstrip('"')
                        dest_file = m_dest
                        task["out_file"] = dest_file

                    # Progress parsing
                    if "[download]" in line and "%" in line:
                        pm = pct_regex.search(line)
                        sm = speed_regex.search(line)
                        em = eta_regex.search(line)
                        if pm:
                            pct = float(pm.group(1)) / 100.0
                            speed = sm.group(1) if sm else ""
                            eta = em.group(1) if em else ""
                            status_str = f"Downloading · {pct*100:.1f}%"
                            det_str = f"Speed: {speed}  ·  ETA: {eta}" if (speed or eta) else ""
                            ui(lambda p=pct, s=status_str, d=det_str: [
                                task["prog"].set(p),
                                task["stat"].configure(text=s, text_color=TEXT),
                                task["details_lbl"].configure(text=d)
                            ])
                    elif any(k in line for k in ("[ExtractAudio]", "[Merger]", "[Metadata]", "[EmbedThumbnail]", "[SponsorBlock]")):
                        ui(lambda: [
                            task["stat"].configure(text=self.t("Processing…"), text_color=WARN),
                            task["details_lbl"].configure(text="Postprocessing audio & metadata tags…")
                        ])

                proc.wait()

                if task["cancelled"]:
                    ui(lambda: [
                        task["stat"].configure(text=self.t("Cancelled"), text_color=WARN),
                        task["card"].configure(border_color=WARN),
                        task["cancel_btn"].pack_forget()
                    ])
                    return

                if proc.returncode == 0:
                    download_succeeded = True
                    break
                else:
                    last_error_msg = "\n".join(last_output_lines[-5:]) if last_output_lines else f"Process exited with code {proc.returncode}"
                    print(f"[Worker] Attempt {dl_attempt}/{max_download_attempts} failed (code {proc.returncode}): {last_error_msg}")
                    if dl_attempt < max_download_attempts:
                        ui(lambda att=dl_attempt: [
                            task["stat"].configure(text=f"Retrying ({att}/{max_download_attempts})…", text_color=WARN),
                            task["card"].configure(border_color=WARN)
                        ])
                        time.sleep(2 * dl_attempt)
            except Exception as ex:
                last_error_msg = str(ex)
                print(f"[Worker] Exception on attempt {dl_attempt}: {ex}")
                if dl_attempt < max_download_attempts:
                    ui(lambda att=dl_attempt: [
                        task["stat"].configure(text=f"Retrying ({att}/{max_download_attempts})…", text_color=WARN),
                        task["card"].configure(border_color=WARN)
                    ])
                    time.sleep(2 * dl_attempt)

        if not download_succeeded:
            task["status"] = "failed"
            classified = classify_download_error(last_error_msg or "")
            if classified:
                short_err = classified.user_message
            else:
                short_err = (last_error_msg or "Download failed").splitlines()[-1][:60]
            ui(lambda err=short_err: [
                task["stat"].configure(text=self.t("Failed ✗"), text_color=ERROR),
                task["card"].configure(border_color=ERROR),
                task["details_lbl"].configure(text=err),
                task["cancel_btn"].pack_forget(),
                _btn(task["actions_frame"], self.t("Retry"), lambda: self.add_to_queue(task["url"], task["title"]), fg=SURFACE2, hv=PRIMARY, width=65, height=26, corner_radius=13).pack(side="right")
            ])
            return

        final_file = dest_file or task.get("out_file")
        if not final_file or not os.path.exists(final_file):
            try:
                media_exts = (".mp3", ".m4a", ".wav", ".flac", ".opus", ".ogg", ".aac", ".mp4", ".mkv", ".webm")
                candidates = [
                    os.path.join(outdir, f) for f in os.listdir(outdir)
                    if not f.endswith((".part", ".ytdl", ".lrc", ".jpg", ".png", ".webp", ".json", ".txt"))
                    and f.lower().endswith(media_exts)
                ]
                if candidates:
                    candidates.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                    if time.time() - os.path.getmtime(candidates[0]) < 180:
                        final_file = candidates[0]
                        task["out_file"] = final_file
            except Exception:
                pass

        # Automatic ID3 Tagging, Cover Art & Synced Lyrics Embedding
        if final_file and os.path.exists(final_file) and not final_file.lower().endswith((".mp4", ".mkv", ".webm")):
            try:
                meta_info = task.get("metadata") or {}
                raw_name = task.get("title") or os.path.basename(final_file).rsplit(".", 1)[0]
                parsed_meta = parse_music_metadata(
                    raw_name,
                    fallback_artist=meta_info.get("artist", ""),
                    fallback_album=meta_info.get("album", "NexusTube Collection"),
                    fallback_track=meta_info.get("track_num", 1)
                )
                final_title = meta_info.get("title") or parsed_meta["title"]
                final_artist = meta_info.get("artist") or parsed_meta["artist"]
                final_album = meta_info.get("album") or parsed_meta["album"]
                final_track = meta_info.get("track_num") or parsed_meta["track_num"]

                meta = {
                    "title": final_title,
                    "artist": final_artist,
                    "album": final_album,
                    "year": time.strftime("%Y"),
                    "genre": "Music",
                    "track_num": final_track,
                }

                # Synchronized Lyrics fetching and saving
                lyrics_text = None
                if self.lyrics_var.get():
                    lyr_res = fetch_lyrics(final_title, final_artist, file_path=final_file)
                    lyrics_text = lyr_res.get("synced_raw") or lyr_res.get("plain")
                    if lyr_res.get("synced_raw"):
                        try:
                            lrc_dest = os.path.splitext(final_file)[0] + ".lrc"
                            with open(lrc_dest, "w", encoding="utf-8") as lf:
                                lf.write(lyr_res["synced_raw"])
                        except Exception:
                            pass

                # Embed tags & cover art into file
                if self.meta_var.get():
                    cover_art = meta_info.get("thumbnail") or (task.get("thumbnail") if self.thumb_var.get() else None)
                    tag_audio_file(final_file, meta, cover_data_or_url=cover_art, lyrics_text=lyrics_text)
            except Exception as tag_err:
                print(f"[Worker] Auto tagger error: {tag_err}")

        task["status"] = "completed"
        ui(lambda: [
            task["prog"].set(1.0),
            task["prog"].configure(progress_color=self.accent_color),
            task["stat"].configure(text=self.t("Complete ✓"), text_color=self.accent_color),
            task["card"].configure(border_color=self.accent_color),
            task["details_lbl"].configure(text="Finished saving to downloads folder"),
            task["cancel_btn"].pack_forget(),
            self._add_completed_actions(task, final_file)
        ])
        show_notify("Download Complete", f"Saved: {os.path.basename(final_file) if final_file else task['title']}")

    def _add_completed_actions(self, task, filepath):
        act = task["actions_frame"]
        if filepath and os.path.exists(filepath):
            _btn(act, self.t("Play"), lambda p=filepath: self._play_track(p), fg=self.accent_color, hv=self.accent_hv, width=60, height=26, corner_radius=13).pack(side="left", padx=3)
            _btn(act, self.t("Show in Folder"), lambda p=filepath: self._reveal_in_explorer(p), fg=SURFACE2, hv=BORDER, width=70, height=26, corner_radius=13).pack(side="left", padx=3)

    def _reveal_in_explorer(self, filepath):
        if not os.path.exists(filepath):
            return
        try:
            if self.is_win:
                subprocess.Popen(["explorer", "/select,", os.path.normpath(filepath)])
            elif self.is_mac:
                subprocess.call(["open", "-R", filepath])
            else:
                subprocess.call(["xdg-open", os.path.dirname(filepath)])
        except Exception:
            pass

    # ── Page 3: Library (In-App Manager) ──────────────────────────────────────
    def _build_library_page(self, parent):
        page = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)

        # Header
        hdr = ctk.CTkFrame(page, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(20, 10))

        self.lbl_lib_title = _label(hdr, self.t("Library"), font=FONT_H)
        self.lbl_lib_title.pack(side="left")

        self.lib_count_lbl = _label(hdr, "0 tracks", font=FONT_XS, color=MUTED)
        self.lib_count_lbl.pack(side="left", padx=12, pady=(8, 0))

        _btn(hdr, self.t("Refresh"), self._refresh_library, fg=SURFACE2, hv=BORDER, width=88).pack(side="right")
        _btn(hdr, self.t("Open Downloads Folder"), self._open_downloads_folder, fg=SURFACE2, hv=BORDER, width=120).pack(side="right", padx=8)

        # Search / Filter Bar in Library
        filter_card = ctk.CTkFrame(page, fg_color=SURFACE, corner_radius=12, border_width=1, border_color=BORDER)
        filter_card.pack(fill="x", padx=24, pady=(0, 10))

        self.lib_search_entry = ctk.CTkEntry(
            filter_card, placeholder_text=self.t("Search Library..."),
            font=FONT_SM, fg_color=SURFACE2, border_color=BORDER, height=36, corner_radius=18
        )
        self.lib_search_entry.pack(fill="x", padx=12, pady=10)
        self.lib_search_entry.bind("<KeyRelease>", lambda e: self._filter_library_cards())

        self.lib_scroll = ctk.CTkScrollableFrame(
            page, fg_color=BG,
            scrollbar_button_color=SURFACE2, scrollbar_button_hover_color=PRIMARY,
        )
        self.lib_scroll.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        return page

    def _refresh_library(self):
        for w in self.lib_scroll.winfo_children():
            w.destroy()

        outdir = self.out_var.get()
        if not os.path.exists(outdir):
            return

        supported_exts = (".mp3", ".m4a", ".flac", ".wav", ".mp4", ".webm", ".opus")
        try:
            files = [f for f in os.listdir(outdir) if f.lower().endswith(supported_exts) and not f.endswith(".part")]
            files.sort(key=lambda x: os.path.getmtime(os.path.join(outdir, x)), reverse=True)
        except Exception:
            files = []

        self.library_items = [os.path.join(outdir, f) for f in files]
        self.lib_count_lbl.configure(text=f"{len(files)} files")

        if not files:
            _label(self.lib_scroll, self.t("No files downloaded yet."), color=MUTED).pack(pady=30)
            return

        self._lib_card_data = []  # [(card, filename, title, artist)]
        for f in files:
            p = os.path.join(outdir, f)
            meta = get_media_info(p)
            dur = meta.get("duration", 0)
            dur_str = f"{dur // 60}:{dur % 60:02d}" if dur else ""
            sz_mb = meta.get("size_bytes", 0) / (1024 * 1024)
            ext = f.rsplit(".", 1)[-1].upper()

            card = ctk.CTkFrame(self.lib_scroll, fg_color=SURFACE, corner_radius=12, border_width=1, border_color=BORDER)
            card.pack(fill="x", pady=4, padx=6)

            # Left Artwork / Format Icon
            thumb_lbl = ctk.CTkLabel(card, text="🎬" if ext == "MP4" else "🎵", font=("Segoe UI", 16), width=48, height=48, fg_color=SURFACE2, corner_radius=6)
            thumb_lbl.pack(side="left", padx=10, pady=8)
            cover = meta.get("cover_image")
            if cover:
                try:
                    ctk_cover = ctk.CTkImage(light_image=cover, dark_image=cover, size=(48, 48))
                    thumb_lbl.configure(image=ctk_cover, text="")
                except Exception:
                    pass

            info = ctk.CTkFrame(card, fg_color="transparent")
            info.pack(side="left", fill="both", expand=True, padx=8, pady=8)

            title = meta.get("title") or f
            artist= meta.get("artist") or "NexusTube"
            _label(info, title[:65] + ("…" if len(title) > 65 else ""), font=FONT_SM, anchor="w").pack(anchor="w")
            _label(info, f"{artist}  ·  {ext}  ·  {dur_str}  ·  {sz_mb:.1f} MB", font=FONT_XS, color=MUTED, anchor="w").pack(anchor="w", pady=(2, 0))

            actions = ctk.CTkFrame(card, fg_color="transparent")
            actions.pack(side="right", padx=12, pady=8)

            _btn(actions, self.t("Play in App"), lambda path=p: self._play_track(path), fg=PRIMARY, hv=PRIMARY_HV, width=74, height=30, corner_radius=15).pack(side="left", padx=3)
            _btn(actions, self.t("Trim"), lambda path=p: self._open_trim_dialog(path), fg=SURFACE2, hv=BORDER, width=64, height=30, corner_radius=15).pack(side="left", padx=3)
            _btn(actions, self.t("Show in Folder"), lambda path=p: self._reveal_in_explorer(path), fg=SURFACE2, hv=BORDER, width=64, height=30, corner_radius=15).pack(side="left", padx=3)
            _btn(actions, self.t("Delete"), lambda path=p: self._delete_library_file(path), fg=SURFACE2, hv=ERROR, width=54, height=30, corner_radius=15).pack(side="left", padx=3)

            self._lib_card_data.append((card, f, title, artist))

    def _filter_library_cards(self):
        kw = self.lib_search_entry.get().strip().lower()
        for card, fname, title, artist in getattr(self, "_lib_card_data", []):
            if not kw or (kw in fname.lower() or kw in title.lower() or kw in artist.lower()):
                card.pack(fill="x", pady=4, padx=6)
            else:
                card.pack_forget()

    def _delete_library_file(self, path):
        fn = os.path.basename(path)
        if not messagebox.askyesno("Delete", f"{self.t('DeleteConfirm')}{fn}"):
            return

        if self.player.current_path == path:
            self.player.stop()

        try:
            os.remove(path)
            self._refresh_library()
            show_notify("Deleted", f"Deleted {fn}")
        except Exception as e:
            messagebox.showerror("Delete Error", str(e))

    # ── Audio Trimmer Pro (Ringtone & Hook Maker) ──────────────────────────────
    def _open_trim_dialog(self, path):
        meta = get_media_info(path)
        total_dur = meta.get("duration", 0)

        top = ctk.CTkToplevel(self)
        top.title(self.t("Trimmer_Title"))
        top.geometry("420x500")
        top.configure(fg_color=BG)
        top.attributes("-topmost", True)

        card = ctk.CTkFrame(top, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        card.pack(fill="both", expand=True, padx=18, pady=18)

        _label(card, "✂️  Audio Trimmer Pro", font=FONT_MD, color=self.accent_color).pack(anchor="w", padx=16, pady=(16, 4))
        _label(card, os.path.basename(path)[:50], font=FONT_SM).pack(anchor="w", padx=16)
        dur_lbl = _label(card, f"Total Duration: {seconds_to_time(total_dur)}", font=FONT_XS, color=MUTED)
        dur_lbl.pack(anchor="w", padx=16, pady=(2, 14))

        # Start Time
        _label(card, self.t("Start Time"), font=FONT_XS, color=MUTED).pack(anchor="w", padx=16)
        start_ent = ctk.CTkEntry(card, font=FONT_SM, fg_color=SURFACE2, height=36)
        start_ent.insert(0, "00:00:00")
        start_ent.pack(fill="x", padx=16, pady=(4, 10))

        # End Time
        default_end = min(total_dur, 30) if total_dur > 0 else 30
        _label(card, self.t("End Time"), font=FONT_XS, color=MUTED).pack(anchor="w", padx=16)
        end_ent = ctk.CTkEntry(card, font=FONT_SM, fg_color=SURFACE2, height=36)
        end_ent.insert(0, seconds_to_time(default_end))
        end_ent.pack(fill="x", padx=16, pady=(4, 12))

        # Presets Row
        preset_row = ctk.CTkFrame(card, fg_color="transparent")
        preset_row.pack(fill="x", padx=16, pady=(0, 14))

        def _apply_preset(s, e):
            start_ent.delete(0, "end")
            start_ent.insert(0, s)
            end_ent.delete(0, "end")
            end_ent.insert(0, e)

        _btn(preset_row, "0-30s", lambda: _apply_preset("00:00:00", "00:00:30"), fg=SURFACE2, width=54, height=28).pack(side="left", padx=2)
        _btn(preset_row, "30-60s", lambda: _apply_preset("00:00:30", "00:01:00"), fg=SURFACE2, width=54, height=28).pack(side="left", padx=2)
        _btn(preset_row, "1-2m", lambda: _apply_preset("00:01:00", "00:02:00"), fg=SURFACE2, width=54, height=28).pack(side="left", padx=2)
        _btn(preset_row, "Full", lambda: _apply_preset("00:00:00", seconds_to_time(total_dur)), fg=SURFACE2, width=54, height=28).pack(side="left", padx=2)

        # Preview Control with Automatic End Time Boundary
        preview_state = {"playing": False, "job": None}

        def _stop_preview():
            self.player.stop()
            preview_state["playing"] = False
            try:
                preview_btn.configure(text=self.t("Preview Slice"), fg_color=PRIMARY, hover_color=PRIMARY_HV)
            except Exception:
                pass

        def _preview_slice():
            if preview_state["playing"]:
                _stop_preview()
                return

            s_sec = time_to_seconds(start_ent.get().strip())
            e_sec = time_to_seconds(end_ent.get().strip())
            if e_sec <= s_sec:
                e_sec = total_dur if total_dur > s_sec else s_sec + 30.0

            ok = self.player.load_and_play(path, start_time=s_sec)
            if ok:
                preview_state["playing"] = True
                preview_btn.configure(text=self.t("Stop Preview"), fg_color=WARN, hover_color="#D97706")

                def _poll_slice_boundary():
                    if not preview_state["playing"]:
                        return
                    cur_pos = self.player.get_pos()
                    if cur_pos >= e_sec or not self.player.is_playing:
                        _stop_preview()
                    else:
                        try:
                            if top.winfo_exists():
                                preview_state["job"] = top.after(200, _poll_slice_boundary)
                        except Exception:
                            _stop_preview()

                preview_state["job"] = top.after(200, _poll_slice_boundary)

        prev_box = ctk.CTkFrame(card, fg_color="transparent")
        prev_box.pack(fill="x", padx=16, pady=(0, 10))

        preview_btn = _btn(prev_box, self.t("Preview Slice"), _preview_slice, fg=PRIMARY, hv=PRIMARY_HV, height=36)
        preview_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

        _btn(prev_box, self.t("Stop Preview"), _stop_preview, fg=SURFACE2, hv=ERROR, width=80, height=36).pack(side="right")

        def _on_dialog_close():
            _stop_preview()
            top.destroy()

        top.protocol("WM_DELETE_WINDOW", _on_dialog_close)

        # Trim & Save Action
        def do_trim():
            s_raw = start_ent.get().strip()
            e_raw = end_ent.get().strip()
            s_sec = time_to_seconds(s_raw)
            e_sec = time_to_seconds(e_raw)
            if e_sec <= s_sec:
                messagebox.showerror("Trim Error", "End Time must be greater than Start Time.")
                return

            _stop_preview()
            top.destroy()

            start = seconds_to_time(s_sec)
            end = seconds_to_time(e_sec)

            base, ext = os.path.splitext(path)
            out_path = f"{base}_trimmed.mp3"
            self.status_var.set("Trimming audio...")

            def _trim_thread():
                try:
                    ffmpeg_bin = self.ffmpeg if (self.ffmpeg and os.path.exists(self.ffmpeg)) else (shutil.which("ffmpeg") or self.ffmpeg)
                    cmd = [
                        ffmpeg_bin, "-y",
                        "-ss", start, "-to", end,
                        "-i", path,
                        "-c:a", "libmp3lame", "-b:a", "320k",
                        out_path
                    ]
                    run_external_tool(cmd, label="ffmpeg trim audio", check=True)
                    self.safe_after(0, lambda: self.status_var.set("Trim complete ✅"))
                    show_notify("Trim Complete", f"Saved: {os.path.basename(out_path)}")
                    self.safe_after(0, self._refresh_library)
                except Exception as e:
                    err_msg = str(e)
                    self.safe_after(0, lambda err=err_msg: messagebox.showerror("Trim Error", err))

            threading.Thread(target=_trim_thread, daemon=True).start()

        _btn(card, self.t("Trim Now"), do_trim, fg=self.accent_color, hv=self.accent_hv, height=40).pack(fill="x", padx=16, pady=(0, 12))

    # ── Page 4: Settings Page ─────────────────────────────────────────────────
    def _build_settings_page(self, parent):
        page = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)

        # Header
        hdr = ctk.CTkFrame(page, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(20, 10))
        self.lbl_set_title = _label(hdr, self.t("Settings_Title"), font=FONT_H)
        self.lbl_set_title.pack(anchor="w")
        self.lbl_set_sub = _label(hdr, self.t("Settings_Sub"), font=FONT_XS, color=MUTED)
        self.lbl_set_sub.pack(anchor="w")

        scroll = ctk.CTkScrollableFrame(page, fg_color=BG, scrollbar_button_color=SURFACE2)
        scroll.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        # Card 1: Default Download Format
        fc = ctk.CTkFrame(scroll, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        fc.pack(fill="x", pady=6, padx=6)
        self.lbl_fmt_card = _label(fc, self.t("Default Format"), font=FONT_MD)
        self.lbl_fmt_card.pack(anchor="w", padx=18, pady=(14, 6))
        ctk.CTkFrame(fc, fg_color=BORDER, height=1).pack(fill="x", padx=16, pady=(0, 8))

        self.type_var = tk.StringVar(value=self.config.get("format", "mp3_320"))
        format_options = [
            ("mp3_320", "Audio  —  MP3 320kbps (Extreme)"),
            ("m4a_best", "Audio  —  M4A / AAC (Source Quality)"),
            ("flac", "Audio  —  FLAC (Lossless)"),
            ("mp4_best", "Video  —  MP4 (Best Available / 4K)"),
            ("mp4_1080", "Video  —  MP4 (1080p Full HD)"),
            ("mp4_720", "Video  —  MP4 (720p HD)"),
        ]
        def _on_fmt_change():
            self.config["format"] = self.type_var.get()
            self._save_config()

        for val, loc_key in format_options:
            r = ctk.CTkRadioButton(
                fc, text=self.t(loc_key), variable=self.type_var, value=val,
                command=_on_fmt_change, font=FONT_SM,
                fg_color=self.accent_color, hover_color=self.accent_hv,
            )
            r.pack(anchor="w", padx=18, pady=4)
        ctk.CTkFrame(fc, fg_color="transparent", height=6).pack()

        # Card 2: Download Options
        oc = ctk.CTkFrame(scroll, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        oc.pack(fill="x", pady=6, padx=6)
        self.lbl_opts_card = _label(oc, self.t("Download Options"), font=FONT_MD)
        self.lbl_opts_card.pack(anchor="w", padx=18, pady=(14, 6))
        ctk.CTkFrame(oc, fg_color=BORDER, height=1).pack(fill="x", padx=16, pady=(0, 8))

        self.thumb_var = tk.BooleanVar(value=self.config.get("embed_thumb", True))
        self.meta_var  = tk.BooleanVar(value=self.config.get("embed_meta", True))
        self.lyrics_var= tk.BooleanVar(value=self.config.get("embed_lyrics", False))
        self.sponsor_var=tk.BooleanVar(value=bool(self.config.get("sponsorblock", "sponsor")))
        self.norm_var   =tk.BooleanVar(value=self.config.get("normalize", False))

        def _on_opt_change():
            self.config["embed_thumb"] = self.thumb_var.get()
            self.config["embed_meta"] = self.meta_var.get()
            self.config["embed_lyrics"] = self.lyrics_var.get()
            self.config["sponsorblock"] = "sponsor" if self.sponsor_var.get() else ""
            self.config["normalize"] = self.norm_var.get()
            self._save_config()

        checkboxes = [
            (self.thumb_var, "Embed thumbnail / album art"),
            (self.meta_var, "Embed metadata & artist info"),
            (self.lyrics_var, "Embed lyrics / subtitles"),
            (self.sponsor_var, "SponsorBlock"),
            (self.norm_var, "Volume Normalization"),
        ]
        for var, loc_key in checkboxes:
            ctk.CTkCheckBox(
                oc, text=self.t(loc_key), variable=var,
                command=_on_opt_change, font=FONT_SM,
                fg_color=self.accent_color, hover_color=self.accent_hv,
                checkmark_color=BG, corner_radius=6,
            ).pack(anchor="w", padx=18, pady=5)
        ctk.CTkFrame(oc, fg_color="transparent", height=6).pack()

        # Card 3: Theme Accent Color (Instant Live Update)
        tc = ctk.CTkFrame(scroll, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        tc.pack(fill="x", pady=6, padx=6)
        self.lbl_theme_card = _label(tc, self.t("Theme Accent Color"), font=FONT_MD)
        self.lbl_theme_card.pack(anchor="w", padx=18, pady=(14, 6))
        ctk.CTkFrame(tc, fg_color=BORDER, height=1).pack(fill="x", padx=16, pady=(0, 10))

        trow = ctk.CTkFrame(tc, fg_color="transparent")
        trow.pack(fill="x", padx=16, pady=(0, 14))

        for name, meta in ACCENT_PALETTE.items():
            btn = ctk.CTkButton(
                trow, text="", width=36, height=36, corner_radius=18,
                fg_color=meta["color"], hover_color=meta["hover"],
                command=lambda c=meta["color"], h=meta["hover"]: self._set_live_accent(c, h),
            )
            btn.pack(side="left", padx=8)

        # Card 4: Language (Instant Live Update)
        lc = ctk.CTkFrame(scroll, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        lc.pack(fill="x", pady=6, padx=6)
        self.lbl_lang_card = _label(lc, self.t("Language"), font=FONT_MD)
        self.lbl_lang_card.pack(anchor="w", padx=18, pady=(14, 6))
        ctk.CTkFrame(lc, fg_color=BORDER, height=1).pack(fill="x", padx=16, pady=(0, 10))

        lrow = ctk.CTkFrame(lc, fg_color="transparent")
        lrow.pack(fill="x", padx=18, pady=(0, 14))

        self.lang_var = tk.StringVar(value=self.lang)
        ctk.CTkRadioButton(
            lrow, text="ภาษาไทย (Thai)", variable=self.lang_var, value="th",
            command=lambda: self._set_live_language("th"),
            font=FONT_SM, fg_color=self.accent_color, hover_color=self.accent_hv,
        ).pack(side="left", padx=(0, 20))
        ctk.CTkRadioButton(
            lrow, text="English", variable=self.lang_var, value="en",
            command=lambda: self._set_live_language("en"),
            font=FONT_SM, fg_color=self.accent_color, hover_color=self.accent_hv,
        ).pack(side="left")

        # Card 5: Output Folder
        dc = ctk.CTkFrame(scroll, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        dc.pack(fill="x", pady=6, padx=6)
        self.lbl_out_card = _label(dc, self.t("Output Folder"), font=FONT_MD)
        self.lbl_out_card.pack(anchor="w", padx=18, pady=(14, 6))
        ctk.CTkFrame(dc, fg_color=BORDER, height=1).pack(fill="x", padx=16, pady=(0, 10))

        row = ctk.CTkFrame(dc, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 14))
        self.out_var = tk.StringVar(value=self._default_outdir)
        ctk.CTkEntry(
            row, textvariable=self.out_var, state="readonly", font=FONT_SM,
            fg_color=SURFACE2, border_color=BORDER, text_color=MUTED, corner_radius=8, height=36,
        ).pack(side="left", fill="x", expand=True, padx=(0, 10))
        _btn(row, self.t("Browse"), self._browse_out, fg=PRIMARY, width=80).pack(side="left", padx=(0, 6))
        _btn(row, self.t("Open Downloads Folder"), self._open_downloads_folder, fg=SURFACE2, width=100).pack(side="left")

        # Card 6: Engines Health & Self-Updating
        ec = ctk.CTkFrame(scroll, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        ec.pack(fill="x", pady=6, padx=6)
        _label(ec, self.t("Engines Status"), font=FONT_MD).pack(anchor="w", padx=18, pady=(14, 6))
        ctk.CTkFrame(ec, fg_color=BORDER, height=1).pack(fill="x", padx=16, pady=(0, 10))

        erow = ctk.CTkFrame(ec, fg_color="transparent")
        erow.pack(fill="x", padx=18, pady=(0, 14))

        self.engine_details_lbl = _label(erow, f"yt-dlp: {self._ytdlp_ver_str}  ·  ffmpeg: {os.path.basename(self.ffmpeg)}", font=FONT_XS, color=MUTED)
        self.engine_details_lbl.pack(side="left", fill="x", expand=True)

        _btn(erow, self.t("Update Engines Now"), lambda: threading.Thread(target=self._check_engine, args=(True,), daemon=True).start(), fg=PRIMARY, width=150).pack(side="right")

        # Card 7: Crash Reporting / Telemetry (Feature 5 — Sentry opt-in)
        tlc = ctk.CTkFrame(scroll, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        tlc.pack(fill="x", pady=6, padx=6)
        _label(tlc, "📊 Crash Reporting (Beta)", font=FONT_MD).pack(anchor="w", padx=18, pady=(14, 6))
        ctk.CTkFrame(tlc, fg_color=BORDER, height=1).pack(fill="x", padx=16, pady=(0, 8))
        _label(
            tlc,
            "ส่งรายงาน crash แบบไม่ระบุตัวตนเพื่อช่วยพัฒนาแอป (ต้องตั้ง SENTRY_DSN ก่อน)",
            font=FONT_XS,
            color=MUTED,
        ).pack(anchor="w", padx=18, pady=(0, 8))
        self._telemetry_var = tk.BooleanVar(value=self.config.get("telemetry_enabled", False))

        def _on_telemetry_change():
            self.config["telemetry_enabled"] = self._telemetry_var.get()
            self._save_config()
            if self._telemetry_var.get():
                init_sentry(self.config)

        ctk.CTkCheckBox(
            tlc,
            text="เปิดใช้งาน Crash Reporting (opt-in)",
            variable=self._telemetry_var,
            command=_on_telemetry_change,
            font=FONT_SM,
            fg_color=self.accent_color,
            hover_color=self.accent_hv,
            checkmark_color=BG,
            corner_radius=6,
        ).pack(anchor="w", padx=18, pady=(0, 14))

        # Card 8: Cookie / Authentication — ดาวน์โหลด age-restricted / members-only
        cc = ctk.CTkFrame(scroll, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        cc.pack(fill="x", pady=6, padx=6)
        _label(cc, "🍪 Cookie / Authentication", font=FONT_MD).pack(anchor="w", padx=18, pady=(14, 6))
        ctk.CTkFrame(cc, fg_color=BORDER, height=1).pack(fill="x", padx=16, pady=(0, 8))
        _label(cc, "ใช้สำหรับดาวน์โหลดคอนเทนต์ที่ต้องล็อกอิน เช่น age-restricted หรือ members-only",
               font=FONT_XS, color=MUTED).pack(anchor="w", padx=18, pady=(0, 8))

        bcrow = ctk.CTkFrame(cc, fg_color="transparent")
        bcrow.pack(fill="x", padx=18, pady=(0, 6))
        _label(bcrow, "Browser:", font=FONT_XS, color=MUTED).pack(side="left")
        browser_options = ["ไม่ใช้ Cookie", "Chrome", "Firefox", "Edge", "Brave", "Opera", "Safari"]
        browser_map = {
            "ไม่ใช้ Cookie": None, "Chrome": "chrome", "Firefox": "firefox",
            "Edge": "edge", "Brave": "brave", "Opera": "opera", "Safari": "safari",
        }
        current_src = self.config.get("cookie_source", None)
        current_display = next((k for k, v in browser_map.items() if v == current_src), "ไม่ใช้ Cookie")
        self._cookie_browser_var = tk.StringVar(value=current_display)

        def _on_browser_cookie_change(choice):
            src = browser_map.get(choice)
            self.config["cookie_source"] = src
            self._save_config()

        ctk.CTkOptionMenu(
            bcrow, values=browser_options, variable=self._cookie_browser_var,
            command=_on_browser_cookie_change, font=FONT_SM,
            fg_color=SURFACE2, button_color=PRIMARY, button_hover_color=PRIMARY_HV, width=140,
        ).pack(side="left", padx=10)

        # Manual cookies.txt file row
        fcrow = ctk.CTkFrame(cc, fg_color="transparent")
        fcrow.pack(fill="x", padx=18, pady=(0, 14))
        _label(fcrow, "หรือไฟล์ cookies.txt:", font=FONT_XS, color=MUTED).pack(side="left")
        self._cookie_file_var = tk.StringVar(value=self.config.get("cookie_file", "") or "")
        ctk.CTkEntry(
            fcrow, textvariable=self._cookie_file_var, state="readonly", font=FONT_SM,
            fg_color=SURFACE2, border_color=BORDER, height=32, corner_radius=8,
        ).pack(side="left", fill="x", expand=True, padx=8)

        def _browse_cookie_file():
            from tkinter import filedialog as _fd
            p = _fd.askopenfilename(filetypes=[("Cookie files", "*.txt"), ("All files", "*.*")])
            if p:
                self._cookie_file_var.set(p)
                self.config["cookie_file"] = p
                self._save_config()

        def _clear_cookie_file():
            self._cookie_file_var.set("")
            self.config["cookie_file"] = None
            self._save_config()

        _btn(fcrow, "Browse", _browse_cookie_file, fg=PRIMARY, width=70, height=30).pack(side="left", padx=3)
        _btn(fcrow, "Clear", _clear_cookie_file, fg=SURFACE2, hv=ERROR, width=54, height=30).pack(side="left")

        return page

    def _browse_out(self):
        folder = filedialog.askdirectory()
        if folder:
            self.out_var.set(folder)
            self.config["outdir"] = folder
            self._save_config()

    def _set_live_accent(self, color, hover):
        self.accent_color = color
        self.accent_hv = hover
        self.config["accent"] = color
        self._save_config()

        # Update accent across running UI widgets
        self.logo_title.configure(text_color=color)
        self.bar_play_btn.configure(fg_color=color, hover_color=hover)
        self.bar_seek_slider.configure(progress_color=color, button_hover_color=color)
        if getattr(self.player, "is_shuffle", False):
            self.bar_shuffle_btn.configure(text_color=color)
        if getattr(self.player, "repeat_mode", "off") in ("all", "one"):
            self.bar_repeat_btn.configure(text_color=color)
        if hasattr(self, "visualizer"):
            self.visualizer.set_color(color)
        self._switch_tab(self._active_tab.get())

    def _set_live_language(self, lang_code):
        self.lang = lang_code
        self.config["lang"] = lang_code
        self._save_config()

        # Refresh titles and buttons
        self.lbl_search_title.configure(text=self.t("Search & Download"))
        self.lbl_search_sub.configure(text=self.t("Search_Sub"))
        self.lbl_results_header.configure(text=self.t("Results"))
        self.lbl_queue_title.configure(text=self.t("Download Queue"))
        self.lbl_queue_sub.configure(text=self.t("Queue_Sub"))
        self.lbl_lib_title.configure(text=self.t("Library"))
        self.lbl_set_title.configure(text=self.t("Settings_Title"))
        self.lbl_set_sub.configure(text=self.t("Settings_Sub"))
        self.lbl_fmt_card.configure(text=self.t("Default Format"))
        self.lbl_opts_card.configure(text=self.t("Download Options"))
        self.lbl_theme_card.configure(text=self.t("Theme Accent Color"))
        self.lbl_lang_card.configure(text=self.t("Language"))
        self.lbl_out_card.configure(text=self.t("Output Folder"))
        self._switch_tab(self._active_tab.get())

    # ── Engine Health & Self-Healing Engine ────────────────────────────────────
    def _check_engine(self, manual=False):
        self._engine_busy = True
        def _set_status(msg, color=TEXT):
            self.safe_after(0, lambda: self.status_var.set(msg))
            self.safe_after(0, lambda: self.engine_dot.configure(text=f"● Engine: {msg[:26]}", text_color=color))

        try:
            import nexus_doctor
            nexus_doctor.register_bin_in_path()
            if not os.path.exists(self.ytdlp) or not os.path.exists(self.ffmpeg):
                _set_status("Healing missing tools…", WARN)
                nexus_doctor.heal_all_dependencies(lambda m: _set_status(f"Doctor: {m[:22]}", WARN))
                self.ytdlp = nexus_doctor.find_binary("yt-dlp") or self.ytdlp
                self.ffmpeg = nexus_doctor.find_binary("ffmpeg") or self.ffmpeg
                self.ffprobe = nexus_doctor.find_binary("ffprobe") or self.ffprobe
        except Exception:
            pass

        _set_status("Checking yt-dlp & ffmpeg…", WARN)

        # 1. yt-dlp Check & Update
        if os.path.exists(self.ytdlp) and not is_valid_binary(self.ytdlp, min_size=500_000):
            try:
                os.remove(self.ytdlp)
            except Exception:
                pass

        if not os.path.exists(self.ytdlp):
            _set_status("Downloading yt-dlp…", WARN)
            try:
                dl_url = (
                    "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
                    if self.is_win
                    else "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
                )
                r = safe_http_get(dl_url, timeout=60, max_retries=3)
                if r and r.status_code == 200 and len(r.content) >= 500_000:
                    is_ok = True
                    if self.is_win and r.content[:2] != b"MZ":
                        is_ok = False
                    if is_ok:
                        tmp_ytdlp = self.ytdlp + ".tmp"
                        with open(tmp_ytdlp, "wb") as f:
                            f.write(r.content)
                        if not self.is_win:
                            os.chmod(tmp_ytdlp, 0o755)
                        os.replace(tmp_ytdlp, self.ytdlp)
                    else:
                        raise ValueError("Invalid yt-dlp executable payload received.")
                else:
                    raise IOError("Failed to retrieve valid yt-dlp binary.")
            except Exception as e:
                _set_status(f"yt-dlp dl error: {e}", ERROR)
                self._engine_busy = False
                return
        else:
            # Self-update yt-dlp if existing
            try:
                ver_proc = run_external_tool([self.ytdlp, "--version"], label="yt-dlp version check", check=False)
                cur_ver = ver_proc.stdout.strip()
                self._ytdlp_ver_str = cur_ver
                if manual:
                    _set_status("Running yt-dlp self-update…", WARN)
                    run_external_tool([self.ytdlp, "-U"], label="yt-dlp self-update", check=False)
            except Exception:
                pass

        # 2. ffmpeg & ffprobe Check & Download
        for f_bin in (self.ffmpeg, self.ffprobe):
            if os.path.exists(f_bin) and not is_valid_binary(f_bin, min_size=1_000_000):
                try:
                    os.remove(f_bin)
                except Exception:
                    pass

        if not os.path.exists(self.ffmpeg) or not os.path.exists(self.ffprobe):
            _set_status("Downloading FFmpeg (~35MB)…", WARN)
            try:
                import tarfile
                import zipfile
                api_url = "https://api.github.com/repos/yt-dlp/FFmpeg-Builds/releases/latest"
                resp = safe_json_response(safe_http_get(api_url, timeout=12, max_retries=2), default={})

                if self.is_win: asset_name = "ffmpeg-master-latest-win64-gpl.zip"
                elif self.is_mac: asset_name = "ffmpeg-master-latest-mac64-gpl.zip"
                else: asset_name = "ffmpeg-master-latest-linux64-gpl.tar.xz"

                asset = next((a for a in resp.get("assets", []) if a.get("name") == asset_name), None)
                dl_url = asset["browser_download_url"] if asset else f"https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/{asset_name}"

                r = safe_http_get(dl_url, timeout=180, max_retries=3)
                if r and r.status_code == 200 and len(r.content) >= 5_000_000:
                    if asset_name.endswith(".zip"):
                        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                            for entry in z.namelist():
                                base_n = os.path.basename(entry)
                                if base_n.lower() in ("ffmpeg.exe", "ffprobe.exe", "ffplay.exe"):
                                    dest = os.path.join(self.appdata_dir, base_n)
                                    tmp_dest = dest + ".tmp"
                                    with open(tmp_dest, "wb") as f_out:
                                        f_out.write(z.read(entry))
                                    if is_valid_binary(tmp_dest, min_size=1_000_000):
                                        os.replace(tmp_dest, dest)
                                    else:
                                        if os.path.exists(tmp_dest):
                                            try: os.remove(tmp_dest)
                                            except Exception: pass
                    else:
                        with tarfile.open(fileobj=io.BytesIO(r.content), mode="r:xz") as t:
                            for member in t.getmembers():
                                base_n = os.path.basename(member.name)
                                if base_n in ("ffmpeg", "ffprobe", "ffplay"):
                                    dest = os.path.join(self.appdata_dir, base_n)
                                    tmp_dest = dest + ".tmp"
                                    with open(tmp_dest, "wb") as f_out:
                                        f_out.write(t.extractfile(member).read())
                                    os.chmod(tmp_dest, 0o755)
                                    if is_valid_binary(tmp_dest, min_size=1_000_000):
                                        os.replace(tmp_dest, dest)
                                    else:
                                        if os.path.exists(tmp_dest):
                                            try: os.remove(tmp_dest)
                                            except Exception: pass
                else:
                    raise IOError("Failed to retrieve valid FFmpeg archive.")

            except Exception as e:
                _set_status(f"FFmpeg error: {e}", ERROR)
                self._engine_busy = False
                return

        _set_status(f"Ready ({self._ytdlp_ver_str})", SUCCESS)
        self.safe_after(0, lambda: self.engine_details_lbl.configure(text=f"yt-dlp: {self._ytdlp_ver_str}  ·  ffmpeg: Ready"))
        self._engine_busy = False

    # ── App Auto-Update ───────────────────────────────────────────────────────
    def _check_app_update(self):
        try:
            resp = safe_http_get(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest", timeout=8, max_retries=2)
            data = safe_json_response(resp, default={})
            latest = data.get("tag_name", "").lstrip("v")
            if not latest or latest == VERSION:
                return

            asset_name = "NexusTube.exe" if self.is_win else "NexusTube"
            asset = next((a for a in data.get("assets", []) if a.get("name", "").lower() == asset_name.lower()), None)

            self._pending_update_url = asset["browser_download_url"] if asset else None
            self._pending_update_ver = latest
            self.safe_after(0, lambda: self._update_banner.pack(fill="x", pady=(4, 0)))
            self.safe_after(0, lambda v=latest: self._update_btn.configure(text=f"🔄 v{v} available!"))
        except Exception:
            pass

    def _do_app_update(self):
        ver = self._pending_update_ver or "?"
        if not self._exe_path or not self._pending_update_url:
            messagebox.showinfo("Update available", f"New version v{ver} is available!\nhttps://github.com/{GITHUB_REPO}/releases/latest")
            return
        if not messagebox.askyesno("Update NexusTube", f"Found v{ver} — download update and restart now?"):
            return
        threading.Thread(target=self._apply_update, daemon=True).start()

    def _apply_update(self):
        try:
            self.safe_after(0, lambda: self._update_btn.configure(text="Downloading…", state="disabled"))
            tmp_exe = self._exe_path + ".new"
            with requests.get(self._pending_update_url, stream=True, timeout=120, headers={"User-Agent": "NexusTube-App"}) as r:
                if r.status_code != 200:
                    raise IOError(f"Update download returned status {r.status_code}")
                total = int(r.headers.get("content-length", 0))
                written = 0
                with open(tmp_exe, "wb") as f:
                    for chunk in r.iter_content(65536):
                        f.write(chunk)
                        written += len(chunk)
                        if total:
                            pct = written / total * 100
                            self.safe_after(0, lambda p=pct: self.status_var.set(f"Downloading update… {p:.0f}%"))

            if not is_valid_binary(tmp_exe, min_size=5_000_000):
                if os.path.exists(tmp_exe):
                    try:
                        os.remove(tmp_exe)
                    except Exception:
                        pass
                raise ValueError("Downloaded update is corrupt or incomplete.")

            if self.is_win:
                bat = self._exe_path + ".update.bat"
                lines = [
                    "@echo off",
                    "timeout /t 2 /nobreak >nul",
                    f'move /y "{tmp_exe}" "{self._exe_path}"',
                    f'start "" "{self._exe_path}"',
                    'del "%~f0"',
                    "",
                ]
                with open(bat, "w") as f:
                    f.write("\n".join(lines))
                subprocess.Popen(["cmd", "/c", bat], creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                sh = self._exe_path + ".update.sh"
                lines = [
                    "#!/bin/bash",
                    "sleep 2",
                    f'mv "{tmp_exe}" "{self._exe_path}"',
                    f'chmod +x "{self._exe_path}"',
                    f'"{self._exe_path}" &',
                    'rm "$0"',
                ]
                with open(sh, "w") as f:
                    f.write("\n".join(lines))
                os.chmod(sh, 0o755)
                subprocess.Popen([sh])

            self.safe_after(0, self.destroy)
        except Exception as e:
            err_msg = str(e)
            self.safe_after(0, lambda msg=err_msg: messagebox.showerror("Update failed", msg))
            self.safe_after(0, lambda: self._update_btn.configure(text="🔄 Retry", state="normal"))


# ── Native Python-JS Bridge for Ultra-Modern pywebview Client ────────────────
class NexusBridgeAPI:
    """
    Exposes full application backend to the modern HTML/Tailwind/JS webview frontend.
    Handles YouTube search, multi-platform URL resolving, background download worker,
    real-time progress updates, in-app playback, 5-band studio EQ DSP, synced lyrics,
    audio trimmer, and self-healing engine integrity.
    """
    def __init__(self, window=None, auto_check=True, config_path=None):
        self._window = window
        self.is_win = sys.platform == "win32"
        self.is_mac = sys.platform == "darwin"
        self.exe_ext = ".exe" if self.is_win else ""

        if getattr(sys, "frozen", False):
            self.base_dir = sys._MEIPASS
            self._exe_path = sys.executable
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
            self._exe_path = None

        appdata_base = os.getenv("APPDATA") or os.path.expanduser("~")
        self.appdata_dir = (
            os.path.join(appdata_base, "YTDownloaderPro")
            if self.is_win
            else os.path.join(appdata_base, ".NexusTube")
        )
        try:
            os.makedirs(self.appdata_dir, exist_ok=True)
        except Exception:
            self.appdata_dir = os.path.join(tempfile.gettempdir(), "NexusTube")
            try:
                os.makedirs(self.appdata_dir, exist_ok=True)
            except Exception:
                pass

        self.config_path = config_path or os.path.join(self.appdata_dir, "config.json")
        self.config = {
            "accent": "#22C55E",
            "lang": "th",
            "format": "mp3_320",
            "embed_thumb": True,
            "embed_meta": True,
            "embed_lyrics": False,
            "sponsorblock": "sponsor",
            "normalize": False,
            "eq_preset": "Flat",
            "eq_bands": {"bass": 0.0, "low_mid": 0.0, "mid": 0.0, "high_mid": 0.0, "treble": 0.0},
            "dsp_effects": {"preamp": 0.0, "bass_boost": 0.0, "surround": False},
            "favorites": [],
            "library_view": "grid",
            "recent_searches": [],
            "outdir": os.path.join(os.path.expanduser("~"), "Downloads", "NexusTube"),
            "discord_rpc": True,
            "global_hotkeys": True,
            "system_tray": True,
            "minimize_to_tray": False,
        }
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.config.update(json.load(f))
            except Exception:
                pass

        # Cookie source config: None, 'chrome', 'firefox', 'edge', 'brave', 'opera', 'safari', หรือ path ไปยัง cookies.txt
        self._cookie_source = self.config.get("cookie_source", None)  # ชื่อ browser หรือ None
        self._cookie_file   = self.config.get("cookie_file", None)    # path ของ cookies.txt หรือ None

        self.ffmpeg  = get_binary_path(self.appdata_dir, "ffmpeg",  self.exe_ext)
        self.ffprobe = get_binary_path(self.appdata_dir, "ffprobe", self.exe_ext)
        self.ffplay  = get_binary_path(self.appdata_dir, "ffplay",  self.exe_ext)
        self.ytdlp   = get_binary_path(self.appdata_dir, "yt-dlp",  self.exe_ext)


        self.executor = ThreadPoolExecutor(max_workers=5)
        self.player = AudioPlayer(ffmpeg_bin=self.ffmpeg)
        self.player.normalize_audio = bool(self.config.get("normalize", False))

        if self.config.get("eq_preset") in EQ_PRESETS:
            self.player.set_eq_preset(self.config["eq_preset"])
        elif "eq_bands" in self.config:
            self.player.set_eq_bands(self.config["eq_bands"])

        if "dsp_effects" in self.config and isinstance(self.config["dsp_effects"], dict):
            self.player.set_dsp_effects(self.config["dsp_effects"])

        # Discord Rich Presence (RPC)
        try:
            self.discord_rpc = DiscordRPC(enabled=bool(self.config.get("discord_rpc", True)))
            if auto_check and self.discord_rpc.enabled:
                threading.Thread(target=self.discord_rpc.connect, daemon=True).start()
        except Exception:
            self.discord_rpc = DiscordRPC(enabled=False)

        # Global Media Hotkeys
        try:
            hotkey_cbs = {
                "play_pause": lambda: self.player_control("play_pause"),
                "next": lambda: self.player_control("next"),
                "prev": lambda: self.player_control("prev"),
                "stop": lambda: self.player_control("stop"),
                "toggle_mini": lambda: self.toggle_mini_player(),
            }
            self.hotkeys = GlobalMediaHotkeys(callbacks=hotkey_cbs, enabled=bool(self.config.get("global_hotkeys", True)))
            if auto_check and self.hotkeys.enabled:
                self.hotkeys.start()
        except Exception:
            self.hotkeys = GlobalMediaHotkeys(enabled=False)

        # Windows System Tray
        try:
            tray_ico = os.path.join(self.base_dir, "icon.ico")
            if not os.path.exists(tray_ico):
                tray_ico = os.path.join(self.base_dir, "NexusTube by herlove.ico")
            self.tray = SystemTrayIcon(
                icon_path=tray_ico,
                tooltip="NexusTube — Next-Gen Music Suite",
                on_restore=self._restore_from_tray,
                on_action=self._handle_tray_action,
                enabled=bool(self.config.get("system_tray", True)),
            )
            if auto_check and self.tray.enabled:
                self.tray.start()
        except Exception:
            self.tray = SystemTrayIcon(enabled=False)

        # Sleep Timer state & audio fade-out engine
        self._sleep_timer_lock = threading.Lock()
        self._sleep_timer_thread = None
        self._sleep_timer_active = False
        self._sleep_timer_mode = None
        self._sleep_timer_end = 0.0
        self._sleep_timer_fade_sec = 30
        self._sleep_timer_fading = False
        self._sleep_timer_id = 0
        self._orig_volume = self.player.volume

        # Mini-Player state
        self._is_mini_player = False
        self._prev_window_size = (1280, 840)
        self._prev_window_pos = (None, None)
        self._was_maximized_before_mini = False

        self.active_tasks = {}
        self._engine_busy = False
        self._ytdlp_ver_str = "Checking..."
        self._preview_stop_timer = None
        self._stream_proc = None
        self._pending_update_url = None
        self._pending_update_ver = None
        self._is_maximized = False

        if auto_check:
            threading.Thread(target=self._check_engine, daemon=True).start()
            threading.Thread(target=self._check_app_update, daemon=True).start()

    def _get_window(self):
        """Safely retrieves the underlying webview.Window instance without triggering reflection recursion."""
        return getattr(self, "_window", None)

    def __getattr__(self, name):
        if name == "window":
            return getattr(self, "_window", None)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def __setattr__(self, name, value):
        if name == "window":
            object.__setattr__(self, "_window", value)
        else:
            object.__setattr__(self, name, value)

    def __dir__(self):
        attrs = set(super().__dir__())
        attrs.discard("window")
        return sorted(attrs)

    @staticmethod
    def _is_same_path(p1, p2):
        if not p1 or not p2:
            return False
        try:
            return os.path.normcase(os.path.normpath(os.path.abspath(p1))) == os.path.normcase(os.path.normpath(os.path.abspath(p2)))
        except Exception:
            return p1 == p2

    def get_clipboard(self):
        """Cross-platform clipboard reader with zero modal popup and 64-bit safety."""
        if self.is_win:
            try:
                import ctypes
                from ctypes import wintypes
                CF_UNICODETEXT = 13
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32

                user32.OpenClipboard.argtypes = [wintypes.HWND]
                user32.OpenClipboard.restype = wintypes.BOOL
                user32.CloseClipboard.argtypes = []
                user32.CloseClipboard.restype = wintypes.BOOL
                user32.GetClipboardData.argtypes = [wintypes.UINT]
                user32.GetClipboardData.restype = wintypes.HANDLE
                kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
                kernel32.GlobalLock.restype = ctypes.c_wchar_p
                kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
                kernel32.GlobalUnlock.restype = wintypes.BOOL

                if user32.OpenClipboard(None):
                    try:
                        h_clip = user32.GetClipboardData(CF_UNICODETEXT)
                        if h_clip:
                            text = kernel32.GlobalLock(h_clip)
                            if text:
                                try:
                                    return str(text)
                                finally:
                                    kernel32.GlobalUnlock(h_clip)
                    finally:
                        user32.CloseClipboard()
            except Exception:
                pass
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            txt = root.clipboard_get()
            root.destroy()
            return txt or ""
        except Exception:
            return ""

    def _save_config(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # ── Cookie / Authentication JS API ──────────────────────────────────────────

    def get_cookie_config(self):
        """คืน cookie configuration ปัจจุบัน สำหรับ JS settings UI"""
        return {
            "source": self._cookie_source,
            "file": self._cookie_file,
            "browsers": ["chrome", "firefox", "edge", "brave", "opera", "safari", "chromium"],
        }

    def set_cookie_source(self, source):
        """กำหนด browser cookie source.  ส่ง None หรือ empty string เพื่อปิดใช้งาน"""
        self._cookie_source = source or None
        self.config["cookie_source"] = self._cookie_source
        self._cookie_file = None          # browser source override ไฟล์
        self.config["cookie_file"] = None
        self._save_config()
        return {"ok": True}

    def set_cookie_file(self, path):
        """กำหนด path ไปยัง cookies.txt. ส่ง None หรือ empty string เพื่อปิดใช้งาน"""
        self._cookie_file = path or None
        self.config["cookie_file"] = self._cookie_file
        self._cookie_source = None        # ไฟล์ override browser source
        self.config["cookie_source"] = None
        self._save_config()
        return {"ok": True}

    def clear_cookies(self):
        """ปิดใช้งาน cookie sources ทั้งหมด"""
        self._cookie_source = None
        self._cookie_file = None
        self.config["cookie_source"] = None
        self.config["cookie_file"] = None
        self._save_config()
        return {"ok": True}

    def _image_to_base64(self, im):
        if not im:
            return ""
        try:
            buf = io.BytesIO()
            im.convert("RGB").save(buf, format="JPEG", quality=80)
            return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception:
            return ""

    def get_initial_state(self):
        return {
            "version": VERSION,
            "config": self.config,
            "locales": LOCALES,
            "accents": ACCENT_PALETTE,
            "eq_presets": EQ_PRESETS,
            "eq_bands": getattr(self.player, "current_eq_bands", {}),
            "dsp_effects": getattr(self.player, "dsp_effects", {"preamp": 0.0, "bass_boost": 0.0, "surround": False}),
            "favorites": self.config.get("favorites", []),
            "recent_searches": self.config.get("recent_searches", []),
            "engine_status": self.get_engine_status(),
            "discord_rpc": self.get_discord_rpc_status(),
            "sleep_timer": self.get_sleep_timer_state(),
            "mini_player": getattr(self, "_is_mini_player", False),
            "normalize": getattr(self.player, "normalize_audio", False),
        }

    def get_engine_status(self):
        ytdlp_ok = bool(os.path.exists(self.ytdlp) or shutil.which("yt-dlp"))
        ffmpeg_ok = bool(os.path.exists(self.ffmpeg) or shutil.which("ffmpeg"))
        ffprobe_ok = bool(os.path.exists(self.ffprobe) or shutil.which("ffprobe"))
        ffplay_ok = bool(os.path.exists(self.ffplay) or shutil.which("ffplay"))
        return {
            "ytdlp_ready": ytdlp_ok,
            "ytdlp_version": self._ytdlp_ver_str,
            "ffmpeg_ready": ffmpeg_ok,
            "ffprobe_ready": ffprobe_ok,
            "ffplay_ready": ffplay_ok,
        }

    def search_youtube(self, query):
        if not query:
            return []
        ytdlp_bin = self.ytdlp if os.path.exists(self.ytdlp) else (shutil.which("yt-dlp") or self.ytdlp)
        cmd = [
            ytdlp_bin, "--dump-json", "--flat-playlist", "--no-warnings",
            f"ytsearch12:{query}"
        ]
        try:
            res = run_external_tool(cmd, label="NexusBridge yt search", check=False)
            items = []
            for line in res.stdout.splitlines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    thumbs = data.get("thumbnails", [])
                    t_url = thumbs[-1]["url"] if thumbs else data.get("thumbnail", "")
                    items.append({
                        "id": data.get("id"),
                        "title": data.get("title") or "Unknown Title",
                        "channel": data.get("uploader") or data.get("channel") or "",
                        "duration": data.get("duration") or 0,
                        "thumbnail": t_url,
                        "url": data.get("url") or data.get("webpage_url") or f"https://www.youtube.com/watch?v={data.get('id')}",
                    })
                except Exception:
                    pass
            return items
        except Exception as e:
            print(f"[NexusBridge] Search error: {e}")
            return []

    def resolve_url(self, url):
        plat, p_type, ident = detect_platform_url(url)
        if plat in ("spotify", "apple_music", "soundcloud"):
            meta = resolve_multiplatform_url(url, ytdlp_bin=self.ytdlp)
            meta["platform"] = plat
            meta["type"] = p_type
            if meta.get("tracks") and len(meta["tracks"]) == 1:
                trk = meta["tracks"][0]
                meta["search_query"] = trk.get("search_query") or f"{trk.get('artist', '')} - {trk.get('title', '')}".strip()
                if not meta.get("thumbnail") and trk.get("thumbnail"):
                    meta["thumbnail"] = trk.get("thumbnail")
            return meta

        if plat == "youtube":
            ytdlp_bin = self.ytdlp if os.path.exists(self.ytdlp) else (shutil.which("yt-dlp") or self.ytdlp)
            cmd = [ytdlp_bin, "--dump-json", "--flat-playlist", "--no-warnings", url]
            try:
                res = run_external_tool(cmd, label="NexusBridge resolve URL", check=False)
                lines = [l for l in res.stdout.splitlines() if l.strip()]
                if len(lines) > 1 or p_type == "playlist":
                    tracks = []
                    for idx, line in enumerate(lines, 1):
                        try:
                            d = json.loads(line)
                            tracks.append({
                                "track_num": idx,
                                "title": d.get("title") or f"Track {idx}",
                                "artist": d.get("uploader") or d.get("channel") or "",
                                "duration": d.get("duration") or 0,
                                "url": d.get("url") or d.get("webpage_url") or f"https://www.youtube.com/watch?v={d.get('id')}",
                            })
                        except Exception:
                            pass
                    return {
                        "platform": "youtube",
                        "type": "playlist",
                        "title": f"YouTube Playlist ({len(tracks)} tracks)",
                        "cover": tracks[0].get("thumbnail") if tracks else "",
                        "tracks": tracks,
                    }
                elif lines:
                    d = json.loads(lines[0])
                    thumbs = d.get("thumbnails", [])
                    t_url = thumbs[-1]["url"] if thumbs else d.get("thumbnail", "")
                    return {
                        "platform": "youtube",
                        "type": "video",
                        "title": d.get("title") or "YouTube Video",
                        "artist": d.get("uploader") or d.get("channel") or "",
                        "duration": d.get("duration") or 0,
                        "thumbnail": t_url,
                        "url": url,
                    }
            except Exception as e:
                print(f"[NexusBridge] YouTube resolve error: {e}")
        return {"platform": plat, "type": p_type, "url": url, "title": url}

    def add_to_queue(self, url, title="", fmt_choice="mp3_320", options=None, metadata=None):
        plat, p_type, ident = detect_platform_url(url)
        resolved_url = url
        resolved_title = title
        resolved_meta = dict(metadata) if metadata else {}

        if plat in ("spotify", "apple_music"):
            try:
                meta_res = resolve_multiplatform_url(url, ytdlp_bin=self.ytdlp)
                tracks = meta_res.get("tracks", [])
                if tracks:
                    trk = tracks[0]
                    sq = trk.get("search_query") or f"{trk.get('artist', '')} - {trk.get('title', '')}".strip()
                    resolved_url = f"ytsearch1:{sq}"
                    if not resolved_title or resolved_title == url:
                        resolved_title = trk.get("title") or meta_res.get("title") or sq
                    if "title" not in resolved_meta:
                        resolved_meta["title"] = trk.get("title") or resolved_title
                    if "artist" not in resolved_meta:
                        resolved_meta["artist"] = trk.get("artist") or meta_res.get("artist", "")
                    if "album" not in resolved_meta:
                        resolved_meta["album"] = trk.get("album") or meta_res.get("title", "NexusTube Collection")
                    if "thumbnail" not in resolved_meta:
                        resolved_meta["thumbnail"] = trk.get("thumbnail") or meta_res.get("thumbnail", "")
                    if "track_num" not in resolved_meta:
                        resolved_meta["track_num"] = trk.get("track_num", 1)
            except Exception as ex:
                print(f"[NexusBridge] Auto-resolve for {plat} failed: {ex}")

        thumb = resolved_meta.get("thumbnail", "")
        if not thumb:
            yt_m = re.search(r"(?:v=|\/|embed\/|shorts\/)([0-9A-Za-z_-]{11})", url)
            if yt_m:
                thumb = f"https://i.ytimg.com/vi/{yt_m.group(1)}/mqdefault.jpg"

        task_id = f"task_{int(time.time() * 1000)}_{len(self.active_tasks)}"
        task = {
            "id": task_id,
            "url": resolved_url,
            "title": resolved_title or resolved_url,
            "override_fmt": fmt_choice,
            "options": options or {},
            "metadata": resolved_meta,
            "thumbnail": thumb,
            "status": "waiting",
            "percent": 0.0,
            "speed": "",
            "eta": "",
            "proc": None,
            "cancelled": False,
            "out_file": None,
        }
        self.active_tasks[task_id] = task
        self.executor.submit(self._download_worker, task)
        return {"task_id": task_id}

    def get_queue_state(self):
        tasks = []
        for t in list(self.active_tasks.values()):
            tasks.append({
                "id": t["id"],
                "url": t["url"],
                "title": t["title"],
                "format": t.get("override_fmt", ""),
                "status": t["status"],
                "percent": t["percent"],
                "speed": t["speed"],
                "eta": t["eta"],
                "thumbnail": t.get("thumbnail", ""),
                "out_file": t["out_file"],
                "error": t.get("error"),
                "warning": t.get("warning"),
            })
        return tasks

    def cancel_task(self, task_id):
        task = self.active_tasks.get(task_id)
        if not task:
            return False
        task["cancelled"] = True
        proc = task.get("proc")
        if proc:
            try:
                proc.terminate()
                proc.kill()
            except Exception:
                pass
        task["status"] = "cancelled"
        return True

    def retry_task(self, task_id):
        task = self.active_tasks.get(task_id)
        if not task:
            return False
        task["cancelled"] = False
        task["status"] = "waiting"
        task["percent"] = 0.0
        task["speed"] = ""
        task["eta"] = ""
        task["error"] = None
        self.executor.submit(self._download_worker, task)
        return True

    def clear_finished(self):
        to_remove = [tid for tid, t in self.active_tasks.items() if t["status"] in ("completed", "cancelled", "failed")]
        for tid in to_remove:
            self.active_tasks.pop(tid, None)
        return True

    def get_library(self, query="", sort_by="date"):
        outdir = self.config.get("outdir") or os.path.join(os.path.expanduser("~"), "Downloads", "NexusTube")
        if not os.path.exists(outdir):
            return []

        media_exts = (".mp3", ".m4a", ".wav", ".flac", ".opus", ".ogg", ".aac", ".mp4", ".mkv", ".webm")
        files = []
        try:
            for f in os.listdir(outdir):
                if f.startswith(".") or f.endswith((".part", ".ytdl", ".lrc", ".jpg", ".png", ".webp", ".json", ".txt")):
                    continue
                p = os.path.join(outdir, f)
                if os.path.isfile(p) and f.lower().endswith(media_exts):
                    files.append(p)
        except Exception:
            return []

        items = []
        q_lower = query.lower().strip()
        favs = list(self.config.get("favorites", []))
        for p in files:
            info = get_media_info(p)
            t = info.get("title", "")
            a = info.get("artist", "")
            if q_lower and (q_lower not in t.lower() and q_lower not in a.lower()):
                continue

            cover_b64 = ""
            if info.get("cover_image"):
                cover_b64 = self._image_to_base64(info["cover_image"])

            ext = os.path.splitext(p)[1].lstrip(".").upper()
            mtime = os.path.getmtime(p) if os.path.exists(p) else 0
            is_fav = any(self._is_same_path(p, f_path) for f_path in favs)

            items.append({
                "path": p,
                "filename": os.path.basename(p),
                "title": t,
                "artist": a,
                "album": info.get("album", "NexusTube"),
                "duration": info.get("duration", 0),
                "size_bytes": info.get("size_bytes", 0),
                "format": ext,
                "mtime": mtime,
                "cover_base64": cover_b64,
                "is_favorite": is_fav,
            })

        if sort_by == "title":
            items.sort(key=lambda x: x["title"].lower())
        elif sort_by == "artist":
            items.sort(key=lambda x: x["artist"].lower())
        elif sort_by == "duration":
            items.sort(key=lambda x: x["duration"], reverse=True)
        elif sort_by == "size":
            items.sort(key=lambda x: x["size_bytes"], reverse=True)
        else:
            items.sort(key=lambda x: x["mtime"], reverse=True)

        return items

    def _dispatch_discord_sync(self):
        """Dispatches Discord RPC synchronization in a non-blocking daemon thread."""
        try:
            threading.Thread(target=self._sync_discord_presence, daemon=True).start()
        except Exception:
            pass

    def play_track(self, filepath):
        if not filepath or not os.path.exists(filepath):
            return None
        ok = self.player.load_and_play(filepath)
        if not ok:
            return None
        self._dispatch_discord_sync()
        info = dict(self.player.info)
        if info.get("cover_image"):
            info["cover_base64"] = self._image_to_base64(info["cover_image"])
            del info["cover_image"]
        return info

    def player_control(self, action, param=None):
        ret = False
        if action == "play_pause":
            ret = self.player.toggle_play_pause()
        elif action == "pause":
            ret = self.player.pause()
        elif action in ("resume", "play"):
            ret = self.player.resume()
        elif action == "set_speed":
            if param is not None:
                ret = self.player.set_speed(param)
            else:
                ret = getattr(self.player, "playback_speed", 1.0)
        elif action == "stop":
            self.player.stop()
            ret = True
        elif action == "seek":
            if param is not None:
                self.player.seek(float(param))
            ret = True
        elif action == "set_volume":
            if param is not None:
                vol = float(param)
                self.player.set_volume(vol)
                if vol > 0 and self.player.is_muted:
                    self.player.is_muted = False
            ret = True
        elif action == "toggle_mute":
            ret = self.player.toggle_mute()
        elif action == "toggle_repeat":
            if param in ("off", "all", "one"):
                self.player.repeat_mode = param
                ret = self.player.repeat_mode
            else:
                ret = self.player.toggle_repeat()
        elif action == "toggle_shuffle":
            if param is not None and isinstance(param, bool):
                self.player.is_shuffle = param
                ret = self.player.is_shuffle
            else:
                ret = self.player.toggle_shuffle()
        elif action in ("prev", "next"):
            lib = self.get_library()
            if not lib:
                return False
            if action == "prev" and self.player.get_pos() > 3.0:
                self.player.seek(0.0)
                self._dispatch_discord_sync()
                return True
            cur_p = self.player.current_path
            idx = 0
            for i, it in enumerate(lib):
                if self._is_same_path(it.get("path"), cur_p):
                    idx = i
                    break
            if action == "next" and getattr(self.player, "is_shuffle", False) and len(lib) > 1:
                import random
                candidates = [i for i in range(len(lib)) if i != idx]
                new_idx = random.choice(candidates)
            elif action == "next":
                new_idx = (idx + 1) % len(lib)
            else:
                new_idx = (idx - 1 + len(lib)) % len(lib)
            self.play_track(lib[new_idx]["path"])
            return True

        if action in ("play_pause", "pause", "resume", "play", "stop", "seek"):
            self._dispatch_discord_sync()
        return ret

    def window_control(self, action):
        """Handle frameless window titlebar controls: minimize, maximize (toggle restore), close."""
        win = self._get_window()
        if not win:
            return False
        try:
            if action == "minimize":
                win.minimize()
                return True
            elif action == "maximize":
                is_max = getattr(self, "_is_maximized", False)
                if is_max:
                    win.restore()
                    self._is_maximized = False
                else:
                    win.maximize()
                    self._is_maximized = True
                return True
            elif action == "close":
                if bool(self.config.get("minimize_to_tray", False)):
                    return self.minimize_to_tray()
                self.cleanup()
                win.destroy()
                return True
        except Exception as e:
            print(f"[NexusBridge] window_control error: {e}")
            return False
        return False

    def get_player_state(self):
        # Auto-detect track finish for repeat / playlist progression (looplist)
        if self.player.is_playing and not self.player.is_paused and getattr(self.player, "_initialized", False):
            try:
                import pygame
                if not pygame.mixer.music.get_busy():
                    if self.player.repeat_mode == "one" and self.player.current_path:
                        self.player.load_and_play(self.player.current_path, 0.0)
                    elif self.player.repeat_mode == "all":
                        # Loop list (playlist repeat all)
                        self.player_control("next")
                    else:
                        # Repeat off: progress through playlist/library until end of list
                        lib = self.get_library()
                        if lib:
                            cur_p = self.player.current_path
                            idx = -1
                            for i, it in enumerate(lib):
                                if self._is_same_path(it.get("path"), cur_p):
                                    idx = i
                                    break
                            if idx != -1 and idx + 1 < len(lib):
                                if getattr(self.player, "is_shuffle", False) and len(lib) > 1:
                                    self.player_control("next")
                                else:
                                    self.play_track(lib[idx + 1]["path"])
                            else:
                                self.player.is_playing = False
                        else:
                            self.player.is_playing = False
            except Exception:
                pass

        info = dict(self.player.info) if hasattr(self.player, "info") else {}
        if info.get("cover_image"):
            info["cover_base64"] = self._image_to_base64(info["cover_image"])
            del info["cover_image"]

        return {
            "is_playing": self.player.is_playing,
            "is_paused": self.player.is_paused,
            "current_pos": self.player.get_pos(),
            "duration": info.get("duration", 0),
            "volume": self.player.volume,
            "is_muted": self.player.is_muted,
            "repeat_mode": self.player.repeat_mode,
            "is_shuffle": self.player.is_shuffle,
            "playback_speed": getattr(self.player, "playback_speed", 1.0),
            "info": info,
            "current_path": self.player.current_path,
            "sleep_timer": self.get_sleep_timer_state(),
            "mini_player": getattr(self, "_is_mini_player", False),
            "normalize": getattr(self.player, "normalize_audio", False),
        }

    def set_eq_preset(self, preset_name):
        self.player.set_eq_preset(preset_name)
        self.config["eq_preset"] = preset_name
        self.config["eq_bands"] = self.player.current_eq_bands
        self._save_config()
        return self.player.current_eq_bands

    def set_eq_bands(self, bands):
        self.player.set_eq_bands(bands)
        self.config["eq_preset"] = "Custom"
        self.config["eq_bands"] = self.player.current_eq_bands
        self._save_config()
        return self.player.current_eq_bands

    def set_dsp_effects(self, effects_or_preamp=None, bass_boost=None, surround=None):
        """Sets preamp gain, dynamic bass boost exciter, and 3D surround simulation."""
        if isinstance(effects_or_preamp, dict):
            effects = effects_or_preamp
        else:
            effects = {}
            if effects_or_preamp is not None:
                effects["preamp"] = float(effects_or_preamp)
            if bass_boost is not None:
                effects["bass_boost"] = float(bass_boost)
            if surround is not None:
                effects["surround"] = bool(surround)
        res = self.player.set_dsp_effects(effects)
        self.config["dsp_effects"] = self.player.dsp_effects
        self._save_config()
        return res

    def toggle_favorite(self, file_path):
        """Toggles favorite state for a track in library."""
        if not file_path:
            return False
        favs = list(self.config.get("favorites", []))
        norm_target = os.path.normpath(file_path)
        found = None
        for it in favs:
            if self._is_same_path(it, norm_target):
                found = it
                break
        if found:
            favs.remove(found)
            is_fav = False
        else:
            favs.append(norm_target)
            is_fav = True
        self.config["favorites"] = favs
        self._save_config()
        return is_fav

    def get_favorites(self):
        """Returns the list of favorited track paths."""
        return list(self.config.get("favorites", []))

    def convert_track(self, input_path, target_format, bitrate=None, normalize=False):
        """Converts local track into another audio format asynchronously."""
        return convert_audio_file(
            input_path=input_path,
            output_format=target_format,
            bitrate=bitrate,
            normalize=normalize,
            ffmpeg_bin=self.ffmpeg,
        )

    def export_library_playlist(self, playlist_name="NexusTube_Playlist", track_paths=None):
        """Exports library tracks or selected tracks into an M3U8 playlist file."""
        outdir = self.config.get("outdir") or os.path.join(os.path.expanduser("~"), "Downloads", "NexusTube")
        if not track_paths:
            lib = self.get_library()
            track_paths = [it["path"] for it in lib]
        res_file = export_m3u8_playlist(track_paths, playlist_name=playlist_name, output_dir=outdir)
        if res_file and os.path.exists(res_file):
            return {"success": True, "path": res_file, "playlist_name": playlist_name}
        return {"success": False, "error": "Export failed"}

    def batch_cancel_all(self):
        """Cancels all active or waiting download tasks and terminates running processes."""
        cancelled = 0
        for tid, task in list(self.active_tasks.items()):
            if task.get("status") in ("waiting", "downloading", "processing"):
                if self.cancel_task(tid):
                    cancelled += 1
        return cancelled

    # ── Discord Rich Presence (RPC) Bridge ──────────────────────────────────
    def get_discord_rpc_status(self):
        """Returns Discord RPC connectivity and enabled state."""
        return {
            "enabled": getattr(getattr(self, "discord_rpc", None), "enabled", False),
            "connected": getattr(getattr(self, "discord_rpc", None), "connected", False),
        }

    def toggle_discord_rpc(self, enabled=None):
        """Toggles Discord Rich Presence broadcast."""
        rpc = getattr(self, "discord_rpc", None)
        if enabled is None:
            enabled = not (rpc.enabled if rpc else False)
        enabled = bool(enabled)
        self.config["discord_rpc"] = enabled
        self._save_config()
        if rpc:
            rpc.enabled = enabled
            if enabled:
                threading.Thread(target=self._sync_discord_presence, daemon=True).start()
            else:
                rpc.clear_activity()
        return enabled

    def _sync_discord_presence(self):
        """Synchronizes current playback metadata and timestamps with Discord."""
        try:
            rpc = getattr(self, "discord_rpc", None)
            if not rpc or not rpc.enabled:
                return
            if not self.player.current_path:
                if getattr(rpc, "connected", False):
                    rpc.clear_activity()
                tray = getattr(self, "tray", None)
                if tray and getattr(tray, "enabled", False):
                    tray.update_tooltip("NexusTube — Next-Gen Music Suite")
                return

            info = getattr(self.player, "info", {}) or {}
            title = info.get("title") or os.path.basename(self.player.current_path or "")
            artist = info.get("artist") or "NexusTube"
            album = info.get("album") or "NexusTube Collection"
            dur = info.get("duration", 0)
            pos = self.player.get_pos()
            thumb = info.get("thumbnail_url") or ""

            rpc.update_playback(
                title=title,
                artist=artist,
                duration=dur,
                current_pos=pos,
                is_playing=self.player.is_playing,
                is_paused=self.player.is_paused,
                album=album,
                cover_url=thumb,
            )

            # Update system tray tooltip with current music
            tray = getattr(self, "tray", None)
            if tray and tray.enabled:
                tray.update_tooltip(f"NexusTube: {title[:50]} - {artist[:40]}")
        except Exception as ex:
            print(f"[NexusBridge] Discord sync error: {ex}")

    # ── Global Media Hotkeys & System Tray Bridge ───────────────────────────
    def toggle_global_hotkeys(self, enabled=None):
        """Enables or disables system-wide media keyboard shortcuts."""
        hotkeys = getattr(self, "hotkeys", None)
        if enabled is None:
            enabled = not (hotkeys.enabled if hotkeys else False)
        enabled = bool(enabled)
        self.config["global_hotkeys"] = enabled
        self._save_config()
        if hotkeys:
            hotkeys.set_enabled(enabled)
        return enabled

    def toggle_system_tray(self, enabled=None):
        """Enables or disables Windows system tray icon."""
        tray = getattr(self, "tray", None)
        if enabled is None:
            enabled = not (tray.enabled if tray else False)
        enabled = bool(enabled)
        self.config["system_tray"] = enabled
        self._save_config()
        if tray:
            tray.enabled = enabled
            if enabled:
                tray.start()
            else:
                tray.stop()
        return enabled

    def toggle_minimize_to_tray(self, enabled=None):
        """Toggles whether closing the window minimizes to tray instead of quitting."""
        if enabled is None:
            enabled = not bool(self.config.get("minimize_to_tray", False))
        enabled = bool(enabled)
        self.config["minimize_to_tray"] = enabled
        self._save_config()
        return enabled

    def minimize_to_tray(self):
        """Hides the main window to the system tray."""
        win = self._get_window()
        if not win:
            return False
        try:
            win.hide()
            return True
        except Exception:
            try:
                win.minimize()
                return True
            except Exception:
                return False

    def _restore_from_tray(self):
        """Restores window from system tray, cleanly exiting mini-player mode if active."""
        win = self._get_window()
        if win:
            try:
                win.show()
                if getattr(self, "_is_mini_player", False):
                    self.toggle_mini_player(False)
                else:
                    win.restore()
            except Exception:
                pass

    def _handle_tray_action(self, action):
        """Handles actions from tray context menu."""
        if action == "play_pause":
            self.player_control("play_pause")
        elif action == "next":
            self.player_control("next")
        elif action == "prev":
            self.player_control("prev")
        elif action == "exit":
            win = self._get_window()
            self.cleanup()
            if win:
                win.destroy()

    # ── Audio Loudness Normalization Bridge ─────────────────────────────────
    def toggle_normalization(self, enabled=None):
        """Toggles dynamic audio loudness normalization (EBU R128 / DynAudNorm)."""
        if enabled is None:
            enabled = not getattr(self.player, "normalize_audio", False)
        enabled = bool(enabled)
        res = self.player.set_normalization(enabled)
        self.config["normalize"] = res
        self._save_config()
        return res

    # ── Sleep Timer & Gradual Audio Fade-out ────────────────────────────────
    def set_sleep_timer(self, minutes_or_mode, fade_out_sec=30):
        """Configures sleep timer with gradual audio fade-out."""
        with self._sleep_timer_lock:
            self._sleep_timer_id += 1
            cur_id = self._sleep_timer_id
            self._sleep_timer_active = True
            self._sleep_timer_fade_sec = max(5, int(fade_out_sec))
            self._sleep_timer_fading = False
            self._orig_volume = self.player.volume

            if str(minutes_or_mode) == "end_of_track":
                self._sleep_timer_mode = "end_of_track"
                self._sleep_timer_end = 0.0
            else:
                try:
                    mins = float(minutes_or_mode)
                except Exception:
                    mins = 30.0
                self._sleep_timer_mode = f"{int(mins)}m"
                self._sleep_timer_end = time.time() + (mins * 60.0)

            self._sleep_timer_thread = threading.Thread(
                target=self._sleep_timer_worker, args=(cur_id,), daemon=True
            )
            self._sleep_timer_thread.start()

        return self.get_sleep_timer_state()

    def cancel_sleep_timer(self):
        """Cancels any running sleep timer and restores original volume."""
        with self._sleep_timer_lock:
            self._sleep_timer_active = False
            self._sleep_timer_mode = None
            self._sleep_timer_end = 0.0
            self._sleep_timer_id += 1
            if self._sleep_timer_fading or abs(self.player.volume - self._orig_volume) > 0.01:
                self.player.set_volume(self._orig_volume)
            self._sleep_timer_fading = False
        return self.get_sleep_timer_state()

    def get_sleep_timer_state(self):
        """Returns current sleep timer progress, remaining seconds, and fade-out state."""
        now = time.time()
        remaining = 0
        if self._sleep_timer_active and self._sleep_timer_mode != "end_of_track":
            remaining = max(0, int(self._sleep_timer_end - now))
        return {
            "active": self._sleep_timer_active,
            "mode": self._sleep_timer_mode,
            "remaining_seconds": remaining,
            "fading": self._sleep_timer_fading,
        }

    def _sleep_timer_worker(self, timer_id):
        """Background thread executing gradual audio fade-out and auto-stop."""
        while self._sleep_timer_active and self._sleep_timer_id == timer_id:
            now = time.time()
            if self._sleep_timer_mode == "end_of_track":
                dur = self.player.info.get("duration", 0) if hasattr(self.player, "info") else 0
                pos = self.player.get_pos()
                rem = (dur - pos) if dur > 0 else 999
                if rem <= self._sleep_timer_fade_sec and rem > 0:
                    self._sleep_timer_fading = True
                    fade_ratio = max(0.0, rem / float(self._sleep_timer_fade_sec))
                    self.player.set_volume(self._orig_volume * fade_ratio)
                if not self.player.is_playing or rem <= 0.5:
                    self.player_control("pause")
                    self.player.set_volume(self._orig_volume)
                    self._sleep_timer_active = False
                    self._sleep_timer_fading = False
                    break
            else:
                rem = self._sleep_timer_end - now
                if rem <= 0:
                    self.player_control("pause")
                    self.player.set_volume(self._orig_volume)
                    self._sleep_timer_active = False
                    self._sleep_timer_fading = False
                    break
                elif rem <= self._sleep_timer_fade_sec:
                    self._sleep_timer_fading = True
                    fade_ratio = max(0.0, rem / float(self._sleep_timer_fade_sec))
                    self.player.set_volume(self._orig_volume * fade_ratio)

            time.sleep(0.5)

    # ── Mini-Player / Picture-in-Picture Mode ──────────────────────────────
    def toggle_mini_player(self, enable=None, width=None, height=None, x=None, y=None, is_maximized=None):
        """Toggles compact floating mini-player mode with always-on-top window resizing and robust coordinate restoration."""
        win = self._get_window()
        if enable is None:
            enable = not self._is_mini_player
        enable = bool(enable)
        self._is_mini_player = enable

        if win:
            try:
                if enable:
                    try:
                        w = width or getattr(win, "width", 1280)
                        h = height or getattr(win, "height", 840)
                        if w and h and int(w) > 450 and int(h) > 300:
                            self._prev_window_size = (int(w), int(h))
                    except Exception:
                        pass

                    if x is not None and y is not None:
                        try:
                            self._prev_window_pos = (int(x), int(y))
                        except Exception:
                            pass

                    # Detect if window was maximized before entering mini-player
                    was_max = bool(is_maximized) or getattr(self, "_is_maximized", False)
                    if not was_max and hasattr(win, "uid"):
                        try:
                            from webview.platforms.winforms import BrowserView
                            bv = BrowserView.instances.get(win.uid)
                            if bv and getattr(bv, "WindowState", None) is not None:
                                if int(bv.WindowState) == 2:  # FormWindowState.Maximized
                                    was_max = True
                            elif bv and hasattr(bv, "Handle"):
                                if ctypes and ctypes.windll.user32.IsZoomed(bv.Handle.ToInt32()):
                                    was_max = True
                        except Exception:
                            pass

                    if was_max:
                        self._was_maximized_before_mini = True
                        try:
                            if hasattr(win, "restore"):
                                win.restore()
                            self._is_maximized = False
                        except Exception:
                            pass
                    else:
                        self._was_maximized_before_mini = False

                    win.resize(400, 230)
                    win.on_top = True
                else:
                    orig_w, orig_h = getattr(self, "_prev_window_size", (1280, 840)) or (1280, 840)
                    if not orig_w or not orig_h or orig_w < 600 or orig_h < 400:
                        orig_w, orig_h = 1280, 840

                    win.on_top = False

                    # Restore position safely onto desktop without off-screen clipping
                    orig_x, orig_y = getattr(self, "_prev_window_pos", (None, None)) or (None, None)
                    if orig_x is None or orig_y is None:
                        orig_x = x
                        orig_y = y

                    if orig_x is not None and orig_y is not None:
                        screen_w, screen_h = 1920, 1080
                        if sys.platform == "win32" and ctypes:
                            try:
                                sw = ctypes.windll.user32.GetSystemMetrics(0)
                                sh = ctypes.windll.user32.GetSystemMetrics(1)
                                if sw > 0 and sh > 0:
                                    screen_w, screen_h = sw, sh
                            except Exception:
                                pass
                        clamped_x = max(0, min(int(orig_x), screen_w - orig_w))
                        clamped_y = max(0, min(int(orig_y), screen_h - orig_h))
                        if hasattr(win, "move"):
                            try:
                                win.move(clamped_x, clamped_y)
                            except Exception:
                                pass

                    if getattr(self, "_was_maximized_before_mini", False):
                        try:
                            if hasattr(win, "restore"):
                                win.restore()
                            win.resize(orig_w, orig_h)
                            if hasattr(win, "maximize"):
                                win.maximize()
                            self._is_maximized = True
                        except Exception:
                            win.resize(orig_w, orig_h)
                        self._was_maximized_before_mini = False
                    else:
                        try:
                            if hasattr(win, "restore"):
                                win.restore()
                        except Exception:
                            pass
                        win.resize(orig_w, orig_h)
                        self._is_maximized = False

                try:
                    if hasattr(win, "evaluate_js"):
                        win.evaluate_js(f"if (window.syncMiniPlayerFromBackend) window.syncMiniPlayerFromBackend({str(enable).lower()});")
                except Exception:
                    pass
            except Exception as e:
                print(f"[NexusBridge] mini-player resize error: {e}")

        return {"mini_player": self._is_mini_player}

    def get_mini_player_state(self):
        """Returns current mini-player active state."""
        return {"mini_player": self._is_mini_player}

    # ── In-App yt-dlp One-Click Updater ─────────────────────────────────────
    def check_ytdlp_update(self):
        """Checks GitHub for newer releases of yt-dlp."""
        cur_ver = self._ytdlp_ver_str
        try:
            url = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
            resp = safe_http_get(url, timeout=8, max_retries=2)
            data = safe_json_response(resp, default={})
            latest_ver = data.get("tag_name", "").lstrip("v")
            notes = data.get("body", "")[:300] if data.get("body") else ""
            has_update = bool(latest_ver and cur_ver != latest_ver and "Checking" not in cur_ver)
            return {
                "current_version": cur_ver,
                "latest_version": latest_ver,
                "has_update": has_update,
                "release_notes": notes,
                "release_url": data.get("html_url", "https://github.com/yt-dlp/yt-dlp/releases/latest"),
            }
        except Exception as ex:
            return {
                "current_version": cur_ver,
                "latest_version": "Unknown",
                "has_update": False,
                "error": str(ex),
            }

    def update_ytdlp(self):
        """Downloads and installs the latest yt-dlp binary with file-lock recovery."""
        for task in self.active_tasks.values():
            if task.get("status") in ("downloading", "processing"):
                return {"success": False, "error": "Cannot update engine while active downloads are in progress."}

        self._engine_busy = True
        tmp_path = None
        try:
            dl_url = (
                "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
                if self.is_win
                else "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
            )
            r = safe_http_get(dl_url, timeout=60, max_retries=3)
            if not r or r.status_code != 200 or len(r.content) < 500_000:
                return {"success": False, "error": "Failed to download update payload."}

            if self.is_win and r.content[:2] != b"MZ":
                return {"success": False, "error": "Downloaded binary is not a valid Windows executable."}

            tmp_path = self.ytdlp + ".update_tmp"
            with open(tmp_path, "wb") as f:
                f.write(r.content)
            if not self.is_win:
                os.chmod(tmp_path, 0o755)

            # Resilient file replacement handling Windows file locks
            replaced = False
            for attempt in range(4):
                try:
                    os.replace(tmp_path, self.ytdlp)
                    replaced = True
                    break
                except (PermissionError, OSError):
                    if self.is_win and os.path.exists(self.ytdlp):
                        try:
                            # Windows NTFS permits renaming a running executable
                            old_bak = f"{self.ytdlp}.old.{int(time.time()*1000)}"
                            os.rename(self.ytdlp, old_bak)
                            os.replace(tmp_path, self.ytdlp)
                            replaced = True
                            try:
                                os.remove(old_bak)
                            except Exception:
                                pass
                            break
                        except Exception:
                            time.sleep(0.3)
                    else:
                        time.sleep(0.3)

            if not replaced:
                return {"success": False, "error": "yt-dlp binary is currently locked by another process."}

            ver_proc = run_external_tool(
                [self.ytdlp, "--version"], label="NexusBridge yt-dlp version", check=False
            )
            self._ytdlp_ver_str = ver_proc.stdout.strip() or "Updated"
            return {"success": True, "new_version": self._ytdlp_ver_str}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            self._engine_busy = False

    def stream_track(self, url_or_path):
        """
        Streams or loads preview audio for an online URL or local track.
        Caches a high-quality PCM WAV slice in the temporary cache directory
        and loads into AudioPlayer, allowing player scrubber, visualizer, EQ, and lyrics.
        """
        if not url_or_path:
            return None
        if os.path.exists(url_or_path):
            return self.play_track(url_or_path)

        plat, p_type, ident = detect_platform_url(url_or_path)
        actual_url = url_or_path
        info_title = "Online Stream"
        info_artist = "NexusTube"
        info_thumb = ""

        if plat in ("spotify", "apple_music"):
            try:
                meta = resolve_multiplatform_url(url_or_path, ytdlp_bin=self.ytdlp)
                if meta.get("tracks"):
                    trk = meta["tracks"][0]
                    sq = trk.get("search_query") or f"{trk.get('artist', '')} - {trk.get('title', '')}".strip()
                    actual_url = f"ytsearch1:{sq}"
                    info_title = trk.get("title") or meta.get("title", info_title)
                    info_artist = trk.get("artist") or meta.get("artist", info_artist)
                    info_thumb = trk.get("thumbnail") or meta.get("thumbnail", "")
            except Exception:
                pass

        cache_dir = os.path.join(tempfile.gettempdir(), "nexustube_cache")
        os.makedirs(cache_dir, exist_ok=True)
        h = hashlib.md5(url_or_path.encode("utf-8", errors="ignore")).hexdigest()
        out_wav = os.path.join(cache_dir, f"stream_{h}.wav")

        if not os.path.exists(out_wav) or os.path.getsize(out_wav) < 1000:
            ytdlp_bin = self.ytdlp if (self.ytdlp and os.path.exists(self.ytdlp)) else (shutil.which("yt-dlp") or self.ytdlp)
            cmd = [
                ytdlp_bin, "--no-warnings", "--download-sections", "*0-180",
                "-x", "--audio-format", "wav", "-o", out_wav, actual_url
            ]
            if os.path.exists(self.ffmpeg):
                cmd += ["--ffmpeg-location", os.path.dirname(self.ffmpeg)]
            try:
                run_external_tool(cmd, label="NexusBridge stream_track cache", check=True)
            except Exception as ex:
                print(f"[NexusBridge] stream_track download error: {ex}")
                return None

        if os.path.exists(out_wav):
            ok = self.player.load_and_play(out_wav)
            if ok:
                self.player.info["title"] = info_title
                self.player.info["artist"] = info_artist
                self.player.info["thumbnail_url"] = info_thumb
                info = dict(self.player.info)
                if info.get("cover_image"):
                    info["cover_base64"] = self._image_to_base64(info["cover_image"])
                    del info["cover_image"]
                elif info_thumb:
                    info["cover_base64"] = info_thumb
                return info
        return None

    def search_lyrics(self, title, artist=""):
        return fetch_lyrics(title, artist)

    def fetch_lyrics_data(self, title, artist="", duration=0, filepath=None):
        return fetch_lyrics(title, artist, duration=duration, file_path=filepath)

    def save_lrc(self, filepath, content):
        target = filepath or self.player.current_path or getattr(self.player, "raw_filepath", None)
        outdir = self.config.get("outdir") or os.path.join(os.path.expanduser("~"), "Downloads", "NexusTube")
        if not target and hasattr(self.player, "info") and self.player.info.get("title"):
            target = os.path.join(outdir, f"{sanitize_filename(self.player.info['title'])}.lrc")
        elif target and not os.path.isabs(target):
            target = os.path.join(outdir, target)
        if not target:
            return False
        base = os.path.splitext(target)[0]
        lrc_path = f"{base}.lrc"
        try:
            os.makedirs(os.path.dirname(os.path.abspath(lrc_path)), exist_ok=True)
            with open(lrc_path, "w", encoding="utf-8") as f:
                f.write(content)
            parsed = parse_lrc(content)
            self.player.lyrics_data = {
                "synced": parsed,
                "synced_raw": content,
                "plain": "\n".join(txt for _, txt in parsed),
                "source": "local",
            }
            return True
        except Exception as e:
            print(f"[NexusBridge] Save LRC error: {e}")
            return False

    def preview_trim(self, filepath, start_sec, end_sec):
        s = time_to_seconds(start_sec)
        e = time_to_seconds(end_sec)
        if e <= s:
            return False
        dur = e - s

        self.stop_trim_preview()

        # Handle remote URLs
        if filepath.startswith("http://") or filepath.startswith("https://"):
            ytdlp_bin = self.ytdlp if (self.ytdlp and os.path.exists(self.ytdlp)) else (shutil.which("yt-dlp") or self.ytdlp)
            actual_url = filepath
            plat, p_type, ident = detect_platform_url(filepath)
            if plat in ("spotify", "apple_music"):
                try:
                    meta_res = resolve_multiplatform_url(filepath, ytdlp_bin=self.ytdlp)
                    if meta_res.get("tracks"):
                        trk = meta_res["tracks"][0]
                        sq = trk.get("search_query") or f"{trk.get('artist', '')} - {trk.get('title', '')}".strip()
                        actual_url = f"ytsearch1:{sq}"
                except Exception:
                    pass

            ffplay = self.ffplay if (self.ffplay and os.path.exists(self.ffplay)) else shutil.which("ffplay")
            if ffplay:
                try:
                    cmd_url = [ytdlp_bin, "-g", "-f", "bestaudio/best", actual_url]
                    p = run_external_tool(cmd_url, label="yt-dlp get stream url", check=False)
                    stream_url = p.stdout.strip().splitlines()[0] if p.stdout.strip() else None
                    if stream_url:
                        play_cmd = [ffplay, "-nodisp", "-autoexit", "-ss", str(s), "-t", str(dur), stream_url]
                        self._stream_proc = subprocess.Popen(
                            play_cmd, creationflags=subprocess.CREATE_NO_WINDOW if self.is_win else 0
                        )
                        return True
                except Exception as ex:
                    print(f"[NexusBridge] Stream preview error: {ex}")

        # Local file playback
        if not filepath or not os.path.exists(filepath):
            return False
        ok = self.player.load_and_play(filepath, start_time=s)
        if ok:
            self._preview_stop_timer = threading.Timer(dur, self.player.stop)
            self._preview_stop_timer.start()
            return True
        return False

    def stop_trim_preview(self):
        if self._preview_stop_timer:
            try:
                self._preview_stop_timer.cancel()
            except Exception:
                pass
            self._preview_stop_timer = None
        if hasattr(self, "_stream_proc") and self._stream_proc:
            try:
                self._stream_proc.terminate()
                self._stream_proc.kill()
            except Exception:
                pass
            self._stream_proc = None
        self.player.stop()
        return True

    def trim_audio_file(self, filepath, start_sec, end_sec, out_format="mp3"):
        s = time_to_seconds(start_sec)
        e = time_to_seconds(end_sec)
        if e <= s:
            return False
        dur = e - s

        outdir = os.path.abspath(self.config.get("outdir") or os.path.join(os.path.expanduser("~"), "Downloads", "NexusTube"))
        os.makedirs(outdir, exist_ok=True)

        # Handle remote URLs seamlessly
        if filepath.startswith("http://") or filepath.startswith("https://"):
            safe_name = "stream_cut"
            plat, p_type, ident = detect_platform_url(filepath)
            download_url = filepath
            if plat in ("spotify", "apple_music"):
                try:
                    meta_res = resolve_multiplatform_url(filepath, ytdlp_bin=self.ytdlp)
                    if meta_res.get("tracks"):
                        trk = meta_res["tracks"][0]
                        sq = trk.get("search_query") or f"{trk.get('artist', '')} - {trk.get('title', '')}".strip()
                        download_url = f"ytsearch1:{sq}"
                        safe_name = sanitize_filename(trk.get("title", "stream_cut"))
                except Exception:
                    pass
            out_path = os.path.join(outdir, f"{safe_name}_trimmed_{int(s)}s_{int(e)}s.{out_format}")
            ytdlp_bin = self.ytdlp if (self.ytdlp and os.path.exists(self.ytdlp)) else (shutil.which("yt-dlp") or self.ytdlp)
            cmd = [
                ytdlp_bin, "--no-warnings", "--windows-filenames",
                "--download-sections", f"*{s}-{e}",
                "-x", "--audio-format", out_format if out_format in ("mp3", "m4a", "flac") else "mp3",
                "--audio-quality", "320K",
                "-o", out_path, download_url
            ]
            try:
                res = run_external_tool(cmd, label="NexusBridge remote trim", check=False)
                return res.returncode == 0 and os.path.exists(out_path)
            except Exception as err:
                print(f"[NexusBridge] Remote trim error: {err}")
                return False

        if not os.path.exists(filepath):
            return False

        base_name = sanitize_filename(os.path.splitext(os.path.basename(filepath))[0])
        out_path = os.path.join(outdir, f"{base_name}_trimmed_{int(s)}s_{int(e)}s.{out_format}")
        ffmpeg = self.ffmpeg if os.path.exists(self.ffmpeg) else (shutil.which("ffmpeg") or "ffmpeg")
        cmd = [
            ffmpeg, "-y", "-ss", str(s), "-t", str(dur),
            "-i", filepath, "-c:a", "libmp3lame" if out_format == "mp3" else "copy",
            "-b:a", "320k",
            out_path
        ]
        try:
            res = run_external_tool(cmd, label="NexusBridge trim local audio", check=False)
            return res.returncode == 0 and os.path.exists(out_path)
        except Exception as err:
            print(f"[NexusBridge] Trim error: {err}")
            return False

    def select_folder(self):
        try:
            win = self._get_window()
            if win:
                import webview
                res = win.create_file_dialog(webview.FOLDER_DIALOG)
                if res:
                    return res[0]
                return ""  # User cancelled dialog; do not trigger Tkinter fallback
        except Exception:
            pass
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            folder = filedialog.askdirectory()
            root.destroy()
            return folder or ""
        except Exception:
            return ""

    def open_folder(self, folder_path=None):
        target = folder_path or self.config.get("outdir") or os.path.join(os.path.expanduser("~"), "Downloads", "NexusTube")
        try:
            os.makedirs(target, exist_ok=True)
            if self.is_win:
                os.startfile(target)
            elif self.is_mac:
                subprocess.Popen(["open", target])
            else:
                subprocess.Popen(["xdg-open", target])
            return True
        except Exception as e:
            print(f"[NexusBridge] open_folder error: {e}")
            return False

    def reveal_file(self, filepath):
        """Reveals the specified file in Windows Explorer, macOS Finder, or Linux file manager."""
        if not filepath:
            return self.open_folder()
        try:
            abs_p = os.path.abspath(filepath)
            if not os.path.exists(abs_p):
                parent_dir = os.path.dirname(abs_p)
                return self.open_folder(parent_dir)

            if self.is_win:
                norm_p = os.path.normpath(abs_p)
                subprocess.Popen(f'explorer /select,"{norm_p}"')
                return True
            elif self.is_mac:
                subprocess.Popen(["open", "-R", abs_p])
                return True
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(abs_p)])
                return True
        except Exception as e:
            print(f"[NexusBridge] reveal_file error: {e}")
            return self.open_folder(os.path.dirname(filepath))

    def delete_file(self, filepath):
        if not filepath or not os.path.exists(filepath):
            return False
        if self._is_same_path(self.player.current_path, filepath) or self._is_same_path(getattr(self.player, "raw_filepath", None), filepath):
            self.player.stop()
            self.player.current_path = None
            self.player.raw_filepath = None
            if PYGAME_AVAILABLE and hasattr(pygame, "mixer") and hasattr(pygame.mixer, "music") and hasattr(pygame.mixer.music, "unload"):
                try:
                    pygame.mixer.music.unload()
                except Exception:
                    pass
            time.sleep(0.1)
        base_no_ext = os.path.splitext(filepath)[0]
        for _ in range(3):
            try:
                os.remove(filepath)
                lrc_p = f"{base_no_ext}.lrc"
                if os.path.exists(lrc_p):
                    try:
                        os.remove(lrc_p)
                    except Exception:
                        pass
                for c_ext in (".jpg", ".jpeg", ".png", ".webp"):
                    img_p = f"{base_no_ext}{c_ext}"
                    if os.path.exists(img_p):
                        try:
                            os.remove(img_p)
                        except Exception:
                            pass
                return True
            except PermissionError:
                time.sleep(0.15)
            except Exception as e:
                print(f"[NexusBridge] Delete error: {e}")
                return False
        return False

    def save_config(self, new_config):
        if isinstance(new_config, dict):
            self.config.update(new_config)
            self._save_config()
            return True
        return False

    def set_telemetry(self, enabled: bool):
        """Toggle crash reporting opt-in from JS settings UI."""
        self.config["telemetry_enabled"] = bool(enabled)
        self._save_config()
        if enabled:
            init_sentry(self.config)
        return {"ok": True, "telemetry_enabled": bool(enabled)}

    def get_telemetry_status(self):
        """Return telemetry status for JS settings UI."""
        return {
            "enabled": self.config.get("telemetry_enabled", False),
            "sentry_available": SENTRY_AVAILABLE,
            "dsn_configured": bool(SENTRY_DSN),
        }

    def update_engines(self):
        self._check_engine(manual=True)
        return self.get_engine_status()

    def _check_engine(self, manual=False):
        self._engine_busy = True

        # 1. yt-dlp Check & Update
        if os.path.exists(self.ytdlp) and not is_valid_binary(self.ytdlp, min_size=500_000):
            try:
                os.remove(self.ytdlp)
            except Exception:
                pass

        if not os.path.exists(self.ytdlp):
            try:
                dl_url = (
                    "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
                    if self.is_win
                    else "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
                )
                r = safe_http_get(dl_url, timeout=60, max_retries=3)
                if r and r.status_code == 200 and len(r.content) >= 500_000:
                    is_ok = True
                    if self.is_win and r.content[:2] != b"MZ":
                        is_ok = False
                    if is_ok:
                        tmp_ytdlp = self.ytdlp + ".tmp"
                        with open(tmp_ytdlp, "wb") as f:
                            f.write(r.content)
                        if not self.is_win:
                            os.chmod(tmp_ytdlp, 0o755)
                        os.replace(tmp_ytdlp, self.ytdlp)
                    else:
                        raise ValueError("Invalid yt-dlp executable payload received.")
                else:
                    raise IOError("Failed to retrieve valid yt-dlp binary.")
            except Exception:
                self._engine_busy = False
                return
        else:
            try:
                ver_proc = run_external_tool([self.ytdlp, "--version"], label="NexusBridge yt-dlp version", check=False)
                self._ytdlp_ver_str = ver_proc.stdout.strip()
                if manual:
                    run_external_tool([self.ytdlp, "-U"], label="NexusBridge yt-dlp update", check=False)
            except Exception:
                pass

        # 2. ffmpeg & ffprobe Check & Download
        for f_bin in (self.ffmpeg, self.ffprobe):
            if os.path.exists(f_bin) and not is_valid_binary(f_bin, min_size=1_000_000):
                try:
                    os.remove(f_bin)
                except Exception:
                    pass

        if not os.path.exists(self.ffmpeg) or not os.path.exists(self.ffprobe):
            try:
                import tarfile
                import zipfile
                api_url = "https://api.github.com/repos/yt-dlp/FFmpeg-Builds/releases/latest"
                resp = safe_json_response(safe_http_get(api_url, timeout=12, max_retries=2), default={})
                if self.is_win: asset_name = "ffmpeg-master-latest-win64-gpl.zip"
                elif self.is_mac: asset_name = "ffmpeg-master-latest-mac64-gpl.zip"
                else: asset_name = "ffmpeg-master-latest-linux64-gpl.tar.xz"

                asset = next((a for a in resp.get("assets", []) if a.get("name") == asset_name), None)
                dl_url = asset["browser_download_url"] if asset else f"https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/{asset_name}"

                r = safe_http_get(dl_url, timeout=180, max_retries=3)
                if r and r.status_code == 200 and len(r.content) >= 5_000_000:
                    if asset_name.endswith(".zip"):
                        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                            for entry in z.namelist():
                                base_n = os.path.basename(entry)
                                if base_n.lower() in ("ffmpeg.exe", "ffprobe.exe", "ffplay.exe"):
                                    dest = os.path.join(self.appdata_dir, base_n)
                                    tmp_dest = dest + ".tmp"
                                    with open(tmp_dest, "wb") as f_out:
                                        f_out.write(z.read(entry))
                                    if is_valid_binary(tmp_dest, min_size=1_000_000):
                                        os.replace(tmp_dest, dest)
                                    else:
                                        if os.path.exists(tmp_dest):
                                            try: os.remove(tmp_dest)
                                            except Exception: pass
                    else:
                        with tarfile.open(fileobj=io.BytesIO(r.content), mode="r:xz") as t:
                            for member in t.getmembers():
                                base_n = os.path.basename(member.name)
                                if base_n in ("ffmpeg", "ffprobe", "ffplay"):
                                    dest = os.path.join(self.appdata_dir, base_n)
                                    tmp_dest = dest + ".tmp"
                                    with open(tmp_dest, "wb") as f_out:
                                        f_out.write(t.extractfile(member).read())
                                    os.chmod(tmp_dest, 0o755)
                                    if is_valid_binary(tmp_dest, min_size=1_000_000):
                                        os.replace(tmp_dest, dest)
                                    else:
                                        if os.path.exists(tmp_dest):
                                            try: os.remove(tmp_dest)
                                            except Exception: pass
                else:
                    raise IOError("Failed to retrieve valid FFmpeg archive.")
            except Exception:
                self._engine_busy = False
                return

        self._engine_busy = False

    def _check_app_update(self):
        try:
            resp = safe_http_get(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest", timeout=8, max_retries=2)
            data = safe_json_response(resp, default={})
            latest = data.get("tag_name", "").lstrip("v")
            if not latest or latest == VERSION:
                return
            asset_name = "NexusTube.exe" if self.is_win else "NexusTube"
            asset = next((a for a in data.get("assets", []) if a.get("name", "").lower() == asset_name.lower()), None)
            self._pending_update_url = asset["browser_download_url"] if asset else None
            self._pending_update_ver = latest
        except Exception:
            pass

    def get_update_info(self):
        """คืนข้อมูล update ที่รอการติดตั้ง สำหรับ JS frontend
        Returns dict: {"has_update": bool, "version": str, "url": str or None}"""
        return {
            "has_update": bool(self._pending_update_ver),
            "version": self._pending_update_ver or "",
            "url": self._pending_update_url or "",
        }

    def apply_update(self):
        """ดาวน์โหลดและรีสตาร์ทแอปด้วย version ใหม่ (เรียกจาก JS frontend)
        Returns {"ok": True} on success dispatch, {"ok": False, "error": str} on error."""
        if not self._pending_update_url or not self._exe_path:
            ver = self._pending_update_ver or "?"
            return {
                "ok": False,
                "error": f"No installable update (v{ver} available). Visit https://github.com/{GITHUB_REPO}/releases/latest",
            }
        threading.Thread(target=self._apply_update, daemon=True).start()
        return {"ok": True}

    def _apply_update(self):
        """ดาวน์โหลด exe ใหม่ แล้วสลับไฟล์และรีสตาร์ท (ทำงานใน background thread)"""
        def _js(script):
            """ส่ง JavaScript ไปยัง webview window อย่างปลอดภัย"""
            try:
                win = self._get_window()
                if win:
                    win.evaluate_js(script)
            except Exception:
                pass

        try:
            _js("window.__nexus_update_status && window.__nexus_update_status('downloading', 0)")
            tmp_exe = self._exe_path + ".new"
            with requests.get(
                self._pending_update_url, stream=True, timeout=120,
                headers={"User-Agent": "NexusTube-App"}
            ) as r:
                if r.status_code != 200:
                    raise IOError(f"Update download returned status {r.status_code}")
                total = int(r.headers.get("content-length", 0))
                written = 0
                with open(tmp_exe, "wb") as f:
                    for chunk in r.iter_content(65536):
                        f.write(chunk)
                        written += len(chunk)
                        if total:
                            pct = written / total * 100
                            _js(f"window.__nexus_update_status && window.__nexus_update_status('downloading', {pct:.1f})")

            if not is_valid_binary(tmp_exe, min_size=5_000_000):
                if os.path.exists(tmp_exe):
                    try:
                        os.remove(tmp_exe)
                    except Exception:
                        pass
                raise ValueError("Downloaded update is corrupt or incomplete.")

            if self.is_win:
                bat = self._exe_path + ".update.bat"
                lines = [
                    "@echo off",
                    "timeout /t 2 /nobreak >nul",
                    f'move /y "{tmp_exe}" "{self._exe_path}"',
                    f'start "" "{self._exe_path}"',
                    'del "%~f0"',
                    "",
                ]
                with open(bat, "w") as f:
                    f.write("\n".join(lines))
                subprocess.Popen(["cmd", "/c", bat], creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                sh = self._exe_path + ".update.sh"
                lines = [
                    "#!/bin/bash",
                    "sleep 2",
                    f'mv "{tmp_exe}" "{self._exe_path}"',
                    f'chmod +x "{self._exe_path}"',
                    f'"{self._exe_path}" &',
                    'rm "$0"',
                ]
                with open(sh, "w") as f:
                    f.write("\n".join(lines))
                os.chmod(sh, 0o755)
                subprocess.Popen([sh])

            _js("window.__nexus_update_status && window.__nexus_update_status('restarting', 100)")
            try:
                win = self._get_window()
                if win:
                    win.destroy()
            except Exception:
                pass
        except Exception as e:
            err_msg = str(e)
            _js(f"window.__nexus_update_status && window.__nexus_update_status('error', 0, {json.dumps(err_msg)})")

    def _get_cookie_args(self):
        """คืน yt-dlp cookie arguments ตาม config ที่ตั้งไว้
        Priority: custom file > browser extraction.
        คืน list ว่างถ้าไม่มี cookie ที่กำหนดไว้"""
        args = []
        if self._cookie_file and os.path.isfile(self._cookie_file):
            args = ["--cookies", self._cookie_file]
        elif self._cookie_source and self._cookie_source in (
            "chrome", "firefox", "edge", "brave", "opera", "safari", "chromium"
        ):
            args = ["--cookies-from-browser", self._cookie_source]
        return args

    def _download_worker(self, task):
        while self._engine_busy:
            if task["cancelled"]:
                return
            task["status"] = "waiting"
            time.sleep(1)

        if task["cancelled"]:
                return

        task["status"] = "downloading"
        fmt_choice = task.get("override_fmt") or self.config.get("format", "mp3_320")
        outdir = os.path.abspath(self.config.get("outdir") or os.path.join(os.path.expanduser("~"), "Downloads", "NexusTube"))
        
        # Self-healing output directory verification & fallback
        try:
            os.makedirs(outdir, exist_ok=True)
            probe = os.path.join(outdir, f".write_test_{int(time.time()*1000)}.tmp")
            with open(probe, "w") as fp:
                fp.write("ok")
            os.remove(probe)
        except Exception as perm_err:
            fallback_dir = os.path.join(os.path.expanduser("~"), "Downloads")
            try:
                os.makedirs(fallback_dir, exist_ok=True)
                outdir = fallback_dir
                task["warning"] = f"Output folder unwritable ({perm_err}); redirected to Downloads."
            except Exception:
                pass

        ffmpeg_dir = os.path.dirname(self.ffmpeg) if (self.ffmpeg and is_valid_binary(self.ffmpeg)) else ""
        ytdlp_bin = self.ytdlp if (self.ytdlp and is_valid_binary(self.ytdlp)) else (shutil.which("yt-dlp") or self.ytdlp)

        if not is_valid_binary(ytdlp_bin):
            task["status"] = "failed"
            task["error"] = "yt-dlp engine not found. Please connect to the internet to download it, or install yt-dlp manually."
            return

        meta_info = task.get("metadata") or {}
        track_num = meta_info.get("track_num")
        is_playlist = meta_info.get("is_playlist", False)

        if task.get("title") and task["title"] != task["url"] and not task["title"].startswith("http"):
            safe_t = sanitize_filename(task["title"])
            if is_playlist and track_num and not re.match(r'^\d{1,3}[\s\.\-_]', safe_t):
                safe_t = f"{int(track_num):02d} - {safe_t}"
            out_template = os.path.join(outdir, f"{safe_t}.%(ext)s")
        else:
            out_template = os.path.join(outdir, "%(title)s.%(ext)s")

        cmd = [
            ytdlp_bin, "--newline", "--no-warnings", "--windows-filenames",
            "--retries", "5", "--fragment-retries", "10", "--socket-timeout", "30",
            "-o", out_template,
        ]
        if ffmpeg_dir:
            cmd += ["--ffmpeg-location", ffmpeg_dir]

        # Inject browser cookies หากมีการกำหนดค่า (เปิดใช้สำหรับ age-restricted / members-only)
        cmd += self._get_cookie_args()

        has_ffmpeg = bool(ffmpeg_dir or shutil.which("ffmpeg"))
        opts = task.get("options", {})

        sb_opt = opts.get("sponsorblock")
        if sb_opt is None:
            sb_opt = self.config.get("sponsorblock", False)
        if sb_opt and has_ffmpeg:
            cmd += ["--sponsorblock-remove", "sponsor,selfpromo"]
        if opts.get("embed_meta", self.config.get("embed_meta", True)) and has_ffmpeg:
            cmd += ["--embed-metadata"]
        if opts.get("embed_thumb", self.config.get("embed_thumb", True)) and has_ffmpeg:
            cmd += ["--embed-thumbnail"]
        if opts.get("embed_lyrics", self.config.get("embed_lyrics", False)) and has_ffmpeg:
            cmd += ["--write-subs", "--sub-langs", "en.*,th.*", "--embed-subs"]

        if fmt_choice == "mp3_320":
            cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "320K"]
        elif fmt_choice == "m4a_best":
            cmd += ["-x", "--audio-format", "m4a", "--audio-quality", "0"]
        elif fmt_choice == "flac":
            cmd += ["-x", "--audio-format", "flac", "--audio-quality", "0"]
        elif fmt_choice == "mp4_1080":
            cmd += ["-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best", "--merge-output-format", "mp4"]
        elif fmt_choice == "mp4_720":
            cmd += ["-f", "bestvideo[height<=720]+bestaudio/best[height<=720]/best", "--merge-output-format", "mp4"]
        else:  # mp4_best
            cmd += ["-f", "bestvideo+bestaudio/best", "--merge-output-format", "mp4"]

        if opts.get("normalize", self.config.get("normalize", False)) and has_ffmpeg:
            if fmt_choice in ("mp3_320", "m4a_best", "flac"):
                cmd += ["--postprocessor-args", "ExtractAudio:-filter:a loudnorm=I=-14:LRA=11:TP=-1.5"]
            else:
                cmd += ["--postprocessor-args", "Merger:-filter:a loudnorm=I=-14:LRA=11:TP=-1.5"]

        cmd.append(task["url"])

        ansi = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        pct_regex = re.compile(r"(\d+\.?\d*)%")
        speed_regex = re.compile(r"at\s+([~0-9\.]+\s*\w+/s)")
        eta_regex = re.compile(r"ETA\s+(\d+:\d+(?::\d+)?)")
        dest_file = None

        max_download_attempts = 3
        download_succeeded = False
        last_error_msg = None

        for dl_attempt in range(1, max_download_attempts + 1):
            if task["cancelled"]:
                task["status"] = "cancelled"
                return

            last_output_lines = []
            try:
                # Task 2: Standardized logging for external streaming tool
                cmd_str = " ".join(f'"{c}"' if " " in c else c for c in cmd)
                try:
                    sys.stderr.write(f"[NexusBridge] Starting download (attempt {dl_attempt}/{max_download_attempts}): {cmd_str}\n")
                except Exception:
                    pass

                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if self.is_win else 0
                )
                task["proc"] = proc

                for raw in proc.stdout:
                    if task["cancelled"]:
                        break
                    line = ansi.sub("", raw.decode("utf-8", errors="replace")).strip()
                    if line:
                        last_output_lines.append(line)
                        if len(last_output_lines) > 20:
                            last_output_lines.pop(0)

                    if os.path.isabs(line) and os.path.exists(line):
                        dest_file = line
                        task["out_file"] = dest_file
                    elif "Destination:" in line:
                        d = line.split("Destination:", 1)[-1].strip()
                        if not d.endswith(".part") and not d.endswith(".ytdl"):
                            dest_file = d
                            task["out_file"] = dest_file
                    elif "already been downloaded" in line:
                        m = re.search(r'\[download\]\s+(.*?)\s+has already been downloaded', line)
                        if m:
                            dest_file = m.group(1).strip()
                            task["out_file"] = dest_file
                    elif "Merging formats into" in line:
                        m_dest = line.split('Merging formats into "', 1)[-1].rstrip('"')
                        dest_file = m_dest
                        task["out_file"] = dest_file

                    if "[download]" in line and "%" in line:
                        pm = pct_regex.search(line)
                        sm = speed_regex.search(line)
                        em = eta_regex.search(line)
                        if pm:
                            pct = float(pm.group(1)) / 100.0
                            task["percent"] = pct
                            if sm:
                                task["speed"] = sm.group(1)
                            if em:
                                task["eta"] = em.group(1)
                    elif any(k in line for k in ("[ExtractAudio]", "[Merger]", "[Metadata]", "[EmbedThumbnail]", "[SponsorBlock]")):
                        task["status"] = "processing"

                proc.wait()

                if task["cancelled"]:
                    task["status"] = "cancelled"
                    return

                if proc.returncode == 0:
                    download_succeeded = True
                    task["status"] = "completed"
                    task["percent"] = 1.0
                    task["error"] = None
                    break
                else:
                    last_error_msg = "\n".join(last_output_lines[-5:]) if last_output_lines else f"Process exited with code {proc.returncode}"
                    print(f"[NexusBridge] Download attempt {dl_attempt}/{max_download_attempts} failed (code {proc.returncode}): {last_error_msg}")
                    if dl_attempt < max_download_attempts:
                        task["status"] = "retrying"
                        time.sleep(2 * dl_attempt)
            except Exception as ex:
                last_error_msg = str(ex)
                print(f"[NexusBridge] Worker process exception on attempt {dl_attempt}: {ex}")
                if dl_attempt < max_download_attempts:
                    task["status"] = "retrying"
                    time.sleep(2 * dl_attempt)

        if not download_succeeded:
            task["status"] = "failed"
            classified = classify_download_error(last_error_msg or "")
            if classified:
                task["error"] = classified.user_message
            else:
                task["error"] = (last_error_msg or "Download failed after multiple attempts.").splitlines()[-1][:120]
            return

        final_file = dest_file or task.get("out_file")
        if not final_file or not os.path.exists(final_file):
            try:
                media_exts = (".mp3", ".m4a", ".wav", ".flac", ".opus", ".ogg", ".aac", ".mp4", ".mkv", ".webm")
                candidates = [
                    os.path.join(outdir, f) for f in os.listdir(outdir)
                    if not f.endswith((".part", ".ytdl", ".lrc", ".jpg", ".png", ".webp", ".json", ".txt"))
                    and f.lower().endswith(media_exts)
                ]
                if candidates:
                    candidates.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                    if time.time() - os.path.getmtime(candidates[0]) < 180:
                        final_file = candidates[0]
                        task["out_file"] = final_file
            except Exception:
                pass

        if final_file and os.path.exists(final_file) and not final_file.lower().endswith((".mp4", ".mkv", ".webm")):
            try:
                meta_info = task.get("metadata") or {}
                raw_name = task.get("title") or os.path.basename(final_file).rsplit(".", 1)[0]
                parsed_meta = parse_music_metadata(
                    raw_name,
                    fallback_artist=meta_info.get("artist", ""),
                    fallback_album=meta_info.get("album", "NexusTube Collection"),
                    fallback_track=meta_info.get("track_num", 1)
                )
                final_title = meta_info.get("title") or parsed_meta["title"]
                final_artist = meta_info.get("artist") or parsed_meta["artist"]
                final_album = meta_info.get("album") or parsed_meta["album"]
                final_track = meta_info.get("track_num") or parsed_meta["track_num"]

                meta = {
                    "title": final_title,
                    "artist": final_artist,
                    "album": final_album,
                    "year": time.strftime("%Y"),
                    "genre": "Music",
                    "track_num": final_track,
                }

                lyrics_text = None
                if opts.get("embed_lyrics", self.config.get("embed_lyrics", False)):
                    lyr_res = fetch_lyrics(final_title, final_artist, file_path=final_file)
                    lyrics_text = lyr_res.get("synced_raw") or lyr_res.get("plain")
                    if lyr_res.get("synced_raw"):
                        try:
                            lrc_dest = os.path.splitext(final_file)[0] + ".lrc"
                            with open(lrc_dest, "w", encoding="utf-8") as lf:
                                lf.write(lyr_res["synced_raw"])
                        except Exception:
                            pass

                cover_data = None
                base_no_ext = os.path.splitext(final_file)[0]
                for c_ext in (".jpg", ".png", ".webp", ".jpeg"):
                    c_cand = f"{base_no_ext}{c_ext}"
                    if os.path.exists(c_cand):
                        try:
                            with open(c_cand, "rb") as cf:
                                cover_data = cf.read()
                            break
                        except Exception:
                            pass

                tag_audio_file(final_file, meta, cover_data_or_url=cover_data or meta_info.get("thumbnail"), lyrics_text=lyrics_text)
            except Exception as tag_err:
                print(f"[NexusBridge] Tagging error: {tag_err}")

        if final_file and not task.get("thumbnail"):
            try:
                task["thumbnail"] = self.get_embedded_cover_base64(final_file)
            except Exception:
                pass

        show_notify("Download Complete", task.get("title") or os.path.basename(final_file or ""))

    def cleanup(self):
        """Releases all hardware resources, background threads, subprocesses, and UI integrations."""
        try:
            if hasattr(self, "tray") and self.tray:
                self.tray.stop()
        except Exception:
            pass
        try:
            if hasattr(self, "hotkeys") and self.hotkeys:
                self.hotkeys.stop()
        except Exception:
            pass
        try:
            if hasattr(self, "discord_rpc") and self.discord_rpc:
                self.discord_rpc.close()
        except Exception:
            pass
        try:
            if hasattr(self, "player") and self.player:
                self.player.cleanup()
        except Exception:
            pass
        try:
            for tid, task in list(getattr(self, "active_tasks", {}).items()):
                proc = task.get("proc")
                if proc and proc.poll() is None:
                    try:
                        proc.terminate()
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            sp = getattr(self, "_stream_proc", None)
            if sp and sp.poll() is None:
                try:
                    sp.terminate()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if hasattr(self, "executor") and self.executor:
                self.executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass


# ── Task 3: Startup Dependency Checks ────────────────────────────────────────
def preflight_startup_checks(output_folder=None) -> dict:
    """
    Task 3: Pre-flight Startup Dependency Checks
    Verifies:
      1. yt-dlp functional (runs `yt-dlp --version`)
      2. ffmpeg functional (runs `ffmpeg -version`)
      3. Output directory is writable (probes file creation and deletion)
      4. WebView2 Runtime availability (on Windows)
    If any dependency is missing, automatically attempts auto-healing via nexus_doctor.
    Displays informative modal warnings if critical components remain absent.
    """
    results = {
        "ytdlp": False,
        "ffmpeg": False,
        "output_writable": False,
        "webview2": False,
        "warnings": [],
        "errors": [],
    }

    # Register APPDATA and bundled bin directories in PATH
    try:
        import nexus_doctor
        nexus_doctor.register_bin_in_path()
    except Exception:
        pass

    # 1. Check yt-dlp
    ytdlp_bin = None
    try:
        from nexus_doctor import find_binary
        ytdlp_bin = find_binary("yt-dlp")
    except Exception:
        pass
    if not ytdlp_bin:
        ytdlp_bin = shutil.which("yt-dlp")

    if ytdlp_bin and os.path.exists(ytdlp_bin):
        try:
            res = run_external_tool([ytdlp_bin, "--version"], timeout=10, retries=1, check=False, label="Preflight yt-dlp")
            if res.returncode == 0 and res.stdout.strip():
                results["ytdlp"] = True
        except Exception:
            pass

    if not results["ytdlp"]:
        # Attempt self-healing via nexus_doctor
        try:
            import nexus_doctor
            healed_yt = nexus_doctor.ensure_ytdlp()
            if healed_yt and os.path.exists(healed_yt):
                res = run_external_tool([healed_yt, "--version"], timeout=10, retries=1, check=False, label="Preflight yt-dlp healed")
                if res.returncode == 0:
                    results["ytdlp"] = True
        except Exception:
            pass

    if not results["ytdlp"]:
        results["errors"].append(
            "ไม่พบหรือเอนจินดาวน์โหลด (yt-dlp) ไม่สามารถทำงานได้\n\n"
            "วิธีแก้ไข:\n"
            "1. ดาวน์โหลด yt-dlp.exe จาก https://github.com/yt-dlp/yt-dlp/releases\n"
            "2. นำไปวางในโฟลเดอร์เดียวกับโปรแกรม หรือ %APPDATA%\\NexusTube\\bin"
        )

    # 2. Check ffmpeg
    ffmpeg_bin = None
    try:
        from nexus_doctor import find_binary
        ffmpeg_bin = find_binary("ffmpeg")
    except Exception:
        pass
    if not ffmpeg_bin:
        ffmpeg_bin = shutil.which("ffmpeg")

    if ffmpeg_bin and os.path.exists(ffmpeg_bin):
        try:
            res = run_external_tool([ffmpeg_bin, "-version"], timeout=10, retries=1, check=False, label="Preflight ffmpeg")
            if res.returncode == 0:
                results["ffmpeg"] = True
        except Exception:
            pass

    if not results["ffmpeg"]:
        # Attempt self-healing via nexus_doctor
        try:
            import nexus_doctor
            healed_ff, _ = nexus_doctor.ensure_ffmpeg()
            if healed_ff and os.path.exists(healed_ff):
                res = run_external_tool([healed_ff, "-version"], timeout=10, retries=1, check=False, label="Preflight ffmpeg healed")
                if res.returncode == 0:
                    results["ffmpeg"] = True
        except Exception:
            pass

    if not results["ffmpeg"]:
        results["warnings"].append(
            "ไม่พบเอนจินประมวลผลเสียง FFmpeg (ffmpeg.exe / ffprobe.exe)\n\n"
            "ผลกระทบ: การแปลงไฟล์เสียงเป็น MP3/FLAC, Equalizer DSP และการตัดต่อเสียงจะไม่สามารถทำงานได้\n\n"
            "วิธีแก้ไข: นำไฟล์ ffmpeg.exe และ ffprobe.exe วางใน %APPDATA%\\NexusTube\\bin หรือโฟลเดอร์โปรแกรม"
        )

    # 3. Check Output Directory write access
    out_dir = output_folder
    if not out_dir or not os.path.isdir(out_dir):
        appdata_dir = os.path.join(os.getenv("APPDATA") or os.path.expanduser("~"), "NexusTube")
        cfg_file = os.path.join(appdata_dir, "config.json")
        if os.path.exists(cfg_file):
            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    out_dir = cfg.get("output_folder")
            except Exception:
                pass
    if not out_dir:
        out_dir = os.path.join(os.path.expanduser("~"), "Downloads", "NexusTube")

    try:
        os.makedirs(out_dir, exist_ok=True)
        probe_path = os.path.join(out_dir, f".nexus_write_test_{os.getpid()}_{int(time.time())}.tmp")
        with open(probe_path, "w", encoding="utf-8") as pf:
            pf.write("nexus_probe_ok")
        if os.path.exists(probe_path):
            os.remove(probe_path)
            results["output_writable"] = True
    except Exception as ex:
        results["output_writable"] = False
        results["warnings"].append(
            f"โฟลเดอร์บันทึกไฟล์ปลายทาง ({out_dir}) ไม่สามารถเขียนไฟล์ได้ (Permission Denied):\n{ex}\n\n"
            "กรุณาตรวจสอบสิทธิ์การเขียน หรือเปลี่ยนโฟลเดอร์ในแท็บ Settings"
        )

    # 4. Check WebView2 Runtime on Windows
    results["webview2"] = is_webview2_available()
    if sys.platform == "win32" and not results["webview2"]:
        # Attempt self-healing via nexus_doctor (prompts consent dialog first)
        try:
            import nexus_doctor
            healed_wv2 = nexus_doctor.ensure_webview2(ask_consent=True)
            if healed_wv2:
                # Windows registry flush delay fallback: retry checking up to 3 times (1s interval)
                for _ in range(3):
                    time.sleep(1.0)
                    if is_webview2_available():
                        results["webview2"] = True
                        break
        except Exception:
            pass

    if sys.platform == "win32" and not results["webview2"]:
        results["warnings"].append(
            "ตรวจพบว่ายังไม่ได้ติดตั้ง Microsoft Edge WebView2 Runtime\n\n"
            "NexusTube จะเริ่มทำงานใน Compatibility Mode (Classic Dark UI) โดยอัตโนมัติ"
        )

    # If critical errors found, show MessageBox alert
    if sys.platform == "win32" and results["errors"]:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                "\n\n".join(results["errors"]),
                "NexusTube — ข้อมูลความต้องการของระบบ (Pre-flight Check)",
                0x10  # MB_ICONERROR
            )
        except Exception:
            pass
    elif sys.platform == "win32" and results["warnings"]:
        for w in results["warnings"]:
            try:
                sys.stderr.write(f"[Preflight Warning] {w}\n")
            except Exception:
                pass

    return results


def run_app():
    setup_crash_handler()
    # โหลด config เพื่อตรวจ telemetry preference แล้ว init Sentry (ถ้า opt-in)
    try:
        import json as _json_for_sentry
        _cfg_path_sentry = os.path.join(
            os.getenv("APPDATA") or os.path.expanduser("~"),
            "NexusTube", "config.json"
        )
        _cfg_sentry = {}
        if os.path.isfile(_cfg_path_sentry):
            with open(_cfg_path_sentry, "r", encoding="utf-8") as _f:
                _cfg_sentry = _json_for_sentry.load(_f)
        init_sentry(_cfg_sentry)
    except Exception:
        pass
    preflight_startup_checks()
    if "--legacy" in sys.argv:
        App().mainloop()
        return

    # Pre-flight verify that Microsoft Edge WebView2 Runtime is installed on Windows
    if not is_webview2_available():
        print("[NexusTube] Microsoft Edge WebView2 Runtime is not installed. Gracefully falling back to Compatibility Mode.")
        App(is_fallback=True).mainloop()
        return

    try:
        import webview
    except ImportError:
        print("[NexusTube] pywebview not installed, falling back to legacy Tkinter UI")
        App(is_fallback=True).mainloop()
        return

    if getattr(sys, "frozen", False):
        base_dir = sys._MEIPASS
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    html_path = os.path.join(base_dir, "web", "index.html")
    if not os.path.exists(html_path):
        print(f"[NexusTube] Web UI not found at {html_path}, falling back to legacy Tkinter UI")
        App(is_fallback=True).mainloop()
        return

    icon_path = os.path.join(base_dir, "NexusTube by herlove.ico")
    if not os.path.exists(icon_path):
        icon_path = os.path.join(base_dir, "icon.ico")

    try:
        bridge = NexusBridgeAPI()
        window = webview.create_window(
            title="NexusTube — Music & Video Downloader",
            url=html_path,
            js_api=bridge,
            width=1280,
            height=840,
            min_size=(360, 200),
            background_color="#05050A",
            easy_drag=False,
        )
        bridge.window = window

        def _on_window_closing():
            # Release native resources (pygame mixer, worker threads, tray icon,
            # hotkeys, discord RPC, subprocesses) before the process exits,
            # ensuring no file handles remain held when PyInstaller's onefile
            # bootloader removes its temp extraction folder.
            try:
                bridge.cleanup()
            except Exception:
                pass

        window.events.closing += _on_window_closing
        import atexit
        atexit.register(lambda: getattr(bridge, "cleanup", lambda: None)())

        webview.start(http_server=True, debug=False, gui="edgechromium")
    except Exception as e:
        print(f"[NexusTube] Webview fatal error: {e}, falling back to legacy Tkinter UI")
        try:
            for win in list(getattr(webview, "windows", [])):
                try:
                    win.destroy()
                except Exception:
                    pass
        except Exception:
            pass
        App(is_fallback=True).mainloop()


if __name__ == "__main__":
    run_app()

