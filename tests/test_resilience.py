"""
Edge Cases & Resilience Test Suite
==================================
Tests system robustness and self-healing under adverse operating conditions:
1. Network Failures:
   - YouTube search, update checks, lyrics queries, and streaming with network down/timeouts.
   - Safe HTTP request handling against DNS drop, SSLError, ConnectionError, and timeouts.
2. YouTube Rate-Limiting & HTTP Errors:
   - Detection and classification of HTTP 429 (Too Many Requests), bot/age verification challenge,
     HTTP 403 Forbidden, and unavailable/DRM-protected media.
   - Graceful worker state transitions to "failed" with user-friendly explanations (no fatal dialogs).
3. Disk Write Permission Denials:
   - Output directory permission denial triggering automatic fallback redirection to Downloads.
   - PermissionError handling in save_lrc, save_config, export_library_playlist, and audio trimming.
4. Corrupt Media Inputs:
   - get_media_info resilience against 0-byte files, random binary garbage, truncated ID3 headers,
     and nonexistent paths.
   - tag_audio_file robustness against corrupt audio files and malformed cover art bytes.
   - AudioPlayer.load_and_play handling of 0-byte, corrupt, or missing media without runtime crashes.
   - Audio trimmer graceful failure when processing corrupt media.
"""

import builtins
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import requests

# Ensure repo root is on sys.path
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import nexus_audio
from YT_Downloader_V2 import (
    AudioPlayer,
    DownloadUnavailableError,
    FormatNotSupportedError,
    NetworkError,
    NexusBridgeAPI,
    classify_download_error,
    get_media_info,
    tag_audio_file,
)


class TestNetworkFailureResilience(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.test_dir, "test_config.json")
        self.bridge = NexusBridgeAPI(auto_check=False, config_path=self.config_path)

    def tearDown(self):
        self.bridge.cleanup()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_search_youtube_network_connection_error(self):
        """Verify search_youtube returns empty list when network or tool execution fails."""
        with patch("YT_Downloader_V2.run_external_tool", side_effect=OSError("Network connection refused")):
            results = self.bridge.search_youtube("Alan Walker Faded")
            self.assertIsInstance(results, list)
            self.assertEqual(len(results), 0)

    def test_search_youtube_network_timeout(self):
        """Verify search_youtube handles external tool timeout cleanly without crashing."""
        mock_proc = MagicMock()
        mock_proc.stdout = ""
        mock_proc.stderr = "Connection timed out after 30000ms"
        mock_proc.returncode = 1
        with patch("YT_Downloader_V2.run_external_tool", return_value=mock_proc):
            results = self.bridge.search_youtube("Coldplay Yellow")
            self.assertIsInstance(results, list)
            self.assertEqual(len(results), 0)

    def test_check_ytdlp_update_network_failure(self):
        """Verify check_ytdlp_update returns graceful status when GitHub API is unreachable."""
        with patch("YT_Downloader_V2.safe_http_get", return_value=None):
            status = self.bridge.check_ytdlp_update()
            self.assertIsInstance(status, dict)
            self.assertFalse(status.get("has_update", True))
            self.assertIn("current_version", status)

    def test_update_ytdlp_network_failure(self):
        """Verify update_ytdlp returns error response when payload download fails."""
        with patch("YT_Downloader_V2.safe_http_get", return_value=None):
            res = self.bridge.update_ytdlp()
            self.assertIsInstance(res, dict)
            self.assertFalse(res.get("success", True))
            self.assertIn("error", res)

    def test_lyrics_search_network_failure(self):
        """Verify lyrics search functions return fallback structure on network failure."""
        with patch("nexus_audio.safe_http_get", return_value=None):
            with patch("requests.get", side_effect=requests.exceptions.ConnectTimeout("Connect timeout")):
                res = self.bridge.search_lyrics("Test Query")
                self.assertIsInstance(res, dict)
                self.assertEqual(res.get("synced", []), [])

                data = self.bridge.fetch_lyrics_data("Unknown Song", "Unknown Artist")
                self.assertIsInstance(data, dict)
                self.assertEqual(data.get("synced", []), [])

    def test_safe_http_get_resilience_matrix(self):
        """Verify safe_http_get safely returns None across various requests network exception classes."""
        exceptions = [
            requests.exceptions.SSLError("Certificate verification failed"),
            requests.exceptions.ConnectTimeout("Timeout connecting"),
            requests.exceptions.ChunkedEncodingError("Connection broken"),
            requests.exceptions.ProxyError("Cannot connect to proxy"),
        ]
        for exc in exceptions:
            with patch("requests.Session.get", side_effect=exc):
                resp = nexus_audio.safe_http_get("https://example.invalid", timeout=1, max_retries=1)
                self.assertIsNone(resp, f"safe_http_get must return None on {exc.__class__.__name__}")

    def test_stream_track_network_failure(self):
        """Verify stream_track handles network drops cleanly without raising unhandled exception."""
        with patch("YT_Downloader_V2.run_external_tool", side_effect=OSError("Network connection refused")):
            res = self.bridge.stream_track("https://www.youtube.com/watch?v=mock_network_drop")
            self.assertIsNone(res)

    def test_download_worker_network_dns_failure(self):
        """Verify _download_worker cleanly transitions task to failed when DNS resolution fails."""
        task = {
            "id": "task-dns-failure",
            "url": "https://www.youtube.com/watch?v=dns_fail",
            "title": "DNS Fail Song",
            "status": "waiting",
            "cancelled": False,
            "options": {},
            "metadata": {},
        }
        self.bridge.active_tasks[task["id"]] = task

        def mock_popen_dns(*args, **kwargs):
            p = MagicMock()
            p.stdout = [b"ERROR: [youtube] unable to download webpage: <urlopen error [Errno 11001] getaddrinfo failed>\n"]
            p.returncode = 1
            p.wait.return_value = 1
            return p

        with patch("subprocess.Popen", side_effect=mock_popen_dns), patch("time.sleep"):
            self.bridge._download_worker(task)

        self.assertEqual(task["status"], "failed")
        self.assertIsNotNone(task["error"])
        self.assertIn("เกิดปัญหาการเชื่อมต่อเครือข่าย", task["error"])


class TestYouTubeRateLimitingAndHttpErrors(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.test_dir, "test_config.json")
        self.bridge = NexusBridgeAPI(auto_check=False, config_path=self.config_path)

    def tearDown(self):
        self.bridge.cleanup()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_classify_download_error_rate_limiting_429(self):
        """Verify HTTP 429 and rate limiting outputs are classified as NetworkError."""
        err1 = classify_download_error("ERROR: [youtube] dQw4w9WgXcQ: HTTP Error 429: Too Many Requests")
        self.assertIsInstance(err1, NetworkError)
        self.assertIn("Rate Limit", err1.user_message)

        err2 = classify_download_error("yt_dlp.utils.DownloadError: HTTP Error 429: Too Many Requests")
        self.assertIsInstance(err2, NetworkError)

    def test_classify_download_error_http_403_forbidden(self):
        """Verify HTTP 403 Forbidden is classified as NetworkError."""
        err = classify_download_error("ERROR: unable to download video data: HTTP Error 403: Forbidden")
        self.assertIsInstance(err, NetworkError)
        self.assertIn("Rate Limit", err.user_message)

    def test_classify_download_error_auth_challenge(self):
        """Verify YouTube authentication challenges (e.g. sign in to confirm age) are classified as DownloadUnavailableError."""
        err = classify_download_error("Sign in to confirm your age. This video may be inappropriate for some users.")
        self.assertIsInstance(err, DownloadUnavailableError)
        self.assertIn("วิดีโอนี้ไม่พร้อมใช้งาน", err.user_message)

    def test_classify_download_error_video_unavailable_and_drm(self):
        """Verify video unavailable and DRM protection errors are correctly mapped."""
        unavail = classify_download_error("ERROR: Video unavailable. This video has been removed by the uploader.")
        self.assertIsInstance(unavail, DownloadUnavailableError)

        drm = classify_download_error("ERROR: DRM protected content is not available for extraction.")
        self.assertIsInstance(drm, FormatNotSupportedError)

    def test_download_worker_resilience_to_rate_limit(self):
        """Verify _download_worker cleanly transitions task to failed with classified error message."""
        task = {
            "id": "task-rate-limit",
            "url": "https://www.youtube.com/watch?v=mock429",
            "title": "Rate Limited Song",
            "status": "waiting",
            "cancelled": False,
            "options": {},
            "metadata": {},
        }
        self.bridge.active_tasks[task["id"]] = task

        def mock_popen_rate_limit(*args, **kwargs):
            p = MagicMock()
            p.stdout = [b"ERROR: [youtube] HTTP Error 429: Too Many Requests\n"]
            p.returncode = 1
            p.wait.return_value = 1
            return p

        with patch("subprocess.Popen", side_effect=mock_popen_rate_limit), patch("time.sleep"):
            self.bridge._download_worker(task)

        self.assertEqual(task["status"], "failed")
        self.assertIsNotNone(task["error"])
        self.assertIn("Rate Limit", task["error"])

    def test_download_worker_resilience_to_403_forbidden(self):
        """Verify _download_worker handles HTTP 403 Forbidden cleanly without crashing."""
        task = {
            "id": "task-403-forbidden",
            "url": "https://www.youtube.com/watch?v=mock403",
            "title": "Forbidden Song",
            "status": "waiting",
            "cancelled": False,
            "options": {},
            "metadata": {},
        }
        self.bridge.active_tasks[task["id"]] = task

        def mock_popen_403(*args, **kwargs):
            p = MagicMock()
            p.stdout = [b"ERROR: unable to download video data: HTTP Error 403: Forbidden\n"]
            p.returncode = 1
            p.wait.return_value = 1
            return p

        with patch("subprocess.Popen", side_effect=mock_popen_403), patch("time.sleep"):
            self.bridge._download_worker(task)

        self.assertEqual(task["status"], "failed")
        self.assertIsNotNone(task["error"])
        self.assertIn("Rate Limit", task["error"])

    def test_resolve_url_rate_limiting_fallback(self):
        """Verify resolve_url handles yt-dlp rate limit error code without crashing."""
        mock_res = MagicMock()
        mock_res.stdout = ""
        mock_res.stderr = "ERROR: [youtube] HTTP Error 429: Too Many Requests"
        mock_res.returncode = 1

        with patch("YT_Downloader_V2.run_external_tool", return_value=mock_res):
            resolved = self.bridge.resolve_url("https://www.youtube.com/watch?v=429mock")
            self.assertIsInstance(resolved, dict)
            self.assertEqual(resolved.get("platform"), "youtube")


class TestDiskWritePermissionDenials(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.test_dir, "test_config.json")
        self.bridge = NexusBridgeAPI(auto_check=False, config_path=self.config_path)

    def tearDown(self):
        self.bridge.cleanup()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_download_worker_unwritable_directory_redirection(self):
        """Verify _download_worker self-heals by redirecting to user Downloads folder when outdir probe fails."""
        self.bridge.config["outdir"] = os.path.join(self.test_dir, "unwritable_outdir")
        task = {
            "id": "task-unwritable-dir",
            "url": "https://example.com/audio",
            "title": "Test Song",
            "status": "waiting",
            "cancelled": False,
            "options": {},
            "metadata": {},
        }
        self.bridge.active_tasks[task["id"]] = task

        # Intercept the probe file open to trigger PermissionError
        orig_open = builtins.open

        def mock_open_with_permission_denial(file, mode="r", *args, **kwargs):
            if isinstance(file, str) and ".write_test_" in file:
                raise PermissionError("[WinError 5] Access is denied")
            return orig_open(file, mode, *args, **kwargs)

        mock_proc = MagicMock()
        mock_proc.stdout = iter([])
        mock_proc.returncode = 0
        mock_proc.wait.return_value = 0

        with patch("builtins.open", side_effect=mock_open_with_permission_denial), \
             patch("subprocess.Popen", return_value=mock_proc), \
             patch("YT_Downloader_V2.show_notify"):
            self.bridge._download_worker(task)

        self.assertIn("warning", task)
        self.assertIn("Output folder unwritable", task["warning"])
        self.assertEqual(task["status"], "completed")

    def test_save_lrc_permission_denied(self):
        """Verify save_lrc returns boolean False rather than throwing unhandled PermissionError."""
        orig_open = builtins.open

        def mock_open_lrc(file, mode="r", *args, **kwargs):
            if isinstance(file, str) and file.endswith(".lrc"):
                raise PermissionError("[WinError 5] Access is denied")
            return orig_open(file, mode, *args, **kwargs)

        with patch("builtins.open", side_effect=mock_open_lrc):
            res = self.bridge.save_lrc(os.path.join(self.test_dir, "protected.mp3"), "[00:01.00] Test Lyric")
            self.assertFalse(res)

    def test_export_library_playlist_permission_denied(self):
        """Verify export_library_playlist returns failure dict when destination cannot be written."""
        orig_open = builtins.open

        def mock_open_m3u8(file, mode="r", *args, **kwargs):
            if isinstance(file, str) and file.endswith(".m3u8"):
                raise PermissionError("[WinError 5] Access is denied")
            return orig_open(file, mode, *args, **kwargs)

        with patch("builtins.open", side_effect=mock_open_m3u8):
            res = self.bridge.export_library_playlist(os.path.join(self.test_dir, "readonly_playlist.m3u8"))
            self.assertIsInstance(res, dict)
            self.assertFalse(res.get("success", True))
            self.assertIn("error", res)

    def test_save_config_permission_denied(self):
        """Verify save_config catches write permission denial cleanly without raising exception."""
        orig_open = builtins.open

        def mock_open_cfg(file, mode="r", *args, **kwargs):
            if isinstance(file, str) and "test_config.json" in file:
                raise PermissionError("[WinError 5] Config write denied")
            return orig_open(file, mode, *args, **kwargs)

        with patch("builtins.open", side_effect=mock_open_cfg):
            try:
                self.bridge.save_config({"volume": 0.75})
            except Exception as e:
                self.fail(f"save_config raised unhandled exception on permission denial: {e}")

    def test_trim_audio_file_unwritable_destination(self):
        """Verify trim_audio_file catches permission error and returns safe failure status."""
        dummy_src = os.path.join(self.test_dir, "dummy_src.wav")
        with open(dummy_src, "wb") as f:
            f.write(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")

        unwritable_dst = "C:\\Windows\\System32\\forbidden_trimmed.wav"
        with patch("subprocess.run", side_effect=PermissionError("Permission denied")):
            res = self.bridge.trim_audio_file(dummy_src, unwritable_dst, 0.0, 1.0)
            self.assertFalse(res)


class TestCorruptMediaResilience(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.bridge = NexusBridgeAPI(auto_check=False)

    def tearDown(self):
        self.bridge.cleanup()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_get_media_info_zero_byte_file(self):
        """Verify get_media_info safely handles 0-byte media file."""
        zero_file = os.path.join(self.test_dir, "empty_song.mp3")
        with open(zero_file, "wb") as f:
            pass  # 0 bytes

        info = get_media_info(zero_file)
        self.assertIsInstance(info, dict)
        self.assertEqual(info.get("size_bytes"), 0)
        self.assertEqual(info.get("duration"), 0)
        self.assertEqual(info.get("title"), "empty_song")

    def test_get_media_info_random_binary_garbage(self):
        """Verify get_media_info safely handles file with 1024 bytes of random noise."""
        garbage_file = os.path.join(self.test_dir, "garbage_data.mp3")
        with open(garbage_file, "wb") as f:
            f.write(os.urandom(1024))

        info = get_media_info(garbage_file)
        self.assertIsInstance(info, dict)
        self.assertEqual(info.get("size_bytes"), 1024)
        self.assertEqual(info.get("duration"), 0)
        self.assertEqual(info.get("title"), "garbage_data")

    def test_get_media_info_truncated_id3_header(self):
        """Verify get_media_info handles truncated ID3v2 header without raising Mutagen/parsing exception."""
        trunc_file = os.path.join(self.test_dir, "truncated_header.mp3")
        with open(trunc_file, "wb") as f:
            f.write(b"ID3\x03\x00\x00\x00\x00\x05\x00" + b"\xff" * 16)

        info = get_media_info(trunc_file)
        self.assertIsInstance(info, dict)
        self.assertEqual(info.get("title"), "truncated_header")

    def test_get_media_info_nonexistent_file(self):
        """Verify get_media_info safely handles completely missing file."""
        info = get_media_info("Z:\\nonexistent_media_path_404.mp3")
        self.assertIsInstance(info, dict)
        self.assertEqual(info.get("duration"), 0)
        self.assertEqual(info.get("size_bytes"), 0)

    def test_tag_audio_file_nonexistent_and_corrupt_files(self):
        """Verify tag_audio_file handles nonexistent and corrupt audio files gracefully."""
        # Non-existent file
        ok = tag_audio_file("Z:\\nonexistent_tag_file.flac", {"title": "Test Title"})
        self.assertFalse(ok)

        # Corrupt FLAC file
        corrupt_flac = os.path.join(self.test_dir, "corrupt.flac")
        with open(corrupt_flac, "wb") as f:
            f.write(os.urandom(256))

        ok2 = tag_audio_file(corrupt_flac, {"title": "Bad FLAC"})
        self.assertFalse(ok2)

        # Tagging with corrupt album art bytes on MP3
        garbage_file = os.path.join(self.test_dir, "garbage_for_tagging.mp3")
        with open(garbage_file, "wb") as f:
            f.write(b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\x00" * 200)

        corrupt_cover = os.urandom(128)  # Not a valid JPEG or PNG
        try:
            res = tag_audio_file(garbage_file, {"title": "Garbage"}, cover_data_or_url=corrupt_cover)
            self.assertIsInstance(res, bool)
        except Exception as e:
            self.fail(f"tag_audio_file raised unhandled exception on corrupt cover: {e}")

    def test_audio_player_resilience_to_corrupt_files(self):
        """Verify AudioPlayer.load_and_play returns False without crashing when fed corrupt audio files."""
        player = AudioPlayer()
        try:
            # 1. Non-existent file
            res1 = player.load_and_play("Z:\\nonexistent_audio_path_8888.mp3")
            self.assertFalse(res1)

            # 2. 0-byte file
            zero_file = os.path.join(self.test_dir, "player_zero.mp3")
            with open(zero_file, "wb") as f:
                pass
            res2 = player.load_and_play(zero_file)
            self.assertFalse(res2)

            # 3. Random binary garbage
            garbage_file = os.path.join(self.test_dir, "player_corrupt.wav")
            with open(garbage_file, "wb") as f:
                f.write(os.urandom(2048))
            res3 = player.load_and_play(garbage_file)
            self.assertFalse(res3)
        finally:
            player.cleanup()

    def test_trim_preview_and_trim_audio_corrupt_inputs(self):
        """Verify preview_trim and trim_audio_file safely reject corrupt audio."""
        corrupt_file = os.path.join(self.test_dir, "corrupt_trim.mp3")
        with open(corrupt_file, "wb") as f:
            f.write(b"CORRUPT_NOT_AUDIO" * 10)

        # preview_trim on corrupt file
        preview_res = self.bridge.preview_trim(corrupt_file, 0.0, 5.0)
        self.assertFalse(preview_res)

        # trim_audio_file on corrupt file
        out_target = os.path.join(self.test_dir, "out_trim.mp3")
        trim_res = self.bridge.trim_audio_file(corrupt_file, out_target, 0.0, 5.0)
        self.assertFalse(trim_res)


if __name__ == "__main__":
    unittest.main()
