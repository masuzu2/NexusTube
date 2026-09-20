"""
NexusTube MSI Installer Builder
================================
สร้างไฟล์ NexusTube_Setup_v3.2.0.msi แบบ professional
รัน: python build_installer.py
"""

# ── Fix encoding ─────────────────────────────────────────────────
import sys, os
if sys.platform == "win32":
    import io
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass
    os.system("chcp 65001 >nul 2>&1")

import subprocess, shutil, zipfile, tempfile, urllib.request, hashlib
from pathlib import Path

# ============================================================
# CONFIG
# ============================================================
PROJECT_ROOT = Path(__file__).parent
INSTALLER_DIR = PROJECT_ROOT / "installer"
DIST_DIR     = PROJECT_ROOT / "dist"
SRC_EXE      = DIST_DIR / "NexusTube.exe"

PRODUCT_NAME    = "NexusTube"
PRODUCT_VERSION = "3.2.0"
MANUFACTURER    = "by herlove"
OUTPUT_MSI      = PROJECT_ROOT / f"NexusTube_Setup_v{PRODUCT_VERSION}.msi"

# WiX Toolset v3.14.1 — stable, no .NET required
WIX_VERSION  = "3.14.1"
WIX_URL      = f"https://github.com/wixtoolset/wix3/releases/download/wix3141rtm/wix314-binaries.zip"
WIX_CACHE    = PROJECT_ROOT / "installer" / ".wix_tools"
WIX_CANDLE   = WIX_CACHE / "candle.exe"
WIX_LIGHT    = WIX_CACHE / "light.exe"

# ============================================================
# ANSI Colors
# ============================================================
class C:
    RESET  = "\033[0m"; BOLD   = "\033[1m"; GREEN  = "\033[92m"
    YELLOW = "\033[93m"; RED   = "\033[91m"; CYAN   = "\033[96m"
    BLUE   = "\033[94m"; WHITE = "\033[97m"; DIM    = "\033[2m"

def enable_ansi():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleMode(
                ctypes.windll.kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass

def ok(m):   print(f"  {C.GREEN}[OK]{C.RESET}  {m}")
def warn(m): print(f"  {C.YELLOW}[!!]{C.RESET}  {m}")
def fail(m): print(f"  {C.RED}[XX]{C.RESET}  {m}")
def info(m): print(f"  {C.CYAN}[>>]{C.RESET}  {m}")
def step(m): print(f"\n{C.BOLD}{C.BLUE}[ {m} ]{C.RESET}")
def hr():    print(f"  {C.DIM}{'-'*60}{C.RESET}")

def banner():
    print(f"""
{C.CYAN}{C.BOLD}
  ================================================
   NexusTube  MSI Installer Builder
   v{PRODUCT_VERSION}  |  Creates NexusTube_Setup_v{PRODUCT_VERSION}.msi
  ================================================
{C.RESET}""")

# ============================================================
# ดาวน์โหลด WiX Toolset v3
# ============================================================
def download_wix():
    step("WiX Toolset (Compiler)")

    if WIX_CANDLE.exists() and WIX_LIGHT.exists():
        ok(f"WiX {WIX_VERSION} พบแล้วใน cache")
        return True

    WIX_CACHE.mkdir(parents=True, exist_ok=True)
    zip_path = WIX_CACHE / "wix-binaries.zip"

    info(f"กำลังดาวน์โหลด WiX Toolset v{WIX_VERSION} ...")
    info(f"URL: {WIX_URL}")

    try:
        def progress_hook(block_num, block_size, total_size):
            if total_size > 0:
                pct = min(100, block_num * block_size * 100 // total_size)
                bar = "#" * (pct // 5) + "-" * (20 - pct // 5)
                print(f"\r  [{bar}] {pct}%", end="", flush=True)

        urllib.request.urlretrieve(WIX_URL, zip_path, reporthook=progress_hook)
        print()  # newline after progress bar

    except Exception as e:
        fail(f"ดาวน์โหลดล้มเหลว: {e}")
        info("ดาวน์โหลดด้วยตัวเองได้ที่:")
        info(f"  {WIX_URL}")
        info(f"แล้ว unzip ไปที่: {WIX_CACHE}")
        return False

    # Extract
    info("กำลัง extract WiX tools ...")
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(WIX_CACHE)
        zip_path.unlink()  # ลบ zip ออกหลัง extract
    except Exception as e:
        fail(f"Extract ล้มเหลว: {e}")
        return False

    if WIX_CANDLE.exists() and WIX_LIGHT.exists():
        ok(f"WiX Toolset v{WIX_VERSION} พร้อมใช้งาน")
        return True
    else:
        fail("ไม่พบ candle.exe / light.exe หลัง extract")
        return False

# ============================================================
# สร้าง License.rtf
# ============================================================
def create_license_rtf():
    rtf_path = INSTALLER_DIR / "License.rtf"
    if rtf_path.exists():
        ok(f"License.rtf มีอยู่แล้ว")
        return

    rtf_content = r"""{\rtf1\ansi\deff0
{\fonttbl{\f0\froman\fcharset0 Times New Roman;}}
{\colortbl;\red0\green0\blue0;}
\f0\fs24
{\b\fs32 NexusTube v3.2.0 — Software License Agreement}\par
\par
Copyright (c) 2026 by herlove. All rights reserved.\par
Repository: https://github.com/masuzu2/NexusTube\par
\par
{\b MIT License}\par
\par
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:\par
\par
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.\par
\par
{\b THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.}\par
\par
{\b Third-Party Components}\par
\par
NexusTube includes and/or depends on the following open-source software:\par
- yt-dlp (Unlicense) — https://github.com/yt-dlp/yt-dlp\par
- FFmpeg (LGPL v2.1+) — https://ffmpeg.org\par
- pywebview (BSD-3-Clause) — https://pywebview.flowrl.com\par
- pygame (LGPL) — https://pygame.org\par
- CustomTkinter (MIT) — https://github.com/TomSchimansky/CustomTkinter\par
- Pillow (HPND) — https://python-pillow.org\par
- mutagen (GPL-2.0) — https://mutagen.readthedocs.io\par
\par
By installing this software, you agree to the terms above.\par
}"""
    rtf_path.write_text(rtf_content, encoding="utf-8")
    ok("License.rtf สร้างแล้ว")

# ============================================================
# สร้าง Bitmap assets (WiX UI ต้องการ)
# ============================================================
def create_bitmaps():
    """สร้าง ultra-modern bitmap assets สำหรับ WiX MSI Installer"""
    try:
        from installer.generate_installer_artwork import create_dialog_bmp, create_banner_bmp
        create_dialog_bmp()
        create_banner_bmp()
        ok("WixUIDialog.bmp สร้างแล้ว  (493x312 — Ultra-Modern OLED & Dynamic Accent)")
        ok("WixUIBanner.bmp สร้างแล้ว  (493x58 — Dual-Tone Neon Gradient Laser Header)")
    except Exception as e:
        warn(f"สร้าง ultra-modern bitmaps ล้มเหลว ({e}) — ใช้ไฟล์เดิมที่มีอยู่")

# ============================================================
# เตรียม Icon (.ico)
# ============================================================
def prepare_icon():
    step("Installer Assets")
    dst = INSTALLER_DIR / "NexusTube.ico"
    # ลอง icon ต่าง ๆ ตามลำดับ
    for src in [
        PROJECT_ROOT / "NexusTube by herlove.ico",
        PROJECT_ROOT / "icon.ico",
    ]:
        if src.exists():
            shutil.copy2(src, dst)
            ok(f"Icon คัดลอกแล้ว: {src.name}")
            break
    else:
        warn("ไม่พบ .ico — WiX จะใช้ default icon")

    create_license_rtf()
    create_bitmaps()

# ============================================================
# เตรียม NexusTube.exe
# ============================================================
def check_exe(force_rebuild: bool = False):
    step("NexusTube.exe")
    spec_path = PROJECT_ROOT / "NexusTube.spec"

    if force_rebuild or (not SRC_EXE.exists() and not (PROJECT_ROOT / "NexusTube.exe").exists()):
        info("กำลังสร้าง NexusTube.exe ด้วย PyInstaller ...")
        cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", str(spec_path)]
        r = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
        if r.returncode != 0:
            fail("PyInstaller build ล้มเหลว!")
            if r.stderr:
                print(f"  {C.DIM}{r.stderr.strip()[-500:]}{C.RESET}")
            return False
        ok("PyInstaller build สำเร็จ ✓")

    if SRC_EXE.exists():
        size_mb = SRC_EXE.stat().st_size / 1024 / 1024
        ok(f"พบ NexusTube.exe  ({size_mb:.1f} MB)")
        # คัดลอกไปไว้ที่ installer/ เพื่อให้ WiX เห็น
        dst = INSTALLER_DIR / "NexusTube.exe"
        if not dst.exists() or dst.stat().st_mtime < SRC_EXE.stat().st_mtime:
            shutil.copy2(SRC_EXE, dst)
            info("คัดลอก NexusTube.exe ไปไว้ใน installer/")
        # คัดลอกไป root ด้วยเพื่อความสะดวก
        root_exe = PROJECT_ROOT / "NexusTube.exe"
        if not root_exe.exists() or root_exe.stat().st_mtime < SRC_EXE.stat().st_mtime:
            shutil.copy2(SRC_EXE, root_exe)
        return True

    # ลอง root folder
    root_exe = PROJECT_ROOT / "NexusTube.exe"
    if root_exe.exists():
        size_mb = root_exe.stat().st_size / 1024 / 1024
        ok(f"พบ NexusTube.exe ใน root  ({size_mb:.1f} MB)")
        shutil.copy2(root_exe, INSTALLER_DIR / "NexusTube.exe")
        return True

    fail("ไม่พบ NexusTube.exe!")
    info(f"สร้าง exe ก่อนด้วย: python -m PyInstaller --noconfirm NexusTube.spec")
    return False

# ============================================================
# Compile WiX → MSI
# ============================================================
def run_wix_build():
    step("Building MSI with WiX Toolset")

    wxs      = INSTALLER_DIR / "NexusTube.wxs"
    wixobj   = INSTALLER_DIR / "NexusTube.wixobj"

    # ── candle.exe (compile .wxs → .wixobj) ─────────────────
    # ลบ artifact เก่าก่อน build ใหม่
    for stale in [wixobj, OUTPUT_MSI]:
        if stale.exists():
            stale.unlink()

    info("candle.exe — compiling NexusTube.wxs ...")
    candle_cmd = [
        str(WIX_CANDLE),
        str(wxs),
        "-out", str(wixobj),
        "-arch", "x64",
        "-nologo",
        "-ext", "WixUIExtension",
        "-ext", "WixUtilExtension",
    ]
    r = subprocess.run(candle_cmd, capture_output=True, text=True,
                       cwd=str(INSTALLER_DIR))
    if r.returncode != 0:
        fail("candle.exe ล้มเหลว!")
        print(f"\n{C.DIM}{r.stdout}\n{r.stderr}{C.RESET}")
        return False
    ok("candle.exe สำเร็จ — NexusTube.wixobj")

    # ── light.exe (link .wixobj → .msi) ─────────────────────
    info("light.exe — linking to NexusTube.msi ...")
    light_cmd = [
        str(WIX_LIGHT),
        str(wixobj),
        "-out", str(OUTPUT_MSI),
        "-nologo",
        "-spdb",            # ไม่สร้าง .wixpdb
        "-cultures:en-us",
        "-ext", "WixUIExtension",
        "-ext", "WixUtilExtension",
        # Suppress ICE warnings ที่เป็น false-positive บน Win10/11
        "-sice:ICE03",      # unchecked string
        "-sice:ICE57",      # per-user/per-machine mixing (handled in WXS)
        "-sice:ICE61",      # upgrade
        "-sice:ICE91",      # shortcut advertise
        "-sw1076",          # cabinet warning
        "-sw1079",          # cabinet warning
    ]
    r = subprocess.run(light_cmd, capture_output=True, text=True,
                       cwd=str(INSTALLER_DIR))
    if r.returncode != 0:
        fail("light.exe ล้มเหลว!")
        print(f"\n{C.DIM}{r.stdout}\n{r.stderr}{C.RESET}")
        return False

    # แสดง warning ที่เหลือ (ถ้ามี) แต่ไม่ fail
    output = (r.stdout + r.stderr).strip()
    if output:
        for line in output.splitlines():
            if "warning" in line.lower():
                warn(line[:120])
            elif "error" in line.lower():
                fail(line[:120])

    ok("light.exe สำเร็จ!")
    return True

# ============================================================
# แสดงผล MSI
# ============================================================
def show_result():
    step("Result")
    if OUTPUT_MSI.exists():
        size_mb = OUTPUT_MSI.stat().st_size / 1024 / 1024
        # SHA256
        sha = hashlib.sha256(OUTPUT_MSI.read_bytes()).hexdigest()
        hr()
        print(f"\n  {C.GREEN}{C.BOLD}MSI สร้างสำเร็จ!{C.RESET}\n")
        print(f"  {C.WHITE}File:   {C.RESET}{OUTPUT_MSI}")
        print(f"  {C.WHITE}Size:   {C.RESET}{size_mb:.2f} MB")
        print(f"  {C.WHITE}SHA256: {C.DIM}{sha}{C.RESET}")
        hr()
        print(f"""
  {C.CYAN}คำแนะนำการแจกจ่าย:{C.RESET}
  - แชร์ไฟล์ NexusTube_Setup_v{PRODUCT_VERSION}.msi ได้เลย
  - ผู้รับดับเบิลคลิกเพื่อติดตั้งแบบ standard Windows installer
  - มี Start Menu + Desktop shortcut + Add/Remove Programs
  - รองรับ silent install: msiexec /i NexusTube_Setup.msi /quiet
""")
        return True
    else:
        fail(f"ไม่พบ {OUTPUT_MSI}")
        return False

# ============================================================
# Cleanup temp files
# ============================================================
def cleanup():
    for tmp in [INSTALLER_DIR / "NexusTube.wixobj",
                INSTALLER_DIR / "NexusTube.exe"]:
        if tmp.exists():
            try:
                tmp.unlink()
            except Exception:
                pass

# ============================================================
# Main
# ============================================================
def main():
    enable_ansi()
    banner()

    # 1. ดาวน์โหลด WiX
    if not download_wix():
        sys.exit(1)

    # 2. ตรวจสอบ exe
    if not check_exe():
        sys.exit(1)

    # 3. เตรียม assets (icon, bitmaps, license)
    prepare_icon()

    # 4. Build!
    if not run_wix_build():
        cleanup()
        sys.exit(1)

    # 5. Cleanup + แสดงผล
    cleanup()
    show_result()


if __name__ == "__main__":
    main()
