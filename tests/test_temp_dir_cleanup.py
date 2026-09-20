"""
Unit and integration tests for temporary directory cleanup and font lock prevention.
Verifies that:
1. CustomTkinter fonts originating in PyInstaller _MEIPASS or %TEMP% are redirected
   to persistent storage so Windows GDI does not lock the temporary extraction directory.
2. Short 8.3 paths (e.g. ADMINI~1) and long paths are both recognized and redirected.
3. CustomTkinter FontManager directly loads fonts via redirected paths.
4. Direct string and byref ctypes invocations are both redirected.
5. Mock _MEIPASS directory containing font assets can be deleted cleanly without [WinError 5].
6. SystemTrayIcon starts and shuts down cleanly without access violations.
7. NexusBridgeAPI.cleanup() and AudioPlayer.cleanup() terminate background threads,
   mixer, and subprocesses cleanly without resource leaks.
"""

import ctypes
from ctypes import wintypes
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

# Ensure repo root is on sys.path
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

# Import the core modules under test
from YT_Downloader_V2 import NexusBridgeAPI, AudioPlayer, _setup_safe_font_loading
from nexus_hotkeys_tray import SystemTrayIcon


class TestTempDirCleanup(unittest.TestCase):
    def setUp(self):
        self.temp_dirs = []

    def tearDown(self):
        for d in self.temp_dirs:
            if os.path.exists(d):
                try:
                    shutil.rmtree(d, ignore_errors=True)
                except Exception:
                    pass

    def _get_ctk_font(self):
        import customtkinter
        src_font = os.path.join(
            os.path.dirname(customtkinter.__file__),
            "assets", "fonts", "Roboto", "Roboto-Regular.ttf"
        )
        if not os.path.exists(src_font):
            src_font = os.path.join(
                os.path.dirname(customtkinter.__file__),
                "assets", "fonts", "CustomTkinter_shapes_font.otf"
            )
        self.assertTrue(os.path.exists(src_font), "CustomTkinter font file must exist")
        return src_font

    def test_safe_font_loading_prevents_temp_dir_lock(self):
        """Verifies that font loading from a temp directory redirects outside and permits clean deletion."""
        if sys.platform != "win32":
            self.skipTest("Windows-only GDI font locking test")

        src_font = self._get_ctk_font()

        # 1. Create a mock _MEIPASS folder inside temp
        mock_mei = tempfile.mkdtemp(prefix="_MEI_unit_test_")
        self.temp_dirs.append(mock_mei)

        # 2. Copy font to mock _MEIPASS
        mock_font_dir = os.path.join(mock_mei, "customtkinter", "assets", "fonts")
        os.makedirs(mock_font_dir, exist_ok=True)
        mock_font_path = os.path.join(mock_font_dir, os.path.basename(src_font))
        shutil.copy2(src_font, mock_font_path)

        # 3. Call AddFontResourceExW via ctypes (which is hooked by _setup_safe_font_loading)
        buf = ctypes.create_unicode_buffer(mock_font_path)
        flags = 0x10 | 0x20  # FR_PRIVATE | FR_NOT_ENUM
        res = ctypes.windll.gdi32.AddFontResourceExW(ctypes.byref(buf), flags, 0)

        # 4. Verify mock _MEIPASS can be deleted cleanly without [WinError 5] Access is denied
        deleted = False
        try:
            shutil.rmtree(mock_mei)
            deleted = True
        except Exception as e:
            self.fail(f"Failed to remove temporary directory containing font: {e}")

        self.assertTrue(deleted, "Mock _MEIPASS temporary directory must be removed without error")

    def test_safe_font_loading_short_and_long_paths(self):
        """Verifies that both 8.3 short path and long path formats trigger redirection and deletion."""
        if sys.platform != "win32":
            self.skipTest("Windows-only GDI font locking test")

        src_font = self._get_ctk_font()
        mock_mei = tempfile.mkdtemp(prefix="_MEI_short_long_")
        self.temp_dirs.append(mock_mei)

        mock_font_dir = os.path.join(mock_mei, "fonts")
        os.makedirs(mock_font_dir, exist_ok=True)
        mock_font_path = os.path.join(mock_font_dir, "test_short_long.ttf")
        shutil.copy2(src_font, mock_font_path)

        # Convert to 8.3 short path if available
        buf = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetShortPathNameW(mock_font_path, buf, 1024):
            test_path = buf.value
        else:
            test_path = mock_font_path

        # Call with string directly
        ctypes.windll.gdi32.AddFontResourceExW(test_path, 0x10, 0)

        # Should delete cleanly
        deleted = False
        try:
            shutil.rmtree(mock_mei)
            deleted = True
        except Exception as e:
            self.fail(f"Failed to remove temporary directory with short path: {e}")

        self.assertTrue(deleted, "Short/long path temp directory must be removed without error")

    def test_customtkinter_font_manager_redirection(self):
        """Verifies that customtkinter FontManager.windows_load_font redirects and allows temp dir deletion."""
        if sys.platform != "win32":
            self.skipTest("Windows-only GDI font locking test")

        import customtkinter
        from customtkinter.windows.widgets.font import font_manager

        src_font = self._get_ctk_font()
        mock_mei = tempfile.mkdtemp(prefix="_MEI_ctk_fm_")
        self.temp_dirs.append(mock_mei)

        mock_font_dir = os.path.join(mock_mei, "customtkinter", "assets", "fonts")
        os.makedirs(mock_font_dir, exist_ok=True)
        mock_font_path = os.path.join(mock_font_dir, os.path.basename(src_font))
        shutil.copy2(src_font, mock_font_path)

        # Load through FontManager
        res = font_manager.FontManager.windows_load_font(mock_font_path)

        # Verify folder can be deleted
        deleted = False
        try:
            shutil.rmtree(mock_mei)
            deleted = True
        except Exception as e:
            self.fail(f"Failed to remove temporary directory after FontManager load: {e}")

        self.assertTrue(deleted, "Temp directory loaded via FontManager must be removed without error")

    def test_system_tray_lifecycle_and_shutdown(self):
        """Verifies that SystemTrayIcon starts, processes, and shuts down without access violations."""
        if sys.platform != "win32":
            self.skipTest("Windows-only SystemTray test")

        tray = SystemTrayIcon(icon_path=None, tooltip="TestTray", on_action=None, on_restore=None)
        tray.start()
        import time
        time.sleep(0.3)
        self.assertTrue(tray._running)
        tray.stop()
        time.sleep(0.3)
        self.assertFalse(tray._running)

    def test_audio_player_cleanup(self):
        """Verifies that AudioPlayer.cleanup() stops and resets mixer properly."""
        player = AudioPlayer()
        self.assertTrue(hasattr(player, "cleanup"))
        player.cleanup()
        self.assertFalse(player.is_playing)
        self.assertFalse(player.is_paused)

    def test_nexus_bridge_cleanup(self):
        """Verifies that NexusBridgeAPI.cleanup() can be invoked safely without crashing."""
        bridge = NexusBridgeAPI(auto_check=False)
        self.assertTrue(hasattr(bridge, "cleanup"))

        # Add mock components
        bridge.tray = MagicMock()
        bridge.hotkeys = MagicMock()
        bridge.discord_rpc = MagicMock()
        bridge.player = MagicMock()
        bridge.executor = MagicMock()

        bridge.cleanup()

        bridge.tray.stop.assert_called_once()
        bridge.hotkeys.stop.assert_called_once()
        bridge.discord_rpc.close.assert_called_once()
        bridge.player.cleanup.assert_called_once()
        bridge.executor.shutdown.assert_called_once_with(wait=False, cancel_futures=True)


if __name__ == "__main__":
    unittest.main()
