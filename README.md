<div align="center">
  <img src="https://raw.githubusercontent.com/masuzu2/NexusTube/main/icon.ico" width="100" alt="NexusTube Logo" />
  <h1>NexusTube v3.4.0</h1>
  <p><b>Next-Gen YouTube & Multi-Platform Music Suite & Studio Desktop Player</b></p>
  <p><i>Spotify & Apple Music Caliber OLED Dark Glassmorphism · pywebview Edge WebView2 · ui-ux-pro-max · by herlove</i></p>

  [![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-4338CA?style=flat-square&logo=python&logoColor=white)](https://python.org)
  [![Desktop](https://img.shields.io/badge/Desktop-pywebview%20Edge%20WebView2-22C55E?style=flat-square)](https://pywebview.flowrl.com/)
  [![Engine](https://img.shields.io/badge/Engine-yt--dlp-22C55E?style=flat-square)](https://github.com/yt-dlp/yt-dlp)
  [![FFmpeg](https://img.shields.io/badge/Engine-FFmpeg-EAB308?style=flat-square)](https://ffmpeg.org)
  [![Tests](https://img.shields.io/badge/Tests-170%2F170%20Passing-22C55E?style=flat-square)](https://github.com/masuzu2/NexusTube)
  [![Design](https://img.shields.io/badge/Design-ui--ux--pro--max%20Glassmorphism-EC4899?style=flat-square)](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)
</div>

<br/>

**NexusTube** เป็นสุดยอดโปรแกรมดาวน์โหลดและเครื่องเล่นเพลงระดับสตูดิโอ ที่ได้รับการยกเครื่องใหม่ทั้งหมดสู่สถาปัตยกรรม **HTML / Tailwind CSS / JavaScript บน Desktop WebView2 (pywebview)** สไตล์ Spotify, Apple Music และ Linear OLED Dark Glassmorphism รองรับ YouTube, Spotify, Apple Music, และ SoundCloud แบบครบวงจร 100% Offline-Ready ปราศจากการพึ่งพา External CDN พร้อมชุดทดสอบอัตโนมัติ 74 รายการผ่านฉลุย 100%

---

## ✨ Features เด่นใน NexusTube v3.2.0

### 🌌 Ultra-Modern OLED Interface (Spotify & Apple Music Caliber)
- **Deep OLED Dark Foundation (`#030307`):** พื้นผิวลึกมีมิติ ตัดด้วยการไล่ระดับแสง Glassmorphism (`backdrop-filter: blur(14px)`) นุ่มนวล สบายตา ป้องกันแสงสะท้อน
- **Dedicated Desktop Navigation Sidebar (240px Fixed):** แถบนำทางด้านซ้ายกว้าง 240px พร้อมไอคอน SVG คมชัด, ชื่อเมนูภาษาไทย/อังกฤษครบถ้วน, ตัวนับ Badge, และการ์ดข้อมูลพื้นที่จัดเก็บข้อมูลด้านล่าง
- **Dynamic 6-Color Live Accent Theming:** สลับธีมสีสด Neon Green, Cyber Indigo, OLED Pink, Electric Cyan, Sunset Amber, และ Ultra Violet ได้ทันทีแบบ Real-time พร้อมปรับแสง Glow และ Dynamic Spectrum Color อัตโนมัติ
- **Vector SVG Iconography:** ใช้ไอคอน SVG สไตล์ Lucide / Heroicons คุณภาพสูง คมชัดทุกระดับความละเอียด ไร้การใช้ Raw Emoji
- **Zero-Latency Python-JS Native Bridge (`NexusBridgeAPI`):** ควบคุมเครื่องยนต์เสียง, ดาวน์โหลด, และจัดการไฟล์ผ่าน IPC ความเร็วสูง

### 📥 Real-Time Download Queue & Dashboard
- **Queue Overview Stats Bar:** แดชบอร์ดสรุปสถิติคิวแบบ Real-time 3 การ์ดย่อย: งานทั้งหมด (Total Tasks), กำลังทำงาน (Active), และเสร็จสมบูรณ์ (Completed)
- **High-Res Thumbnail Preview:** แสดงรูปภาพหน้าปกจริงของวิดีโอ YouTube หรืออัลบั้มเพลงบนการ์ดดาวน์โหลดทันที พร้อมระบบ Fallback SVG กรณีออฟไลน์
- **Complete Bilingual Localization:** สถานะคิวและปุ่มควบคุมทั้งหมดแปลภาษาอัตโนมัติตามภาษาของระบบ (ดาวน์โหลดเสร็จสมบูรณ์ ✓, ความเร็ว, เวลาที่เหลือ, ▶ เล่น, 📂 เปิดโฟลเดอร์, 🛑 ยกเลิก, 🔄 ลองใหม่)

### 🎤 Synchronized Karaoke Lyrics (LRC Engine)
- **Interactive Full Karaoke View:** แสดงเนื้อเพลงที่เลื่อนตามเสียงเพลงแบบเรียลไทม์ (Synchronized LRC) พร้อมเน้นข้อความท่อนปัจจุบันด้วยสี Accent เรืองแสง
- **Click-to-Seek:** คลิกที่เนื้อเพลงท่อนใดก็ได้เพื่อกระโดดข้ามเวลาเล่นไปยังท่อนนั้นทันที
- **Multi-tier Lyric Lookup:** ค้นหาเนื้อเพลงอัตโนมัติจากไฟล์ `.lrc` ในเครื่อง, แท็กที่ฝังในไฟล์เสียง, และฐานข้อมูลออนไลน์สาธารณะ (LRCLIB)
- **Save .LRC:** ปุ่มบันทึกไฟล์เนื้อเพลง `.lrc` แยกเคียงคู่ไฟล์เพลงทันทีในคลิกเดียว

### 🎛️ Studio 5-Band Equalizer & Frequency Curve Canvas
- **5 Precision Frequency Bands:** ปรับแต่งย่านความถี่เสียง 60Hz (Sub-Bass), 250Hz (Low-Mid), 1kHz (Mid), 4kHz (High-Mid), และ 12kHz (Treble) แบบละเอียด ±15dB
- **Dynamic Response Curve Canvas:** แคนวาสจำลองเส้นกราฟการตอบสนองความถี่เสียงแบบเรียลไทม์ (Cubic Bezier Spline)
- **8 Studio Presets:** Flat, Bass Boost, Treble Boost, Vocal, Club, Rock, Acoustic, Electronic พร้อมระบบ Debounce ป้องกันเสียงสะดุด

### 📊 Animated Frequency Visualizer & Streamlined Player Bar
- **Docked 16-Bar Spectrum:** แถบกราฟิกวิเคราะห์คลื่นเสียง 16 แท่งบน Player bar ตอบสนองตามจังหวะเพลง ความดัง และ Bass Boost (60 FPS rAF throttled)
- **Streamlined Controls:** แถบควบคุมตามมาตรฐานเครื่องเล่นสตรีมมิ่งระดับพรีเมียม (Shuffle, Prev, Play/Pause วงกลมเรืองแสงขนาดใหญ่, Next, Repeat Loop List / Single Track)
- **Expanded Scrubber:** แถบเลื่อนเวลาและเวลาหัวท้ายความยาวกว้างสบายตา ป้องกันการกระตุกขณะลาก (Anti-Jitter Seek)

### 🌐 Multi-Platform Universal URL Resolver
- **Zero-Auth Platform Scraping:** รองรับการวางลิงก์จาก **Spotify** (Track, Album, Playlist), **Apple Music** (Track, Album, Playlist ผ่าน iTunes Lookup API), และ **SoundCloud** (Track, Set/Playlist)
- **Universal Playlist Selector:** หน้าต่างพรีวิวแทร็กทั้งหมดพร้อมปก, ช่องค้นหากรองเพลง, ปุ่มเลือกทั้งหมด (Select/Deselect All), และเลือกดาวน์โหลดลงคิวพร้อมกันแบบ Batch Download

### 🏷️ Smart Audio Tagger & Album Art Embedding
- **Title Sanitizer:** ลบคำรกรุงรังในชื่อเพลงของ YouTube ออกอัตโนมัติ เช่น `[Official Music Video]`, `(HD 1080p)`, `[4K 60FPS]`, `(Lyrics)`
- **Metadata & Lyrics Tagging:** ฝังข้อมูลศิลปิน, ชื่อเพลง, อัลบั้ม, ปี, แนวเพลง, เนื้อเพลง, และภาพหน้าปกคุณภาพสูงลงในไฟล์เสียง MP3, M4A, FLAC

### 🎧 Core Engine Features
- 🪄 **Zero Setup:** ไม่ต้องติดตั้ง `yt-dlp` หรือ `ffmpeg` เอง แอปดาวน์โหลดและตั้งค่า binary ให้อัตโนมัติในโฟลเดอร์เครื่อง
- 🔄 **Self-Healing Binary Engine:** ตรวจสอบความสมบูรณ์และอัปเดตเครื่องมือ `yt-dlp` และ `ffmpeg` ใหม่อยู่เสมอ
- ⚡ **Universal Audio Decoder:** เล่นไฟล์เสียงทุกนามสกุลทั้ง MP3, WAV, M4A/AAC, Opus, FLAC, OGG ผ่าน Fast On-Demand Transcode Cache
- 🔊 **EBU R128 Loudness Normalization:** ปรับระดับความดังของเพลงให้เท่ากันทุกเพลงอย่างแท้จริง
- 🎬 **Unrestricted Full HD / 4K:** ดาวน์โหลดวิดีโอความคมชัดสูงสุด 1080p, 2K, 4K (VP9/AV1/H.264) พร้อม Remux รวมเสียง
- 🎵 **Advanced Library Manager:** คลังเพลงพร้อมระบบค้นหา กรองเพลง จัดเรียง (ล่าสุด, ชื่อเพลง, ศิลปิน, ความยาว, ขนาดไฟล์)
- ✂️ **Audio Trimmer Pro:** เครื่องมือตัดต่อเสียงทำเสียงเรียกเข้าหรือท่อนฮุก มีปุ่ม **Preview Slice** และหยุดอัตโนมัติเมื่อครบเวลา
- 🌐 **Instant Bilingual UI:** สลับภาษาได้ทันทีระหว่าง **ภาษาไทย** และ **English** ทั่วทั้งแอป

---

## 🚀 Quickstart (วิธีใช้งาน)

### 1. สำหรับผู้ใช้งานทั่วไป (Windows Standalone)
1. ไปที่โฟลเดอร์ `C:\Users\Administrator\Downloads\NexusTube\` หรือแตกไฟล์ `NexusTube_v3.2.0_Windows.zip`
2. ดับเบิลคลิกเปิดไฟล์ `NexusTube.exe` ขึ้นมาใช้งานได้ทันทีโดยไม่ต้องติดตั้ง Python!

### 2. การดาวน์โหลดเพลงและวิดีโอ
- คัดลอกลิงก์จาก YouTube, Spotify, Apple Music, หรือ SoundCloud
- วางในกล่องข้อความหน้า **Search & Discover** หรือกดปุ่ม **📋 วางลิงก์**
- เลือกฟอร์แมตเสียง/วิดีโอที่ต้องการ (MP3 320k, M4A, FLAC, MP4 1080p, 4K)
- หากเป็นเพลย์ลิสต์ ระบบจะเปิดหน้าต่าง **Universal Playlist Selector** ให้เลือกเฉพาะเพลงที่ต้องการได้ทันที
- กด **Download** เพื่อเริ่มกระบวนการ และสลับไปดูสถานะที่แท็บ **คิวดาวน์โหลด (Queue)**

### 3. การฟังเพลงและใช้งาน Studio Tools
- ไปที่แท็บ **คลังเพลง (Music Library)** เพื่อดูเพลงทั้งหมดที่ดาวน์โหลดแล้ว
- คลิกที่การ์ดเพลงเพื่อเริ่มเล่นทันที แถบควบคุมด้านล่างจะเริ่มเล่นเพลงพร้อมคลื่นเสียง Spectrum
- กดปุ่ม **🎤 Karaoke Lyrics** เพื่อดูเนื้อเพลงวิ่งตามเวลาสด หรือคลิกท่อนใดก็ได้เพื่อกระโดดข้ามเวลา
- กดปุ่ม **🎛️ Studio Equalizer** เพื่อเลือกพรีเซ็ตเสียงหรือปรับแต่งความถี่ 5 แถบด้วยตัวเอง

---

## 🛠️ Developer Setup & Architecture

### Prerequisites
- Windows 10/11 / Windows Server 2022+ (x64)
- Python 3.11.x หรือ 3.12.x
- Microsoft Edge WebView2 Runtime (ติดตั้งมาพร้อมกับ Windows 10/11 เป็นมาตรฐาน)

### Installation
```powershell
# Navigate to the project directory
cd C:\Users\Administrator\NexusTube

# Install required dependencies
pip install -r requirements.txt

# Run complete automated test suite (74 tests)
pytest -v tests/

# Launch NexusTube in Modern Web Desktop mode
python YT_Downloader_V2.py

# (Optional) Launch legacy Tkinter fallback mode
python YT_Downloader_V2.py --legacy
```

### Building Standalone Executable with PyInstaller
```powershell
# Build standalone NexusTube.exe with official icon and embedded Web UI
pyinstaller --noconfirm NexusTube.spec
```
ไฟล์ Executable ขนาดกะทัดรัด (~41 MB) จะถูกสร้างไว้ในโฟลเดอร์ `dist/NexusTube.exe`

---

## 📂 Project Structure

```text
NexusTube/
├── YT_Downloader_V2.py          # Native Python Application & NexusBridgeAPI IPC
├── nexus_audio.py               # Audio Subsystem (LRC, 5-Band EQ, URL Resolver, ID3 Tagger)
├── nexus_discord.py             # Discord Rich Presence Subsystem
├── nexus_doctor.py              # Environment Diagnostics & Self-Healing Engine
├── nexus_hotkeys_tray.py        # System Tray, Notification & Global Hotkeys Engine
├── NexusTube.spec               # PyInstaller Bundling Specification
├── build_installer.py           # WiX Toolset MSI Installer Builder
├── NexusTube by herlove.ico     # Official High-Resolution Application Icon
├── icon.ico                     # Fallback Application Icon
├── requirements.txt             # Python Package Dependencies
├── docs/                        # Comprehensive Architecture & Design Specifications
│   ├── ARCHITECTURE.md          # Technical Architecture, DSP & IPC Deep Dive
│   ├── API_REFERENCE.md         # Complete NexusBridgeAPI Method Reference
│   ├── DESIGN.md                # Formal UI/UX Design System Specification
│   ├── USER_GUIDE.md            # Comprehensive User Manual (TH/EN)
│   ├── DEVNOTES.md              # Developer Notes & Maintenance Guide
│   └── BUILD_CHECKLIST.md       # Pre-flight Build & Verification Checklist
├── web/                         # Self-Contained WebUI Assets (Zero External CDN)
│   ├── index.html               # Main Single-Page Desktop Application Layout
│   ├── styles.css               # OLED Dark Glassmorphism Design System Stylesheet
│   ├── app.js                   # Application State, Navigation, and Bridge Controllers
│   └── tailwind.js              # Offline Standalone Tailwind Engine Core
├── tests/                       # Automated Test Suite (170/170 Passing — 100%)
│   ├── test_nexus_bridge.py     # Bridge IPC, Queue, Thumbnail, and Web UI Tests
│   ├── test_nexus_tube.py       # Audio Engine, Resolvers, Tagger, and Player Tests
│   ├── test_error_handling.py   # Crash Handling, Logging, and Diagnostics Tests
│   ├── test_temp_dir_cleanup.py # GDI Font Redirection & Temporary Cleanup Tests
│   ├── test_v340_features.py    # v3.4.0 Features Integration Tests
│   ├── test_exe_lifecycle.py    # Live Standalone Binary Lifecycle & Exit Tests
│   ├── test_web_contract.py     # Web UI ⟷ Python Bridge Contract Integrity Tests
│   ├── test_resilience.py       # Network Outage, Rate Limit & File Error Resilience Tests
│   └── test_installer_integrity.py # MSI & Packaged Bundle Integrity Tests
├── installer/                   # WiX MSI Packaging Configuration & Assets
├── README.md                    # Project Master Presentation & Overview
├── CHANGELOG.md                 # Full Chronological Version History
└── LICENSE                      # MIT Open-Source License
```

---

## 📜 Documentation Index
- 🎨 [DESIGN.md](docs/DESIGN.md) — ระบบการออกแบบ UI/UX Pro Max 9 บทฉบับเต็ม
- 🏗️ [ARCHITECTURE.md](docs/ARCHITECTURE.md) — สถาปัตยกรรมระบบ, การประมวลผลเสียง, และ IPC
- 📖 [USER_GUIDE.md](docs/USER_GUIDE.md) — คู่มือการใช้งานอย่างละเอียดแบบสองภาษา
- 🔌 [API_REFERENCE.md](docs/API_REFERENCE.md) — สเปกและเอกสารของ NexusBridgeAPI ทุกฟังก์ชัน
- 📝 [DEVNOTES.md](docs/DEVNOTES.md) — บันทึกการพัฒนาและการบำรุงรักษา
- ✅ [BUILD_CHECKLIST.md](docs/BUILD_CHECKLIST.md) — รายการตรวจสอบความสมบูรณ์ก่อนบิลด์และแจกจ่าย
- 📜 [CHANGELOG.md](CHANGELOG.md) — ประวัติการอัปเดตและการเปลี่ยนแปลงทุกเวอร์ชัน

---

## ⚖️ License & Credits
- **Author & Architect**: by herlove
- **Repository**: [https://github.com/masuzu2/NexusTube](https://github.com/masuzu2/NexusTube)
- **License**: [MIT License](LICENSE)
- **Design Standard**: Inspired by [ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) and [web-skills](https://github.com/andreasbm/web-skills)
