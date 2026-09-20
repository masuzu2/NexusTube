import contextlib
import json
import os
import struct
import sys
import tempfile
import unittest
import wave

# Ensure repo root is on sys.path
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from YT_Downloader_V2 import (
    ACCENT_PALETTE,
    EQ_PRESETS,
    LOCALES,
    App,
    AudioPlayer,
    AudioVisualizer,
    clean_music_title,
    detect_platform_url,
    fetch_lyrics,
    format_lrc,
    generate_ffmpeg_eq_filter,
    get_active_lyric_index,
    get_binary_path,
    get_media_info,
    parse_lrc,
    parse_music_metadata,
    resolve_multiplatform_url,
    sanitize_filename,
    seconds_to_time,
    tag_audio_file,
    time_to_seconds,
)


class TestNexusTubeLocales(unittest.TestCase):
    def test_locales_completeness(self):
        """Every locale key must have non-empty 'en' and 'th' translations."""
        self.assertGreater(len(LOCALES), 20)
        for key, trans in LOCALES.items():
            self.assertIn("en", trans, f"Key '{key}' missing 'en' translation")
            self.assertIn("th", trans, f"Key '{key}' missing 'th' translation")
            self.assertTrue(len(trans["en"]) > 0, f"Key '{key}' has empty 'en'")
            self.assertTrue(len(trans["th"]) > 0, f"Key '{key}' has empty 'th'")

    def test_accent_palette(self):
        """All accents in palette must have valid color and hover hex codes."""
        self.assertGreaterEqual(len(ACCENT_PALETTE), 6)
        for meta in ACCENT_PALETTE.values():
            self.assertTrue(meta["color"].startswith("#"))
            self.assertTrue(meta["hover"].startswith("#"))
            self.assertEqual(len(meta["color"]), 7)
            self.assertEqual(len(meta["hover"]), 7)


class TestMediaInfo(unittest.TestCase):
    def test_nonexistent_file(self):
        info = get_media_info("C:/path/does/not/exist/fake_song.mp3")
        self.assertEqual(info["title"], "fake_song")
        self.assertEqual(info["artist"], "Local Audio")
        self.assertEqual(info["duration"], 0)
        self.assertEqual(info["size_bytes"], 0)
        self.assertIsNone(info["cover_image"])

    def test_valid_wav_file(self):
        tf = os.path.join(tempfile.gettempdir(), "nexus_test_audio.wav")
        try:
            with wave.open(tf, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(44100)
                # 2 seconds of audio
                samples = [int(32767 * 0.1 * (i % 100 < 50)) for i in range(88200)]
                w.writeframes(struct.pack("<" + "h" * len(samples), *samples))

            info = get_media_info(tf)
            self.assertEqual(info["title"], "nexus_test_audio")
            self.assertGreater(info["size_bytes"], 1000)
            self.assertGreaterEqual(info["duration"], 1)
        finally:
            if os.path.exists(tf):
                os.remove(tf)


class TestAudioPlayer(unittest.TestCase):
    def setUp(self):
        self.player = AudioPlayer()
        self.tf = os.path.join(tempfile.gettempdir(), "player_test_sample.wav")
        with wave.open(self.tf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(44100)
            samples = [int(32767 * 0.1 * (i % 100 < 50)) for i in range(44100 * 3)] # 3s
            w.writeframes(struct.pack("<" + "h" * len(samples), *samples))

    def tearDown(self):
        self.player.stop()
        if os.path.exists(self.tf):
            with contextlib.suppress(Exception):
                os.remove(self.tf)

    def test_playback_controls(self):
        ok = self.player.load_and_play(self.tf)
        self.assertTrue(ok)
        self.assertTrue(self.player.is_playing)
        self.assertFalse(self.player.is_paused)

        # Toggle to pause
        self.player.toggle_play_pause()
        self.assertTrue(self.player.is_paused)
        self.assertFalse(self.player.is_playing)

        # Toggle to resume
        self.player.toggle_play_pause()
        self.assertTrue(self.player.is_playing)
        self.assertFalse(self.player.is_paused)

        # Seeking
        self.player.seek(1.5)
        self.assertEqual(self.player.seek_offset, 1.5)

        # Volume & Mute
        self.player.set_volume(0.5)
        self.assertAlmostEqual(self.player.volume, 0.5, places=2)
        muted = self.player.toggle_mute()
        self.assertTrue(muted)
        self.assertTrue(self.player.is_muted)
        unmuted = self.player.toggle_mute()
        self.assertFalse(unmuted)
        self.assertFalse(self.player.is_muted)

        # Stop
        self.player.stop()
        self.assertFalse(self.player.is_playing)
        self.assertFalse(self.player.is_paused)

    def test_repeat_and_shuffle(self):
        self.assertEqual(self.player.repeat_mode, "off")
        self.assertEqual(self.player.toggle_repeat(), "all")
        self.assertEqual(self.player.toggle_repeat(), "one")
        self.assertEqual(self.player.toggle_repeat(), "off")

        self.assertFalse(self.player.is_shuffle)
        self.assertTrue(self.player.toggle_shuffle())
        self.assertFalse(self.player.toggle_shuffle())

    def test_audio_player_m4a_transcode_playback(self):
        appdata_dir = os.path.join(os.getenv("APPDATA") or "", "YTDownloaderPro")
        ffmpeg_bin = os.path.join(appdata_dir, "ffmpeg.exe") if sys.platform == "win32" else "ffmpeg"
        if not os.path.exists(ffmpeg_bin):
            import shutil
            ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin or not os.path.exists(ffmpeg_bin):
            self.skipTest("FFmpeg not available for transcode test")

        m4a_path = os.path.join(tempfile.gettempdir(), "test_transcode.m4a")
        try:
            import subprocess
            subprocess.run([ffmpeg_bin, "-y", "-i", self.tf, m4a_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            player = AudioPlayer(ffmpeg_bin=ffmpeg_bin)
            ok = player.load_and_play(m4a_path)
            self.assertTrue(ok)
            self.assertTrue(player.is_playing)
            player.stop()
        finally:
            if os.path.exists(m4a_path):
                with contextlib.suppress(Exception):
                    os.remove(m4a_path)


class TestUtilityHelpers(unittest.TestCase):
    def test_time_to_seconds(self):
        self.assertEqual(time_to_seconds("00:01:30"), 90.0)
        self.assertEqual(time_to_seconds("01:30"), 90.0)
        self.assertEqual(time_to_seconds("45.5"), 45.5)
        self.assertEqual(time_to_seconds(""), 0.0)
        self.assertEqual(time_to_seconds("invalid"), 0.0)
        self.assertEqual(time_to_seconds(None), 0.0)

    def test_seconds_to_time(self):
        self.assertEqual(seconds_to_time(0), "00:00:00")
        self.assertEqual(seconds_to_time(90), "00:01:30")
        self.assertEqual(seconds_to_time(3665), "01:01:05")

    def test_sanitize_filename(self):
        self.assertEqual(sanitize_filename("Artist: Song / Track? * < > |"), "Artist Song Track")
        self.assertEqual(sanitize_filename("  Normal Title  "), "Normal Title")
        self.assertEqual(sanitize_filename(""), "track")

    def test_get_binary_path(self):
        dummy_dir = tempfile.gettempdir()
        p = get_binary_path(dummy_dir, "python", ".exe" if sys.platform == "win32" else "")
        self.assertTrue(os.path.exists(p))


class TestAppUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = App(check_updates=False)
        cls.app.withdraw()  # Hide UI during testing

    @classmethod
    def tearDownClass(cls):
        with contextlib.suppress(Exception):
            cls.app.player.stop()
            cls.app.update_idletasks()
            cls.app.destroy()

    def test_tab_switching(self):
        tabs = ["search", "queue", "library", "settings"]
        for tab in tabs:
            self.app._switch_tab(tab)
            self.assertEqual(self.app._active_tab.get(), tab)

    def test_live_theme_change(self):
        new_color = "#EC4899"
        new_hover = "#DB2777"
        self.app._set_live_accent(new_color, new_hover)
        self.assertEqual(self.app.accent_color, new_color)
        self.assertEqual(self.app.accent_hv, new_hover)
        self.assertEqual(self.app.config["accent"], new_color)

    def test_live_language_change(self):
        self.app._set_live_language("en")
        self.assertEqual(self.app.lang, "en")
        self.assertEqual(self.app.config["lang"], "en")
        self.assertEqual(self.app.t("Search"), "Search")

        self.app._set_live_language("th")
        self.assertEqual(self.app.lang, "th")
        self.assertEqual(self.app.config["lang"], "th")
        self.assertEqual(self.app.t("Search"), "ค้นหา")

    def test_queue_task_creation_and_cancellation(self):
        from unittest.mock import patch
        initial_count = len(self.app.active_tasks)
        with patch.object(self.app, "_download_worker", return_value=None):
            self.app.add_to_queue("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "Test Song")
        self.assertEqual(len(self.app.active_tasks), initial_count + 1)

        task_id = list(self.app.active_tasks.keys())[-1]
        task = self.app.active_tasks[task_id]
        self.assertEqual(task["title"], "Test Song")

        # Cancel the task
        self.app._cancel_task(task_id)
        self.assertTrue(task["cancelled"])
        self.assertEqual(task["status"], "cancelled")

    def test_audio_player_invalid_file(self):
        player = AudioPlayer()
        # Loading nonexistent file should return False and not crash
        res = player.load_and_play("nonexistent_corrupt_file.mp3")
        self.assertFalse(res)
        self.assertFalse(player.is_playing)

    def test_library_refresh_and_filtering(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a test audio file
            mp3_file = os.path.join(temp_dir, "Summer Breeze - Artist.mp3")
            with open(mp3_file, "wb") as f:
                f.write(b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\x00" * 500)

            orig_out = self.app.out_var.get()
            try:
                self.app.out_var.set(temp_dir)
                self.app._refresh_library()
                self.assertIn(mp3_file, self.app.library_items)

                # Test live filter
                self.app.lib_search_entry.delete(0, "end")
                self.app.lib_search_entry.insert(0, "Summer")
                self.app._filter_library_cards()

                # Filter non-matching
                self.app.lib_search_entry.delete(0, "end")
                self.app.lib_search_entry.insert(0, "WinterNotExisting")
                self.app._filter_library_cards()
            finally:
                self.app.out_var.set(orig_out)

    def test_download_worker_options_and_sanitization(self):
        # Verify custom title sanitization and loudnorm settings
        task = {"title": "01 - My Song: Rock/Pop Edition?", "url": "https://youtu.be/dummy", "override_fmt": "mp3_320"}
        safe_name = sanitize_filename(task["title"])
        self.assertEqual(safe_name, "01 - My Song RockPop Edition")
        self.assertNotIn(":", safe_name)
        self.assertNotIn("/", safe_name)
        self.assertNotIn("?", safe_name)

        # Verify loudnorm option toggles
        self.app.norm_var.set(True)
        self.assertTrue(self.app.norm_var.get())
        self.app.norm_var.set(False)
        self.assertFalse(self.app.norm_var.get())

    def test_eq_and_lyrics_windows_launch(self):
        # Test lyrics window open & close
        self.app._open_lyrics_window()
        self.assertIsNotNone(self.app.lyrics_window)
        self.assertTrue(self.app.lyrics_window.winfo_exists())
        self.app.lyrics_window.destroy()

        # Test EQ window open & close
        self.app._open_eq_window()
        self.assertIsNotNone(self.app.eq_window)
        self.assertTrue(self.app.eq_window.winfo_exists())
        self.app._on_eq_preset_selected("Bass Boost")
        self.assertEqual(self.app.player.current_eq_preset, "Bass Boost")
        self.app.eq_window.destroy()

    def test_config_eq_persistence(self):
        orig_preset = self.app.config.get("eq_preset")
        orig_bands = dict(self.app.config.get("eq_bands", {}))
        try:
            self.app.config["eq_preset"] = "Vocal"
            self.app.config["eq_bands"] = {"bass": -2.0, "low_mid": 1.0, "mid": 5.0, "high_mid": 4.0, "treble": 1.0}
            self.app._save_config()

            # Read back from config_path
            with open(self.app.config_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            self.assertEqual(saved.get("eq_preset"), "Vocal")
            self.assertEqual(saved.get("eq_bands", {}).get("mid"), 5.0)
        finally:
            self.app.config["eq_preset"] = orig_preset
            self.app.config["eq_bands"] = orig_bands
            self.app._save_config()


class TestLyricsAndLrcEngine(unittest.TestCase):
    def test_clean_music_title(self):
        self.assertEqual(clean_music_title("Alan Walker - Faded (Official Music Video)"), "Alan Walker - Faded")
        self.assertEqual(clean_music_title("Ed Sheeran - Shape of You [Official Video]"), "Ed Sheeran - Shape of You")
        self.assertEqual(clean_music_title("Rick Astley - Never Gonna Give You Up (Official MV)"), "Rick Astley - Never Gonna Give You Up")
        self.assertEqual(clean_music_title("Artist - Song [4K 60FPS] (Remastered)"), "Artist - Song")
        self.assertEqual(clean_music_title(""), "")

    def test_parse_and_format_lrc(self):
        sample = """
        [00:05.12] First line of song
        [00:10.50] Second line of lyrics
        [01:20.00] Third line later
        """
        parsed = parse_lrc(sample)
        self.assertEqual(len(parsed), 3)
        self.assertEqual(parsed[0], (5.12, "First line of song"))
        self.assertEqual(parsed[1], (10.5, "Second line of lyrics"))
        self.assertEqual(parsed[2], (80.0, "Third line later"))

        # Test format_lrc
        formatted = format_lrc(parsed)
        self.assertIn("[00:05.12] First line of song", formatted)
        self.assertIn("[01:20.00] Third line later", formatted)

    def test_get_active_lyric_index(self):
        lyrics = [
            (5.0, "Line 1"),
            (10.0, "Line 2"),
            (15.5, "Line 3"),
        ]
        self.assertEqual(get_active_lyric_index(lyrics, 0.0), -1)
        self.assertEqual(get_active_lyric_index(lyrics, 4.9), -1)
        self.assertEqual(get_active_lyric_index(lyrics, 5.0), 0)
        self.assertEqual(get_active_lyric_index(lyrics, 7.5), 0)
        self.assertEqual(get_active_lyric_index(lyrics, 10.0), 1)
        self.assertEqual(get_active_lyric_index(lyrics, 15.4), 1)
        self.assertEqual(get_active_lyric_index(lyrics, 15.5), 2)
        self.assertEqual(get_active_lyric_index(lyrics, 99.0), 2)
        self.assertEqual(get_active_lyric_index([], 10.0), -1)


class TestAudioEqualizer(unittest.TestCase):
    def test_eq_presets(self):
        self.assertIn("Flat", EQ_PRESETS)
        self.assertIn("Bass Boost", EQ_PRESETS)
        self.assertIn("Treble Boost", EQ_PRESETS)
        self.assertIn("Vocal", EQ_PRESETS)

        for p in EQ_PRESETS.values():
            self.assertIn("bass", p)
            self.assertIn("low_mid", p)
            self.assertIn("mid", p)
            self.assertIn("high_mid", p)
            self.assertIn("treble", p)
            self.assertIn("name_en", p)
            self.assertIn("name_th", p)

    def test_generate_ffmpeg_eq_filter(self):
        flat_bands = {"bass": 0, "low_mid": 0, "mid": 0, "high_mid": 0, "treble": 0}
        self.assertEqual(generate_ffmpeg_eq_filter(flat_bands), "")

        boost_bands = {"bass": 6.0, "low_mid": 0, "mid": 2.0, "high_mid": 0, "treble": -3.0}
        f_str = generate_ffmpeg_eq_filter(boost_bands)
        self.assertIn("equalizer=f=60:width_type=o:w=1:g=6.0", f_str)
        self.assertIn("equalizer=f=1000:width_type=o:w=1:g=2.0", f_str)
        self.assertIn("equalizer=f=12000:width_type=o:w=1:g=-3.0", f_str)

    def test_audio_player_eq_switching(self):
        player = AudioPlayer()
        player.set_eq_preset("Bass Boost")
        self.assertEqual(player.current_eq_preset, "Bass Boost")
        self.assertEqual(player.current_eq_bands["bass"], 7.0)

        player.set_eq_bands({"bass": 4.0, "low_mid": 1.0, "mid": 0, "high_mid": 0, "treble": 0})
        self.assertEqual(player.current_eq_preset, "Custom")
        self.assertEqual(player.current_eq_bands["bass"], 4.0)


class TestMultiPlatformUrlDetection(unittest.TestCase):
    def test_spotify_url_detection(self):
        plat, p_type, ident = detect_platform_url("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT")
        self.assertEqual(plat, "spotify")
        self.assertEqual(p_type, "track")
        self.assertEqual(ident, "4cOdK2wGLETKBW3PvgPWqT")

        plat, p_type, ident = detect_platform_url("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M")
        self.assertEqual(plat, "spotify")
        self.assertEqual(p_type, "playlist")
        self.assertEqual(ident, "37i9dQZF1DXcBWIGoYBM5M")

        plat, p_type, ident = detect_platform_url("https://open.spotify.com/album/4eLPsYPBmXABThSJ821sqY")
        self.assertEqual(plat, "spotify")
        self.assertEqual(p_type, "album")

    def test_apple_music_and_soundcloud_detection(self):
        plat, p_type, _ = detect_platform_url("https://music.apple.com/us/playlist/todays-hits/pl.f4d106fed2bd41149aaacabb233eb5eb")
        self.assertEqual(plat, "apple_music")
        self.assertEqual(p_type, "playlist")

        plat, p_type, _ = detect_platform_url("https://soundcloud.com/artist/sets/my-set")
        self.assertEqual(plat, "soundcloud")
        self.assertEqual(p_type, "playlist")

        plat, p_type, _ = detect_platform_url("https://youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(plat, "youtube")
        self.assertEqual(p_type, "video")

        plat, p_type, _ = detect_platform_url("Alan Walker Faded")
        self.assertEqual(plat, "search")


class TestAudioTaggerAndEmbedding(unittest.TestCase):
    def test_mp3_tagging_and_inspection(self):
        tf = os.path.join(tempfile.gettempdir(), "test_tagged_audio.mp3")
        try:
            with open(tf, "wb") as f:
                f.write(b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\x00" * 3000)

            meta = {
                "title": "Starlight Harmony",
                "artist": "Nexus Artist",
                "album": "OLED Dreams",
                "year": "2026",
                "genre": "Synthwave",
                "track_num": 1,
            }
            lyrics_sample = "[00:01.00] Starlight shining bright\n[00:05.00] In the midnight sky"
            ok = tag_audio_file(tf, meta, cover_data_or_url=b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4", lyrics_text=lyrics_sample)
            self.assertTrue(ok)

            info = get_media_info(tf)
            self.assertEqual(info["title"], "Starlight Harmony")
            self.assertEqual(info["artist"], "Nexus Artist")
            self.assertEqual(info["album"], "OLED Dreams")
            self.assertEqual(info["year"], "2026")
            self.assertIn("Starlight shining bright", info["lyrics"])
        finally:
            if os.path.exists(tf):
                with contextlib.suppress(Exception):
                    os.remove(tf)


class TestAudioVisualizerWidget(unittest.TestCase):
    def test_visualizer_canvas(self):
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        try:
            vis = AudioVisualizer(root, width=88, height=26, num_bars=14)
            self.assertEqual(vis.num_bars, 14)
            # Update with playback
            vis.update_bars(True, volume=0.8, bass_boost=6.0)
            # Update paused
            vis.update_bars(False)
            vis.set_color("#EC4899")
            self.assertEqual(vis.color, "#EC4899")
        finally:
            root.destroy()


class TestModernEdgeCasesAndRobustness(unittest.TestCase):
    def test_fetch_lyrics_local_file(self):
        tf = os.path.join(tempfile.gettempdir(), "test_song_with_lrc.mp3")
        lrc_file = os.path.join(tempfile.gettempdir(), "test_song_with_lrc.lrc")
        try:
            with open(tf, "wb") as f:
                f.write(b"dummy")
            with open(lrc_file, "w", encoding="utf-8") as f:
                f.write("[00:03.00] Local lyric line 1\n[00:08.50] Local lyric line 2\n")

            res = fetch_lyrics("test_song_with_lrc", file_path=tf)
            self.assertEqual(res["source"], "local_lrc")
            self.assertEqual(len(res["synced"]), 2)
            self.assertEqual(res["synced"][0], (3.0, "Local lyric line 1"))
        finally:
            for p in (tf, lrc_file):
                if os.path.exists(p):
                    with contextlib.suppress(Exception):
                        os.remove(p)

    def test_generate_ffmpeg_eq_filter_clamping(self):
        # Extreme values should be clamped to [-15, 15] dB
        extreme_bands = {"bass": 25.0, "treble": -30.0}
        f_str = generate_ffmpeg_eq_filter(extreme_bands)
        self.assertIn("equalizer=f=60:width_type=o:w=1:g=15.0", f_str)
        self.assertIn("equalizer=f=12000:width_type=o:w=1:g=-15.0", f_str)

        # Invalid or non-dict input returns empty string
        self.assertEqual(generate_ffmpeg_eq_filter(None), "")
        self.assertEqual(generate_ffmpeg_eq_filter("invalid"), "")

    def test_tag_audio_file_resilience(self):
        # Nonexistent file returns False without crashing
        res = tag_audio_file("C:/nonexistent_file_path.mp3", {"title": "Ghost"})
        self.assertFalse(res)


    def test_parse_music_metadata_and_prefix_stripping(self):
        # 1. Numbered playlist track with fallback artist must NOT corrupt artist to "01"
        m1 = parse_music_metadata("01 - Come Together", fallback_artist="The Beatles", fallback_album="Abbey Road", fallback_track=1)
        self.assertEqual(m1["title"], "Come Together")
        self.assertEqual(m1["artist"], "The Beatles")
        self.assertEqual(m1["track_num"], 1)
        self.assertEqual(m1["album"], "Abbey Road")

        # 2. Numbered track with inline artist
        m2 = parse_music_metadata("05 - Queen - Bohemian Rhapsody")
        self.assertEqual(m2["title"], "Bohemian Rhapsody")
        self.assertEqual(m2["artist"], "Queen")
        self.assertEqual(m2["track_num"], 5)

        # 3. Clean YouTube video title
        m3 = parse_music_metadata("Alan Walker - Faded (Official Music Video 4K)")
        self.assertEqual(m3["title"], "Faded")
        self.assertEqual(m3["artist"], "Alan Walker")

    def test_parse_lrc_extended_minutes_and_format_rollover(self):
        # 1. DJ mix / live concert over 99 minutes
        lrc_text = "[120:30.50] Deep in the live concert mix\n[01:05.3] Single decimal\n[00:01.999] Rollover mark"
        parsed = parse_lrc(lrc_text)
        self.assertEqual(len(parsed), 3)
        # 120 * 60 + 30.50 = 7230.50
        self.assertEqual(parsed[2][0], 7230.50)
        self.assertEqual(parsed[2][1], "Deep in the live concert mix")

        # 2. format_lrc boundary rollover (1.999 -> [00:02.00] not [00:01.100])
        formatted = format_lrc([(1.999, "Boundary Test")])
        self.assertIn("[00:02.00] Boundary Test", formatted)

    def test_apple_music_itunes_resolution(self):
        # Verify resolution using official iTunes lookup
        test_url = "https://music.apple.com/us/album/come-together/1441164426?i=1441164427"
        res = resolve_multiplatform_url(test_url)
        self.assertEqual(res["platform"], "apple_music")
        self.assertEqual(len(res["tracks"]), 1)
        trk = res["tracks"][0]
        self.assertIn("Beatles", trk["artist"])
        self.assertIn("Beatles", trk["search_query"])
        self.assertGreater(trk["duration"], 60)
        self.assertTrue(trk["thumbnail"].startswith("http"))

    def test_spotify_uri_resolution(self):
        plat, p_type, ident = detect_platform_url("spotify:track:4cOdK2wGLETKBW3PvgPWqT")
        self.assertEqual(plat, "spotify")
        self.assertEqual(p_type, "track")
        self.assertEqual(ident, "4cOdK2wGLETKBW3PvgPWqT")

        plat, p_type, ident = detect_platform_url("spotify:playlist:37i9dQZF1DXcBWIGoYBM5M")
        self.assertEqual(plat, "spotify")
        self.assertEqual(p_type, "playlist")

    def test_id3_duplicate_tag_cleansing(self):
        from mutagen.id3 import APIC, ID3, USLT
        tf = os.path.join(tempfile.gettempdir(), "test_id3_cleanse.mp3")
        try:
            with open(tf, "wb") as f:
                f.write(b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\x00" * 2500)
            audio = ID3(tf)
            audio.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Old", data=b"OLD"))
            audio.add(USLT(encoding=3, lang="eng", desc="Old", text="Old lyrics"))
            audio.save()

            ok = tag_audio_file(tf, {"title": "New", "artist": "New"}, cover_data_or_url=b"\xff\xd8\xff\xe0NEW", lyrics_text="[00:01.00] New lyrics")
            self.assertTrue(ok)

            audio2 = ID3(tf)
            self.assertEqual(len(audio2.getall("APIC")), 1)
            self.assertEqual(len(audio2.getall("USLT")), 1)
        finally:
            if os.path.exists(tf):
                with contextlib.suppress(Exception):
                    os.remove(tf)

    def test_audio_player_cleanup_and_cache(self):
        player = AudioPlayer()
        player._cleanup_cache(max_files=10)
        player.cleanup()
        self.assertEqual(len(player._temp_pcm_files), 0)

    def test_v330_16_presets_completeness(self):
        from nexus_audio import EQ_PRESETS
        expected_presets = [
            "Flat", "Bass Boost", "Treble Boost", "Vocal", "Club", "Rock",
            "Pop", "Jazz", "Hip Hop", "Dance", "Electronic", "Acoustic",
            "Vocal Booster", "Deep Bass", "Nightcore", "Slowed Reverb"
        ]
        self.assertEqual(len(EQ_PRESETS), 16)
        for preset in expected_presets:
            self.assertIn(preset, EQ_PRESETS, f"Missing preset: {preset}")
            bands = EQ_PRESETS[preset]
            for band_name in ("bass", "low_mid", "mid", "high_mid", "treble"):
                self.assertIn(band_name, bands)
                self.assertGreaterEqual(bands[band_name], -15.0)
                self.assertLessEqual(bands[band_name], 15.0)

    def test_v330_generate_ffmpeg_filter_dsp(self):
        from nexus_audio import generate_ffmpeg_eq_filter
        bands = {"bass": 5.0, "low_mid": 2.0, "mid": 0.0, "high_mid": -2.0, "treble": 4.0}

        # Baseline filter
        f_base = generate_ffmpeg_eq_filter(bands)
        self.assertIn("equalizer=f=60", f_base)
        self.assertIn("equalizer=f=12000", f_base)

        # Preamp gain
        f_preamp = generate_ffmpeg_eq_filter(bands, preamp=3.5)
        self.assertIn("volume=3.5dB", f_preamp)

        # Bass boost exciter (ratio 0.5 -> 50% -> 4.0dB boost at 50Hz)
        f_bass = generate_ffmpeg_eq_filter(bands, bass_boost=0.5)
        self.assertIn("equalizer=f=50:width_type=o:w=1.5:g=4.0", f_bass)

        # 3D spatial surround
        f_surround = generate_ffmpeg_eq_filter(bands, surround=True)
        self.assertIn("extrastereo=m=1.6", f_surround)

    def test_v330_export_m3u8_direct(self):
        import shutil

        from nexus_audio import export_m3u8_playlist
        temp_dir = tempfile.mkdtemp()
        track1 = os.path.join(temp_dir, "Track One.mp3")
        track2 = os.path.join(temp_dir, "Track Two.flac")
        with open(track1, "w") as f:
            f.write("audio")
        with open(track2, "w") as f:
            f.write("audio")

        try:
            m3u8_path = export_m3u8_playlist([track1, track2], "My Hits", temp_dir)
            self.assertTrue(os.path.exists(m3u8_path))
            with open(m3u8_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            self.assertEqual(lines[0].strip(), "#EXTM3U")
            self.assertTrue(any("Track One" in line for line in lines))
            self.assertTrue(any("Track Two" in line for line in lines))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_v330_convert_audio_file_tag_preservation(self):
        import shutil
        from unittest.mock import MagicMock, patch

        from nexus_audio import convert_audio_file

        temp_dir = tempfile.mkdtemp()
        src_file = os.path.join(temp_dir, "Original Song.mp3")
        fake_ffmpeg = os.path.join(temp_dir, "fake_ffmpeg.exe")
        with open(src_file, "wb") as f:
            f.write(b"dummy audio content")
        with open(fake_ffmpeg, "wb") as f:
            f.write(b"")

        try:
            with patch("subprocess.run") as mock_sub, \
                 patch("nexus_audio.tag_audio_file") as mock_tag:

                # Simulate successful ffmpeg transcoding producing a file
                def fake_ffmpeg_run(cmd, *args, **kwargs):
                    out_f = cmd[-1]
                    with open(out_f, "wb") as of:
                        of.write(b"x" * 2048)
                    return MagicMock(returncode=0)

                mock_sub.side_effect = fake_ffmpeg_run

                res = convert_audio_file(src_file, "flac", "320k", normalize=True, ffmpeg_bin=fake_ffmpeg)
                self.assertTrue(res["success"])
                self.assertEqual(res["format"], "flac")
                self.assertTrue(os.path.exists(res["output_path"]))
                # Check that tag_audio_file was invoked to embed tags
                mock_tag.assert_called_once()
                call_args = mock_tag.call_args
                self.assertEqual(call_args[0][0], res["output_path"])
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

