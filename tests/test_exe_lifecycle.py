"""
Integration and End-to-End Lifecycle Tests for NexusTube.exe
============================================================
Automated testing of the built PyInstaller onefile binary:
1. Locates dist/NexusTube.exe or NexusTube.exe in repository root.
2. Validates PE headers, machine architecture (x64), and GUI subsystem (no console window).
3. Launches the binary, detects the main UI window, and ensures zero warning/error popups appear.
4. Dispatches WM_CLOSE message to initiate graceful shutdown.
5. Verifies clean exit code 0 and verifies that the PyInstaller temporary extraction folder
   (%TEMP%\\_MEI*) is deleted cleanly without file locks (WinError 5 / Access Denied).
"""

import ctypes
from ctypes import wintypes
import os
import struct
import subprocess
import sys
import tempfile
import time
import unittest

# Ensure repo root is on sys.path
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)


TH32CS_SNAPPROCESS = 0x00000002

class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_char * 260),
    ]

def get_descendant_pids(root_pid):
    """Retrieve root_pid and all child/descendant process IDs via Toolhelp32."""
    if not root_pid or sys.platform != "win32":
        return set()
    k32 = ctypes.windll.kernel32
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == -1 or snap == 0xFFFFFFFF:
        return {root_pid}
    entry = PROCESSENTRY32()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
    descendants = {root_pid}
    proc_list = []
    if k32.Process32First(snap, ctypes.byref(entry)):
        while True:
            proc_list.append((entry.th32ProcessID, entry.th32ParentProcessID))
            if not k32.Process32Next(snap, ctypes.byref(entry)):
                break
    k32.CloseHandle(snap)
    changed = True
    while changed:
        changed = False
        for pid, ppid in proc_list:
            if ppid in descendants and pid not in descendants:
                descendants.add(pid)
                changed = True
    return descendants


def find_nexus_exe():
    """Locate dist/NexusTube.exe or root NexusTube.exe."""
    candidates = [
        os.path.join(repo_root, "dist", "NexusTube.exe"),
        os.path.join(repo_root, "NexusTube.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c) and os.path.getsize(c) > 1024 * 1024:
            return c
    return None


class TestExeLifecycle(unittest.TestCase):
    def setUp(self):
        if sys.platform != "win32":
            self.skipTest("EXE Lifecycle testing requires Windows OS.")
        self.exe_path = find_nexus_exe()
        if not self.exe_path:
            self.skipTest("NexusTube.exe not found in dist/ or repository root.")
        self.proc = None

    def tearDown(self):
        if self.proc and self.proc.poll() is None:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(self.proc.pid)],
                    capture_output=True,
                    timeout=5,
                )
            except Exception:
                try:
                    self.proc.kill()
                    self.proc.wait(timeout=3)
                except Exception:
                    pass

    def test_exe_pe_headers_and_subsystem(self):
        """Verify binary format: MZ header, PE32+ (x64), and GUI subsystem (subsystem == 2)."""
        self.assertTrue(os.path.exists(self.exe_path))
        file_size = os.path.getsize(self.exe_path)
        # Should be a fully bundled binary (> 25 MB)
        self.assertGreater(file_size, 25 * 1024 * 1024, f"Binary size {file_size} is unexpectedly small")

        with open(self.exe_path, "rb") as f:
            header = f.read(4096)

        # 1. DOS 'MZ' Header
        self.assertEqual(header[:2], b"MZ", "Executable must start with MZ signature")

        # 2. PE Header
        e_lfanew = struct.unpack_from("<I", header, 0x3C)[0]
        self.assertEqual(header[e_lfanew : e_lfanew + 4], b"PE\x00\x00", "Must have valid PE signature")

        # 3. Machine type: IMAGE_FILE_MACHINE_AMD64 = 0x8664
        machine = struct.unpack_from("<H", header, e_lfanew + 4)[0]
        self.assertEqual(machine, 0x8664, "Binary must target AMD64/x64 architecture")

        # 4. Optional Header Magic: 0x20b = PE32+ (64-bit)
        opt_magic = struct.unpack_from("<H", header, e_lfanew + 24)[0]
        self.assertEqual(opt_magic, 0x20B, "Binary must be PE32+ (64-bit)")

        # 5. Windows Subsystem: IMAGE_SUBSYSTEM_WINDOWS_GUI = 2 (console=False)
        subsystem = struct.unpack_from("<H", header, e_lfanew + 24 + 68)[0]
        self.assertEqual(
            subsystem, 2, "Binary must be built with GUI subsystem (subsystem=2) to suppress console window"
        )

    def test_exe_lifecycle_wm_close_and_temp_cleanup(self):
        """Launch NexusTube.exe, verify 0 warning popups, send WM_CLOSE, verify exit 0, and verify %TEMP%\\_MEI* cleanup."""
        user32 = ctypes.windll.user32
        WM_CLOSE = 0x0010

        temp_dir = tempfile.gettempdir()
        initial_meis = set(
            d for d in os.listdir(temp_dir)
            if d.startswith("_MEI") and os.path.isdir(os.path.join(temp_dir, d))
        )

        # Launch the EXE
        self.proc = subprocess.Popen([self.exe_path])
        self.assertIsNotNone(self.proc.pid)

        detected_mei = None
        main_hwnd = None
        warning_popups = []
        target_pids = {self.proc.pid}

        start_time = time.time()
        timeout_seconds = 30.0

        def enum_window_callback(hwnd, _):
            nonlocal main_hwnd
            if not user32.IsWindowVisible(hwnd):
                return True

            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

            # Only inspect windows belonging to this process or its children
            if pid.value not in target_pids:
                return True

            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value

            class_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, class_buf, 256)
            class_name = class_buf.value

            # Detect main window
            if "NexusTube" in title and not main_hwnd:
                main_hwnd = hwnd

            # Detect unexpected error / warning dialogs (#32770 is standard Windows dialog)
            lower_title = title.lower()
            if class_name == "#32770" or any(err_kw in lower_title for err_kw in ["error", "warning", "fatal", "crash", "tclerror"]):
                warning_popups.append({
                    "hwnd": hwnd,
                    "title": title,
                    "class": class_name,
                    "pid": pid.value,
                })

            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        enum_proc = WNDENUMPROC(enum_window_callback)

        while time.time() - start_time < timeout_seconds:
            # Dynamically refresh child processes of NexusTube
            target_pids = get_descendant_pids(self.proc.pid)

            # Check for newly created _MEI directory
            current_meis = set(
                d for d in os.listdir(temp_dir)
                if d.startswith("_MEI") and os.path.isdir(os.path.join(temp_dir, d))
            ) - initial_meis
            if current_meis and not detected_mei:
                detected_mei = list(current_meis)[0]

            # Enumerate top-level windows
            user32.EnumWindows(enum_proc, 0)

            if main_hwnd:
                break

            # If the process already terminated prematurely, abort loop
            if self.proc.poll() is not None:
                break

            time.sleep(0.4)

        # 1. Ensure binary did not fail or crash on startup
        self.assertIsNone(
            self.proc.poll(),
            f"Process exited prematurely before window was detected (return code: {self.proc.returncode})"
        )
        self.assertIsNotNone(main_hwnd, "Main NexusTube window must appear within timeout")
        self.assertEqual(len(warning_popups), 0, f"Expected 0 warning/error popups, found: {warning_popups}")

        # 2. Dispatch WM_CLOSE to initiate graceful application exit
        user32.PostMessageW(main_hwnd, WM_CLOSE, 0, 0)

        # 3. Wait for process exit and verify clean exit code 0
        try:
            exit_code = self.proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.fail("NexusTube.exe did not exit within timeout following WM_CLOSE")

        self.assertEqual(exit_code, 0, f"NexusTube.exe must exit with code 0 on WM_CLOSE, got {exit_code}")

        # 4. Verify temporary extraction directory (%TEMP%\\_MEI*) is deleted cleanly
        if detected_mei:
            mei_full_path = os.path.join(temp_dir, detected_mei)
            # PyInstaller bootloader cleans up the folder immediately before process exit,
            # allow brief grace period (up to 5s) for any asynchronous file handle release
            cleanup_success = False
            for _ in range(25):
                if not os.path.exists(mei_full_path):
                    cleanup_success = True
                    break
                time.sleep(0.2)

            self.assertTrue(
                cleanup_success,
                f"PyInstaller temporary extraction folder {mei_full_path} was not cleanly deleted upon exit"
            )


if __name__ == "__main__":
    unittest.main()
