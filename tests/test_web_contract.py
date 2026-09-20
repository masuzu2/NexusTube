"""
Web UI & Bridge Contract Test Suite
===================================
Verifies:
1. Complete IPC contract parity: All JavaScript `window.pywebview.api.*` calls
   in `web/app.js` and other web assets have corresponding methods on `NexusBridgeAPI`.
2. Bridge reflection safety: `bridge.window` does NOT appear in `dir(bridge)`
   to prevent pywebview recursion or object leaks.
3. Bridge core contract API returns: `get_initial_state`, `get_player_state`,
   `get_queue_state`, `get_library`, and `get_engine_status` conform to the expected schemas.
4. Web UI assets integrity: `index.html`, `app.js`, `styles.css`, and `tailwind.js`
   exist, are non-empty, use valid UTF-8 encoding, and have intact references.
5. DOM contract integrity: Core element IDs accessed by `app.js` exist in `index.html`.
"""

import glob
import inspect
import os
import re
import sys
import unittest

# Ensure repo root is on sys.path
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from YT_Downloader_V2 import NexusBridgeAPI


class TestWebContractAndBridge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.web_dir = os.path.join(repo_root, "web")
        cls.app_js_path = os.path.join(cls.web_dir, "app.js")
        cls.index_html_path = os.path.join(cls.web_dir, "index.html")
        cls.styles_css_path = os.path.join(cls.web_dir, "styles.css")
        cls.tailwind_js_path = os.path.join(cls.web_dir, "tailwind.js")

        with open(cls.app_js_path, "r", encoding="utf-8") as f:
            cls.app_js_content = f.read()
        with open(cls.index_html_path, "r", encoding="utf-8") as f:
            cls.index_html_content = f.read()

        cls.bridge = NexusBridgeAPI(auto_check=False)

    def test_web_assets_existence_and_sizes(self):
        """Verify all core web assets exist, are non-empty, and exceed minimum viable size."""
        required_assets = {
            self.index_html_path: 10 * 1024,   # > 10 KB
            self.app_js_path: 50 * 1024,       # > 50 KB
            self.styles_css_path: 10 * 1024,   # > 10 KB
            self.tailwind_js_path: 100 * 1024, # > 100 KB
        }
        for file_path, min_size in required_assets.items():
            self.assertTrue(os.path.isfile(file_path), f"Asset missing: {file_path}")
            size = os.path.getsize(file_path)
            self.assertGreater(
                size, min_size,
                f"Asset {os.path.basename(file_path)} too small ({size} bytes < {min_size} bytes)"
            )

    def test_web_assets_utf8_encoding(self):
        """Ensure all web assets are clean UTF-8 text without corrupted multi-byte sequences."""
        for ext in ("*.html", "*.js", "*.css"):
            for full_path in glob.glob(os.path.join(self.web_dir, ext)):
                with open(full_path, "rb") as f:
                    raw = f.read()
                try:
                    raw.decode("utf-8")
                except UnicodeDecodeError as err:
                    self.fail(f"Corrupt UTF-8 encoding in {os.path.basename(full_path)}: {err}")

    def test_index_html_structure_and_links(self):
        """Verify index.html contains proper HTML5 structure and references all asset scripts and stylesheets."""
        html = self.index_html_content
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("<html", html)
        self.assertIn("<head>", html)
        self.assertIn("<body", html)
        self.assertIn('name="viewport"', html)

        # Asset linkages
        self.assertTrue(
            re.search(r'<script[^>]+src=[\x27\x22]tailwind\.js[\x27\x22]', html),
            "index.html must reference tailwind.js"
        )
        self.assertTrue(
            re.search(r'<link[^>]+href=[\x27\x22]styles\.css[\x27\x22]', html),
            "index.html must reference styles.css"
        )
        self.assertTrue(
            re.search(r'<script[^>]+src=[\x27\x22]app\.js[\x27\x22]', html),
            "index.html must reference app.js"
        )

    def _get_all_web_js_calls(self):
        """Extract all window.pywebview.api.<method> calls across all JS and HTML files in web/."""
        js_calls = set()
        for ext in ("*.js", "*.html"):
            for full_path in glob.glob(os.path.join(self.web_dir, ext)):
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                js_calls.update(re.findall(r"(?:window\.)?pywebview\.api\.([a-zA-Z0-9_]+)", content))
        return js_calls

    def test_all_js_pywebview_api_calls_match_nexus_bridge(self):
        """Extract all window.pywebview.api.* calls across web assets and assert 100% parity with NexusBridgeAPI."""
        js_calls = self._get_all_web_js_calls()

        # Ensure we actually found calls across web assets
        self.assertGreater(
            len(js_calls), 30,
            f"Expected at least 30 pywebview.api calls across web assets, found {len(js_calls)}"
        )

        # Extract all public callable methods from NexusBridgeAPI
        bridge_methods = set(
            m for m in dir(self.bridge)
            if not m.startswith("_") and callable(getattr(self.bridge, m))
        )

        missing_methods = js_calls - bridge_methods
        self.assertEqual(
            missing_methods,
            set(),
            f"JavaScript invokes methods missing from NexusBridgeAPI: {sorted(missing_methods)}"
        )

    def test_bridge_methods_are_callable(self):
        """Ensure all JS API methods mapped to bridge are callable functions."""
        js_calls = self._get_all_web_js_calls()
        for name in js_calls:
            attr = getattr(self.bridge, name, None)
            self.assertIsNotNone(attr, f"Bridge method {name} not found")
            self.assertTrue(
                callable(attr),
                f"Bridge attribute {name} should be callable method"
            )

    def test_bridge_window_reflection_guard(self):
        """Ensure bridge.window does NOT appear in dir(bridge) to prevent pywebview traversal recursion."""
        self.assertNotIn("window", dir(self.bridge))

    def test_get_initial_state_contract(self):
        """Verify get_initial_state returns full expected schema for frontend hydration."""
        state = self.bridge.get_initial_state()
        self.assertIsInstance(state, dict)

        required_keys = [
            "version",
            "config",
            "locales",
            "accents",
            "eq_presets",
            "eq_bands",
            "dsp_effects",
            "favorites",
            "recent_searches",
            "engine_status",
            "discord_rpc",
            "sleep_timer",
            "mini_player",
            "normalize",
        ]
        for key in required_keys:
            self.assertIn(key, state, f"get_initial_state missing key: {key}")

        self.assertIsInstance(state["config"], dict)
        self.assertIsInstance(state["engine_status"], dict)
        self.assertIsInstance(state["locales"], dict)
        self.assertIsInstance(state["accents"], dict)

    def test_get_player_state_contract(self):
        """Verify get_player_state returns valid player fields."""
        player_state = self.bridge.get_player_state()
        self.assertIsInstance(player_state, dict)

        expected_player_keys = [
            "is_playing",
            "is_paused",
            "current_pos",
            "duration",
            "volume",
            "is_muted",
            "repeat_mode",
            "is_shuffle",
            "playback_speed",
            "sleep_timer",
        ]
        for key in expected_player_keys:
            self.assertIn(key, player_state, f"get_player_state missing key: {key}")

    def test_get_queue_and_library_state_contracts(self):
        """Verify get_queue_state and get_library return lists."""
        queue = self.bridge.get_queue_state()
        self.assertIsInstance(queue, list)

        lib = self.bridge.get_library()
        self.assertIsInstance(lib, list)

    def test_get_engine_status_contract(self):
        """Verify get_engine_status returns valid dictionary with all tool readiness flags."""
        status = self.bridge.get_engine_status()
        self.assertIsInstance(status, dict)
        for key in ["ytdlp_ready", "ytdlp_version", "ffmpeg_ready", "ffprobe_ready", "ffplay_ready"]:
            self.assertIn(key, status, f"get_engine_status missing key: {key}")
        self.assertIsInstance(status["ytdlp_ready"], bool)
        self.assertIsInstance(status["ffmpeg_ready"], bool)
        self.assertIsInstance(status["ffprobe_ready"], bool)
        self.assertIsInstance(status["ffplay_ready"], bool)

    def test_get_discord_rpc_and_sleep_timer_contracts(self):
        """Verify get_discord_rpc_status and get_sleep_timer_state schemas."""
        rpc = self.bridge.get_discord_rpc_status()
        self.assertIsInstance(rpc, dict)
        self.assertIn("enabled", rpc)
        self.assertIn("connected", rpc)

        sleep = self.bridge.get_sleep_timer_state()
        self.assertIsInstance(sleep, dict)
        self.assertIn("active", sleep)
        self.assertIn("remaining_seconds", sleep)

    def test_critical_dom_elements_in_index_html(self):
        """Verify critical DOM element IDs used by frontend exist in index.html."""
        html_ids = set(re.findall(r'id=[\x27\x22]([^\x27\x22]+)[\x27\x22]', self.index_html_content))

        essential_ids = [
            "app-root",
            "search-input",
            "btn-execute-search",
            "btn-download-resolved",
            "queue-tasks-list",
            "btn-clear-finished-queue",
            "btn-cancel-all-queue",
            "btn-play-pause",
            "player-title",
            "player-artist",
            "app-version-badge",
            "btn-browse-folder",
            "btn-check-ytdlp-update",
            "btn-export-m3u8",
            "btn-fetch-lyrics",
            "btn-filter-favorites",
            "btn-player-loudnorm",
            "btn-player-mini",
            "btn-quick-eq",
            "accent-colors-container",
            "ambient-visualizer-canvas",
        ]
        missing_ids = [eid for eid in essential_ids if eid not in html_ids]
        self.assertEqual(
            missing_ids,
            [],
            f"Essential DOM elements missing from index.html: {missing_ids}"
        )


if __name__ == "__main__":
    unittest.main()
