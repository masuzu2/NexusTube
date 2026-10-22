<div align="center">
  <img src="https://raw.githubusercontent.com/masuzu2/NexusTube/main/icon.ico" width="100" alt="NexusTube Logo" />
  <h1>NexusTube v3.4.0</h1>
  <p><b>Next-Gen YouTube & Multi-Platform Music Suite & Studio Desktop Player</b></p>
  <p><i>Spotify & Apple Music Caliber OLED Dark Glassmorphism · Electron · by herlove</i></p>

  [![Desktop](https://img.shields.io/badge/Desktop-Electron-22C55E?style=flat-square)](https://www.electronjs.org/)
  [![Engine](https://img.shields.io/badge/Engine-yt--dlp-22C55E?style=flat-square)](https://github.com/yt-dlp/yt-dlp)
  [![FFmpeg](https://img.shields.io/badge/Engine-FFmpeg-EAB308?style=flat-square)](https://ffmpeg.org)
  [![Design](https://img.shields.io/badge/Design-ui--ux--pro--max%20Glassmorphism-EC4899?style=flat-square)](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)
</div>

<br/>

**NexusTube** เป็นโปรแกรมดาวน์โหลดและเครื่องเล่นเพลงบนเดสก์ท็อป ใช้ Electron กับหน้าเว็บในตัว รองรับ YouTube, Spotify, Apple Music และ SoundCloud

---

## ✨ Features เด่นใน NexusTube v3.2.0

### 🌌 Ultra-Modern OLED Interface (Spotify & Apple Music Caliber)
- **Deep OLED Dark Foundation (`#030307`):** พื้นผิวลึกมีมิติ ตัดด้วยการไล่ระดับแสง Glassmorphism (`backdrop-filter: blur(14px)`) นุ่มนวล สบายตา ป้องกันแสงสะท้อน
- **Dedicated Desktop Navigation Sidebar (240px Fixed):** แถบนำทางด้านซ้ายกว้าง 240px พร้อมไอคอน SVG คมชัด, ชื่อเมนูภาษาไทย/อังกฤษครบถ้วน, ตัวนับ Badge, และการ์ดข้อมูลพื้นที่จัดเก็บข้อมูลด้านล่าง
- **Dynamic 6-Color Live Accent Theming:** สลับธีมสีสด Neon Green, Cyber Indigo, OLED Pink, Electric Cyan, Sunset Amber, และ Ultra Violet ได้ทันทีแบบ Real-time พร้อมปรับแสง Glow และ Dynamic Spectrum Color อัตโนมัติ
- **Vector SVG Iconography:** ใช้ไอคอน SVG สไตล์ Lucide / Heroicons คุณภาพสูง คมชัดทุกระดับความละเอียด ไร้การใช้ Raw Emoji
- **Desktop bridge (`NexusBridgeAPI`):** หน้าเว็บสั่งดาวน์โหลด เล่นเพลง และจัดการไฟล์ผ่าน IPC ของ Electron

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

### 1. สำหรับผู้ใช้งานทั่วไป (Windows)
1. ติดตั้ง `NexusTube_Setup_v3.4.0.msi`
2. เปิด NexusTube จากช็อตคัตบนเดสก์ท็อปหรือเมนูเริ่ม

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
- Windows 10/11 (x64)
- Node.js ใช้ตอนพัฒนาและตอนสร้างตัวติดตั้ง

### Run and build
```powershell
# Launch the unpacked app
START_ELECTRON.bat

# Build NexusTube_Setup_v3.4.0.msi
BUILD_INSTALLER.bat
```

---

## 📂 Project Structure

```text
NexusTube/
├── index.js                     # Electron main process
├── src/                         # Download queue, engines, player, bridge
├── web/                         # Desktop UI
├── build_msi.js                 # WiX MSI builder
├── BUILD_INSTALLER.bat          # Build NexusTube_Setup_v3.4.0.msi
├── START_ELECTRON.bat           # Launch the unpacked app
├── package.json
├── installer/                   # WiX layout and license
├── tests/                       # Node tests for download policy
├── docs/
│   ├── DESIGN.md
│   └── USER_GUIDE.md
└── LICENSE
```

---

## 📜 Documentation Index
- 🎨 [DESIGN.md](docs/DESIGN.md) — ระบบการออกแบบหน้าตา
- 📖 [USER_GUIDE.md](docs/USER_GUIDE.md) — คู่มือการใช้งาน
- 📜 [CHANGELOG.md](CHANGELOG.md) — ประวัติการอัปเดต

---

## ⚖️ License & Credits
- **Author & Architect**: by herlove
- **Repository**: [https://github.com/masuzu2/NexusTube](https://github.com/masuzu2/NexusTube)
- **License**: [MIT License](LICENSE)
- **Design Standard**: Inspired by [ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) and [web-skills](https://github.com/andreasbm/web-skills)
