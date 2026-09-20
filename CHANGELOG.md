# Changelog

All notable changes to the **NexusTube** project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [3.3.0] - 2026-09-07 — State-of-the-Art Music Suite Modernization

### 🎧 Audio Engine & DSP Mastering Suite
- **16 Studio EQ Presets**:
  - Expanded equalizer presets from 8 to 16 studio curves: Flat, Bass Boost, Treble Boost, Vocal, Club, Rock, Pop, Jazz, Hip Hop, Dance, Electronic, Classical, Acoustic, Vocal Booster, Deep Bass, Nightcore, and Slowed Reverb.
- **DSP Mastering Suite Controls**:
  - Pre-Amp gain adjustment (±6.0 dB) with safe gain staging.
  - Sub-Bass Exciter knob (0-100%) leveraging FFmpeg `bass=g=...` filter.
  - 3D Spatial Surround toggle leveraging FFmpeg `extrastereo=m=1.35` psychoacoustic stereo widening.
- **Studio Audio Transcoder Modal**:
  - Transcode between MP3, AAC/M4A, FLAC, WAV, OGG, and OPUS with bitrate selection (128k, 192k, 256k, 320k) and optional EBU R128 international broadcast loudness normalization (-14 LUFS).
- **M3U8 Standard Playlist Export**:
  - Full UTF-8 `#EXTM3U` playlist generation for music library collections compatible with standard media players.

### 🌟 UI/UX & Music Library Modernization
- **Dual View Modes (Grid vs Table View)**:
  - Added Spotify/Apple Music caliber list/table view alongside high-density responsive grid view.
  - Detailed metadata rows: track number, cover art thumbnail, title, artist, format badge, duration, file size, and quick actions.
- **Favorites Management**:
  - Heart icon on every track card and table row with persistent JSON storage.
  - "Favorites Only" quick filter chip in library toolbar.
- **Library Play All & Shuffle All**:
  - One-click "Play All" and "Shuffle All" buttons in Music Library header.
- **Search Discovery Vibes & Recent Searches**:
  - Trending vibes discovery carousel (Pop Hits, Lofi Chill, Gym Motivation, Midnight Jazz, Deep Focus, Acoustic Coffee).
  - Recent search history chips persisted across sessions.
- **Karaoke Lyrics Enhancements**:
  - Copy lyrics to clipboard button.
  - Interactive font size zoom (`A-` / `A+`).
  - Immersive Fullscreen Karaoke mode with large glowing active lyrics and floating mini player bar.
- **Docked Persistent Player Upgrades**:
  - Seek bar hover time tooltip with millisecond precision.
  - Playback speed button (cycling through 0.75x, 1.0x, 1.25x, 1.5x, 1.75x, 2.0x).
  - Sleep Timer with customizable durations (15m, 30m, 45m, 60m, end of track) and auto-pause.
  - Keyboard Shortcuts cheat sheet modal and global hotkeys (`Space`, `Ctrl+K`, `←/→`, `Ctrl+←/→`, `↑/↓`, `M`, `F`, `?`, `Alt+1..6`).

### 🧪 Automated Testing & Integrity
- Expanded test suite to **83 automated tests**, all passing 100% with zero regressions.
- Synchronized codebase with development root.

---

## [3.2.0] - 2026-09-06 — Master Modernization & UI/UX Perfection Release

### 🎨 Visual & Layout Modernization (ui-ux-pro-max-skill & web-skills)
- **Fixed Sidebar Desktop Width & Visibility**:
  - Replaced responsive collapse classes `w-16 md:w-64` with fixed `w-60` (240px) dedicated desktop navigation.
  - Removed `hidden md:inline` and `hidden md:block` from sidebar items, ensuring that navigation labels ("Search & Discover", "Download Queue", "Music Library", "Studio Equalizer", "Karaoke Lyrics", "Settings"), category dividers ("Navigation", "Studio Tools"), badges, and the Quick Output Folder card are permanently visible and readable.
- **High-Resolution Queue Video Thumbnails**:
  - Enhanced `add_to_queue()` and `get_queue_state()` in `YT_Downloader_V2.py` to extract and propagate YouTube video thumbnails (`https://i.ytimg.com/vi/<id>/mqdefault.jpg`) and embedded ID3 cover art into queue items.
  - Updated `renderQueueList()` in `web/app.js` with sleek `14x14` (56px) rounded cover art images with graceful fallback SVG icons on offline/error.
- **Full Bilingual Localization in Queue**:
  - Wrapped all queue status badges (`Complete ✓`, `Downloading`, `Processing Tags…`, `Cancelled`, `Failed ✗`, `Waiting…`), metric labels (`Speed`, `ETA`), and action buttons (`Play`, `Folder`, `Cancel`, `Retry`) with dynamic `t()` localization helper keys.
  - Added full Thai and English vocabulary in `LOCALES` dictionary.
- **Streamlined Docked Player Controls**:
  - Removed legacy, intrusive `btn-stop` button from between Prev and Play/Pause.
  - Expanded scrubber bar from `max-w-xl` to `max-w-2xl` for fluid, comfortable seek control.
  - Centered playback buttons (`Shuffle`, `Prev`, 44px circular `Play/Pause` with glow, `Next`, `Repeat`) adhering to Spotify and Apple Music caliber standards.
- **Queue Overview Statistics Dashboard**:
  - Added a 3-card stats header above download queue: Total Tasks, Active Downloads (with spinner), and Completed Tasks (with success checkmark), eliminating awkward negative black space.

### 🧪 Automated Testing & Reliability
- Expanded unit and integration test suite from 71 to **74 automated tests**, passing 100% with zero regressions.
- Added tests covering queue thumbnail propagation, `LOCALES` dictionary completeness, and WebUI DOM layout integrity.
- Verified PyInstaller standalone build producing a 41.3 MB standalone `NexusTube.exe`.

---

## [3.1.0] - 2026-09-05 — Multi-Platform Resolver & Studio Tools Release

### 🌐 Multi-Platform Integration
- **Universal Zero-Auth URL Resolvers**:
  - Added Spotify track, album, and playlist scraper.
  - Added Apple Music scraping via native iTunes Search/Lookup API.
  - Added SoundCloud track and set resolver.
- **Universal Playlist Selector Modal**:
  - Added popup modal for multi-track links allowing users to select individual tracks, filter by title, or batch download.

### 🎤 Synchronized Karaoke Lyrics
- **LRC Parser & Engine**:
  - Added support for parsing timestamps `[mm:ss.xx]` and formatting synced lyrics.
  - Implemented 3-tier lyrics resolution: local `.lrc`, embedded metadata tag, and LRCLIB public API fallback.
  - Added interactive full-screen Karaoke view with automatic scrolling and click-to-seek playback.

### 🎛️ Studio 5-Band Equalizer
- **DSP Filter Generation**:
  - Added 5-band biquad equalizer (60Hz, 250Hz, 1kHz, 4kHz, 12kHz) with safety clamping [-15dB, +15dB].
  - 8 Studio Presets: Flat, Bass Boost, Treble Boost, Vocal, Club, Rock, Acoustic, Electronic.
  - Real-time cubic Bezier curve visualization on HTML5 Canvas.

---

## [3.0.0] - 2026-09-04 — Desktop WebUI Architecture Transformation

### ⚡ Architectural Rewrite
- Migrated primary desktop interface from Tkinter to **pywebview with Microsoft Edge WebView2** (`edgechromium`).
- Implemented **`NexusBridgeAPI`** native IPC bridge connecting JavaScript front-end to Python backend.
- Designed 100% self-contained Web UI assets (`web/index.html`, `web/styles.css`, `web/app.js`, `web/tailwind.js`) with zero CDN dependencies for offline execution.
- Added 16-bar spectrum audio visualizer running at 60 FPS via `requestAnimationFrame`.

---

## [2.0.0] - 2026-08-15 — Self-Healing Engines & Audio Decoders

### 🔧 Core Engine Upgrades
- Added self-healing automatic download and update system for `yt-dlp` and `ffmpeg`.
- Added EBU R128 audio volume normalization.
- Added smart title sanitizer removing unwanted YouTube brackets (e.g. `[Official Video]`).
- Implemented fast on-demand audio transcode cache for non-standard audio formats.

---

## [1.0.0] - 2026-07-01 — Initial Release

- Core YouTube audio and video downloading using `yt-dlp`.
- Formats supported: MP3 (320k, 192k), M4A, MP4 (1080p, 720p).
- Basic audio player and folder manager.
