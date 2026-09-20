import contextlib
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import nexus_audio
from YT_Downloader_V2 import (
    App,
    NexusBridgeAPI,
    run_app,
    setup_crash_handler,
)


class TestErrorHandlingAndFallbacks(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_config_path = os.path.join(self.test_dir, "test_config.json")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            with contextlib.suppress(Exception):
                import shutil
                shutil.rmtree(self.test_dir)

    def test_setup_crash_handler_installation(self):
        orig_excepthook = sys.excepthook
        try:
            setup_crash_handler()
            self.assertNotEqual(sys.excepthook, orig_excepthook)

            # Test invoking excepthook with KeyboardInterrupt does not crash
            sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)

            # Test invoking excepthook with custom exception writes to crash log
            with patch("ctypes.windll.user32.MessageBoxW", return_value=1):
                try:
                    raise ValueError("Test crash handler exception message")
                except ValueError:
                    exc_type, exc_val, exc_tb = sys.exc_info()
                    sys.excepthook(exc_type, exc_val, exc_tb)

            # Check if nexus_crash.log was created
            if os.path.exists("nexus_crash.log"):
                with open("nexus_crash.log", "r", encoding="utf-8") as f:
                    content = f.read()
                self.assertIn("Test crash handler exception message", content)
                # Cleanup local log
                with contextlib.suppress(Exception):
                    os.remove("nexus_crash.log")
        finally:
            sys.excepthook = orig_excepthook

    def test_bridge_window_reflection_guard(self):
        """Ensure bridge.window does NOT appear in dir(bridge) to prevent pywebview traversal recursion."""
        bridge = NexusBridgeAPI(auto_check=False, config_path=self.test_config_path)
        fake_window = MagicMock()
        bridge.window = fake_window

        self.assertNotIn("window", dir(bridge))
        self.assertEqual(bridge._get_window(), fake_window)
        self.assertEqual(bridge.window, fake_window)

    def test_queue_state_error_and_warning_fields(self):
        """Ensure get_queue_state returns error and warning fields for frontend notification."""
        bridge = NexusBridgeAPI(auto_check=False, config_path=self.test_config_path)
        task_id = "test-task-123"
        bridge.active_tasks[task_id] = {
            "id": task_id,
            "url": "https://example.com/test",
            "title": "Test Title",
            "override_fmt": "mp3_320",
            "status": "failed",
            "percent": 0.5,
            "speed": "",
            "eta": "",
            "thumbnail": "",
            "out_file": None,
            "error": "HTTP Error 403: Forbidden",
            "warning": "Unwritable directory redirected",
        }

        q = bridge.get_queue_state()
        self.assertEqual(len(q), 1)
        self.assertEqual(q[0]["error"], "HTTP Error 403: Forbidden")
        self.assertEqual(q[0]["warning"], "Unwritable directory redirected")

    def test_retry_task_clears_error(self):
        bridge = NexusBridgeAPI(auto_check=False, config_path=self.test_config_path)
        task_id = "task-failed-1"
        bridge.active_tasks[task_id] = {
            "id": task_id,
            "url": "https://example.com/test",
            "title": "Failed Song",
            "status": "failed",
            "percent": 0.0,
            "speed": "",
            "eta": "",
            "out_file": None,
            "cancelled": False,
            "error": "Previous error message",
        }

        with patch.object(bridge, "_download_worker", return_value=None):
            ok = bridge.retry_task(task_id)
            self.assertTrue(ok)
            task = bridge.active_tasks[task_id]
            self.assertIsNone(task["error"])
            self.assertEqual(task["status"], "waiting")
            self.assertFalse(task["cancelled"])

    def test_app_fallback_mode_title_and_indicator(self):
        """Verify App initialization in fallback mode reflects compatibility."""
        with patch.object(App, "mainloop", return_value=None):
            app = App(check_updates=False, is_fallback=True)
            self.assertTrue(app.is_fallback)
            self.assertIn("Compatibility Mode", app.title())
            app.destroy()

    def test_run_app_fallback_on_webview_start_failure(self):
        """Verify run_app cleanly catches webview initialization errors and invokes App(is_fallback=True)."""
        mock_app_instance = MagicMock()
        with patch("sys.argv", ["YT_Downloader_V2.py"]), \
             patch("YT_Downloader_V2.App", return_value=mock_app_instance) as mock_app_cls, \
             patch("webview.create_window", side_effect=RuntimeError("WebView2 COM error")):
            run_app()
            mock_app_cls.assert_called_with(is_fallback=True)
            mock_app_instance.mainloop.assert_called_once()

    def test_resilient_session_and_http_get(self):
        """Verify safe_http_get retries on network failures and handles exceptions safely."""
        with patch("requests.Session.get", side_effect=Exception("Connection refused")):
            resp = nexus_audio.safe_http_get("https://example.invalid/test", timeout=1, max_retries=1)
            self.assertIsNone(resp)

    def test_safe_json_response(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("Malformed JSON")
        data = nexus_audio.safe_json_response(mock_resp, default={"fallback": True})
        self.assertEqual(data, {"fallback": True})

        # Test None response
        data_none = nexus_audio.safe_json_response(None, default=[])
        self.assertEqual(data_none, [])

    def test_safe_float_clamping(self):
        self.assertEqual(nexus_audio._safe_float(5.5, 0.0, -10.0, 10.0), 5.5)
        self.assertEqual(nexus_audio._safe_float(100.0, 0.0, -10.0, 10.0), 10.0)
        self.assertEqual(nexus_audio._safe_float(-50.0, 0.0, -10.0, 10.0), -10.0)
        self.assertEqual(nexus_audio._safe_float("invalid", 3.0, -10.0, 10.0), 3.0)
        self.assertEqual(nexus_audio._safe_float(float("nan"), 2.0, -10.0, 10.0), 2.0)
        self.assertEqual(nexus_audio._safe_float(float("inf"), 2.0, -10.0, 10.0), 2.0)

    def test_download_worker_unwritable_directory_fallback(self):
        """Test _download_worker detects unwritable directory and falls back without crashing."""
        bridge = NexusBridgeAPI(auto_check=False, config_path=self.test_config_path)
        # Point to a path that will fail when creating a test file
        bridge.config["outdir"] = "Z:\\NonexistentDrive\\ForbiddenPath"
        task = {
            "id": "t-dir-fallback",
            "url": "https://example.com/song",
            "title": "Song",
            "status": "waiting",
            "cancelled": False,
            "options": {},
            "metadata": {},
        }

        # Mock subprocess.Popen to immediately succeed
        mock_proc = MagicMock()
        mock_proc.stdout = iter([])
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0

        with patch("subprocess.Popen", return_value=mock_proc), patch("YT_Downloader_V2.show_notify"):
            bridge._download_worker(task)

        self.assertIn("warning", task)
        self.assertIn("Output folder unwritable", task["warning"])
        self.assertEqual(task["status"], "completed")


if __name__ == "__main__":
    unittest.main()
