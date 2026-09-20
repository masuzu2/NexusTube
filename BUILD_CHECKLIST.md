# NexusTube — Release Build Checklist & Verification Guide

เอกสารนี้กำหนดขั้นตอนและรายการตรวจสอบก่อน, ระหว่าง และหลังการ Compile **NexusTube (.exe & .msi)** เพื่อรับประกันความเสถียร 100% ปราศจาก Silent Crashes, Missing DLLs หรือ Bundle Asset ผิดพลาด

---

## 1. Pre-Build Checklist (ก่อนทำการ Build)

- [ ] **1.1 Version Syncing**
  - ตรวจสอบว่าตัวแปร `VERSION` ใน `YT_Downloader_V2.py` (บรรทัดที่ 8) ตรงกับเวอร์ชันที่จะแจก (เช่น `VERSION = "3.2.0"`)
  - ตรวจสอบว่าตัวแปร `PRODUCT_VERSION` ใน `build_installer.py` ตรงกัน (`"3.2.0"`)
  - ตรวจสอบ `installer/License.rtf` ว่าระบุ Version ตรงกัน

- [ ] **1.2 Clean Artifacts**
  - ลบโฟลเดอร์ `build/` เก่าทิ้งทั้งหมดเพื่อป้องกัน cached object files ตกค้าง
  - ลบโฟลเดอร์ `dist/` เก่าทิ้งทั้งหมด
  - ใช้คำสั่ง: `Remove-Item -Recurse -Force build, dist` หรือรันผ่าน `pyinstaller --clean`

- [ ] **1.3 Package & Asset Verification**
  - **CustomTkinter**: ต้องมั่นใจว่ามีการเรียก `collect_all('customtkinter')` ใน `.spec` และมีโฟลเดอร์ `assets/fonts/` (โดยเฉพาะ `Roboto` และ `CustomTkinter_shapes.otf`) ถูก bundle เข้าไป เพื่อป้องกัน font warning crash
  - **Multimedia Engines**: ตรวจสอบว่า `collect_all('pygame')` และ `collect_all('mutagen')` ถูกรวมใน `.spec`
  - **Doctor & Modules**: ตรวจสอบว่า `nexus_doctor.py`, `nexus_audio.py`, `nexus_discord.py`, `nexus_hotkeys_tray.py` อยู่ใน `datas` และ `hiddenimports`
  - **Web Studio Assets**: ตรวจสอบว่าโฟลเดอร์ `web/` (HTML/CSS/JS) และไฟล์ `.ico` ถูกรวมใน `datas`
  - **TCL/TK & DLLs**: ตรวจสอบว่า `collect_tcltk_to_root()` ทำงานและ bundle `tcl8.6` / `tk8.6` ไว้ที่ root ของ `_MEIPASS` และยกเว้น `pygame\zlib1.dll` เพื่อป้องกัน DLL conflict

---

## 2. Build Commands (ขั้นตอนการ Compile)

### ขั้นที่ 1: Build Standalone Executable (.exe)
รันคำสั่ง PyInstaller พร้อม `--clean` และ `--noconfirm`:
```powershell
python -m PyInstaller --clean --noconfirm NexusTube.spec
```

### ขั้นที่ 2: Build Windows Installer (.msi)
รันสคริปต์ WiX Toolset automation:
```powershell
python build_installer.py
```
*ผลลัพธ์: จะได้ไฟล์ `dist\NexusTube_Setup_v3.2.0.msi` ที่มี Studio OLED Glassmorphism artwork ครบถ้วน*

---

## 3. Post-Build Smoke Test (การทดสอบก่อน Sign-Off)

> [!IMPORTANT]
> ห้ามแจกจ่าย build ใดๆ ก่อนผ่านการรัน Smoke Test อย่างน้อย 1 รอบทั้งแบบอัตโนมัติและด้วยมือ

- [ ] **3.1 Automated Sanity Check**
  - รันสคริปต์ทดสอบ:
    ```powershell
    python smoke_test.py
    ```
  - ตรวจสอบว่า:
    1. Pre-flight dependency check ผ่าน (`yt-dlp`, `ffmpeg`, write probe, WebView2)
    2. Headless URL resolution ผ่าน
    3. Process terminate ได้สะอาด ไม่มี zombie/orphan process ค้างใน task manager

- [ ] **3.2 Executable Launch Verification**
  - ดับเบิ้ลคลิกเปิด `dist\NexusTube\NexusTube.exe` (หรือไฟล์ติดตั้ง `.msi`)
  - หน้าต่างแอปต้องเปิดขึ้นมาได้ทันที โดยไม่มี Modal Crash Dialog หรือ Native MessageBox เตือน error

- [ ] **3.3 Manual Workflow Verification**
  - วาง YouTube URL ทดสอบ 1 รายการ และตรวจสอบว่า Title/Cover Art ถูก resolve แสดงผลบนหน้าจอ
  - ทดลองกดดาวน์โหลด 1 เพลง (เช่นเลือก MP3 320kbps) จนดาวน์โหลดและ convert สำร็จ 100%
  - ตรวจสอบไฟล์ผลลัพธ์ในโฟลเดอร์ Downloads ว่ามีขนาดไฟล์และเล่นเสียงได้ปกติ
  - ปิดโปรแกรม และเปิด Task Manager เช็คว่าไม่มี `NexusTube.exe`, `yt-dlp.exe` หรือ `ffmpeg.exe` ค้างในระบบ

---

## 4. Sign-Off Record

| วันที่ | เวอร์ชัน | ผู้ทดสอบ | สถานะการทดสอบ | หมายเหตุ |
| :--- | :--- | :--- | :--- | :--- |
| 2026-09-14 | v3.2.0 | Automated Smoke Test | PASS | Verified on Windows 10/11 |
