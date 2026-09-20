# -*- mode: python ; coding: utf-8 -*-
# NexusTube EXE Build Spec — Final Distributable Edition
# Fixed: _tkinter DLL load failed → bundle tcl8.6/ tk8.6/ at _MEIPASS ROOT

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules
import sys, os, sysconfig

# ── Bundle tcl8.6/ และ tk8.6/ ที่ ROOT ของ _MEIPASS ──────────────────────────
# PyInstaller runtime hook (pyi_rth__tkinter.py) ตั้ง TCL_LIBRARY ไปที่
# _MEIPASS/tcl8.6  และ TK_LIBRARY → _MEIPASS/tk8.6  (ต้องอยู่ที่ root!)
def collect_tcltk_to_root():
    """หา tcl8.6/ tk8.6/ จาก Python install แล้ว bundle ไปที่ root ของ _MEIPASS"""
    python_dir = os.path.dirname(sys.executable)
    result = []

    # Windows: Python วาง tcl/tk ไว้ใน <Python>/tcl/
    tcl_base = os.path.join(python_dir, 'tcl')

    # โฟลเดอร์ที่ต้องการ (dest = ชื่อโฟลเดอร์ตรงๆ ที่ root)
    wanted = {
        'tcl8.6': None, 'tk8.6': None,
        'tcl8':   None,               # tcl8/ ใน tcl_base บางครั้งจำเป็น
    }

    if os.path.isdir(tcl_base):
        for name in os.listdir(tcl_base):
            full = os.path.join(tcl_base, name)
            if os.path.isdir(full) and name in wanted:
                result.append((full, name))   # dest at ROOT, no tcl/ prefix
                print("[spec] tcltk bundle: %s/ -> _MEIPASS/%s/" % (name, name))


    # fallback: ถ้าไม่มี tcl_base ลองหาจาก sysconfig paths
    if not result:
        for root in [sysconfig.get_path('stdlib'), python_dir]:
            for name in ['tcl8.6', 'tk8.6']:
                p = os.path.join(root, name)
                if os.path.isdir(p):
                    result.append((p, name))
                    print("[spec] tcltk fallback: %s -> _MEIPASS/%s/" % (p, name))


    return result

# ── Collect all package data ─────────────────────────────────────────────────
datas = [
    ('icon.ico', '.'),
    ('NexusTube by herlove.ico', '.'),
    ('web', 'web'),
    ('nexus_audio.py', '.'),
    ('nexus_discord.py', '.'),
    ('nexus_hotkeys_tray.py', '.'),
    ('nexus_doctor.py', '.'),
]

# Bundle tcl/tk ที่ ROOT (fix _tkinter DLL initialization)
datas += collect_tcltk_to_root()


binaries = []
hiddenimports = [
    'nexus_doctor',
    'nexus_discord',
    'nexus_hotkeys_tray',
    'nexus_audio',
    # tkinter
    'tkinter',
    'tkinter.filedialog',
    'tkinter.messagebox',
    'tkinter.ttk',
    '_tkinter',
    # stdlib
    'calendar',
    'tarfile',
    'zipfile',
    'wave',
    'winreg',
    'ctypes',
    'ctypes.wintypes',
    'msvcrt',
    # requests / network
    'requests',
    'requests.adapters',
    'urllib3',
    'urllib3.util.retry',
    'charset_normalizer',
    'certifi',
    'idna',
    # image
    'PIL',
    'PIL.Image',
    'PIL.ImageTk',
    # audio
    'pygame',
    'pygame.mixer',
    'mutagen',
    'mutagen.id3',
    'mutagen.mp4',
    'mutagen.flac',
    'mutagen._util',
    # notifications
    'plyer',
    'plyer.platforms',
    'plyer.platforms.win.notification',
    # concurrent
    'concurrent.futures',
    # sentry-sdk (optional crash reporting — Feature 5)
    'sentry_sdk',
    'sentry_sdk.integrations',
    'sentry_sdk.integrations.threading',
    'sentry_sdk.integrations.logging',
]

# customtkinter (UI framework) — must collect_all
tmp = collect_all('customtkinter')
datas   += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]

# mutagen
tmp2 = collect_all('mutagen')
datas   += tmp2[0]; binaries += tmp2[1]; hiddenimports += tmp2[2]

# pygame
tmp3 = collect_all('pygame')
datas   += tmp3[0]; binaries += tmp3[1]; hiddenimports += tmp3[2]

# plyer
tmp4 = collect_all('plyer')
datas   += tmp4[0]; binaries += tmp4[1]; hiddenimports += tmp4[2]

# PIL / Pillow
tmp5 = collect_all('PIL')
datas   += tmp5[0]; binaries += tmp5[1]; hiddenimports += tmp5[2]

# requests
tmp6 = collect_all('requests')
datas   += tmp6[0]; binaries += tmp6[1]; hiddenimports += tmp6[2]

# Try to collect pywebview optionally (won't fail if not installed)
try:
    tmp7 = collect_all('webview')
    datas   += tmp7[0]; binaries += tmp7[1]; hiddenimports += tmp7[2]
    hiddenimports += [
        'webview',
        'webview.platforms',
        'webview.platforms.winforms',
        'webview.platforms.edgechromium',
    ]
except Exception:
    pass

# Try pythonnet / clr optionally
try:
    tmp8 = collect_all('pythonnet')
    datas   += tmp8[0]; binaries += tmp8[1]; hiddenimports += tmp8[2]
except Exception:
    pass

try:
    tmp9 = collect_all('clr_loader')
    datas   += tmp9[0]; binaries += tmp9[1]; hiddenimports += tmp9[2]
except Exception:
    pass

# bottle (used by pywebview http_server)
try:
    tmp10 = collect_all('bottle')
    datas   += tmp10[0]; binaries += tmp10[1]; hiddenimports += tmp10[2]
except Exception:
    pass

# ── DLL Sanitization & Conflict Resolution ─────────────────────────────────────
# Remove pygame's bundled MinGW zlib1.dll to avoid shadowing Python's official zlib1.dll
clean_binaries = []
for src, dst in binaries:
    if 'zlib1.dll' in os.path.basename(src).lower() and 'pygame' in src.lower():
        print(f"[spec] Excluded conflicting pygame zlib1.dll: {src}")
        continue
    clean_binaries.append((src, dst))
binaries = clean_binaries

# Explicitly ensure Python's official DLLs are bundled at root
py_dll_dir = os.path.join(os.path.dirname(sys.executable), 'DLLs')
for official_dll in ['zlib1.dll', 'tcl86t.dll', 'tk86t.dll', '_tkinter.pyd']:
    dll_path = os.path.join(py_dll_dir, official_dll)
    if os.path.isfile(dll_path):
        binaries.append((dll_path, '.'))
        print(f"[spec] Added official Python DLL: {official_dll}")

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    ['YT_Downloader_V2.py'],
    pathex=[os.path.abspath('.')],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['installer/pyi_rth_safestreams.py'],
    excludes=[
        # Exclude heavy unused libs to keep size manageable
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
        'notebook',
        'IPython',
        'test',
        'unittest',
        '_pytest',
        'pydoc',
        'doctest',
        'pdb',
        'profile',
        'cProfile',
        'timeit',
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='NexusTube',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # No black console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['NexusTube by herlove.ico'],
    version_file=None,
)
