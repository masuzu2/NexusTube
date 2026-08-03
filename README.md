# NexusTube by herlove

**NexusTube** คือ YouTube Music Downloader ที่ออกแบบโดย herlove

![Dark OLED UI](https://img.shields.io/badge/UI-Dark%20OLED-0F0F23?style=flat-square&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.12-4338CA?style=flat-square&logo=python&logoColor=white)
![yt-dlp](https://img.shields.io/badge/Engine-yt--dlp-22C55E?style=flat-square)

---

## Features

- 🔍 **Search YouTube** — ค้นหาและเลือกเพลงได้ทันที
- ➕ **Quick Add** — วาง YouTube URL แล้วโหลดได้เลย
- 🎵 **Audio MP3 320kbps** — คุณภาพสูงสุด
- 🎬 **Video MP4** — best quality video + audio merge
- 📋 **Download Queue** — โหลดหลายเพลงพร้อมกัน
- 🚫 **SponsorBlock** — ตัด sponsor/intro ออกอัตโนมัติ
- 🖼️ **Embed Metadata & Thumbnail** — ฝัง cover art + ข้อมูลเพลง
- 🔄 **Auto-update yt-dlp** — อัพเดท engine อัตโนมัติ

---

## Requirements

เครื่องต้องมี:
- `ffmpeg.exe` ใน `%APPDATA%\YTDownloaderPro\`
- `yt-dlp.exe` ใน `%APPDATA%\YTDownloaderPro\` (โหลดอัตโนมัติถ้าไม่มี)

---

## Run from source

```bash
pip install customtkinter requests
python YT_Downloader_V2.py
```

## Build EXE

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name NexusTube YT_Downloader_V2.py
```

---

## Design

- **Style:** Dark OLED
- **Colors:** Indigo `#4338CA` + Green `#22C55E`
- **Font:** Poppins
- **Engine:** yt-dlp + ffmpeg

---

*made with ♥ by herlove*
