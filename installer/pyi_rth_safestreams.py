# -*- coding: utf-8 -*-
"""
NexusTube PyInstaller Early Runtime Hook: Safe Streams & Crash Logger
Guarantees sys.stdout and sys.stderr are NEVER None in windowed (--noconsole) mode,
preventing AttributeError: 'NoneType' object has no attribute 'write'.
Also initializes file-based runtime logging and unhandled crash handler.
"""
import sys
import os

class _SafeStream:
    def __init__(self, log_path=None, original=None):
        self._log_path = log_path
        self._original = original
        self.encoding = 'utf-8'
        self.errors = 'replace'

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
                with open(self._log_path, 'a', encoding='utf-8', errors='replace') as f:
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


def _setup_safe_streams():
    appdata = os.environ.get('APPDATA', '')
    if appdata:
        log_dir = os.path.join(appdata, 'NexusTube', 'logs')
    else:
        log_dir = os.path.join(os.path.expanduser('~'), '.nexustube', 'logs')

    try:
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, 'runtime.log')
    except Exception:
        log_file = None

    if sys.stdout is None:
        sys.stdout = _SafeStream(log_file, None)
    if sys.stderr is None:
        sys.stderr = _SafeStream(log_file, None)

    # Windows DLL directory registration
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass and hasattr(os, 'add_dll_directory'):
        try:
            os.add_dll_directory(meipass)
        except Exception:
            pass

_setup_safe_streams()


def _setup_font_redirection_and_cleanup():
    r"""
    Prevents PyInstaller onefile 'Failed to remove temporary directory: ...\_MEIxxxx' warning.
    Root cause: CustomTkinter loads fonts (.otf, .ttf) into Windows GDI via AddFontResourceExW.
    Windows GDI kernel subsystem keeps the font file locked, preventing the PyInstaller bootloader
    from removing the _MEIPASS extraction folder on exit.
    Fix:
      1. Intercept AddFontResourceExW / AddFontResourceExA calls and CustomTkinter FontManager
         so that any font originating inside _MEIPASS or temp directories is copied to and
         loaded from persistent storage (%LOCALAPPDATA%\NexusTube\fonts).
      2. Windows GDI only locks the persistent copy, leaving _MEIPASS completely free to delete.
      3. Clean up older abandoned _MEI folders left by previous runs across all short/long temp paths.
    """
    if sys.platform != 'win32':
        return

    import atexit
    import shutil
    import tempfile

    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return

    meipass = getattr(sys, '_MEIPASS', None)
    temp_dir = tempfile.gettempdir()
    loaded_fonts = []

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
                return arg.decode('utf-8', errors='replace')
            except Exception:
                return None
        obj = getattr(arg, '_obj', None)
        if obj is not None:
            val = getattr(obj, 'value', None)
            if isinstance(val, (str, bytes)):
                return _extract_path(val)
        val = getattr(arg, 'value', None)
        if isinstance(val, (str, bytes)):
            return _extract_path(val)
        return None

    def _is_temp_or_meipass(raw_path):
        if not raw_path or not isinstance(raw_path, str):
            return False
        p_lower = raw_path.lower().replace('/', '\\')
        if '\\_mei' in p_lower or '/_mei' in p_lower or '_mei' in p_lower:
            return True
        if 'customtkinter' in p_lower and ('.ttf' in p_lower or '.otf' in p_lower or 'roboto' in p_lower or 'shape' in p_lower):
            return True
        check_dirs = [temp_dir, os.environ.get('TEMP'), os.environ.get('TMP'), meipass]
        for td in check_dirs:
            if not td:
                continue
            for cand in (td, _get_long_path(td), _get_short_path(td)):
                if cand:
                    cand_norm = cand.lower().replace('/', '\\')
                    if cand_norm in p_lower:
                        return True
        return False

    def _get_persistent_font_path(raw_path):
        if not raw_path or not isinstance(raw_path, str):
            return None
        if not _is_temp_or_meipass(raw_path):
            return None
        local_appdata = (
            os.environ.get('LOCALAPPDATA')
            or os.environ.get('APPDATA')
            or os.path.expanduser('~')
        )
        persistent_dir = os.path.join(local_appdata, 'NexusTube', 'fonts')
        try:
            os.makedirs(persistent_dir, exist_ok=True)
            dest = os.path.join(persistent_dir, os.path.basename(raw_path))
            if not os.path.exists(dest) or (os.path.exists(raw_path) and os.path.getsize(dest) != os.path.getsize(raw_path)):
                shutil.copy2(raw_path, dest)
            return dest
        except Exception:
            return None

    # 1. Sweep and clean older abandoned _MEI* temp folders across short/long paths
    try:
        import glob
        import time
        sweep_dirs = set()
        for d in [temp_dir, os.environ.get('TEMP'), os.environ.get('TMP')]:
            if d:
                sweep_dirs.add(d)
                sweep_dirs.add(_get_long_path(d))
                sweep_dirs.add(_get_short_path(d))

        active_meis = set()
        if meipass:
            active_meis.add(os.path.normcase(os.path.normpath(meipass)))
            active_meis.add(os.path.normcase(os.path.normpath(_get_long_path(meipass))))
            active_meis.add(os.path.normcase(os.path.normpath(_get_short_path(meipass))))

        for sdir in sweep_dirs:
            if not sdir or not os.path.isdir(sdir):
                continue
            for item in glob.glob(os.path.join(sdir, '_MEI*')):
                try:
                    norm_item = os.path.normcase(os.path.normpath(item))
                    if norm_item in active_meis:
                        continue
                    if os.path.isdir(item) and (time.time() - os.path.getmtime(item) > 30):
                        shutil.rmtree(item, ignore_errors=True)
                        if os.path.exists(item):
                            MOVEFILE_DELAY_UNTIL_REBOOT = 0x00000004
                            for root, dirs, files in os.walk(item, topdown=False):
                                for f in files:
                                    try:
                                        ctypes.windll.kernel32.MoveFileExW(
                                            os.path.join(root, f), None, MOVEFILE_DELAY_UNTIL_REBOOT
                                        )
                                    except Exception:
                                        pass
                                for subd in dirs:
                                    try:
                                        ctypes.windll.kernel32.MoveFileExW(
                                            os.path.join(root, subd), None, MOVEFILE_DELAY_UNTIL_REBOOT
                                        )
                                    except Exception:
                                        pass
                            try:
                                ctypes.windll.kernel32.MoveFileExW(item, None, MOVEFILE_DELAY_UNTIL_REBOOT)
                            except Exception:
                                pass
                except Exception:
                    pass
    except Exception:
        pass

    # 2. Hook GDI AddFontResourceExW and AddFontResourceExA
    try:
        gdi32 = ctypes.windll.gdi32
        orig_add_w = gdi32.AddFontResourceExW
        orig_add_a = getattr(gdi32, 'AddFontResourceExA', None)

        def hooked_add_w(byref_buf, flags=0x10, pdv=0):
            raw_path = _extract_path(byref_buf)
            if raw_path and _is_temp_or_meipass(raw_path):
                p_path = _get_persistent_font_path(raw_path)
                if p_path:
                    loaded_fonts.append((p_path, flags, True))
                    if isinstance(byref_buf, str):
                        return orig_add_w(p_path, flags, pdv)
                    new_buf = ctypes.create_unicode_buffer(p_path)
                    return orig_add_w(ctypes.byref(new_buf), flags, pdv)
            if raw_path:
                loaded_fonts.append((raw_path, flags, True))
            return orig_add_w(byref_buf, flags, pdv)

        def hooked_add_a(byref_buf, flags=0x10, pdv=0):
            raw_path = _extract_path(byref_buf)
            if raw_path and _is_temp_or_meipass(raw_path):
                p_path = _get_persistent_font_path(raw_path)
                if p_path:
                    loaded_fonts.append((p_path, flags, False))
                    if isinstance(byref_buf, (str, bytes)):
                        enc = p_path.encode('utf-8', errors='replace')
                        return orig_add_a(enc, flags, pdv)
                    new_buf = ctypes.create_string_buffer(p_path.encode('utf-8', errors='replace'))
                    return orig_add_a(ctypes.byref(new_buf), flags, pdv)
            if raw_path:
                loaded_fonts.append((raw_path, flags, False))
            return orig_add_a(byref_buf, flags, pdv)

        gdi32.AddFontResourceExW = hooked_add_w
        if orig_add_a:
            gdi32.AddFontResourceExA = hooked_add_a

        def _cleanup_fonts():
            for fpath, flags, is_wide in list(loaded_fonts):
                try:
                    if is_wide:
                        buf = ctypes.create_unicode_buffer(fpath)
                        gdi32.RemoveFontResourceExW(ctypes.byref(buf), flags, 0)
                    else:
                        buf = ctypes.create_string_buffer(fpath.encode('utf-8', errors='replace'))
                        gdi32.RemoveFontResourceExA(ctypes.byref(buf), flags, 0)
                except Exception:
                    pass
            loaded_fonts.clear()

        atexit.register(_cleanup_fonts)
    except Exception:
        pass


_setup_font_redirection_and_cleanup()

