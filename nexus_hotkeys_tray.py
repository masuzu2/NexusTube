"""
NexusTube — Global Media Hotkeys & Windows System Tray
Lightweight, native Win32 system-wide media keyboard shortcuts and system tray menu.
"""

import os
import sys
import threading
import time

is_win = sys.platform == "win32"
if is_win:
    import ctypes
    from ctypes import wintypes
else:
    ctypes = None
    wintypes = None


class GlobalMediaHotkeys:
    """
    Background daemon listener for system-wide media hotkeys.
    Responds to Play/Pause, Next, Previous, Stop, Volume, and custom shortcuts
    across all running apps on Windows.
    """

    VK_MEDIA_NEXT = 0xB0
    VK_MEDIA_PREV = 0xB1
    VK_MEDIA_STOP = 0xB2
    VK_MEDIA_PLAY_PAUSE = 0xB3
    VK_VOLUME_MUTE = 0xAD
    VK_VOLUME_DOWN = 0xAE
    VK_VOLUME_UP = 0xAF

    VK_CONTROL = 0x11
    VK_MENU = 0x12  # Alt
    VK_SPACE = 0x20
    VK_LEFT = 0x25
    VK_RIGHT = 0x27
    VK_UP = 0x26
    VK_DOWN = 0x28
    VK_KEY_M = 0x4D

    def __init__(self, callbacks=None, enabled=True):
        """
        callbacks: dict mapping action names ('play_pause', 'next', 'prev', 'stop', 'volume_up', 'volume_down', 'toggle_mini')
                   to callable functions.
        """
        self.callbacks = callbacks or {}
        self.enabled = bool(enabled)
        self._running = False
        self._thread = None
        self._key_states = {}

    def start(self):
        if not is_win or not self.enabled:
            return
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="NexusHotkeys")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        if self.enabled and not self._running:
            self.start()
        elif not self.enabled and self._running:
            self.stop()

    def _is_pressed(self, vk):
        if not ctypes:
            return False
        state = ctypes.windll.user32.GetAsyncKeyState(vk)
        return bool(state & 0x8000)

    def _trigger(self, action):
        cb = self.callbacks.get(action)
        if cb and callable(cb):
            try:
                threading.Thread(target=cb, daemon=True).start()
            except Exception:
                pass

    def _poll_loop(self):
        user32 = ctypes.windll.user32 if ctypes else None
        if not user32:
            return

        tracked_single = [
            (self.VK_MEDIA_PLAY_PAUSE, "play_pause"),
            (self.VK_MEDIA_NEXT, "next"),
            (self.VK_MEDIA_PREV, "prev"),
            (self.VK_MEDIA_STOP, "stop"),
        ]

        combo_states = {
            "space": False,
            "right": False,
            "left": False,
            "m": False,
        }

        while self._running:
            try:
                # 1. Single-key Media Keys
                for vk, action in tracked_single:
                    pressed = bool(user32.GetAsyncKeyState(vk) & 0x8000)
                    was_pressed = self._key_states.get(vk, False)
                    self._key_states[vk] = pressed
                    if pressed and not was_pressed:
                        self._trigger(action)

                # 2. Key Combos (Ctrl + Alt + ...)
                ctrl_down = bool(user32.GetAsyncKeyState(self.VK_CONTROL) & 0x8000)
                alt_down = bool(user32.GetAsyncKeyState(self.VK_MENU) & 0x8000)

                if ctrl_down and alt_down:
                    # Space -> play/pause
                    sp_down = bool(user32.GetAsyncKeyState(self.VK_SPACE) & 0x8000)
                    if sp_down and not combo_states["space"]:
                        self._trigger("play_pause")
                    combo_states["space"] = sp_down

                    # Right -> next
                    rt_down = bool(user32.GetAsyncKeyState(self.VK_RIGHT) & 0x8000)
                    if rt_down and not combo_states["right"]:
                        self._trigger("next")
                    combo_states["right"] = rt_down

                    # Left -> prev
                    lt_down = bool(user32.GetAsyncKeyState(self.VK_LEFT) & 0x8000)
                    if lt_down and not combo_states["left"]:
                        self._trigger("prev")
                    combo_states["left"] = lt_down

                    # M -> toggle mini player
                    m_down = bool(user32.GetAsyncKeyState(self.VK_KEY_M) & 0x8000)
                    if m_down and not combo_states["m"]:
                        self._trigger("toggle_mini")
                    combo_states["m"] = m_down
                else:
                    combo_states["space"] = False
                    combo_states["right"] = False
                    combo_states["left"] = False
                    combo_states["m"] = False

                time.sleep(0.04)  # 25 Hz low overhead polling
            except Exception:
                time.sleep(0.1)


class SystemTrayIcon:
    """
    Windows System Tray icon integration using Win32 Shell_NotifyIconW.
    Provides context menu, click-to-restore, and background minimized mode.
    """

    WM_USER = 0x0400
    WM_TRAYICON = WM_USER + 20
    NIM_ADD = 0x00000000
    NIM_MODIFY = 0x00000001
    NIM_DELETE = 0x00000002
    NIF_MESSAGE = 0x00000001
    NIF_ICON = 0x00000002
    NIF_TIP = 0x00000004
    NIF_INFO = 0x00000010

    WM_LBUTTONUP = 0x0202
    WM_LBUTTONDBLCLK = 0x0203
    WM_RBUTTONUP = 0x0205

    ID_RESTORE = 1001
    ID_PLAY_PAUSE = 1002
    ID_NEXT = 1003
    ID_PREV = 1004
    ID_EXIT = 1005

    def __init__(self, icon_path=None, tooltip="NexusTube", on_restore=None, on_action=None, enabled=True):
        self.icon_path = icon_path
        self.tooltip = tooltip[:127]
        self.on_restore = on_restore
        self.on_action = on_action
        self.enabled = bool(enabled)
        self._hwnd = None
        self._running = False
        self._thread = None
        self._icon_loaded = False
        self._hicon = None

    def start(self):
        if not is_win or not self.enabled:
            return
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="NexusTray")
        self._thread.start()

    def stop(self):
        self._running = False
        if is_win and ctypes and self._hwnd:
            try:
                ctypes.windll.user32.PostMessageW(self._hwnd, 0x0010, 0, 0)  # WM_CLOSE
            except Exception:
                pass
        if self._thread and self._thread.is_alive() and threading.current_thread() != self._thread:
            try:
                self._thread.join(timeout=0.5)
            except Exception:
                pass


    def update_tooltip(self, text):
        self.tooltip = str(text)[:127]
        if not is_win or not ctypes or not self._hwnd:
            return
        try:
            self._modify_tray()
        except Exception:
            pass

    def _modify_tray(self):
        if not is_win or not ctypes:
            return

        class NOTIFYICONDATAW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT),
                ("uFlags", wintypes.UINT),
                ("uCallbackMessage", wintypes.UINT),
                ("hIcon", wintypes.HICON),
                ("szTip", wintypes.WCHAR * 128),
                ("dwState", wintypes.DWORD),
                ("dwStateMask", wintypes.DWORD),
                ("szInfo", wintypes.WCHAR * 256),
                ("uTimeoutOrVersion", wintypes.UINT),
                ("szInfoTitle", wintypes.WCHAR * 64),
                ("dwInfoFlags", wintypes.DWORD),
            ]

        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self._hwnd
        nid.uID = 1
        nid.uFlags = self.NIF_ICON | self.NIF_TIP
        nid.hIcon = self._hicon if self._hicon else ctypes.windll.user32.LoadIconW(0, 32512)
        nid.szTip = self.tooltip
        ctypes.windll.shell32.Shell_NotifyIconW(self.NIM_MODIFY, ctypes.byref(nid))

    def _run_loop(self):
        if not is_win or not ctypes:
            return

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        shell32 = ctypes.windll.shell32

        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.DefWindowProcW.restype = ctypes.c_longlong
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID
        ]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.DestroyWindow.restype = wintypes.BOOL
        user32.DestroyIcon.argtypes = [wintypes.HICON]
        user32.DestroyIcon.restype = wintypes.BOOL
        user32.LoadImageW.argtypes = [
            wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
            ctypes.c_int, ctypes.c_int, wintypes.UINT
        ]
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
        user32.LoadIconW.restype = wintypes.HICON
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.PostMessageW.restype = wintypes.BOOL
        user32.PostQuitMessage.argtypes = [ctypes.c_int]
        user32.PostQuitMessage.restype = None

        class NOTIFYICONDATAW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT),
                ("uFlags", wintypes.UINT),
                ("uCallbackMessage", wintypes.UINT),
                ("hIcon", wintypes.HICON),
                ("szTip", wintypes.WCHAR * 128),
                ("dwState", wintypes.DWORD),
                ("dwStateMask", wintypes.DWORD),
                ("szInfo", wintypes.WCHAR * 256),
                ("uTimeoutOrVersion", wintypes.UINT),
                ("szInfoTitle", wintypes.WCHAR * 64),
                ("dwInfoFlags", wintypes.DWORD),
            ]

        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

        def wndproc(hwnd, msg, wparam, lparam):
            try:
                if msg == self.WM_TRAYICON:
                    if lparam in (self.WM_LBUTTONUP, self.WM_LBUTTONDBLCLK):
                        if self.on_restore:
                            try:
                                self.on_restore()
                            except Exception:
                                pass
                    elif lparam == self.WM_RBUTTONUP:
                        # Show Context Menu
                        pt = wintypes.POINT()
                        user32.GetCursorPos(ctypes.byref(pt))
                        hmenu = user32.CreatePopupMenu()
                        MF_STRING = 0x00000000
                        MF_SEPARATOR = 0x00000800
                        MF_GRAYED = 0x00000001

                        user32.AppendMenuW(hmenu, MF_GRAYED, 0, "NexusTube v3.4.0")
                        user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
                        user32.AppendMenuW(hmenu, MF_STRING, self.ID_PLAY_PAUSE, "⏯️ Play / Pause")
                        user32.AppendMenuW(hmenu, MF_STRING, self.ID_NEXT, "⏭️ Next Track")
                        user32.AppendMenuW(hmenu, MF_STRING, self.ID_PREV, "⏮️ Previous Track")
                        user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
                        user32.AppendMenuW(hmenu, MF_STRING, self.ID_RESTORE, "🪟 Open NexusTube")
                        user32.AppendMenuW(hmenu, MF_STRING, self.ID_EXIT, "❌ Exit")

                        user32.SetForegroundWindow(hwnd)
                        cmd = user32.TrackPopupMenuEx(hmenu, 0x0100, pt.x, pt.y, hwnd, None)  # TPM_RETURNCMD
                        user32.DestroyMenu(hmenu)

                        if cmd == self.ID_RESTORE and self.on_restore:
                            self.on_restore()
                        elif cmd == self.ID_PLAY_PAUSE and self.on_action:
                            self.on_action("play_pause")
                        elif cmd == self.ID_NEXT and self.on_action:
                            self.on_action("next")
                        elif cmd == self.ID_PREV and self.on_action:
                            self.on_action("prev")
                        elif cmd == self.ID_EXIT and self.on_action:
                            self.on_action("exit")

                    return 0
                elif msg == 0x0010:  # WM_CLOSE
                    try:
                        nid = NOTIFYICONDATAW()
                        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
                        nid.hWnd = hwnd
                        nid.uID = 1
                        shell32.Shell_NotifyIconW(self.NIM_DELETE, ctypes.byref(nid))
                    except Exception:
                        pass
                    user32.DestroyWindow(hwnd)
                    return 0
                elif msg == 0x0002:  # WM_DESTROY
                    user32.PostQuitMessage(0)
                    return 0
            except Exception:
                pass
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wndproc_cb = WNDPROC(wndproc)

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [
                ("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        hinst = kernel32.GetModuleHandleW(None)
        class_name = f"NexusTubeTrayWndClass_{int(time.time()*1000)}"

        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wndproc_cb
        wc.hInstance = hinst
        wc.lpszClassName = class_name
        user32.RegisterClassW(ctypes.byref(wc))

        hwnd = user32.CreateWindowExW(
            0, class_name, "NexusTubeTrayWindow", 0, 0, 0, 0, 0, 0, 0, hinst, None
        )
        self._hwnd = hwnd

        # Load Icon
        hicon = None
        self._custom_icon = False
        if self.icon_path and os.path.exists(self.icon_path):
            IMAGE_ICON = 1
            LR_LOADFROMFILE = 0x00000010
            hicon = user32.LoadImageW(0, os.path.abspath(self.icon_path), IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
            if hicon:
                self._custom_icon = True
        if not hicon:
            hicon = user32.LoadIconW(0, wintypes.LPCWSTR(32512))  # IDI_APPLICATION
            self._custom_icon = False
        self._hicon = hicon

        # Add Notify Icon
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = hwnd
        nid.uID = 1
        nid.uFlags = self.NIF_MESSAGE | self.NIF_ICON | self.NIF_TIP
        nid.uCallbackMessage = self.WM_TRAYICON
        nid.hIcon = hicon
        nid.szTip = self.tooltip
        shell32.Shell_NotifyIconW(self.NIM_ADD, ctypes.byref(nid))

        # Message Loop
        msg = wintypes.MSG()
        while self._running:
            res = user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
            if res <= 0:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        # Cleanup
        try:
            nid = NOTIFYICONDATAW()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
            nid.hWnd = hwnd
            nid.uID = 1
            shell32.Shell_NotifyIconW(self.NIM_DELETE, ctypes.byref(nid))
        except Exception:
            pass
        try:
            user32.UnregisterClassW(class_name, hinst)
        except Exception:
            pass
        if self._hicon and getattr(self, "_custom_icon", False):
            try:
                user32.DestroyIcon(self._hicon)
            except Exception:
                pass
        self._hicon = None
        self._hwnd = None

