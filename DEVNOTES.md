# NexusTube — Dev Notes

> โปรเจกต์ YouTube Music Downloader by herlove
> Repo: https://github.com/masuzu2/NexusTube

---

## โครงสร้างโปรเจกต์

```
YT-Music/
├── YT_Downloader_V2.py        ← source code หลัก
├── README.md
├── .gitignore
├── .github/
│   └── workflows/
│       └── build.yml          ← GitHub Actions: build EXE อัตโนมัติตอน push tag
├── Audio/                     ← เพลงที่โหลดมาเก็บที่นี่
└── dist/
    └── NexusTube.exe          ← EXE ที่ build ได้ (ไม่ได้ push ขึ้น git)
```

```
%APPDATA%\YTDownloaderPro\
├── yt-dlp.exe                 ← engine หลัก (auto-download/update)
└── ffmpeg.exe                 ← ใช้ convert audio/merge video
```

---

## Design System (ui-ux-pro-max)

| Token | Value | |
|---|---|---|
| Background | `#0F0F23` | OLED black |
| Surface | `#1A1A35` | card |
| Primary | `#4338CA` | Indigo-700 |
| Accent | `#22C55E` | Green-500 |
| Error | `#EF4444` | Red |
| Font | Poppins | sidebar/body |

Style: **Dark OLED** · ไม่มี light mode

---

## ระบบ Auto-Update

แอปมี 2 ชั้น update:

### 1. yt-dlp (engine)
- เช็ค `github.com/yt-dlp/yt-dlp/releases/latest` ทุกครั้งที่เปิด
- ถ้า version ไม่ตรง → โหลดใหม่ทับ `%APPDATA%\YTDownloaderPro\yt-dlp.exe` เงียบๆ

### 2. NexusTube (ตัวแอปเอง)
- เช็ค `github.com/masuzu2/NexusTube/releases/latest`
- compare กับ `VERSION` ที่ hardcode ในโค้ด
- ถ้ามีใหม่ → แสดงปุ่ม **🔄 vX.X.X available!** ใน sidebar
- กดปุ่ม → โหลด `NexusTube.exe` ใหม่ → ใช้ `.bat` swap ไฟล์ → restart อัตโนมัติ

**bat-swap trick** (เพราะ Windows ไม่ให้ overwrite EXE ที่กำลังรันอยู่):
```
แอปปิดตัว
  → bat รอ 2 วิ
  → move NexusTube.exe.new → NexusTube.exe
  → เปิด NexusTube.exe ใหม่
  → bat ลบตัวเอง
```

---

## วิธีปล่อย Version ใหม่

```bash
# 1. แก้ไข VERSION ในโค้ด
# บรรทัดที่ 7 ของ YT_Downloader_V2.py
VERSION = "1.0.1"   # ← เปลี่ยนตรงนี้

# 2. commit
git add YT_Downloader_V2.py
git commit -m "bump: v1.0.1"

# 3. push tag → GitHub Actions build EXE ให้อัตโนมัติ
git tag v1.0.1
git push origin main --tags
```

GitHub Actions จะ:
1. ติดตั้ง Python 3.12 + deps
2. `pyinstaller --onefile --windowed NexusTube.exe`
3. อัพโหลด EXE ไว้ใน GitHub Release

แอปทุกตัวที่รันอยู่จะเห็น update banner ครั้งถัดไปที่เปิด ✅

---

## Dependencies

```bash
# run จาก source
pip install customtkinter requests

# build EXE
pip install pyinstaller
pyinstaller --onefile --windowed --name NexusTube YT_Downloader_V2.py
```

Python ที่ใช้: **3.12** (ไม่ใช้ 3.14 เพราะ PyInstaller ยังไม่รองรับ)

---

## Changelog

| Version | วันที่ | อะไรเปลี่ยน |
|---|---|---|
| 1.0.0 | 2026-08-03 | Initial release — Dark OLED UI, Search, Queue, Auto-update system |

---

## Links

- Repo: https://github.com/masuzu2/NexusTube
- Actions: https://github.com/masuzu2/NexusTube/actions
- Releases: https://github.com/masuzu2/NexusTube/releases
- yt-dlp: https://github.com/yt-dlp/yt-dlp
