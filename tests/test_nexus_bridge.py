import contextlib
import os
import struct
import sys
import tempfile
import unittest
import wave
from unittest.mock import MagicMock, patch

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from YT_Downloader_V2 import NexusBridgeAPI


class TestNexusBridgeAPI(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_config_path = os.path.join(self.test_dir, "test_config.json")
        self.bridge = NexusBridgeAPI(auto_check=False, config_path=self.test_config_path)
        self.bridge.config["outdir"] = self.test_dir
        self.bridge.config["dsp_effects"] = {"preamp": 0.0, "bass_boost": 0.0, "surround": False}
        self.bridge.player.dsp_effects = {"preamp": 0.0, "bass_boost": 0.0, "surround": False}
        self.bridge.config["favorites"] = []

        # Create a sample test wav file
        self.wav_path = os.path.join(self.test_dir, "test_song.wav")
        with wave.open(self.wav_path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(44100)
            samples = [int(32767 * 0.1 * (i % 100 < 50)) for i in range(44100 * 2)]
            w.writeframes(struct.pack("<" + "h" * len(samples), *samples))

    def tearDown(self):
        self.bridge.player.stop()
        if os.path.exists(self.wav_path):
            with contextlib.suppress(Exception):
                os.remove(self.wav_path)
        if os.path.exists(self.test_dir):
            with contextlib.suppress(Exception):
                import shutil
                shutil.rmtree(self.test_dir)

    def test_initial_state(self):
        st = self.bridge.get_initial_state()
        self.assertIn("config", st)
        self.assertIn("locales", st)
        self.assertIn("accents", st)
        self.assertIn("eq_presets", st)
        self.assertIn("eq_bands", st)
        self.assertIn("engine_status", st)

    def test_engine_status(self):
        st = self.bridge.get_engine_status()
        self.assertIn("ytdlp_ready", st)
        self.assertIn("ffmpeg_ready", st)
        self.assertIn("ffprobe_ready", st)
        self.assertIn("ffplay_ready", st)

    def test_queue_lifecycle(self):
        with patch.object(self.bridge, "_download_worker", return_value=None):
            res = self.bridge.add_to_queue("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "Never Gonna Give You Up", "mp3_320")
            task_id = res["task_id"]
            self.assertIn(task_id, self.bridge.active_tasks)

            q_state = self.bridge.get_queue_state()
            self.assertEqual(len(q_state), 1)
            self.assertEqual(q_state[0]["id"], task_id)
            self.assertEqual(q_state[0]["title"], "Never Gonna Give You Up")

            # Cancel task
            cancelled = self.bridge.cancel_task(task_id)
            self.assertTrue(cancelled)
            self.assertEqual(self.bridge.active_tasks[task_id]["status"], "cancelled")

            # Clear finished
            self.bridge.clear_finished()
            self.assertEqual(len(self.bridge.get_queue_state()), 0)

    def test_library_scanning_and_filtering(self):
        items = self.bridge.get_library()
        self.assertGreaterEqual(len(items), 1)
        found = any(it["path"] == self.wav_path for it in items)
        self.assertTrue(found)

        # Filter matching
        filtered = self.bridge.get_library(query="test_song")
        self.assertEqual(len(filtered), 1)

        # Filter non-matching
        none_matched = self.bridge.get_library(query="nonexistent_artist_xyz")
        self.assertEqual(len(none_matched), 0)

    def test_player_controls_via_bridge(self):
        res = self.bridge.play_track(self.wav_path)
        self.assertIsNotNone(res)
        self.assertEqual(self.bridge.player.current_path, self.wav_path)

        st = self.bridge.get_player_state()
        self.assertTrue(st["is_playing"])
        self.assertFalse(st["is_paused"])

        # Pause
        self.bridge.player_control("play_pause")
        st = self.bridge.get_player_state()
        self.assertTrue(st["is_paused"])

        # Volume
        self.bridge.player_control("set_volume", 0.5)
        self.assertAlmostEqual(self.bridge.player.volume, 0.5, places=2)

        # Mute
        muted = self.bridge.player_control("toggle_mute")
        self.assertTrue(muted)
        unmuted = self.bridge.player_control("toggle_mute")
        self.assertFalse(unmuted)

        # Repeat & Shuffle
        mode = self.bridge.player_control("toggle_repeat")
        self.assertEqual(mode, "all")
        shuf = self.bridge.player_control("toggle_shuffle")
        self.assertTrue(shuf)

        # Stop
        self.bridge.player_control("stop")
        st = self.bridge.get_player_state()
        self.assertFalse(st["is_playing"])

    def test_equalizer_bridge(self):
        bands = self.bridge.set_eq_preset("Bass Boost")
        self.assertEqual(self.bridge.player.current_eq_preset, "Bass Boost")
        self.assertEqual(bands["bass"], 7.0)

        custom_bands = {"bass": 2.0, "low_mid": 1.0, "mid": 0.0, "high_mid": -1.0, "treble": 3.0}
        ret_bands = self.bridge.set_eq_bands(custom_bands)
        self.assertEqual(self.bridge.player.current_eq_preset, "Custom")
        self.assertEqual(ret_bands["treble"], 3.0)

    def test_save_lrc(self):
        lrc_sample = "[00:01.00] Hello World\n[00:05.00] Testing LRC"
        ok = self.bridge.save_lrc(self.wav_path, lrc_sample)
        self.assertTrue(ok)
        expected_lrc = os.path.splitext(self.wav_path)[0] + ".lrc"
        self.assertTrue(os.path.exists(expected_lrc))
        with open(expected_lrc, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, lrc_sample)

    def test_trim_preview_and_stop(self):
        ok = self.bridge.preview_trim(self.wav_path, "00:00:00", "00:00:01")
        self.assertTrue(ok)
        stopped = self.bridge.stop_trim_preview()
        self.assertTrue(stopped)

    def test_config_save(self):
        new_conf = {"accent": "#EC4899", "lang": "en"}
        saved = self.bridge.save_config(new_conf)
        self.assertTrue(saved)
        self.assertEqual(self.bridge.config["accent"], "#EC4899")
        self.assertEqual(self.bridge.config["lang"], "en")

    def test_resolve_url_detection(self):
        res = self.bridge.resolve_url("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT")
        self.assertEqual(res.get("platform"), "spotify")
        self.assertEqual(res.get("type"), "track")

    def test_get_clipboard(self):
        txt = self.bridge.get_clipboard()
        self.assertIsInstance(txt, str)

    def test_spotify_auto_resolution_in_queue(self):
        with patch.object(self.bridge, "_download_worker", return_value=None):
            spotify_url = "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"
            res = self.bridge.add_to_queue(spotify_url)
            task_id = res["task_id"]
            task = self.bridge.active_tasks[task_id]
            # Should have converted to ytsearch1: or populated metadata
            self.assertTrue(task["url"].startswith("ytsearch1:") or "Never Gonna Give You Up" in task["title"] or "Rick Astley" in str(task["metadata"]))
            self.assertIn("title", task["metadata"])

    def test_window_maximize_toggle(self):
        mock_win = MagicMock()
        self.bridge.window = mock_win
        self.assertFalse(self.bridge._is_maximized)
        self.bridge.window_control("maximize")
        self.assertTrue(self.bridge._is_maximized)
        mock_win.maximize.assert_called_once()

        self.bridge.window_control("maximize")
        self.assertFalse(self.bridge._is_maximized)
        mock_win.restore.assert_called_once()

    def test_library_sorting_modes(self):
        # Create second test file with different name
        wav2 = os.path.join(self.test_dir, "alpha_song.wav")
        with wave.open(wav2, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(44100)
            samples = [0] * 44100
            w.writeframes(struct.pack("<" + "h" * len(samples), *samples))

        by_title = self.bridge.get_library(sort_by="title")
        self.assertEqual(len(by_title), 2)
        self.assertTrue(by_title[0]["filename"].startswith("alpha") or by_title[0]["title"] <= by_title[1]["title"])

        by_date = self.bridge.get_library(sort_by="date")
        self.assertEqual(len(by_date), 2)

        if os.path.exists(wav2):
            os.remove(wav2)

    def test_web_assets_integrity(self):
        web_dir = os.path.join(repo_root, "web")
        self.assertTrue(os.path.exists(os.path.join(web_dir, "index.html")))
        self.assertTrue(os.path.exists(os.path.join(web_dir, "styles.css")))
        self.assertTrue(os.path.exists(os.path.join(web_dir, "app.js")))
        self.assertTrue(os.path.exists(os.path.join(web_dir, "tailwind.js")))

        # Check that tailwind.js is non-trivial (>100KB)
        tw_size = os.path.getsize(os.path.join(web_dir, "tailwind.js"))
        self.assertGreater(tw_size, 100000)

        # Check that index.html references app.js, styles.css, and tailwind.js
        with open(os.path.join(web_dir, "index.html"), "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("styles.css", html)
        self.assertIn("app.js", html)
        self.assertIn("tailwind.js", html)
        self.assertIn("v3.2.0", html)
        self.assertIn("NexusTube", html)

    def test_reveal_file(self):
        with patch("subprocess.Popen") as mock_popen, patch.object(self.bridge, "open_folder") as mock_open_folder:
            # 1. Valid local file
            res = self.bridge.reveal_file(self.wav_path)
            self.assertTrue(res)
            mock_popen.assert_called()

            # 2. Non-existent file -> calls open_folder on parent directory
            mock_open_folder.return_value = True
            test_missing_path = "C:/nonexistent/fake_path.mp3"
            res_missing = self.bridge.reveal_file(test_missing_path)
            self.assertTrue(res_missing)
            mock_open_folder.assert_called_with(os.path.dirname(os.path.abspath(test_missing_path)))

            # 3. None or empty filepath -> calls open_folder with None
            self.bridge.reveal_file("")
            mock_open_folder.assert_called_with()

    def test_search_lyrics(self):
        with patch("YT_Downloader_V2.fetch_lyrics") as mock_fetch:
            mock_fetch.return_value = {
                "lrc": "[00:01.00] Test Lyric",
                "parsed": [(1.0, "Test Lyric")],
                "source": "LRCLIB",
            }
            res = self.bridge.search_lyrics("Never Gonna Give You Up", "Rick Astley")
            self.assertEqual(res["source"], "LRCLIB")
            self.assertIn("Test Lyric", res["lrc"])
            mock_fetch.assert_called_with("Never Gonna Give You Up", "Rick Astley")

    def test_stream_track(self):
        # 1. Local file path returns play_track result
        res_local = self.bridge.stream_track(self.wav_path)
        self.assertIsNotNone(res_local)
        self.assertEqual(res_local.get("title"), "test_song")

        # 2. Remote URL with mock subprocess.run producing wav
        with patch("subprocess.run") as mock_run:
            def create_fake_wav(*args, **kwargs):
                cmd = args[0]
                out_idx = cmd.index("-o") + 1
                out_file = cmd[out_idx]
                with wave.open(out_file, "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(44100)
                    samples = [0] * 44100
                    w.writeframes(struct.pack("<" + "h" * len(samples), *samples))
                return MagicMock(returncode=0)

            mock_run.side_effect = create_fake_wav
            res_remote = self.bridge.stream_track("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
            self.assertIsNotNone(res_remote)
            self.assertEqual(res_remote.get("title"), "Online Stream")

    def test_delete_file(self):
        # Create a temp file to delete
        del_target = os.path.join(self.test_dir, "to_delete.wav")
        lrc_target = os.path.join(self.test_dir, "to_delete.lrc")
        with open(del_target, "w") as f:
            f.write("dummy")
        with open(lrc_target, "w") as f:
            f.write("[00:01.00] test")

        self.assertTrue(os.path.exists(del_target))
        self.assertTrue(os.path.exists(lrc_target))

        # Test delete existing
        deleted = self.bridge.delete_file(del_target)
        self.assertTrue(deleted)
        self.assertFalse(os.path.exists(del_target))
        self.assertFalse(os.path.exists(lrc_target))

        # Test delete non-existent
        deleted_again = self.bridge.delete_file("C:/does_not_exist/random.wav")
        self.assertFalse(deleted_again)

    def test_player_control_prev_behavior(self):
        # Setup second song in library
        wav2 = os.path.join(self.test_dir, "song2.wav")
        with wave.open(wav2, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(44100)
            samples = [0] * 44100
            w.writeframes(struct.pack("<" + "h" * len(samples), *samples))

        try:
            self.bridge.play_track(self.wav_path)
            # 1. If pos > 3.0s, prev seeks to 0.0 and keeps current track
            with patch.object(self.bridge.player, "get_pos", return_value=5.5), \
                 patch.object(self.bridge.player, "seek") as mock_seek:
                res = self.bridge.player_control("prev")
                self.assertTrue(res)
                mock_seek.assert_called_with(0.0)

            # 2. If pos <= 3.0s, prev plays previous song in library
            with patch.object(self.bridge.player, "get_pos", return_value=1.0), \
                 patch.object(self.bridge, "play_track") as mock_play:
                res = self.bridge.player_control("prev")
                self.assertTrue(res)
                mock_play.assert_called()
        finally:
            if os.path.exists(wav2):
                os.remove(wav2)

    def test_player_control_next_shuffle(self):
        # Create second song
        wav2 = os.path.join(self.test_dir, "song_b.wav")
        with wave.open(wav2, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(44100)
            samples = [0] * 44100
            w.writeframes(struct.pack("<" + "h" * len(samples), *samples))

        try:
            self.bridge.play_track(self.wav_path)
            self.bridge.player.is_shuffle = True
            with patch.object(self.bridge, "play_track") as mock_play:
                res = self.bridge.player_control("next")
                self.assertTrue(res)
                mock_play.assert_called()
        finally:
            if os.path.exists(wav2):
                os.remove(wav2)

    def test_auto_unmute_on_volume_set(self):
        self.bridge.player.is_muted = True
        self.bridge.player_control("set_volume", 0.75)
        self.assertFalse(self.bridge.player.is_muted)
        self.assertAlmostEqual(self.bridge.player.volume, 0.75, places=2)

    def test_stop_trim_preview_with_stream_proc(self):
        mock_proc = MagicMock()
        self.bridge._stream_proc = mock_proc
        stopped = self.bridge.stop_trim_preview()
        self.assertTrue(stopped)
        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_called_once()
        self.assertIsNone(self.bridge._stream_proc)

    def test_reveal_file_windows_path_normalization(self):
        with patch("subprocess.Popen") as mock_popen:
            # File with forward slashes
            test_file = self.wav_path.replace("\\", "/")
            res = self.bridge.reveal_file(test_file)
            self.assertTrue(res)
            if self.bridge.is_win:
                called_cmd = mock_popen.call_args[0][0]
                self.assertNotIn("/", called_cmd.split('explorer /select,')[1])

    def test_delete_file_cover_art_cleanup(self):
        del_target = os.path.join(self.test_dir, "cover_track.mp3")
        jpg_target = os.path.join(self.test_dir, "cover_track.jpg")
        png_target = os.path.join(self.test_dir, "cover_track.png")
        for f in (del_target, jpg_target, png_target):
            with open(f, "w") as fp:
                fp.write("dummy")

        self.assertTrue(os.path.exists(del_target))
        self.assertTrue(os.path.exists(jpg_target))
        self.assertTrue(os.path.exists(png_target))

        res = self.bridge.delete_file(del_target)
        self.assertTrue(res)
        self.assertFalse(os.path.exists(del_target))
        self.assertFalse(os.path.exists(jpg_target))
        self.assertFalse(os.path.exists(png_target))

    def test_trim_audio_file_saved_in_outdir(self):
        # Place input file outside outdir
        other_dir = tempfile.mkdtemp()
        try:
            other_wav = os.path.join(other_dir, "outside_song.wav")
            with wave.open(other_wav, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(44100)
                samples = [0] * 44100
                w.writeframes(struct.pack("<" + "h" * len(samples), *samples))

            with patch("subprocess.run") as mock_run:
                def fake_trim(cmd, *args, **kwargs):
                    out_f = cmd[-1]
                    with open(out_f, "w") as f:
                        f.write("trimmed audio")
                    return MagicMock(returncode=0)
                mock_run.side_effect = fake_trim

                res = self.bridge.trim_audio_file(other_wav, "00:00:00", "00:00:01", "mp3")
                self.assertTrue(res)

                # Confirm trimmed file is saved in self.bridge.config["outdir"]
                lib = self.bridge.get_library()
                trimmed_in_lib = any("outside_song_trimmed" in item["filename"] for item in lib)
                self.assertTrue(trimmed_in_lib)
        finally:
            import shutil
            shutil.rmtree(other_dir, ignore_errors=True)

    def test_save_lrc_with_outdir_fallback(self):
        self.bridge.player.info = {"title": "Dreaming In The Rain"}
        ok = self.bridge.save_lrc(None, "[00:01.00] In the rain")
        self.assertTrue(ok)
        expected = os.path.join(self.test_dir, "Dreaming In The Rain.lrc")
        self.assertTrue(os.path.exists(expected))

    def test_cache_cleanup_stream_and_audio(self):
        cache_dir = os.path.join(tempfile.gettempdir(), "nexustube_cache")
        os.makedirs(cache_dir, exist_ok=True)
        # Create 12 files (mix of audio_ and stream_)
        created = []
        for i in range(12):
            prefix = "stream_" if i % 2 == 0 else "audio_"
            p = os.path.join(cache_dir, f"{prefix}test_{i}.wav")
            with open(p, "w") as fp:
                fp.write("wav")
            created.append(p)

        self.bridge.player._cleanup_cache(max_files=5)
        remaining = [f for f in os.listdir(cache_dir) if f.startswith(("audio_test_", "stream_test_"))]
        self.assertLessEqual(len(remaining), 5)

        for f in created:
            if os.path.exists(f):
                with contextlib.suppress(Exception):
                    os.remove(f)

    def test_window_controls(self):
        # Window not attached
        self.assertFalse(self.bridge.window_control("minimize"))

        # Mock window
        mock_win = MagicMock()
        self.bridge.window = mock_win

        # Minimize
        self.assertTrue(self.bridge.window_control("minimize"))
        mock_win.minimize.assert_called_once()

        # Maximize and toggle restore
        self.assertTrue(self.bridge.window_control("maximize"))
        mock_win.maximize.assert_called_once()
        self.assertTrue(self.bridge._is_maximized)

        self.assertTrue(self.bridge.window_control("maximize"))
        mock_win.restore.assert_called_once()
        self.assertFalse(self.bridge._is_maximized)

        # Close
        self.assertTrue(self.bridge.window_control("close"))
        mock_win.destroy.assert_called_once()

        # Invalid action
        self.assertFalse(self.bridge.window_control("invalid_action"))

    def test_looplist_progression(self):
        # Create second test track
        wav2_path = os.path.join(self.test_dir, "test_song_2.wav")
        with wave.open(wav2_path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(44100)
            samples = [int(32767 * 0.1 * (i % 100 < 50)) for i in range(44100 * 2)]
            w.writeframes(struct.pack("<" + "h" * len(samples), *samples))

        try:
            # Play first song
            self.bridge.play_track(self.wav_path)
            self.assertEqual(self.bridge.player.current_path, self.wav_path)

            # Test Next track advances
            self.assertTrue(self.bridge.player_control("next"))
            self.assertEqual(self.bridge.player.current_path, wav2_path)

            # Test Next track loops back (looplist)
            self.assertTrue(self.bridge.player_control("next"))
            self.assertEqual(self.bridge.player.current_path, self.wav_path)

            # Test Prev track
            self.assertTrue(self.bridge.player_control("prev"))
            self.assertEqual(self.bridge.player.current_path, wav2_path)
        finally:
            if os.path.exists(wav2_path):
                with contextlib.suppress(Exception):
                    os.remove(wav2_path)

    def test_looplist_auto_progression_modes(self):
        wav2_path = os.path.join(self.test_dir, "test_song_2.wav")
        with wave.open(wav2_path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(44100)
            samples = [int(32767 * 0.1 * (i % 100 < 50)) for i in range(44100 * 2)]
            w.writeframes(struct.pack("<" + "h" * len(samples), *samples))

        try:
            # 1. Test Repeat All (Loop List)
            self.bridge.play_track(self.wav_path)
            self.bridge.player.repeat_mode = "all"
            self.bridge.player.is_playing = True
            self.bridge.player.is_paused = False
            self.bridge.player._initialized = True

            with patch("pygame.mixer.music.get_busy", return_value=False):
                # When track ends in "all" mode, should auto-advance to track 2
                self.bridge.get_player_state()
                self.assertTrue(self.bridge._is_same_path(self.bridge.player.current_path, wav2_path))

                # When track 2 ends in "all" mode, should loop back to track 1
                self.bridge.player.is_playing = True
                self.bridge.player.is_paused = False
                self.bridge.get_player_state()
                self.assertTrue(self.bridge._is_same_path(self.bridge.player.current_path, self.wav_path))

            # 2. Test Repeat Off (Progress through library until last track, then stop)
            lib = self.bridge.get_library()
            first_track = lib[0]["path"]
            second_track = lib[1]["path"]

            self.bridge.play_track(first_track)
            self.bridge.player.repeat_mode = "off"
            self.bridge.player.is_playing = True
            self.bridge.player.is_paused = False

            with patch("pygame.mixer.music.get_busy", return_value=False):
                # First track ends -> advances to second track
                self.bridge.get_player_state()
                self.assertTrue(self.bridge._is_same_path(self.bridge.player.current_path, second_track))

                # Second track ends (last track in library) -> stops playback
                self.bridge.player.is_playing = True
                self.bridge.player.is_paused = False
                self.bridge.get_player_state()
                self.assertFalse(self.bridge.player.is_playing)

            # 3. Test Repeat One (Loop single track)
            self.bridge.play_track(self.wav_path)
            self.bridge.player.repeat_mode = "one"
            self.bridge.player.is_playing = True
            self.bridge.player.is_paused = False

            with patch("pygame.mixer.music.get_busy", return_value=False), \
                 patch.object(self.bridge.player, "load_and_play") as mock_replay:
                self.bridge.get_player_state()
                mock_replay.assert_called_with(self.wav_path, 0.0)

        finally:
            if os.path.exists(wav2_path):
                with contextlib.suppress(Exception):
                    os.remove(wav2_path)

    def test_path_normalization_resilience(self):
        # Mixed slashes and case normalization
        p_win = "C:\\Users\\Administrator\\Music\\Song.mp3"
        p_unix = "c:/users/administrator/music/song.mp3"
        self.assertTrue(self.bridge._is_same_path(p_win, p_unix))
        self.assertFalse(self.bridge._is_same_path(p_win, "C:\\Different\\Song.mp3"))
        self.assertFalse(self.bridge._is_same_path(None, p_win))

        # Delete active file with mixed slash path
        self.bridge.player.current_path = self.wav_path.replace("\\", "/").lower()
        self.bridge.player.is_playing = True
        self.assertTrue(self.bridge.delete_file(self.wav_path))
        self.assertIsNone(self.bridge.player.current_path)
        self.assertFalse(self.bridge.player.is_playing)

    def test_queue_thumbnail_and_stats_integration(self):
        with patch.object(self.bridge.executor, "submit"):
            res = self.bridge.add_to_queue("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "Never Gonna Give You Up")
            self.assertIn("task_id", res)
            tasks = self.bridge.get_queue_state()
            self.assertGreaterEqual(len(tasks), 1)
            matching = [t for t in tasks if t["id"] == res["task_id"]]
            self.assertEqual(len(matching), 1)
            task = matching[0]
            self.assertIn("thumbnail", task)
            self.assertIn("dQw4w9WgXcQ", task["thumbnail"])

    def test_locales_queue_and_navigation_keys(self):
        from YT_Downloader_V2 import LOCALES
        required_keys = [
            "Speed", "ETA", "Downloading", "Processing Tags…",
            "Folder", "MENU", "STUDIO_TOOLS", "Total Downloads", "Active", "Completed"
        ]
        for key in required_keys:
            self.assertIn(key, LOCALES, f"Missing key in LOCALES: {key}")
            self.assertIn("th", LOCALES[key], f"Missing Thai translation for {key}")
            self.assertIn("en", LOCALES[key], f"Missing English translation for {key}")

    def test_web_index_sidebar_and_stats_markup(self):
        html_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "index.html")
        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn('id="queue-stats-bar"', html)
        self.assertIn('w-60 bg-sidebar', html)
        # Ensure legacy btn-stop is removed from footer player bar
        self.assertNotIn('id="btn-stop"', html)

    def test_v330_dsp_effects_and_bridge_integration(self):
        # Initial dsp effects default
        initial_dsp = self.bridge.player.dsp_effects
        self.assertEqual(initial_dsp["preamp"], 0.0)
        self.assertEqual(initial_dsp["bass_boost"], 0.0)
        self.assertFalse(initial_dsp["surround"])

        # Update DSP effects
        res = self.bridge.set_dsp_effects(3.0, 0.5, True)
        self.assertEqual(res["preamp"], 3.0)
        self.assertEqual(res["bass_boost"], 0.5)
        self.assertTrue(res["surround"])
        self.assertEqual(self.bridge.player.dsp_effects["preamp"], 3.0)
        self.assertEqual(self.bridge.player.dsp_effects["bass_boost"], 0.5)
        self.assertTrue(self.bridge.player.dsp_effects["surround"])

    def test_v330_favorites_toggle_and_library_state(self):
        # Toggle on
        is_fav = self.bridge.toggle_favorite(self.wav_path)
        self.assertTrue(is_fav)
        favs = self.bridge.get_favorites()
        self.assertTrue(any(self.bridge._is_same_path(f, self.wav_path) for f in favs))

        # In get_library(), track must have is_favorite: True
        lib = self.bridge.get_library()
        matching = [t for t in lib if self.bridge._is_same_path(t["path"], self.wav_path)]
        self.assertEqual(len(matching), 1)
        self.assertTrue(matching[0]["is_favorite"])

        # Toggle off
        is_fav_off = self.bridge.toggle_favorite(self.wav_path)
        self.assertFalse(is_fav_off)
        favs_off = self.bridge.get_favorites()
        self.assertFalse(any(self.bridge._is_same_path(f, self.wav_path) for f in favs_off))

    def test_v330_batch_cancel_all(self):
        with patch.object(self.bridge.executor, "submit"):
            t1 = self.bridge.add_to_queue("https://www.youtube.com/watch?v=video1", "Video 1")
            t2 = self.bridge.add_to_queue("https://www.youtube.com/watch?v=video2", "Video 2")
            self.assertIn("task_id", t1)
            self.assertIn("task_id", t2)

            cancelled_count = self.bridge.batch_cancel_all()
            self.assertGreaterEqual(cancelled_count, 2)

            # Check queue status has them cancelled
            q = self.bridge.get_queue_state()
            for task in q:
                if task["id"] in (t1["task_id"], t2["task_id"]):
                    self.assertEqual(task["status"], "cancelled")

    def test_v330_export_m3u8_playlist(self):
        res = self.bridge.export_library_playlist("Unit_Test_Playlist")
        self.assertTrue(res["success"])
        self.assertTrue(os.path.exists(res["path"]))
        with open(res["path"], "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("#EXTM3U", content)
        self.assertIn("test_song", content)

    def test_v330_convert_track_validation(self):
        # Non-existent file test
        res_fail = self.bridge.convert_track("C:\\nonexistent\\track.mp3", "flac")
        self.assertFalse(res_fail["success"])
        self.assertIn("not found", res_fail["error"])

        # Valid source file test with mock conversion
        mock_ret = {"success": True, "output_path": "/mock/out.flac"}
        with patch("YT_Downloader_V2.convert_audio_file", return_value=mock_ret):
            res_ok = self.bridge.convert_track(self.wav_path, "flac", "320k", True)
            self.assertTrue(res_ok["success"])
            self.assertEqual(res_ok["output_path"], "/mock/out.flac")

    def test_v330_web_markup_completeness(self):
        html_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "index.html")
        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn('id="modal-converter"', html)
        self.assertIn('id="modal-shortcuts"', html)
        self.assertIn('id="modal-sleep-timer"', html)
        self.assertIn('id="fullscreen-karaoke-modal"', html)
        self.assertIn('id="library-table-container"', html)
        self.assertIn('id="btn-playback-speed"', html)
        self.assertIn('id="seek-hover-tooltip"', html)
        self.assertIn('id="dsp-preamp-slider"', html)
        self.assertIn('id="dsp-bass-slider"', html)
        self.assertIn('id="dsp-surround-toggle"', html)
        self.assertIn('id="eq-curve-canvas"', html)
        self.assertIn('id="btn-sleep-timer"', html)
        self.assertIn('id="btn-keyboard-shortcuts"', html)
        self.assertIn('id="recent-searches-tags"', html)

    def test_v330_player_control_pause_resume_speed(self):
        self.bridge.play_track(self.wav_path)
        self.assertTrue(self.bridge.player.is_playing)

        # 1. Test explicit pause
        self.assertTrue(self.bridge.player_control("pause"))
        self.assertTrue(self.bridge.player.is_paused)
        self.assertFalse(self.bridge.player.is_playing)

        # Calling pause again should remain paused (not toggle)
        self.assertTrue(self.bridge.player_control("pause"))
        self.assertTrue(self.bridge.player.is_paused)

        # 2. Test explicit resume
        self.assertTrue(self.bridge.player_control("resume"))
        self.assertTrue(self.bridge.player.is_playing)
        self.assertFalse(self.bridge.player.is_paused)

        # 3. Test set_speed
        sp = self.bridge.player_control("set_speed", 1.5)
        self.assertEqual(sp, 1.5)
        self.assertEqual(self.bridge.player.playback_speed, 1.5)
        st = self.bridge.get_player_state()
        self.assertEqual(st.get("playback_speed"), 1.5)

        # Clamp speed limits [0.5, 2.0]
        self.assertEqual(self.bridge.player_control("set_speed", 5.0), 2.0)
        self.assertEqual(self.bridge.player_control("set_speed", 0.1), 0.5)
        self.bridge.player.stop()

    def test_v330_batch_cancel_terminates_processes(self):
        with patch.object(self.bridge.executor, "submit"):
            t = self.bridge.add_to_queue("https://www.youtube.com/watch?v=process_test", "Process Test")
            tid = t["task_id"]
            mock_proc = MagicMock()
            self.bridge.active_tasks[tid]["proc"] = mock_proc
            self.bridge.active_tasks[tid]["status"] = "downloading"

            count = self.bridge.batch_cancel_all()
            self.assertEqual(count, 1)
            mock_proc.terminate.assert_called_once()
            mock_proc.kill.assert_called_once()
            self.assertTrue(self.bridge.active_tasks[tid]["cancelled"])
            self.assertEqual(self.bridge.active_tasks[tid]["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()


