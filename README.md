<div align="center">
  <img src="https://raw.githubusercontent.com/masuzu2/NexusTube/main/icon.ico" width="100" alt="NexusTube Logo" />
  <h1>NexusTube</h1>
  <p><b>Premium YouTube Music & Video Downloader</b></p>
  <p><i>Design System: Dark OLED · Indigo/Green · Poppins · by herlove</i></p>

  [![Python](https://img.shields.io/badge/Python-3.12-4338CA?style=flat-square&logo=python&logoColor=white)](https://python.org)
  [![yt-dlp](https://img.shields.io/badge/Engine-yt--dlp-22C55E?style=flat-square)](https://github.com/yt-dlp/yt-dlp)
  [![FFmpeg](https://img.shields.io/badge/Engine-FFmpeg-EAB308?style=flat-square)](https://ffmpeg.org)
  [![Build](https://img.shields.io/github/actions/workflow/status/masuzu2/NexusTube/build.yml?style=flat-square)](https://github.com/masuzu2/NexusTube/actions)
</div>

<br/>

**NexusTube** เป็นโปรแกรมดาวน์โหลดเพลงและวิดีโอจาก YouTube ที่ถูกออกแบบมาเพื่อ **"โหลดครั้งเดียวจบ ใช้งานได้ถาวร"** ตัวโปรแกรมมีขนาดเล็ก (~13MB) ไม่ต้องติดตั้ง (Portable) และมาพร้อมระบบดูแลตัวเอง (Self-healing) อัตโนมัติ

---

## ✨ Features (ความสามารถเด่น)

- 🪄 **Zero Setup (เปิดปุ๊บพร้อมใช้):** ไม่ต้องไปหาโหลด `yt-dlp` หรือ `ffmpeg` เอง แอปจะดาวน์โหลดและติดตั้งเครื่องมือแท้จากเซิร์ฟเวอร์ให้อัตโนมัติในครั้งแรกที่เปิด
- 🔄 **Self-Updating Engine:** แอบอัปเดต `yt-dlp` และ `ffmpeg` ให้ใหม่ล่าสุดอยู่เสมอแบบเงียบๆ เบื้องหลัง
- 📑 **Smart Playlist:** แปะลิงก์ Playlist แล้วจะมีหน้าต่างขึ้นมาให้ติ๊กเลือกโหลดเฉพาะเพลงที่ต้องการได้เลย!
- 🎵 **Library & In-App Player:** มีแท็บรวบรวมไฟล์ที่โหลดไว้ และสามารถกด ⏸️ Play ฟังได้ทันทีจากในแอป
- ✂️ **Audio Trimmer (ระบบตัดเสียง):** มีเครื่องมือตัดแต่งเสียงในตัว (ใช้ FFmpeg) สามารถตัดท่อนฮุคทำเสียงเรียกเข้าได้ใน 1 วินาที!
- 📝 **Embed Lyrics & Metadata:** ฝังปกอัลบั้ม, ชื่อศิลปิน, และ **เนื้อเพลง** ลงไปในไฟล์ MP3 อัตโนมัติ
- 🚫 **SponsorBlock Integration:** โหลดเพลงโดยตัดช่วงโฆษณา/คนพูด Sponsor ในคลิปออกให้อัตโนมัติ
- 🎨 **Dynamic Theme Colors:** เปลี่ยนสีธีม (Accent Color) ของแอปได้ตามใจชอบ (Green, Pink, Yellow, Cyan)

---

## 🚀 How to Use (วิธีใช้งาน)

1. ไปที่หน้า [Releases](https://github.com/masuzu2/NexusTube/releases) แล้วดาวน์โหลดไฟล์ `NexusTube.exe` (หรือ `NexusTube_Windows.zip`)
2. ดับเบิลคลิกเปิดไฟล์ขึ้นมาใช้งานได้เลย!
3. **การดาวน์โหลด:**
   - พิมพ์ชื่อเพลงในช่องค้นหา แล้วกด **Search**
   - หรือ ก๊อปปี้ URL จาก YouTube มาแปะแล้วกด **+ Add URL**

---

## 🛠️ Build from Source (สำหรับนักพัฒนา)

หากต้องการนำโค้ดไปรันด้วยตัวเอง หรือแก้ไข:

1. **ติดตั้ง Python 3.12+**
2. **ติดตั้ง Dependencies:**
   ```bash
   pip install customtkinter requests
   ```
3. **รันโปรแกรม:**
   ```bash
   python YT_Downloader_V2.py
   ```
4. **Build เป็น EXE ด้วยตัวเอง:**
   ```bash
   pip install pyinstaller
   pyinstaller --noconfirm --clean --onefile --windowed --icon=icon.ico --add-data="icon.ico;." --name "NexusTube" YT_Downloader_V2.py
   ```

*(หมายเหตุ: บน GitHub มีระบบ Smart CI/CD Pipeline ที่จะ Build และบีบอัด Zip ให้แบบอัตโนมัติทุกครั้งที่มีการ Push โค้ดใหม่)*

---

<div align="center">
  <p><b>made with ♥ by herlove</b></p>
</div>
