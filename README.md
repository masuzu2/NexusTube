<div align="center">
  <img src="https://raw.githubusercontent.com/masuzu2/NexusTube/main/icon.ico" width="100" alt="NexusTube Logo" />
  <h1>NexusTube v3.4.0</h1>
  <p><b>Next-Gen YouTube & Multi-Platform Music Suite & Studio Desktop Player</b></p>

  [![Desktop](https://img.shields.io/badge/Desktop-Electron-22C55E?style=flat-square)](https://www.electronjs.org/)
  [![Engine](https://img.shields.io/badge/Engine-yt--dlp-22C55E?style=flat-square)](https://github.com/yt-dlp/yt-dlp)
  [![FFmpeg](https://img.shields.io/badge/Engine-FFmpeg-EAB308?style=flat-square)](https://ffmpeg.org)
</div>

<br/>

**NexusTube** มีสองอย่าง เว็บใช้โหลดอย่างเดียว และโปรแกรมเดสก์ท็อปที่เป็นทั้งตัวโหลดและเครื่องเล่น รองรับ YouTube, Spotify, Apple Music และ SoundCloud

---

## Features

### ดาวน์โหลด
- คิวดาวน์โหลด ดูความเร็วและเวลาที่เหลือ ยกเลิก ลองใหม่ และเปิดไฟล์หรือโฟลเดอร์ได้
- รับลิงก์ YouTube, Spotify, Apple Music และ SoundCloud ทั้งเพลงเดียวและเพลย์ลิสต์ เลือกเพลงในเพลย์ลิสต์ก่อนลงคิวได้
- บันทึกเป็น MP3, M4A, FLAC หรือวิดีโอสูงสุด 4K
- ตัดคำอย่าง Official MV ออกจากชื่อ แล้วฝังศิลปิน ชื่อเพลง อัลบั้ม ปี แนวเพลง เนื้อเพลง และหน้าปกลงไฟล์

### เครื่องเล่นและคลัง
- เล่น MP3, WAV, M4A, Opus, FLAC และ OGG
- คลังเพลงค้นหา จัดเรียง และทำรายการโปรดได้
- อีควอไลเซอร์ 5 ย่านพร้อมพรีเซ็ต และปรับความดังเพลงให้ใกล้กัน
- ดึงเนื้อเพลงจากไฟล์ `.lrc` แท็กในไฟล์ หรือ LRCLIB บันทึก `.lrc` ได้ และคลิกท่อนเพลงเพื่อกระโดดเวลา
- ตัดช่วงไฟล์เสียงและฟังตัวอย่างก่อนบันทึก

### ระบบ
- ตัวติดตั้งมากับ `yt-dlp` และ FFmpeg ตรวจและอัปเดตเครื่องมือได้จากในแอป
- สลับภาษาไทยกับ English ได้
- ติดตั้ง ซ่อม และถอนการติดตั้งได้จากตัวติดตั้ง Windows
- ปิดหน้าต่างแล้วโปรแกรมออกจากหน่วยความจำ งานที่ยังไม่เสร็จถูกเก็บไว้แล้วทำต่อเมื่อเปิดใหม่

---

## 🚀 Quickstart (วิธีใช้งาน)

### 1. เว็บ ใช้โหลดอย่างเดียว
1. เปิด `START_WEB.bat`
2. เบราว์เซอร์จะไปที่ `http://127.0.0.1:8787`
3. วางลิงก์แล้วกดโหลด หน้านี้ไม่มีเครื่องเล่น

### 2. โปรแกรมเดสก์ท็อป
1. ติดตั้ง `NexusTube_Setup_v3.4.0.msi`
2. เปิด NexusTube จากช็อตคัตบนเดสก์ท็อปหรือเมนูเริ่ม
3. โปรแกรมนี้มีทั้งตัวโหลดและเครื่องเล่น

อย่าเปิดเว็บกับโปรแกรมพร้อมกัน เพราะทั้งคู่ใช้คิวเดียวกัน

### 3. การดาวน์โหลดเพลงและวิดีโอ
- คัดลอกลิงก์จาก YouTube, Spotify, Apple Music, หรือ SoundCloud
- วางในกล่องข้อความหน้า **Search & Discover** หรือกดปุ่ม **📋 วางลิงก์**
- เลือกฟอร์แมตเสียง/วิดีโอที่ต้องการ (MP3 320k, M4A, FLAC, MP4 1080p, 4K)
- หากเป็นเพลย์ลิสต์ ระบบจะเปิดหน้าต่าง **Universal Playlist Selector** ให้เลือกเฉพาะเพลงที่ต้องการได้ทันที
- กด **Download** เพื่อเริ่มกระบวนการ และสลับไปดูสถานะที่แท็บ **คิวดาวน์โหลด (Queue)**

### 4. การฟังเพลงในโปรแกรม
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
# Launch the download-only site
START_WEB.bat

# Launch the unpacked desktop app
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
├── START_WEB.bat                # Open the download-only site
├── package.json
├── installer/                   # WiX layout and license
├── tests/                       # Node tests for download policy
├── docs/
│   ├── DESIGN.md
│   └── USER_GUIDE.md
└── LICENSE
```
