# NexusTube — Architecture (Electron Edition v3.9.0)

## ภาพรวม

NexusTube เป็นแอป Electron (main + preload + renderer) ที่รวมเครื่องเล่นเพลง, คลังเพลง,
ตัวดาวน์โหลด และเว็บโหลดเพลง Local-first ไว้ในโปรเซสสถาปัตยกรรมเดียว

```
┌────────────────────────────── Electron main process ──────────────────────────────┐
│ index.js                                                                          │
│  ├── ConfigManager     (config.json ใน %APPDATA%\NexusTube)                       │
│  ├── EngineManager     (yt-dlp / ffmpeg — self-healing, โหลดเองถ้าไม่มี)          │
│  ├── DownloadManager   (คิวดาวน์โหลด 1 งานพร้อมกัน + metadata tagging)            │
│  ├── PlayerManager     (playback state, equalizer, sleep timer)                   │
│  ├── LibraryManager    (สแกนคลังเพลง, M3U8)                                       │
│  ├── LyricsEngine      (LRC parse/format/lookup)                                  │
│  ├── TrayManager       (system tray + global hotkeys)                             │
│  ├── DiscordRPC        (Rich Presence)                                            │
│  ├── AppUpdater        (auto-update จาก GitHub Releases + rollback)               │
│  ├── Logger            (ไฟล์ log ใน appdata, เก็บ 7 วัน)                          │
│  └── web-download.js   (HTTP server 127.0.0.1:8787 — ใช้ manager ตัวเดียวกับแอป)   │
└───────────────────────────────────────────────────────────────────────────────────┘
                 │ contextBridge (src/preload/preload.js)
                 ▼
┌─────────────── Renderer (web/index.html + app.js) ────────────────────────────────┐
│  UI OLED Dark Glassmorphism — เรียกผ่าน window.pywebview.api (ชื่อเดิมคงไว้)       │
└───────────────────────────────────────────────────────────────────────────────────┘
                 │ (แยกต่างหาก — ไม่แชร์ state กับแอปหลัก)
┌─────────────── เว็บโหลดเพลง (http://127.0.0.1:8787) ──────────────────────────────┐
│  web/download.html + download.js — เสิร์ฟจาก main process, auth ด้วย session token │
└───────────────────────────────────────────────────────────────────────────────────┘
```

## โมดูลฝั่ง main (`src/main/`)

| ไฟล์ | หน้าที่ |
|------|--------|
| `config.js` | ค่าตั้งทั้งหมด (VERSION, theme, EQ presets, locale ไทย/อังกฤษ) เก็บที่ `%APPDATA%\NexusTube\config.json` |
| `engine.js` | หา/ตรวจ/ดาวน์โหลด yt-dlp + ffmpeg (`ensureEngines`, `getStatus`) เก็บ binary ใน appdata |
| `downloader.js` | คิวงาน (`addToQueue/getQueueState/cancelTask/retryTask/clearFinished`), รัน yt-dlp, ฝัง tag + cover |
| `resolver.js` | `searchYoutube`, `detectPlatformUrl` (YouTube/Spotify/Apple Music/SoundCloud), title sanitizer |
| `library.js` | สแกนไฟล์เสียงในโฟลเดอร์, export M3U8, ลบไฟล์ + sidecar |
| `lyrics.js` | parse/format LRC, `getActiveLyricIndex`, save `.lrc` |
| `player.js` | เข้าควบคุม playback + equalizer + sleep timer (clamps ค่าให้ปลอดภัย) |
| `web-download.js` | `startWebServer({config, engine, downloads})` — HTTP API แบบ token-auth; รันเองได้เมื่อถูกเรียกตรง (`require.main === module`) |
| `download-plan.js` | pure helpers: ตรวจ URL, ขนาดไฟล์ขั้นต่ำ, เนื้อที่ว่าง, `isInsideDir` (มี test ครอบ) |
| `updater.js` | ดึง `version.json` + `app-update.zip` จาก releases/latest, backup เดิมก่อนเขียนทับ, คืนค่าถ้าอัปครึ่งทาง |
| `tray.js`, `discord.js`, `bridge.js`, `logger.js` | tray/hotkeys, Rich Presence, IPC surface, ไฟล์ log |

## เว็บโหลดเพลง (Local-first)

- **Binding**: `index.js` เริ่มเซิร์ฟเวอร์พร้อมแอปโดยส่ง manager ตัวเดียวกันเข้าไป — คิว/ค่าตั้งตรงกันทุกอย่าง
- **Auth**: ทุก POST `/api` ต้องมี header `X-Nexus-Token` (token สุ่มต่อ session, ฝังในหน้า HTML ตอนเสิร์ฟ)
- **Host check**: รับเฉพาะ `127.0.0.1` / `localhost` — ไม่มีทางเรียกจากภายนอกเครื่อง
- **Endpoints**: `POST /api` (ops: state/search/add/queue/cancel/retry/clear/folder/open/reveal), `GET /file?id=…` (ดาวน์โหลดไฟล์ที่เสร็จ), `GET /health` (CORS เปิดให้หน้า portal ตรวจ)
- **Standalone**: `node src/main/web-download.js` หรือ `NexusTube.exe --web-server` — สร้าง manager ชุดใหม่ของตัวเอง

## ระบบโหลดกันพัง 7 ชั้น (`download-resilience.js` + `downloader.js`)

| ชั้น | อาการที่กัน | กลไก |
|------|------------|------|
| 1 | พื้นที่ดิสก์ใกล้เต็ม | ตรวจ `fs.statfs` ก่อนเริ่มงาน ต้องเหลือ ≥ 250 MB |
| 2 | งานค้าง (เน็ตตาย/เซิร์ฟเวอร์ห้อย) | watchdog ตรวจทุก 15 วิ — ไม่มีความคืบหน้า 90 วิ ฆ่าแล้วลองใหม่ |
| 3 | error ต่างสาเหตุต้องการการจัดการต่างกัน | `classifyError()` แยก transient / extractor / fatal จากข้อความ yt-dlp |
| 4 | เครือข่ายสะดุดชั่วคราว | auto-retry ถึง 3 ครั้ง ถอยหลัง 3s → 10s → 30s โดยไม่ต้องกดเอง |
| 5 | yt-dlp เก่าเมื่อ YouTube เปลี่ยน | โหลดพังแบบ extractor → อัปเดต yt-dlp ทันทีแล้วลองใหม่ / ลูปเช็คทุก 12 ชม. (`ensureFreshYtdlp`) |
| 6 | format ที่ขอไม่มีให้โหลดกับคลิปนั้น | fallback chain: mp3_320→m4a, flac→mp3, mp4_1080→720→best สลับให้อัตโนมัติ |
| 7 | ปิดแอปแล้วคิวหาย | คิวถูกเซฟลง `queue.json` (debounced) — เปิดใหม่งานกลับเข้าคิวเอง |

งานที่เสียถาวรจริง ๆ (คลิปถูกลบ / private / copyright) ระบบรายงานทันทีด้วยข้อความภาษาไทยที่บอกสาเหตุ — ไม่เปลืองเวลา retry ให้ทุกอย่างอย่างเดียวกัน

## Auto-Update

1. แอปดึง `https://github.com/masuzu2/NexusTube/releases/latest/download/version.json`
2. ถ้าเวอร์ชันใหม่กว่า → โหลด `app-update.zip` (ข้างในคือไฟล์แอปทั้งก้อน)
3. แตกเป็น staging → backup ไฟล์เดิมลง `update-backup/` → คัดลอกทับ → เขียน marker `.update-success`
4. เปิดครั้งถัดไป: ถ้าไม่มี marker (อัปครึ่งทาง) → คืนไฟล์จาก backup อัตโนมัติ

## Build & Release

- `npm run dist` → electron-builder → `dist_electron/` (NSIS assisted + portable + `latest.yml`)
- Package ที่แนบ release: Setup exe, Portable exe, `latest.yml`, `.blockmap`, `version.json`, `app-update.zip`
- GitHub Actions: `ci.yml` (test ทุก push สาย main), `release.yml` (build + attach ไฟล์อัตโนมัติเมื่อ push tag `v*`)
- เวอร์ชันปรับพร้อมกัน 2 ที่: `package.json` และ `src/main/config.js` (`VERSION`)
