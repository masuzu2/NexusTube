# Changelog

All notable changes to the **NexusTube** project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [3.10.0] - 2026-11-22 — Cross-Platform Search & Download Settings

### 🔍 ค้นหาข้ามแพลตฟอร์ม
- ค้นหาครั้งเดียวได้ผลจาก **YouTube + Apple Music** (iTunes Search API สาธารณะ) — dedupe ตามชื่อ+ศิลปินอัตโนมัติ
- badge แหล่งที่มาบนผลค้นหา (▶ YouTube / ♪ Apple Music)
- วางลิงก์ Apple Music → หาคลิปคู่บน YouTube ให้อัตโนมัติแล้วคง metadata คุณภาพสูงของ Apple
- กันค้นหาชนตอน self-update กำลังแทนที่ yt-dlp (gate รอ engine พร้อม)

### ⚙️ ตั้งค่าในเว็บโหลด (ใหม่)
- ฝังภาพปก / metadata / เนื้อเพลง / SponsorBlock / normalize — เปลี่ยนแล้วบันทึกทันที
- **จำนวนดาวน์โหลดพร้อมกันปรับได้ 1–6** (เดิมล็อก 3 ตายตัว) อ่านสดจาก config

### 🧰 Desktop
- เมนู tray ใหม่: **🌐 เปิดเว็บโหลดเพลง** (เปิดเบราว์เซอร์ 127.0.0.1:8787 ให้เลย)
- เมนู tray: **🐞 รายงานปัญหา…** — เปิด GitHub Issues พร้อม log 60 บรรทัดล่าสุด (opt-in)

### 🌐 เว็บโหลดสองภาษา
- toggle ไทย/English ทั้งหน้า (จำความต้องการไว้) — queue, ตั้งค่า, สถานะงาน, ปุ่มทุกตัว

---
## [3.9.2] - 2026-11-22 — Update Progress UI

- **แถบสถานะอัปเดตถาวร** (update pill): แทน toast ที่ระเบิดทุก chunk ระหว่างดาวน์โหลด — เห็น % แบบเรียลไทม์ในแถบเดียว พร้อม progress bar ไล่สี ม่วง→เขียว, indeterminate ตอนติดตั้ง, เปลี่ยนสีตามผลสำเร็จ/ล้มเหลว
- ลิงก์ดาวน์โหลดบนเว็บ portal เป็นแบบ dynamic ดึงจาก GitHub API — เปลี่ยนเวอร์ชันกี่ครั้งปุ่มก็ถูกต้องเสมอ

---
## [3.9.1] - 2026-11-22 — Hardened Build

รีลีส build ใหม่ให้ผู้ใช้ที่ติดตั้ง 3.9.0 ไว้ก่อนหน้า ผ่านระบบ auto-update (เวอร์ชันเดิมเลขเดียวกัน อัปเดตไม่ trigger) — build นี้มีครบ:
- ระบบโหลดกันพัง 7 ชั้น (watchdog, auto-retry, yt-dlp self-heal, format fallback, queue persistence, disk pre-flight)
- asar packaging + updater ที่ตรวจ SHA-256
- self-updater แข็งแรง 5 ชั้น (hash verify, download retry, crash-loop rollback, integrity check, auto-relaunch)

---

## [3.9.0] - 2026-11-22 — Unified Electron Edition & Local-first Download Site

### 🛡️ Download Resilience — ระบบโหลดกันพัง 7 ชั้น
- **Watchdog จับงานค้าง**: ไม่มีความคืบหน้า 90 วิ → ฆ่าแล้วลองใหม่อัตโนมัติ (ตรวจทุก 15 วิ)
- **จำแนก error อัตโนมัติ** (download-resilience.js): transient → retry 3 ครั้งถอยหลัง 3s/10s/30s · extractor → อัปเดต yt-dlp แล้วลองใหม่ · fatal → รายงานเหตุผลเป็นภาษาไทยทันที
- **yt-dlp self-healing**: ensureFreshYtdlp เทียบเวอร์ชันจริงกับ GitHub แล้วอัปเดตเอง + ลูปเช็คทุก 12 ชม.
- **Format fallback chain**: flac→mp3→m4a, mp4_1080→720→best — สลับให้เองเมื่อคลิปไม่มีรูปแบบที่ขอ
- **คิวอยู่รอด**: เซฟลง queue.json — ปิดแอปกลางคัน เปิดใหม่งานกลับเข้าคิวเอง
- **เช็คพื้นที่ดิสก์**: เหลือ < 250 MB แจ้งเตือนก่อนเริ่มงาน ไม่ให้ไฟล์เสียหาย
- **/health ครบขึ้น**: รายงานสถานะเครื่องมือ + สถิติคิว

---
### 🔄 Self-Updater แข็งแรงขึ้น 5 ชั้น
- **ตรวจ SHA-256 ก่อนติดตั้ง**: zip ไม่ตรงลายเซ็น (จาก zip_sha256 ใน version.json) = ทิ้งทันที ไม่แตะไฟล์แอป
- **ดาวน์โหลดมี retry** 3 รอบ กัน CDN/เน็ตสะดุดช่วงสั้น
- **จับอัปเดตเสีย**: นับจำนวนบูตหลังอัปเดต ล้มซ้ำ ≥ 3 ครั้ง → คืนเวอร์ชันเดิมอัตโนมัติ
- **ยืนยันความเสถียร**: รันเนียน 90 วิ = เคลียร์ boot counter + backup เก่า
- **npm run update-package**: สร้าง app-update.zip + version.json พร้อม hash ในคำสั่งเดียว

---
### 🧹 Cleanup
- ลบไฟล์ยุค Python ทั้งหมด (PyInstaller, WiX MSI, spec, scripts), media, logs, mockups — repo เหลือแต่แอป Electron จริง
- ลบ GitHub workflows ยุค Python ออก

### 🌐 Local-first Download Site
- เว็บโหลดเพลงรันที่ 127.0.0.1:8787 ในตัวแอป (ใช้ config/คิวตัวเดียวกับแอป)
- เพิ่ม endpoint /health; ตัด Cloudflare tunnel และ site-CORS ออกทั้งหมด
- หน้า gh-pages เปลี่ยนเป็น portal: ปุ่มดาวน์โหลด + ตรวจจับเว็บในเครื่อง
- รันแบบไม่เปิดหน้าต่างได้ด้วย NexusTube.exe --web-server หรือ START_WEB.bat

### 🛠 Installer (NSIS)
- Assisted installer: เลือกภาษา ไทย/อังกฤษ, หน้า license, เลือกโฟลเดอร์, Desktop/Start Menu shortcuts, run-after-finish
- ชื่อไฟล์มาตรฐาน NexusTube-Setup-3.9.0.exe / NexusTube-3.9.0-Portable.exe
- ระบบ auto-update (version.json + app-update.zip) กลับมาทำงาน

---

## [3.5.1] - 2026-11-18 — Crash-Proof Systems & Update Rollback

### 🛡️ Crash Resilience
- **File Logger**: log ทุก event/error ลง `%APPDATA%\NexusTube\logs\app-YYYY-MM-DD.log` (ตัด log เก่าอัตโนมัติเกิน 7 วัน) — วินิจฉัยเครื่องเพื่อนระยะไกลได้
- **uncaughtException / unhandledRejection handlers**: แอปไม่ตายเงียบ ๆ อีกต่อไป ทุก error ถูกบันทึก
- **Renderer auto-reload**: หน้าจอ crash/OOM → โหลด UI ใหม่อัตโนมัติ ไม่จอดำ

### ⏪ Update Rollback Safety
- **สำรองก่อนอัปเดต**: ทุกครั้งที่ self-update ก็อปไฟล์เดิมเก็บใน `update-backup` ก่อนเขียนทับ
- **Startup integrity check**: เปิดแอปแล้วเจอว่าอัปเดตครั้งก่อนโดนขัดจังหวะกลางทาง (ไม่มี marker) → คืนไฟล์เดิมจาก backup อัตโนมัติ กันแอปเปิดไม่ติดแบบเคยเกิด

### 🔄 Engine Self-Healing (รายวัน)
- เช็ค yt-dlp เวอร์ชันใหม่วันละครั้งแบบเงียบ ๆ (เว้น 20 ชม.) — เจอของใหม่อัปเองโดยไม่ต้องไปกดปุ่มใน Settings

### 🔒 Security
- **Content-Security-Policy**: จำกัด script/style/img/media/connect sources ที่ชัดเจน ลดพื้นที่โจมตีถ้ามี injection ใน UI

---

## [3.5.0] - 2026-11-18 — App Self-Update System (FLUX-style)

- **Automatic self-update**: เช็ค `version.json` บน GitHub Releases ตอนเปิด + ทุก 5 นาที — เจอเวอร์ชันใหม่โหลด `app-update.zip` แตกไฟล์ทับแล้ว relaunch เองเงียบ ๆ
- Progress แจ้งผ่าน toast: พบเวอร์ชันใหม่ → กำลังโหลด x% → ติดตั้ง → รีสตาร์ท
- โหมด dev ข้ามระบบอัตโนมัติ (กันเผลออัปทับ source)
- `make-app-update.ps1` สร้างแพ็กเกจรวม production node_modules ในคลิกเดียว

---

## [3.4.1] - 2026-11-18 — True Zero-Setup & State Restore

### ⚙️ Engine Auto-Setup (Zero Setup แบบจริงจัง)
- **Automatic Engine Download on First Launch**:
  - แอปตรวจจับอัตโนมัติว่ายังไม่มี `yt-dlp` หรือ `FFmpeg` แล้วดาวน์โหลดเองทันทีตอนเปิดโปรแกรมครั้งแรก (ไม่ต้องกดปุ่มในหน้า Settings อีกต่อไป)
  - Header badge แสดง progress สด ๆ: `Engines: กำลังโหลด 44%` → `Engines: Ready` พร้อม toast แจ้งเมื่อพร้อมใช้งาน
  - Progress ส่งผ่าน IPC channel ใหม่ `nexus:engine-progress` (main → preload → CustomEvent ใน renderer)

### 🔄 State Restore & Polish
- **`get_initial_state` ครบสมบูรณ์**:
  - คืน `sleep_timer`, `mini_player`, `normalize` ให้ UI restore สถานะล่าสุดได้หลังปิด-เปิดแอปใหม่
- **System Tray version label** อ่านจาก `VERSION` ใน config แทนการ hardcode

### ✅ Verified End-to-End
- ค้นหา YouTube ผ่าน `yt-dlp` จริง (12 ผลลัพธ์ใน 3.2 วินาที)
- ดาวน์โหลด → transcode MP3 320k → ฝัง metadata ครบวงจร (ทดสอบกับไฟล์ยาว 6 ชั่วโมง)
- โหลด engine อัตโนมัติ: yt-dlp 22.5MB + FFmpeg/FFprobe/FFplay ~162MB ต่อตัวเสร็จสมบูรณ์

---

## [3.4.0] - 2026-09-20 — Next-Gen Desktop Music Suite & Professional MSI Installer

### 📦 Packaging & Installation
- **Professional Windows MSI Installer**:
  - Added WiX Toolset v3 packaging pipeline generating `NexusTube_Setup_v3.4.0.msi`.
  - Full support for standard Windows Add/Remove Programs, Desktop and Start Menu shortcuts, and silent enterprise deployment (`msiexec /i NexusTube_Setup.msi /quiet`).
- **GDI Font Locking & Temp Directory Cleanup Fix**:
  - Permanently resolved `Failed to remove temporary directory: _MEI...` on application exit.
  - Redirected font extraction to user local app data (`%LOCALAPPDATA%\NexusTube\fonts`) and added 64-bit HWND pointer safety in system tray.

### 🎛️ Features & Usability
- **Floating Always-on-Top Mini Player**:
  - Compact picture-in-picture player mode with persistent coordinate preservation and screen clamping.
- **In-App yt-dlp One-Click Updater**:
  - Automatic check and one-click binary update for yt-dlp directly from GitHub releases.
- **Enterprise-Grade Automated Test Suite**:
  - 170 automated unit and integration tests covering audio engines, bridge contracts, error resilience, and installer packaging.

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
