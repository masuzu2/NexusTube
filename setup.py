"""
NexusTube Auto-Setup & Environment Checker
==========================================
Run this script before using NexusTube to check and auto-install dependencies.
"""

# ── Fix stdout encoding FIRST (before any import that prints) ──
import sys, os
if sys.platform == "win32":
    import io
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass
    os.system("chcp 65001 >nul 2>&1")

import subprocess
import platform
import importlib
import shutil
from pathlib import Path

# ============================================================
# ANSI Colors
# ============================================================
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    RED     = "\033[91m"
    CYAN    = "\033[96m"
    BLUE    = "\033[94m"
    MAGENTA = "\033[95m"
    WHITE   = "\033[97m"
    DIM     = "\033[2m"

def enable_ansi():
    if platform.system() == "Windows":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass

def banner():
    print(f"""
{C.CYAN}{C.BOLD}
  ================================================
   NexusTube  Auto-Setup & Environment Checker
   v3.2.0  |  Next-Gen YouTube & Music Suite
  ================================================
{C.RESET}""")

def ok(msg):   print(f"  {C.GREEN}[OK]{C.RESET}  {msg}")
def warn(msg): print(f"  {C.YELLOW}[!!]{C.RESET}  {msg}")
def fail(msg): print(f"  {C.RED}[XX]{C.RESET}  {msg}")
def info(msg): print(f"  {C.CYAN}[>>]{C.RESET}  {msg}")
def step(msg): print(f"\n{C.BOLD}{C.BLUE}[ {msg} ]{C.RESET}")
def hr():      print(f"  {C.DIM}{'-'*55}{C.RESET}")

# ============================================================
# ตรวจสอบ Python version
# ============================================================
REQUIRED_PYTHON = (3, 11)

def check_python():
    step("Python Version")
    v = sys.version_info
    ver_str = f"{v.major}.{v.minor}.{v.micro}"
    if v >= REQUIRED_PYTHON:
        ok(f"Python {ver_str}  (ต้องการ ≥ {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]})")
        return True
    else:
        fail(f"Python {ver_str}  —  ต้องการ Python {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}+ ขึ้นไป")
        info("ดาวน์โหลดได้ที่: https://www.python.org/downloads/")
        return False

# ============================================================
# ตรวจสอบ pip
# ============================================================
def check_pip():
    step("pip")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "--version"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        pip_ver = result.stdout.split()[1]
        ok(f"pip {pip_ver}")
        return True
    else:
        fail("ไม่พบ pip")
        info("ลองรัน: python -m ensurepip --upgrade")
        return False

# ============================================================
# ตรวจสอบ & ติดตั้ง Python packages
# ============================================================
# label → (import_name, pip_install_name, pip_package_name_for_metadata)
PACKAGES = {
    "customtkinter": ("customtkinter", "customtkinter", "customtkinter"),
    "requests":      ("requests",      "requests",      "requests"),
    "plyer":         ("plyer",         "plyer",         "plyer"),
    "pygame":        ("pygame",        "pygame",        "pygame"),
    "Pillow":        ("PIL",           "Pillow",        "Pillow"),
    "mutagen":       ("mutagen",       "mutagen",       "mutagen"),
    "pywebview":     ("webview",       "pywebview",     "pywebview"),
    # pyinstaller — optional (dev only)
    "pyinstaller":   ("PyInstaller",   "pyinstaller",   "pyinstaller"),
}

def get_installed_version(import_name: str, pip_pkg: str) -> str | None:
    """ดึงเวอร์ชัน package — ใช้ importlib.metadata เป็นหลัก, fallback import"""
    # 1) importlib.metadata (แม่นที่สุด ไม่ต้อง import module จริง)
    try:
        import importlib.metadata as meta
        return meta.version(pip_pkg)
    except Exception:
        pass
    # 2) import module แล้วดู __version__
    try:
        # suppress pygame hello stdout
        if import_name == "pygame":
            import io as _io, contextlib as _ctx
            with _ctx.redirect_stdout(_io.StringIO()), _ctx.redirect_stderr(_io.StringIO()):
                mod = importlib.import_module(import_name)
        else:
            mod = importlib.import_module(import_name)
        ver = getattr(mod, "__version__", None)
        if ver:
            return ver
    except ImportError:
        return None
    # 3) pip show fallback
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "show", pip_pkg],
            capture_output=True, text=True
        )
        for line in r.stdout.splitlines():
            if line.startswith("Version:"):
                return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return None

def install_package(install_name: str) -> bool:
    """ติดตั้ง package ผ่าน pip"""
    info(f"กำลังติดตั้ง {C.YELLOW}{install_name}{C.RESET} ...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", install_name],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        ok(f"{install_name} ติดตั้งสำเร็จ ✓")
        return True
    else:
        fail(f"ติดตั้ง {install_name} ล้มเหลว")
        if result.stderr:
            print(f"  {C.DIM}{result.stderr.strip()[:200]}{C.RESET}")
        return False

def check_packages(auto_install: bool = True):
    step("Python Packages")
    all_ok = True
    failed = []

    for pkg_label, (import_name, install_name, pip_pkg) in PACKAGES.items():
        ver = get_installed_version(import_name, pip_pkg)
        if ver is not None:
            ok(f"{pkg_label:<18} {C.DIM}v{ver}{C.RESET}")
        else:
            if auto_install:
                warn(f"{pkg_label:<18} ไม่พบ — กำลังติดตั้ง...")
                success = install_package(install_name)
                if not success:
                    failed.append(pkg_label)
                    all_ok = False
            else:
                fail(f"{pkg_label:<18} ไม่พบ")
                failed.append(pkg_label)
                all_ok = False

    if failed:
        hr()
        fail(f"Package ที่ติดตั้งไม่สำเร็จ: {', '.join(failed)}")
        info("ลองรันด้วยตัวเอง: pip install " + " ".join(failed))

    return all_ok


# ============================================================
# ตรวจสอบ requirements.txt (ครอบคลุมทุก packages)
# ============================================================
def install_from_requirements():
    req_path = Path(__file__).parent / "requirements.txt"
    if not req_path.exists():
        warn("ไม่พบ requirements.txt")
        return False
    info(f"กำลังติดตั้งจาก requirements.txt ...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(req_path), "--upgrade"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        ok("ติดตั้งทุก requirements สำเร็จ ✓")
        return True
    else:
        fail("pip install -r requirements.txt ล้มเหลว")
        print(f"  {C.DIM}{result.stderr.strip()[:400]}{C.RESET}")
        return False

# ============================================================
# ตรวจสอบ & ติดตั้ง FFmpeg อัตโนมัติ
# ============================================================
def check_ffmpeg():
    step("FFmpeg (Audio/Video Engine)")
    try:
        from nexus_doctor import find_binary, ensure_ffmpeg
        f = find_binary("ffmpeg")
        if f:
            result = subprocess.run([f, "-version"], capture_output=True, text=True)
            ver_line = result.stdout.split("\n")[0] if result.stdout else f
            ok(f"ffmpeg พร้อมใช้งาน: {C.DIM}{ver_line[:60]}{C.RESET}")
            return True
        info("ไม่พบ FFmpeg — กำลังดาวน์โหลดและติดตั้งให้ทันทีอัตโนมัติ...")
        f, fp = ensure_ffmpeg(lambda m: info(f"  {m}"))
        if f:
            ok(f"ติดตั้ง FFmpeg สำเร็จอัตโนมัติ ✓ ({f})")
            return True
    except Exception as e:
        warn(f"ตรวจเช็ค FFmpeg ผ่าน doctor: {e}")

    warn("ไม่พบ ffmpeg — NexusTube จะดาวน์โหลดให้อัตโนมัติเมื่อรันครั้งแรก")
    return True

# ============================================================
# ตรวจสอบ & ติดตั้ง yt-dlp อัตโนมัติ
# ============================================================
def check_ytdlp():
    step("yt-dlp (Download Engine)")
    ver = get_installed_version("yt_dlp", "yt-dlp")
    if ver:
        ok(f"yt-dlp (Python package) v{ver}")

    try:
        from nexus_doctor import find_binary, ensure_ytdlp
        y = find_binary("yt-dlp")
        if y:
            ok(f"yt-dlp binary พบแล้ว: {y}")
            return True
        info("ไม่พบ yt-dlp binary — กำลังดาวน์โหลดตัวล่าสุดให้อัตโนมัติ...")
        y = ensure_ytdlp(lambda m: info(f"  {m}"))
        if y:
            ok(f"ติดตั้ง yt-dlp binary สำเร็จอัตโนมัติ ✓ ({y})")
            return True
    except Exception as e:
        warn(f"ตรวจเช็ค yt-dlp ผ่าน doctor: {e}")

    warn("ไม่พบ yt-dlp binary — NexusTube จะดาวน์โหลดให้อัตโนมัติ")
    return True

# ============================================================
# ตรวจสอบ & ติดตั้ง Microsoft Edge WebView2 อัตโนมัติ
# ============================================================
def check_webview2():
    step("Microsoft Edge WebView2 Runtime")
    if platform.system() != "Windows":
        info(f"ระบบปฏิบัติการ: {platform.system()} — ข้ามการตรวจสอบ WebView2")
        return True

    try:
        from nexus_doctor import is_webview2_installed, ensure_webview2
        if is_webview2_installed():
            ok("Edge WebView2 Runtime ติดตั้งเรียบร้อยแล้ว ✓")
            return True
        info("ไม่พบ WebView2 — กำลังดาวน์โหลดและติดตั้ง Microsoft WebView2 Runtime ให้อัตโนมัติ...")
        if ensure_webview2(lambda m: info(f"  {m}")):
            ok("ติดตั้ง Edge WebView2 Runtime สำเร็จอัตโนมัติ ✓")
            return True
    except Exception as e:
        warn(f"ตรวจเช็ค WebView2 ผ่าน doctor: {e}")

    warn("ไม่พบ Edge WebView2 Runtime — จะใช้โหมด Tkinter ปกติแทน")
    return True

# ============================================================
# ตรวจสอบ Project Files
# ============================================================
REQUIRED_FILES = [
    "YT_Downloader_V2.py",
    "nexus_audio.py",
    "requirements.txt",
    "web/index.html",
    "web/app.js",
    "web/styles.css",
    "web/tailwind.js",
]

def check_project_files():
    step("Project Files")
    base = Path(__file__).parent
    all_ok = True
    for rel_path in REQUIRED_FILES:
        full = base / rel_path
        if full.exists():
            size_kb = full.stat().st_size / 1024
            ok(f"{rel_path:<35} {C.DIM}{size_kb:,.1f} KB{C.RESET}")
        else:
            fail(f"{rel_path:<35} ❌ ไม่พบไฟล์!")
            all_ok = False
    return all_ok

# ============================================================
# ตรวจสอบ OS / Platform
# ============================================================
def check_system():
    step("System Information")
    sys_info = {
        "OS":           platform.system() + " " + platform.release(),
        "Version":      platform.version()[:50],
        "Architecture": platform.machine(),
        "Python Path":  sys.executable,
    }
    for k, v in sys_info.items():
        ok(f"{k:<18} {C.DIM}{v}{C.RESET}")

    if platform.system() != "Windows":
        warn("NexusTube ออกแบบมาสำหรับ Windows 10/11 เป็นหลัก")
        warn("ฟีเจอร์บางอย่างอาจทำงานไม่ครบบนระบบนี้")
    return True

# ============================================================
# สรุปผล & Launch
# ============================================================
def print_summary(results: dict):
    step("Summary")
    all_pass = all(results.values())

    for check_name, passed in results.items():
        if passed:
            ok(f"{check_name}")
        else:
            fail(f"{check_name}")

    hr()
    if all_pass:
        print(f"\n  {C.GREEN}{C.BOLD}🎉 ทุกอย่างพร้อมใช้งานแล้ว!{C.RESET}\n")
        print(f"  {C.WHITE}เปิดแอปได้เลยด้วยคำสั่ง:{C.RESET}")
        print(f"  {C.CYAN}  python YT_Downloader_V2.py{C.RESET}")
        print(f"  {C.DIM}  (หรือดับเบิลคลิก NexusTube.exe){C.RESET}\n")
    else:
        print(f"\n  {C.YELLOW}{C.BOLD}⚠ มีบางรายการที่ต้องแก้ไข — ดูรายละเอียดด้านบน{C.RESET}\n")

    return all_pass

def ask_launch():
    try:
        ans = input(f"  {C.CYAN}ต้องการเปิด NexusTube เลยหรือไม่? {C.DIM}[Y/n]{C.RESET} ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        ans = "n"
    return ans in ("", "y", "yes", "ใช่")

# ============================================================
# Main
# ============================================================
def main():
    enable_ansi()
    banner()

    results = {}

    # 1. System
    results["System / OS"]          = check_system()

    # 2. Python version
    py_ok = check_python()
    results["Python ≥ 3.11"]        = py_ok
    if not py_ok:
        print(f"\n  {C.RED}Python version ไม่รองรับ — หยุดการตรวจสอบ{C.RESET}\n")
        sys.exit(1)

    # 3. pip
    pip_ok = check_pip()
    results["pip"]                  = pip_ok

    # 4. Install requirements.txt ก่อน (ทำครั้งเดียวครอบทุก package)
    if pip_ok:
        step("Installing / Upgrading from requirements.txt")
        req_ok = install_from_requirements()
        # จากนั้น yt-dlp (ไม่ได้อยู่ใน requirements.txt)
        results["Python Packages"]  = req_ok

    # 5. ตรวจสอบแต่ละ package แยก (เพื่อรายงาน)
    check_packages(auto_install=not pip_ok)

    # 6. yt-dlp
    results["yt-dlp"]               = check_ytdlp()

    # 7. FFmpeg
    results["FFmpeg"]               = check_ffmpeg()

    # 8. WebView2
    results["Edge WebView2"]        = check_webview2()

    # 9. Project files
    results["Project Files"]        = check_project_files()

    # Summary
    all_ok = print_summary(results)

    # Launch option
    if all_ok:
        if ask_launch():
            main_py = Path(__file__).parent / "YT_Downloader_V2.py"
            print(f"\n  {C.GREEN}กำลังเปิด NexusTube...{C.RESET}\n")
            subprocess.Popen([sys.executable, str(main_py)])
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
