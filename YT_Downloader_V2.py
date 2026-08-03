"""
NexusTube — YT Downloader Pro
Design system: Dark OLED · Indigo/Green · Poppins · ui-ux-pro-max
"""

VERSION     = "1.0.2"
GITHUB_REPO = "masuzu2/NexusTube"

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
import subprocess, threading, os, sys, re, json, requests
from concurrent.futures import ThreadPoolExecutor

# ── Design Tokens ─────────────────────────────────────────────────────────────
BG        = "#0F0F23"
SURFACE   = "#1A1A35"
SURFACE2  = "#22223D"
BORDER    = "#312E81"
PRIMARY   = "#4338CA"
ACCENT    = "#22C55E"
ACCENT_HV = "#16A34A"
TEXT      = "#F8FAFC"
MUTED     = "#94A3B8"
ERROR     = "#EF4444"
WARN      = "#F59E0B"
GLOW      = "#4338CA"

FONT_H  = ("Poppins", 18, "bold")
FONT_MD = ("Poppins", 13, "bold")
FONT_SM = ("Poppins", 11)
FONT_XS = ("Poppins", 9)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def _btn(parent, text, cmd, fg=PRIMARY, hv=None, width=120, **kw):
    return ctk.CTkButton(
        parent, text=text, command=cmd,
        fg_color=fg, hover_color=hv or fg,
        font=FONT_SM, corner_radius=8, width=width, **kw
    )

def _label(parent, text, font=FONT_SM, color=TEXT, **kw):
    return ctk.CTkLabel(parent, text=text, font=font, text_color=color, **kw)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("NexusTube")
        self.geometry("780x580")
        self.minsize(700, 520)
        self.configure(fg_color=BG)

        if getattr(sys, "frozen", False):
            base_dir = os.path.dirname(sys.executable)
            self._exe_path = sys.executable
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self._exe_path = None   # running as .py — ไม่ swap ตัวเอง

        self.appdata_dir = os.path.join(os.getenv("APPDATA"), "YTDownloaderPro")
        os.makedirs(self.appdata_dir, exist_ok=True)

        for fname in ("ffmpeg.exe", "yt-dlp.exe"):
            src = os.path.join(base_dir, fname)
            dst = os.path.join(self.appdata_dir, fname)
            if os.path.exists(src) and not os.path.exists(dst):
                import shutil; shutil.copy(src, dst)

        self.ffmpeg = os.path.join(self.appdata_dir, "ffmpeg.exe")
        self.ytdlp  = os.path.join(self.appdata_dir, "yt-dlp.exe")

        self._default_outdir = os.path.join(base_dir, "Audio")
        os.makedirs(self._default_outdir, exist_ok=True)

        self._pending_update_url = None
        self._pending_update_ver = None

        self.executor = ThreadPoolExecutor(max_workers=4)
        self._build_ui()
        threading.Thread(target=self._check_engine, daemon=True).start()
        threading.Thread(target=self._check_app_update, daemon=True).start()

    # ─────────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # sidebar
        sidebar = ctk.CTkFrame(self, width=180, fg_color=SURFACE, corner_radius=0)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        logo_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        logo_frame.pack(fill="x", pady=(24, 8), padx=16)
        _label(logo_frame, "▶  NexusTube",   font=("Poppins", 15, "bold"), color=ACCENT).pack(anchor="w")
        _label(logo_frame, "Music Downloader", font=FONT_XS, color=MUTED).pack(anchor="w")
        _label(logo_frame, "by herlove",       font=("Poppins", 8), color="#4338CA").pack(anchor="w")
        _label(logo_frame, f"v{VERSION}",      font=("Poppins", 8), color=MUTED).pack(anchor="w")

        # update banner (ซ่อนไว้ก่อน)
        self._update_banner = ctk.CTkFrame(logo_frame, fg_color="#1a3a1a", corner_radius=6)
        self._update_btn = ctk.CTkButton(
            self._update_banner, text="🔄 Update!",
            font=("Poppins", 9, "bold"), text_color=ACCENT,
            fg_color="transparent", hover_color="#1e4a1e",
            height=24, command=self._do_app_update,
        )
        self._update_btn.pack(padx=4, pady=2)

        ctk.CTkFrame(sidebar, fg_color=BORDER, height=1).pack(fill="x", padx=12, pady=8)

        self._active_tab = tk.StringVar(value="search")
        nav_items = [("  Search", "search"), ("  Queue", "queue"), ("  Settings", "settings")]
        self._nav_btns = {}
        for label, key in nav_items:
            btn = ctk.CTkButton(
                sidebar, text=label, anchor="w",
                font=FONT_SM, corner_radius=8,
                fg_color="transparent", hover_color=SURFACE2,
                text_color=TEXT, height=40,
                command=lambda k=key: self._switch_tab(k),
            )
            btn.pack(fill="x", padx=8, pady=2)
            self._nav_btns[key] = btn

        ctk.CTkFrame(sidebar, fg_color="transparent").pack(expand=True)
        ctk.CTkFrame(sidebar, fg_color=BORDER, height=1).pack(fill="x", padx=12, pady=4)
        self.status_var = tk.StringVar(value="Ready")
        ctk.CTkLabel(sidebar, textvariable=self.status_var,
                     font=FONT_XS, text_color=MUTED, wraplength=160).pack(padx=10, pady=(4, 16))

        # main
        self._main = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self._main.pack(side="left", fill="both", expand=True)

        self._pages = {
            "search":   self._build_search_page(self._main),
            "queue":    self._build_queue_page(self._main),
            "settings": self._build_settings_page(self._main),
        }
        self._switch_tab("search")

    def _switch_tab(self, key):
        self._active_tab.set(key)
        for k, page in self._pages.items():
            (page.pack if k == key else page.pack_forget)(
                **({} if k != key else {"fill": "both", "expand": True})
            )
        for k, btn in self._nav_btns.items():
            btn.configure(
                fg_color=SURFACE2 if k == key else "transparent",
                text_color=ACCENT if k == key else TEXT,
            )

    # ── Search ────────────────────────────────────────────────────────────────
    def _build_search_page(self, parent):
        page = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        hdr = ctk.CTkFrame(page, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(20, 12))
        _label(hdr, "Search & Download", font=FONT_H).pack(anchor="w")
        _label(hdr, "Search YouTube or paste a link", font=FONT_XS, color=MUTED).pack(anchor="w")

        card = ctk.CTkFrame(page, fg_color=SURFACE, corner_radius=12)
        card.pack(fill="x", padx=24, pady=(0, 12))
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=12)
        self.search_entry = ctk.CTkEntry(
            row, placeholder_text="Search or paste YouTube URL...",
            font=FONT_SM, corner_radius=8,
            fg_color=SURFACE2, border_color=BORDER, text_color=TEXT,
            placeholder_text_color=MUTED, height=38,
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.search_entry.bind("<Return>", lambda e: self._do_search())
        _btn(row, "Search", self._do_search, fg=PRIMARY, hv=GLOW, width=90).pack(side="left", padx=(0, 6))
        _btn(row, "+ Add URL", self._quick_add, fg=ACCENT, hv=ACCENT_HV, width=90).pack(side="left")

        _label(page, "Results", font=FONT_MD, color=MUTED).pack(anchor="w", padx=24, pady=(4, 4))
        self.results_scroll = ctk.CTkScrollableFrame(
            page, fg_color=BG,
            scrollbar_button_color=SURFACE2, scrollbar_button_hover_color=PRIMARY,
        )
        self.results_scroll.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        return page

    def _do_search(self):
        q = self.search_entry.get().strip()
        if not q: return
        for w in self.results_scroll.winfo_children(): w.destroy()
        card = ctk.CTkFrame(self.results_scroll, fg_color=SURFACE, corner_radius=10)
        card.pack(fill="x", pady=4, padx=4)
        _label(card, "Searching YouTube...", color=MUTED).pack(pady=12)
        threading.Thread(target=self._search_thread, args=(q,), daemon=True).start()

    def _search_thread(self, q):
        while getattr(self, "_engine_busy", False):
            self.after(0, lambda: self.status_var.set("Waiting for engine setup…"))
            import time; time.sleep(1)
        try:
            proc = subprocess.Popen(
                [self.ytdlp, f"ytsearch8:{q}", "--dump-json",
                 "--no-playlist", "--flat-playlist", "--no-warnings"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
            results = []
            for line in proc.stdout:
                try: results.append(json.loads(line.decode("utf-8")))
                except: pass
            proc.wait()
            self.after(0, lambda: self._render_results(results))
        except Exception as e:
            self.after(0, lambda: self.status_var.set(f"Error: {e}"))

    def _render_results(self, results):
        for w in self.results_scroll.winfo_children(): w.destroy()
        if not results:
            _label(self.results_scroll, "No results found.", color=MUTED).pack(pady=20)
            return
        for item in results:
            title    = item.get("title", "Unknown")
            uploader = item.get("uploader", "")
            dur      = item.get("duration") or 0
            url      = item.get("webpage_url", "")
            mins, secs = int(dur) // 60, int(dur) % 60
            card = ctk.CTkFrame(self.results_scroll, fg_color=SURFACE, corner_radius=10,
                                border_width=1, border_color=BORDER)
            card.pack(fill="x", pady=4, padx=4)
            info = ctk.CTkFrame(card, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True, padx=14, pady=10)
            _label(info, title[:72] + ("…" if len(title) > 72 else ""),
                   font=("Poppins", 11, "bold"), anchor="w").pack(anchor="w")
            _label(info, f"{uploader}  ·  {mins}:{secs:02d}",
                   font=FONT_XS, color=MUTED, anchor="w").pack(anchor="w", pady=(2, 0))
            _btn(card, "Download", lambda u=url, t=title: self.add_to_queue(u, t),
                 fg=ACCENT, hv=ACCENT_HV, width=88).pack(side="right", padx=12, pady=10)

    def _quick_add(self):
        url = self.search_entry.get().strip()
        if "youtu" not in url:
            messagebox.showerror("Error", "Please enter a valid YouTube URL.")
            return
        self.add_to_queue(url, url)
        self.search_entry.delete(0, "end")

    # ── Queue ─────────────────────────────────────────────────────────────────
    def _build_queue_page(self, parent):
        page = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        hdr = ctk.CTkFrame(page, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(20, 12))
        _label(hdr, "Download Queue", font=FONT_H).pack(anchor="w")
        _label(hdr, "All downloads appear here", font=FONT_XS, color=MUTED).pack(anchor="w")
        self.queue_scroll = ctk.CTkScrollableFrame(
            page, fg_color=BG,
            scrollbar_button_color=SURFACE2, scrollbar_button_hover_color=PRIMARY,
        )
        self.queue_scroll.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        return page

    def add_to_queue(self, url, title=""):
        self._switch_tab("queue")
        card = ctk.CTkFrame(self.queue_scroll, fg_color=SURFACE, corner_radius=10,
                            border_width=1, border_color=BORDER)
        card.pack(fill="x", pady=5, padx=4)
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(10, 4))
        lbl  = _label(top, (title or url)[:70], font=("Poppins", 11, "bold"), anchor="w")
        lbl.pack(side="left", fill="x", expand=True)
        stat = _label(top, "Waiting…", font=FONT_XS, color=MUTED)
        stat.pack(side="right")
        prog = ctk.CTkProgressBar(card, mode="determinate",
                                  fg_color=SURFACE2, progress_color=PRIMARY,
                                  corner_radius=4, height=6)
        prog.pack(fill="x", padx=14, pady=(0, 12))
        prog.set(0)
        self.executor.submit(self._download_worker,
                             {"url": url, "lbl": lbl, "prog": prog, "stat": stat, "card": card})

    # ── Settings ──────────────────────────────────────────────────────────────
    def _build_settings_page(self, parent):
        page = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        hdr = ctk.CTkFrame(page, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(20, 12))
        _label(hdr, "Settings", font=FONT_H).pack(anchor="w")
        _label(hdr, "Customize your download preferences", font=FONT_XS, color=MUTED).pack(anchor="w")

        fc = ctk.CTkFrame(page, fg_color=SURFACE, corner_radius=12)
        fc.pack(fill="x", padx=24, pady=(0, 10))
        _label(fc, "Format", font=FONT_MD).pack(anchor="w", padx=16, pady=(12, 6))
        ctk.CTkFrame(fc, fg_color=BORDER, height=1).pack(fill="x", padx=12)
        self.type_var = tk.StringVar(value="audio")
        for val, txt in [("audio", "Audio  —  MP3 320kbps"), ("video", "Video  —  MP4 Max")]:
            row = ctk.CTkFrame(fc, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=6)
            ctk.CTkRadioButton(row, text=txt, variable=self.type_var, value=val,
                               font=FONT_SM, fg_color=ACCENT, hover_color=ACCENT_HV).pack(side="left")
        ctk.CTkFrame(fc, fg_color="transparent", height=6).pack()

        oc = ctk.CTkFrame(page, fg_color=SURFACE, corner_radius=12)
        oc.pack(fill="x", padx=24, pady=(0, 10))
        _label(oc, "Options", font=FONT_MD).pack(anchor="w", padx=16, pady=(12, 6))
        ctk.CTkFrame(oc, fg_color=BORDER, height=1).pack(fill="x", padx=12)
        self.sponsor_var  = tk.BooleanVar()
        self.meta_var     = tk.BooleanVar(value=True)
        self.playlist_var = tk.BooleanVar()
        for var, txt in [
            (self.sponsor_var,  "SponsorBlock — remove sponsors & intros"),
            (self.meta_var,     "Embed metadata & thumbnail"),
            (self.playlist_var, "Download full playlist"),
        ]:
            ctk.CTkCheckBox(oc, text=txt, variable=var, font=FONT_SM,
                            fg_color=ACCENT, hover_color=ACCENT_HV,
                            checkmark_color=BG, corner_radius=4).pack(anchor="w", padx=16, pady=5)
        ctk.CTkFrame(oc, fg_color="transparent", height=4).pack()

        dc = ctk.CTkFrame(page, fg_color=SURFACE, corner_radius=12)
        dc.pack(fill="x", padx=24, pady=(0, 10))
        _label(dc, "Output Folder", font=FONT_MD).pack(anchor="w", padx=16, pady=(12, 6))
        ctk.CTkFrame(dc, fg_color=BORDER, height=1).pack(fill="x", padx=12)
        row = ctk.CTkFrame(dc, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=10)
        self.out_var = tk.StringVar(value=self._default_outdir)
        ctk.CTkEntry(row, textvariable=self.out_var, state="readonly",
                     font=FONT_SM, fg_color=SURFACE2, border_color=BORDER,
                     text_color=MUTED, corner_radius=8).pack(side="left", fill="x", expand=True, padx=(0, 8))
        _btn(row, "Browse", self._browse_out, fg=PRIMARY, hv=GLOW, width=72).pack(side="left")
        return page

    def _browse_out(self):
        folder = filedialog.askdirectory()
        if folder: self.out_var.set(folder)

    # ── Engine update (yt-dlp & ffmpeg) ───────────────────────────────────────
    def _check_engine(self):
        self._engine_busy = True
        def _set_status(msg): self.after(0, lambda: self.status_var.set(msg))
        
        # 1. yt-dlp check
        if not os.path.exists(self.ytdlp):
            _set_status("Downloading yt-dlp…")
            try:
                data = requests.get("https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe", timeout=60).content
                with open(self.ytdlp, "wb") as f: f.write(data)
            except Exception as e:
                _set_status(f"❌ yt-dlp dl error: {e}")
                self._engine_busy = False
                return

        # 2. ffmpeg check
        ffmpeg_ver_file = os.path.join(self.appdata_dir, "ffmpeg_version.txt")
        if not os.path.exists(self.ffmpeg):
            _set_status("Downloading ffmpeg (~30MB)…")
            try:
                import zipfile, io
                resp = requests.get("https://api.github.com/repos/yt-dlp/FFmpeg-Builds/releases/latest", timeout=10).json()
                tag = resp["tag_name"]
                url = next(a["browser_download_url"] for a in resp["assets"] if a["name"] == "ffmpeg-master-latest-win64-gpl.zip")
                zip_data = requests.get(url, timeout=120).content
                with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
                    exe_path = next(name for name in z.namelist() if name.endswith("bin/ffmpeg.exe"))
                    with open(self.ffmpeg, "wb") as f:
                        f.write(z.read(exe_path))
                with open(ffmpeg_ver_file, "w") as f: f.write(tag)
            except Exception as e:
                _set_status(f"❌ ffmpeg dl error: {e}")
                self._engine_busy = False
                return

        # 3. Check for updates
        _set_status("Checking engine updates…")
        try:
            # yt-dlp update
            resp_yt = requests.get("https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest", timeout=8).json()
            latest_yt = resp_yt["tag_name"]
            current_yt = subprocess.check_output([self.ytdlp, "--version"], text=True).strip()
            
            if current_yt != latest_yt:
                _set_status(f"Updating yt-dlp to {latest_yt}…")
                url = next(a["browser_download_url"] for a in resp_yt["assets"] if a["name"] == "yt-dlp.exe")
                with open(self.ytdlp, "wb") as f: f.write(requests.get(url, timeout=60).content)
                _set_status("yt-dlp updated ✅")

            # ffmpeg update
            resp_ff = requests.get("https://api.github.com/repos/yt-dlp/FFmpeg-Builds/releases/latest", timeout=8).json()
            latest_ff = resp_ff["tag_name"]
            current_ff = open(ffmpeg_ver_file, "r").read().strip() if os.path.exists(ffmpeg_ver_file) else ""
            
            if current_ff != latest_ff:
                _set_status(f"Updating ffmpeg to {latest_ff}…")
                import zipfile, io
                url = next(a["browser_download_url"] for a in resp_ff["assets"] if a["name"] == "ffmpeg-master-latest-win64-gpl.zip")
                zip_data = requests.get(url, timeout=120).content
                with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
                    exe_path = next(name for name in z.namelist() if name.endswith("bin/ffmpeg.exe"))
                    with open(self.ffmpeg, "wb") as f: f.write(z.read(exe_path))
                with open(ffmpeg_ver_file, "w") as f: f.write(latest_ff)
                _set_status("ffmpeg updated ✅")

            if current_yt == latest_yt and current_ff == latest_ff:
                _set_status("Engines up to date ✅")

        except Exception:
            _set_status("Offline mode ⚠️")
        finally:
            self._engine_busy = False


    # ── App self-update (NexusTube) ───────────────────────────────────────────
    def _check_app_update(self):
        """เช็ค GitHub Releases — ถ้ามี version ใหม่ → แสดง banner"""
        try:
            resp = requests.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                timeout=8,
            )
            if resp.status_code != 200:
                return
            data   = resp.json()
            latest = data.get("tag_name", "").lstrip("v")
            if not latest or latest == VERSION:
                return
            # หา asset NexusTube.exe
            asset = next(
                (a for a in data.get("assets", []) if a["name"].lower() == "nexustube.exe"),
                None,
            )
            self._pending_update_url = asset["browser_download_url"] if asset else None
            self._pending_update_ver = latest
            # แสดง banner
            self.after(0, lambda: self._update_banner.pack(fill="x", pady=(4, 0)))
            self.after(0, lambda v=latest: self._update_btn.configure(text=f"🔄 v{v} available!"))
        except Exception:
            pass  # offline — ข้ามไป

    def _do_app_update(self):
        """กดปุ่ม update banner"""
        ver = self._pending_update_ver or "?"
        # ถ้ารัน .py โดยตรง → บอกให้โหลดเอง
        if not self._exe_path:
            messagebox.showinfo(
                "Update available",
                f"New version v{ver} available!\n\n"
                f"https://github.com/{GITHUB_REPO}/releases/latest"
            )
            return
        # ไม่มี asset EXE ใน release
        if not self._pending_update_url:
            messagebox.showinfo(
                "Update",
                f"https://github.com/{GITHUB_REPO}/releases"
            )
            return
        if not messagebox.askyesno(
            "Update NexusTube",
            f"Found v{ver} — update and restart now?"
        ):
            return
        threading.Thread(target=self._apply_update, daemon=True).start()

    def _apply_update(self):
        """
        โหลด EXE ใหม่ → เขียน .bat → bat รอให้แอปปิด → copy ทับ → restart
        ponytail: bat-swap trick เพราะ Windows ไม่ให้ overwrite running EXE ตรงๆ
        """
        try:
            self.after(0, lambda: self._update_btn.configure(text="Downloading…", state="disabled"))
            tmp_exe = self._exe_path + ".new"

            # stream download + progress
            with requests.get(self._pending_update_url, stream=True, timeout=120) as r:
                total   = int(r.headers.get("content-length", 0))
                written = 0
                with open(tmp_exe, "wb") as f:
                    for chunk in r.iter_content(65536):
                        f.write(chunk)
                        written += len(chunk)
                        if total:
                            pct = written / total * 100
                            self.after(0, lambda p=pct: self.status_var.set(f"Downloading… {p:.0f}%"))

            # เขียน bat ที่จะรันหลังจากแอปนี้ปิด
            bat = self._exe_path + ".update.bat"
            lines = [
                "@echo off",
                "timeout /t 2 /nobreak >nul",
                f'move /y "{tmp_exe}" "{self._exe_path}"',
                f'start "" "{self._exe_path}"',
                'del "%~f0"',
                "",
            ]
            with open(bat, "w") as f:
                f.write("\n".join(lines))

            subprocess.Popen(["cmd", "/c", bat], creationflags=subprocess.CREATE_NO_WINDOW)
            self.after(0, self.destroy)   # ปิดตัวเอง → bat จะเปิดตัวใหม่ให้

        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Update failed", str(e)))
            self.after(0, lambda: self._update_btn.configure(text="🔄 Retry", state="normal"))

    # ── Download worker ───────────────────────────────────────────────────────
    def _download_worker(self, task):
        url  = task["url"]
        prog = task["prog"]
        stat = task["stat"]
        card = task["card"]

        def ui(fn): self.after(0, fn)
        
        while getattr(self, "_engine_busy", False):
            ui(lambda: stat.configure(text="Waiting for engine setup…", text_color=WARN))
            import time; time.sleep(1)

        ui(lambda: stat.configure(text="Starting…", text_color=PRIMARY))
        ui(lambda: card.configure(border_color=PRIMARY))

        fmt    = self.type_var.get()
        outdir = os.path.abspath(self.out_var.get())
        os.makedirs(outdir, exist_ok=True)
        ffmpeg = self.ffmpeg if os.path.exists(self.ffmpeg) else "ffmpeg"

        cmd = [
            self.ytdlp, "--newline", "--no-warnings",
            "--ffmpeg-location", ffmpeg,
            "-o", outdir + "/%(title)s.%(ext)s",
            "--no-playlist" if not self.playlist_var.get() else "--yes-playlist",
        ]
        if self.sponsor_var.get():  cmd += ["--sponsorblock-remove", "all"]
        if self.meta_var.get():     cmd += ["--embed-thumbnail", "--embed-metadata"]
        if fmt == "audio":
            cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
        else:
            cmd += ["-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                    "--merge-output-format", "mp4"]
        cmd.append(url)

        ansi = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            for raw in proc.stdout:
                line = ansi.sub("", raw.decode("utf-8", errors="replace")).strip()
                if "[download]" in line and "%" in line:
                    m = re.search(r"(\d+\.?\d*)%", line)
                    if m:
                        pct = float(m.group(1)) / 100
                        ui(lambda p=pct: prog.set(p))
                        ui(lambda p=pct: prog.configure(progress_color=ACCENT if p >= 1 else PRIMARY))
                elif any(t in line for t in ("[ExtractAudio]", "[Merger]", "[Metadata]", "[SponsorBlock]")):
                    ui(lambda: stat.configure(text="Processing…", text_color=WARN))
            proc.wait()
            if proc.returncode == 0:
                ui(lambda: prog.set(1))
                ui(lambda: prog.configure(progress_color=ACCENT))
                ui(lambda: stat.configure(text="Complete ✓", text_color=ACCENT))
                ui(lambda: card.configure(border_color=ACCENT))
            else:
                ui(lambda: stat.configure(text="Failed ✗", text_color=ERROR))
                ui(lambda: card.configure(border_color=ERROR))
        except Exception as e:
            ui(lambda: stat.configure(text=f"Error: {str(e)[:40]}", text_color=ERROR))
            ui(lambda: card.configure(border_color=ERROR))


if __name__ == "__main__":
    App().mainloop()
