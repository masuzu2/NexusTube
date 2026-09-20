"""
Unit tests for NexusTube v3.4.0 advanced systems:
1. Discord Rich Presence (RPC) IPC client and presence formatting
2. Global Media Hotkeys & System Tray lifecycle
3. Dynamic Audio Loudness Normalization (dynaudnorm / EBU R128)
4. Sleep Timer with gradual audio fade-out
5. Mini-Player / PiP mode bridge
6. In-App yt-dlp One-Click Updater
"""

import contextlib
import io
import json
import os
import struct
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from nexus_audio import generate_ffmpeg_eq_filter
from nexus_discord import OP_FRAME, DiscordRPC
from nexus_hotkeys_tray import GlobalMediaHotkeys, SystemTrayIcon
from YT_Downloader_V2 import VERSION, NexusBridgeAPI


class TestV340Features(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_config_path = os.path.join(self.test_dir, "test_config_v340.json")
        self.bridge = NexusBridgeAPI(auto_check=False, config_path=self.test_config_path)
        self.bridge.config["outdir"] = self.test_dir

    def tearDown(self):
        self.bridge.player.stop()
        if hasattr(self.bridge, "discord_rpc") and self.bridge.discord_rpc:
            self.bridge.discord_rpc.close()
        if hasattr(self.bridge, "hotkeys") and self.bridge.hotkeys:
            self.bridge.hotkeys.stop()
        if hasattr(self.bridge, "tray") and self.bridge.tray:
            self.bridge.tray.stop()
        if os.path.exists(self.test_dir):
            with contextlib.suppress(Exception):
                import shutil
                shutil.rmtree(self.test_dir)

    # ──────────────────────────────────────────────────────────────────────────
    # 1. Discord Rich Presence (RPC) Tests
    # ──────────────────────────────────────────────────────────────────────────
    def test_discord_rpc_initialization_and_framing(self):
        rpc = DiscordRPC(client_id="123456789012345678", enabled=True)
        self.assertEqual(rpc.client_id, "123456789012345678")
        self.assertTrue(rpc.enabled)
        self.assertFalse(rpc.connected)

        # Test frame serialization
        payload = {"cmd": "SET_ACTIVITY", "args": {"activity": {"details": "Testing"}}}
        encoded = json.dumps(payload).encode("utf-8")
        header = struct.pack("<ii", OP_FRAME, len(encoded))
        self.assertEqual(len(header), 8)
        op, length = struct.unpack("<ii", header)
        self.assertEqual(op, OP_FRAME)
        self.assertEqual(length, len(encoded))

    def test_discord_rpc_update_playback_structure(self):
        rpc = DiscordRPC(enabled=True)
        # Mock the pipe to intercept frame sends
        mock_pipe = io.BytesIO()
        rpc._pipe = mock_pipe
        rpc._connected = True

        rpc.update_playback(
            title="Bohemian Rhapsody",
            artist="Queen",
            duration=354,
            current_pos=42,
            is_playing=True,
            is_paused=False,
            album="A Night at the Opera",
            cover_url="https://example.com/cover.jpg",
        )

        mock_pipe.seek(0)
        data = mock_pipe.read()
        self.assertGreater(len(data), 8)
        op, length = struct.unpack("<ii", data[:8])
        self.assertEqual(op, OP_FRAME)
        body = json.loads(data[8:8 + length].decode("utf-8"))
        self.assertEqual(body["cmd"], "SET_ACTIVITY")
        act = body["args"]["activity"]
        self.assertIn("Bohemian Rhapsody", act["details"])
        self.assertIn("Queen", act["state"])
        self.assertIn("timestamps", act)
        self.assertIn("assets", act)
        self.assertEqual(act["assets"]["large_text"], "A Night at the Opera")

    def test_discord_rpc_toggle_via_bridge(self):
        # Toggle off
        res = self.bridge.toggle_discord_rpc(False)
        self.assertFalse(res)
        status = self.bridge.get_discord_rpc_status()
        self.assertFalse(status["enabled"])

        # Toggle on
        res = self.bridge.toggle_discord_rpc(True)
        self.assertTrue(res)
        status = self.bridge.get_discord_rpc_status()
        self.assertTrue(status["enabled"])

    # ──────────────────────────────────────────────────────────────────────────
    # 2. Global Media Hotkeys & System Tray Tests
    # ──────────────────────────────────────────────────────────────────────────
    def test_global_hotkeys_lifecycle(self):
        cb_called = []
        def on_play():
            cb_called.append("play")

        hotkeys = GlobalMediaHotkeys(callbacks={"play_pause": on_play}, enabled=False)
        self.assertFalse(hotkeys.enabled)
        hotkeys.set_enabled(True)
        self.assertTrue(hotkeys.enabled)

        # Trigger callback directly
        hotkeys._trigger("play_pause")
        time.sleep(0.1)
        self.assertEqual(cb_called, ["play"])

        hotkeys.stop()
        self.assertFalse(hotkeys._running)

    def test_system_tray_lifecycle(self):
        tray = SystemTrayIcon(enabled=False)
        self.assertFalse(tray.enabled)
        tray.update_tooltip("NexusTube Player")
        self.assertIn("NexusTube Player", tray.tooltip)
        tray.enabled = True
        self.assertTrue(tray.enabled)
        tray.stop()
        self.assertFalse(tray._running)

    def test_tray_and_hotkeys_toggle_via_bridge(self):
        # Toggle hotkeys
        h_res = self.bridge.toggle_global_hotkeys(True)
        self.assertTrue(h_res)
        self.assertTrue(self.bridge.config["global_hotkeys"])

        # Toggle system tray
        t_res = self.bridge.toggle_system_tray(False)
        self.assertFalse(t_res)
        self.assertFalse(self.bridge.config["system_tray"])

        # Toggle minimize to tray
        m_res = self.bridge.toggle_minimize_to_tray(True)
        self.assertTrue(m_res)
        self.assertTrue(self.bridge.config["minimize_to_tray"])

    # ──────────────────────────────────────────────────────────────────────────
    # 3. Dynamic Audio Loudness Normalization Tests
    # ──────────────────────────────────────────────────────────────────────────
    def test_dynaudnorm_filter_generation(self):
        bands = {"bass": 0.0, "low_mid": 0.0, "mid": 0.0, "high_mid": 0.0, "treble": 0.0}
        filt_without = generate_ffmpeg_eq_filter(bands, normalize=False)
        self.assertNotIn("dynaudnorm", filt_without)

        filt_with = generate_ffmpeg_eq_filter(bands, normalize=True)
        self.assertIn("dynaudnorm=f=150:g=15:p=0.95:m=10.0", filt_with)

    def test_normalization_toggle_via_bridge(self):
        res = self.bridge.toggle_normalization(True)
        self.assertTrue(res)
        self.assertTrue(self.bridge.player.normalize_audio)
        self.assertTrue(self.bridge.config["normalize"])

        res2 = self.bridge.toggle_normalization(False)
        self.assertFalse(res2)
        self.assertFalse(self.bridge.player.normalize_audio)
        self.assertFalse(self.bridge.config["normalize"])

    # ──────────────────────────────────────────────────────────────────────────
    # 4. Sleep Timer with Gradual Audio Fade-Out Tests
    # ──────────────────────────────────────────────────────────────────────────
    def test_sleep_timer_lifecycle_and_state(self):
        # Set 15 minutes sleep timer
        st = self.bridge.set_sleep_timer(15, fade_out_sec=20)
        self.assertTrue(st["active"])
        self.assertEqual(st["mode"], "15m")
        self.assertGreaterEqual(st["remaining_seconds"], 890)
        self.assertFalse(st["fading"])

        # Check state query
        cur_st = self.bridge.get_sleep_timer_state()
        self.assertTrue(cur_st["active"])

        # Cancel sleep timer
        cancelled_st = self.bridge.cancel_sleep_timer()
        self.assertFalse(cancelled_st["active"])
        self.assertEqual(cancelled_st["remaining_seconds"], 0)

    def test_sleep_timer_end_of_track_mode(self):
        st = self.bridge.set_sleep_timer("end_of_track", fade_out_sec=15)
        self.assertTrue(st["active"])
        self.assertEqual(st["mode"], "end_of_track")
        self.bridge.cancel_sleep_timer()

    # ──────────────────────────────────────────────────────────────────────────
    # 5. Mini-Player / Floating PiP Mode Tests
    # ──────────────────────────────────────────────────────────────────────────
    def test_mini_player_toggle_state(self):
        st = self.bridge.get_mini_player_state()
        self.assertFalse(st["mini_player"])

        # Mock window to verify resize call
        mock_win = MagicMock()
        mock_win.width = 1280
        mock_win.height = 800
        self.bridge._window = mock_win

        res = self.bridge.toggle_mini_player(True)
        self.assertTrue(res["mini_player"])
        mock_win.resize.assert_called_with(400, 230)
        self.assertTrue(mock_win.on_top)

        res2 = self.bridge.toggle_mini_player(False)
        self.assertFalse(res2["mini_player"])
        mock_win.resize.assert_called_with(1280, 800)
        self.assertFalse(mock_win.on_top)
        mock_win.evaluate_js.assert_called_with("if (window.syncMiniPlayerFromBackend) window.syncMiniPlayerFromBackend(false);")

    def test_mini_player_maximized_restoration(self):
        mock_win = MagicMock()
        mock_win.width = 1920
        mock_win.height = 1080
        self.bridge._window = mock_win
        self.bridge._is_maximized = True

        # Enter mini-player while maximized
        res = self.bridge.toggle_mini_player(True)
        self.assertTrue(res["mini_player"])
        mock_win.restore.assert_called()
        mock_win.resize.assert_called_with(400, 230)
        self.assertTrue(self.bridge._was_maximized_before_mini)

        # Restore from mini-player back to maximized
        res2 = self.bridge.toggle_mini_player(False)
        self.assertFalse(res2["mini_player"])
        mock_win.maximize.assert_called()
        self.assertTrue(self.bridge._is_maximized)
        self.assertFalse(self.bridge._was_maximized_before_mini)
        self.assertFalse(mock_win.on_top)

    def test_mini_player_custom_dimensions_and_fallback(self):
        mock_win = MagicMock()
        self.bridge._window = mock_win

        # Pass custom dimensions from JS
        self.bridge.toggle_mini_player(True, width=1600, height=900)
        self.assertEqual(self.bridge._prev_window_size, (1600, 900))
        mock_win.resize.assert_called_with(400, 230)

        # Restore
        self.bridge.toggle_mini_player(False)
        mock_win.resize.assert_called_with(1600, 900)

        # Corrupted small dimension fallback
        self.bridge._prev_window_size = (200, 100)
        self.bridge.toggle_mini_player(False)
        mock_win.resize.assert_called_with(1280, 840)

    def test_mini_player_position_preservation_and_clamping(self):
        mock_win = MagicMock()
        self.bridge._window = mock_win

        # Pass position coordinates from JS
        self.bridge.toggle_mini_player(True, width=1280, height=800, x=300, y=200)
        self.assertEqual(self.bridge._prev_window_pos, (300, 200))
        mock_win.resize.assert_called_with(400, 230)

        # Restore: window should move back to clamped previous position
        self.bridge.toggle_mini_player(False)
        mock_win.move.assert_called()
        clamped_x, clamped_y = mock_win.move.call_args[0]
        self.assertEqual(clamped_x, 300)
        self.assertEqual(clamped_y, 200)
        mock_win.resize.assert_called_with(1280, 800)

    def test_system_tray_restore_exits_mini_player(self):
        mock_win = MagicMock()
        mock_win.width = 1280
        mock_win.height = 800
        self.bridge._window = mock_win

        # Enter mini-player mode
        self.bridge.toggle_mini_player(True)
        self.assertTrue(self.bridge._is_mini_player)

        # Tray restore should cleanly restore full window mode
        self.bridge._restore_from_tray()
        self.assertFalse(self.bridge._is_mini_player)
        mock_win.resize.assert_called_with(1280, 800)

    # ──────────────────────────────────────────────────────────────────────────
    # 6. In-App yt-dlp One-Click Updater Tests
    # ──────────────────────────────────────────────────────────────────────────
    def test_check_ytdlp_update_mocked(self):
        with patch("YT_Downloader_V2.safe_http_get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "tag_name": "2026.09.01",
                "body": "Bug fixes and YouTube updates",
                "html_url": "https://github.com/yt-dlp/yt-dlp/releases/tag/2026.09.01",
            }
            mock_get.return_value = mock_resp

            self.bridge._ytdlp_ver_str = "2026.08.01"
            info = self.bridge.check_ytdlp_update()
            self.assertEqual(info["current_version"], "2026.08.01")
            self.assertEqual(info["latest_version"], "2026.09.01")
            self.assertTrue(info["has_update"])

    def test_update_ytdlp_validation(self):
        with patch("YT_Downloader_V2.safe_http_get") as mock_get:
            # Simulate invalid small download (< 500KB)
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.content = b"Too small payload"
            mock_get.return_value = mock_resp

            res = self.bridge.update_ytdlp()
            self.assertFalse(res["success"])
            self.assertIn("error", res)

    def test_discord_rpc_nonblocking_timeout_guard(self):
        rpc = DiscordRPC(enabled=True)
        rpc._pipe = io.BytesIO()
        t0 = time.time()
        op, data = rpc._read(timeout=0.1)
        t1 = time.time()
        self.assertIsNone(op)
        self.assertIsNone(data)
        self.assertLess(t1 - t0, 0.5)

    def test_sleep_timer_generation_counter_avoids_thread_race(self):
        id1 = self.bridge._sleep_timer_id
        self.bridge.set_sleep_timer(10)
        id2 = self.bridge._sleep_timer_id
        self.assertGreater(id2, id1)
        self.bridge.set_sleep_timer(20)
        id3 = self.bridge._sleep_timer_id
        self.assertGreater(id3, id2)
        self.bridge.cancel_sleep_timer()

    def test_update_ytdlp_busy_download_block(self):
        self.bridge.active_tasks["task_test"] = {"status": "downloading"}
        res = self.bridge.update_ytdlp()
        self.assertFalse(res["success"])
        self.assertIn("active downloads", res["error"])
        del self.bridge.active_tasks["task_test"]

    # ──────────────────────────────────────────────────────────────────────────
    # 7. Version Bump Verification
    # ──────────────────────────────────────────────────────────────────────────
    def test_version_bump_v340(self):
        self.assertEqual(VERSION, "3.4.0")
        init_st = self.bridge.get_initial_state()
        self.assertEqual(init_st.get("version"), "3.4.0")


if __name__ == "__main__":
    unittest.main()
