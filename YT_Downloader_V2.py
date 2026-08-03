"""
NexusTube — YT Downloader Pro
Design system: Dark OLED · Indigo/Green · Poppins · ui-ux-pro-max
"""

VERSION     = "1.0.7"
GITHUB_REPO = "masuzu2/NexusTube"

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
import subprocess, threading, os, sys, re, json, requests
from concurrent.futures import ThreadPoolExecutor

try:
    from plyer import notification
except ImportError:
    notification = None

def show_notify(title, msg):
    if notification:
        try: notification.notify(title=title, message=msg, app_name="NexusTube", timeout=5)
        except: pass

# ── Design Tokens ─────────────────────────────────────────────────────────────
BG        = "#0A0A16"   # Deep void black for background
SIDEBAR   = "#06060F"   # Even darker for sidebar depth
SURFACE   = "#13132B"   # Elevated card background
SURFACE2  = "#1D1D3A"   # Secondary elevation (inputs)
BORDER    = "#282846"   # Soft borders
PRIMARY   = "#4F46E5"   # Vibrant Indigo
ACCENT    = "#22C55E"   # Neon Green
ACCENT_HV = "#16A34A"
TEXT      = "#F8FAFC"
MUTED     = "#8B9BB4"   # High legibility muted text
ERROR     = "#EF4444"
WARN      = "#F59E0B"

FONT_H  = ("Segoe UI", 26, "bold")
FONT_MD = ("Segoe UI", 16, "bold")
FONT_SM = ("Segoe UI", 13)
FONT_XS = ("Segoe UI", 11)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── Localization ──────────────────────────────────────────────────────────────
LOCALES = {
    "Search": {"en": "Search", "th": "ค้นหา"},
    "Queue": {"en": "Queue", "th": "คิวโหลด"},
    "Library": {"en": "Library", "th": "คลังไฟล์"},
    "Settings": {"en": "Settings", "th": "ตั้งค่า"},
    "Search & Download": {"en": "Search & Download", "th": "ค้นหาและดาวน์โหลด"},
    "Search YouTube or paste a link": {"en": "Search YouTube or paste a link", "th": "ค้นหาจาก YouTube หรือวางลิงก์"},
    "+ Add URL": {"en": "+ Add URL", "th": "+ เพิ่ม URL"},
    "Import TXT": {"en": "Import TXT", "th": "นำเข้าจาก TXT"},
    "Results": {"en": "Results", "th": "ผลการค้นหา"},
    "No results found.": {"en": "No results found.", "th": "ไม่พบผลลัพธ์"},
    "Download Queue": {"en": "Download Queue", "th": "คิวการดาวน์โหลด"},
    "All downloads appear here": {"en": "All downloads appear here", "th": "รายการดาวน์โหลดทั้งหมดจะแสดงที่นี่"},
    "Refresh": {"en": "Refresh", "th": "รีเฟรช"},
    "No files downloaded yet.": {"en": "No files downloaded yet.", "th": "ยังไม่มีไฟล์ที่ดาวน์โหลด"},
    "Trim": {"en": "Trim", "th": "ตัดเสียง"},
    "Play": {"en": "Play", "th": "เล่น"},
    "Customize your download preferences": {"en": "Customize your download preferences", "th": "ปรับแต่งการดาวน์โหลดของคุณ"},
    "Format": {"en": "Format", "th": "รูปแบบไฟล์"},
    "Options": {"en": "Options", "th": "ตัวเลือกเพิ่มเติม"},
    "Theme Accent Color": {"en": "Theme Accent Color", "th": "สีธีมหลัก"},
    "Language": {"en": "Language", "th": "ภาษา (Language)"},
    "Output Folder": {"en": "Output Folder", "th": "โฟลเดอร์บันทึกไฟล์"},
    "Browse": {"en": "Browse", "th": "เลือกโฟลเดอร์"},
    "Audio  —  MP3 320kbps": {"en": "Audio  —  MP3 320kbps", "th": "เสียง  —  MP3 320kbps"},
    "Video  —  MP4 Max": {"en": "Video  —  MP4 Max", "th": "วิดีโอ  —  MP4 ชัดสุด"},
}

def _btn(parent, text, cmd, fg=None, hv=None, width=120, height=36, **kw):
    return ctk.CTkButton(
        parent, text=text, command=cmd,
        fg_color=fg or PRIMARY, hover_color=hv or fg or PRIMARY,
        font=FONT_SM, corner_radius=8, width=width, height=height, **kw
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

        self.is_win = sys.platform == "win32"
        self.is_mac = sys.platform == "darwin"
        self.exe_ext = ".exe" if self.is_win else ""

        if getattr(sys, "frozen", False):
            base_dir = sys._MEIPASS
            self._exe_path = sys.executable
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self._exe_path = None

        icon_path = os.path.join(base_dir, "icon.ico")
        if os.path.exists(icon_path) and self.is_win:
            self.iconbitmap(icon_path)

        self.appdata_dir = os.path.join(os.path.expanduser("~"), ".NexusTube") if not self.is_win else os.path.join(os.getenv("APPDATA"), "YTDownloaderPro")
        os.makedirs(self.appdata_dir, exist_ok=True)
        
        self.config_path = os.path.join(self.appdata_dir, "config.json")
        try:
            with open(self.config_path, "r") as f: self.config = json.load(f)
        except:
            self.config = {"accent": "#22C55E", "lang": "en"}
            
        global ACCENT
        ACCENT = self.config.get("accent", "#22C55E")
        self.lang = self.config.get("lang", "en")

        self.ffmpeg = os.path.join(self.appdata_dir, f"ffmpeg{self.exe_ext}")
        self.ytdlp  = os.path.join(self.appdata_dir, f"yt-dlp{self.exe_ext}")

        self._default_outdir = os.path.join(os.path.expanduser("~"), "Downloads", "NexusTube")
        os.makedirs(self._default_outdir, exist_ok=True)

        self._pending_update_url = None
        self._pending_update_ver = None

        self.executor = ThreadPoolExecutor(max_workers=4)
        self._build_ui()
        threading.Thread(target=self._check_engine, daemon=True).start()
        threading.Thread(target=self._check_app_update, daemon=True).start()

    def t(self, key):
        return LOCALES.get(key, {}).get(self.lang, key)

    def _build_ui(self):
        sidebar = ctk.CTkFrame(self, width=200, fg_color=SIDEBAR, corner_radius=0)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        logo_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        logo_frame.pack(fill="x", pady=(28, 12), padx=20)
        _label(logo_frame, "▶  NexusTube",   font=FONT_MD, color=ACCENT).pack(anchor="w")
        _label(logo_frame, "Music Downloader", font=FONT_XS, color=MUTED).pack(anchor="w")
        _label(logo_frame, "by herlove",       font=FONT_XS, color=PRIMARY).pack(anchor="w", pady=(4, 0))
        _label(logo_frame, f"v{VERSION}",      font=FONT_XS, color=MUTED).pack(anchor="w")

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
        nav_items = [
            (f"  {self.t('Search')}", "search"), 
            (f"  {self.t('Queue')}", "queue"), 
            (f"  {self.t('Library')}", "library"),
            (f"  {self.t('Settings')}", "settings")
        ]
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

        self._main = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self._main.pack(side="left", fill="both", expand=True)

        self._pages = {
            "search":   self._build_search_page(self._main),
            "queue":    self._build_queue_page(self._main),
            "library":  self._build_library_page(self._main),
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
        if key == "library":
            self._refresh_library()

    def _build_search_page(self, parent):
        page = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        hdr = ctk.CTkFrame(page, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(20, 12))
        _label(hdr, self.t("Search & Download"), font=FONT_H).pack(anchor="w")
        _label(hdr, self.t("Search YouTube or paste a link"), font=FONT_XS, color=MUTED).pack(anchor="w")

        card = ctk.CTkFrame(page, fg_color=SURFACE, corner_radius=12)
        card.pack(fill="x", padx=24, pady=(0, 12))
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=12)
        self.search_entry = ctk.CTkEntry(
            row, placeholder_text="URL / Search...",
            font=FONT_SM, corner_radius=22,
            fg_color=SURFACE2, border_color=BORDER, border_width=1, text_color=TEXT,
            placeholder_text_color=MUTED, height=44,
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.search_entry.bind("<Return>", lambda e: self._do_search())
        _btn(row, self.t("Search"), self._do_search, fg=PRIMARY, width=80, height=36, corner_radius=18).pack(side="left", padx=(0, 8))
        _btn(row, self.t("+ Add URL"), self._quick_add, fg=ACCENT, hv=ACCENT_HV, width=80, height=36, corner_radius=18).pack(side="left", padx=(0, 8))
        _btn(row, self.t("Import TXT"), self._import_txt, fg=SURFACE2, width=80, height=36, corner_radius=18).pack(side="left")

        _label(page, self.t("Results"), font=FONT_MD, color=MUTED).pack(anchor="w", padx=24, pady=(4, 4))
        self.results_scroll = ctk.CTkScrollableFrame(
            page, fg_color=BG,
            scrollbar_button_color=SURFACE2, scrollbar_button_hover_color=PRIMARY,
        )
        self.results_scroll.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        return page

    def _import_txt(self):
        filepath = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if not filepath: return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                urls = [line.strip() for line in f if line.strip() and "http" in line]
            if urls:
                for url in urls: self.add_to_queue(url, url)
                show_notify("Batch Import", f"Added {len(urls)} videos to queue.")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _do_search(self):
        q = self.search_entry.get().strip()
        if not q: return
        for w in self.results_scroll.winfo_children(): w.destroy()
        card = ctk.CTkFrame(self.results_scroll, fg_color=SURFACE, corner_radius=10)
        card.pack(fill="x", pady=4, padx=4)
        _label(card, "Searching...", color=MUTED).pack(pady=12)
        threading.Thread(target=self._search_thread, args=(q,), daemon=True).start()

    def _search_thread(self, q):
        while getattr(self, "_engine_busy", False):
            self.after(0, lambda: self.status_var.set("Waiting for engine..."))
            import time; time.sleep(1)
        try:
            proc = subprocess.Popen(
                [self.ytdlp, f"ytsearch8:{q}", "--dump-json",
                 "--no-playlist", "--flat-playlist", "--no-warnings"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if self.is_win else 0
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
            _label(self.results_scroll, self.t("No results found."), color=MUTED).pack(pady=20)
            return
        for item in results:
            title    = item.get("title", "Unknown")
            uploader = item.get("uploader", "")
            dur      = item.get("duration") or 0
            url      = item.get("webpage_url", "")
            mins, secs = int(dur) // 60, int(dur) % 60
            card = ctk.CTkFrame(self.results_scroll, fg_color=SURFACE, corner_radius=12,
                                border_width=1, border_color=BORDER)
            card.pack(fill="x", pady=5, padx=6)
            info = ctk.CTkFrame(card, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True, padx=16, pady=12)
            _label(info, title[:72] + ("…" if len(title) > 72 else ""),
                   font=FONT_SM, anchor="w").pack(anchor="w")
            _label(info, f"{uploader}  ·  {mins}:{secs:02d}",
                   font=FONT_XS, color=MUTED, anchor="w").pack(anchor="w", pady=(2, 0))
            _btn(card, "Download", lambda u=url, t=title: self.add_to_queue(u, t),
                 fg=ACCENT, hv=ACCENT_HV, width=88).pack(side="right", padx=12, pady=10)

    def _quick_add(self):
        url = self.search_entry.get().strip()
        if not url: return
        self.search_entry.delete(0, "end")
        if "list=" in url or "playlist" in url:
            if messagebox.askyesno("Playlist", "Do you want to select specific videos from this playlist?"):
                threading.Thread(target=self._fetch_playlist, args=(url,), daemon=True).start()
                return
        self.add_to_queue(url, url)

    def _fetch_playlist(self, url):
        self.after(0, lambda: self.status_var.set("Fetching playlist..."))
        try:
            proc = subprocess.Popen([self.ytdlp, "--flat-playlist", "--dump-json", url], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW if self.is_win else 0)
            items = []
            for line in proc.stdout:
                try: items.append(json.loads(line.decode("utf-8")))
                except: pass
            proc.wait()
            self.after(0, lambda: self._show_playlist_selector(items))
            self.after(0, lambda: self.status_var.set("Ready"))
        except Exception as e:
            self.after(0, lambda: self.status_var.set(f"Error: {e}"))
            
    def _show_playlist_selector(self, items):
        if not items: return
        top = ctk.CTkToplevel(self)
        top.title("Smart Playlist")
        top.geometry("500x600")
        top.attributes("-topmost", True)
        scroll = ctk.CTkScrollableFrame(top, fg_color=BG)
        scroll.pack(fill="both", expand=True, padx=10, pady=10)
        vars_list = []
        for item in items:
            var = tk.BooleanVar(value=True)
            title = item.get("title", "Unknown")
            url = item.get("url", "")
            if not url: url = "https://youtube.com/watch?v=" + item.get("id", "")
            ctk.CTkCheckBox(scroll, text=title[:60], variable=var, font=FONT_SM, text_color=TEXT, fg_color=ACCENT).pack(anchor="w", pady=2)
            vars_list.append((var, url, title))
        def do_dl():
            top.destroy()
            dl_count = 0
            for var, url, title in vars_list:
                if var.get(): 
                    self.add_to_queue(url, title)
                    dl_count += 1
            show_notify("Playlist Added", f"Added {dl_count} videos to the queue.")
        _btn(top, "Download Selected", do_dl, fg=ACCENT).pack(pady=10)

    def _build_queue_page(self, parent):
        page = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        hdr = ctk.CTkFrame(page, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(20, 12))
        _label(hdr, self.t("Download Queue"), font=FONT_H).pack(anchor="w")
        _label(hdr, self.t("All downloads appear here"), font=FONT_XS, color=MUTED).pack(anchor="w")
        self.queue_scroll = ctk.CTkScrollableFrame(
            page, fg_color=BG,
            scrollbar_button_color=SURFACE2, scrollbar_button_hover_color=PRIMARY,
        )
        self.queue_scroll.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        return page

    def add_to_queue(self, url, title=""):
        self._switch_tab("queue")
        card = ctk.CTkFrame(self.queue_scroll, fg_color=SURFACE, corner_radius=12, border_width=1, border_color=BORDER)
        card.pack(fill="x", pady=6, padx=6)
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(12, 6))
        lbl  = _label(top, (title or url)[:70], font=FONT_SM, anchor="w")
        lbl.pack(side="left", fill="x", expand=True)
        stat = _label(top, "Waiting…", font=FONT_XS, color=MUTED)
        stat.pack(side="right")
        prog = ctk.CTkProgressBar(card, mode="determinate", fg_color=SURFACE2, progress_color=PRIMARY, corner_radius=4, height=6)
        prog.pack(fill="x", padx=14, pady=(0, 12))
        prog.set(0)
        self.executor.submit(self._download_worker, {"url": url, "lbl": lbl, "prog": prog, "stat": stat, "card": card})

    def _build_library_page(self, parent):
        page = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        hdr = ctk.CTkFrame(page, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(20, 12))
        _label(hdr, self.t("Library"), font=FONT_H).pack(side="left")
        _btn(hdr, "🔄 " + self.t("Refresh"), self._refresh_library, fg=SURFACE2, width=80).pack(side="right")
        self.lib_scroll = ctk.CTkScrollableFrame(page, fg_color=BG, scrollbar_button_color=SURFACE2, scrollbar_button_hover_color=PRIMARY)
        self.lib_scroll.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        return page

    def _refresh_library(self):
        for w in self.lib_scroll.winfo_children(): w.destroy()
        outdir = self.out_var.get()
        if not os.path.exists(outdir): return
        files = [f for f in os.listdir(outdir) if f.endswith(".mp3") or f.endswith(".mp4") or f.endswith(".m4a")]
        files.sort(key=lambda x: os.path.getmtime(os.path.join(outdir, x)), reverse=True)
        if not files:
            _label(self.lib_scroll, self.t("No files downloaded yet."), color=MUTED).pack(pady=20)
            return
        for f in files:
            path = os.path.join(outdir, f)
            card = ctk.CTkFrame(self.lib_scroll, fg_color=SURFACE, corner_radius=12, border_width=1, border_color=BORDER)
            card.pack(fill="x", pady=5, padx=6)
            _label(card, f[:60], font=FONT_SM).pack(side="left", padx=14, pady=12)
            _btn(card, "✂️ " + self.t("Trim"), lambda p=path: self._open_trim_dialog(p), fg=SURFACE2, width=65, height=30, corner_radius=15).pack(side="right", padx=(0, 10))
            
            def play_media(p=path):
                if self.is_win: os.startfile(p)
                elif self.is_mac: subprocess.call(["open", p])
                else: subprocess.call(["xdg-open", p])
            _btn(card, "▶️ " + self.t("Play"), play_media, fg=PRIMARY, width=65, height=30, corner_radius=15).pack(side="right", padx=(0, 10))

    def _open_trim_dialog(self, path):
        top = ctk.CTkToplevel(self)
        top.title("Audio Trimmer")
        top.geometry("300x250")
        top.attributes("-topmost", True)
        _label(top, "Start Time (HH:MM:SS)", font=FONT_SM).pack(pady=(20, 0))
        start_ent = ctk.CTkEntry(top, font=FONT_SM, fg_color=SURFACE2)
        start_ent.insert(0, "00:00:00")
        start_ent.pack()
        _label(top, "End Time (HH:MM:SS)", font=FONT_SM).pack(pady=(10, 0))
        end_ent = ctk.CTkEntry(top, font=FONT_SM, fg_color=SURFACE2)
        end_ent.insert(0, "00:01:00")
        end_ent.pack()
        
        def do_trim():
            start = start_ent.get().strip()
            end = end_ent.get().strip()
            top.destroy()
            out_path = path.rsplit(".", 1)[0] + "_trimmed." + path.rsplit(".", 1)[1]
            self.status_var.set("Trimming audio...")
            def _trim_thread():
                try:
                    subprocess.run([self.ffmpeg, "-y", "-i", path, "-ss", start, "-to", end, "-c", "copy", out_path], check=True, creationflags=subprocess.CREATE_NO_WINDOW if self.is_win else 0)
                    self.after(0, lambda: self.status_var.set("Trim complete ✅"))
                    show_notify("Trim Complete", f"Saved to {os.path.basename(out_path)}")
                    self.after(0, self._refresh_library)
                except Exception as e:
                    self.after(0, lambda: messagebox.showerror("Trim Error", str(e)))
            threading.Thread(target=_trim_thread, daemon=True).start()
        _btn(top, "✂️ Trim Now", do_trim, fg=ACCENT).pack(pady=20)

    def _build_settings_page(self, parent):
        page = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        hdr = ctk.CTkFrame(page, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(20, 12))
        _label(hdr, self.t("Settings"), font=FONT_H).pack(anchor="w")
        _label(hdr, self.t("Customize your download preferences"), font=FONT_XS, color=MUTED).pack(anchor="w")

        fc = ctk.CTkFrame(page, fg_color=SURFACE, corner_radius=16)
        fc.pack(fill="x", padx=24, pady=(0, 16))
        _label(fc, self.t("Format"), font=FONT_MD).pack(anchor="w", padx=20, pady=(16, 8))
        ctk.CTkFrame(fc, fg_color=BORDER, height=1).pack(fill="x", padx=16)
        self.type_var = tk.StringVar(value="audio")
        for val, txt in [("audio", self.t("Audio  —  MP3 320kbps")), ("video", self.t("Video  —  MP4 Max"))]:
            row = ctk.CTkFrame(fc, fg_color="transparent")
            row.pack(fill="x", padx=20, pady=8)
            ctk.CTkRadioButton(row, text=txt, variable=self.type_var, value=val, font=FONT_SM, fg_color=ACCENT, hover_color=ACCENT_HV).pack(side="left")
        ctk.CTkFrame(fc, fg_color="transparent", height=10).pack()

        oc = ctk.CTkFrame(page, fg_color=SURFACE, corner_radius=16)
        oc.pack(fill="x", padx=24, pady=(0, 16))
        _label(oc, self.t("Options"), font=FONT_MD).pack(anchor="w", padx=20, pady=(16, 8))
        ctk.CTkFrame(oc, fg_color=BORDER, height=1).pack(fill="x", padx=16)
        self.sponsor_var, self.meta_var, self.playlist_var, self.lyrics_var = tk.BooleanVar(), tk.BooleanVar(value=True), tk.BooleanVar(), tk.BooleanVar()
        for var, txt in [
            (self.sponsor_var,  "SponsorBlock (Remove ads)"),
            (self.meta_var,     "Embed metadata & thumbnail"),
            (self.playlist_var, "Download full playlist (Legacy)"),
            (self.lyrics_var,   "Embed Lyrics"),
        ]:
            ctk.CTkCheckBox(oc, text=txt, variable=var, font=FONT_SM, fg_color=ACCENT, hover_color=ACCENT_HV, checkmark_color=BG, corner_radius=6).pack(anchor="w", padx=20, pady=6)
        ctk.CTkFrame(oc, fg_color="transparent", height=10).pack()

        lc = ctk.CTkFrame(page, fg_color=SURFACE, corner_radius=16)
        lc.pack(fill="x", padx=24, pady=(0, 16))
        _label(lc, self.t("Language"), font=FONT_MD).pack(anchor="w", padx=20, pady=(16, 8))
        ctk.CTkFrame(lc, fg_color=BORDER, height=1).pack(fill="x", padx=16)
        lrow = ctk.CTkFrame(lc, fg_color="transparent")
        lrow.pack(fill="x", padx=20, pady=12)
        def _set_lang(v):
            self.config["lang"] = v
            with open(self.config_path, "w") as f: json.dump(self.config, f)
            messagebox.showinfo("Language", "Please restart the app to apply language changes.")
        self.lang_var = tk.StringVar(value=self.lang)
        ctk.CTkRadioButton(lrow, text="English", variable=self.lang_var, value="en", command=lambda: _set_lang("en"), font=FONT_SM, fg_color=ACCENT).pack(side="left", padx=(0, 16))
        ctk.CTkRadioButton(lrow, text="ภาษาไทย", variable=self.lang_var, value="th", command=lambda: _set_lang("th"), font=FONT_SM, fg_color=ACCENT).pack(side="left")

        tc = ctk.CTkFrame(page, fg_color=SURFACE, corner_radius=16)
        tc.pack(fill="x", padx=24, pady=(0, 16))
        _label(tc, self.t("Theme Accent Color"), font=FONT_MD).pack(anchor="w", padx=20, pady=(16, 8))
        ctk.CTkFrame(tc, fg_color=BORDER, height=1).pack(fill="x", padx=16)
        trow = ctk.CTkFrame(tc, fg_color="transparent")
        trow.pack(fill="x", padx=16, pady=12)
        def _set_color(c):
            self.config["accent"] = c
            with open(self.config_path, "w") as f: json.dump(self.config, f)
            messagebox.showinfo("Theme", "Color saved! Please restart the app to apply.")
        colors = [("Green", "#22C55E"), ("Indigo", "#4F46E5"), ("Pink", "#EC4899"), ("Yellow", "#EAB308"), ("Cyan", "#06B6D4")]
        for name, hx in colors:
            btn = ctk.CTkButton(trow, text="", width=32, height=32, corner_radius=16, fg_color=hx, hover_color=hx, command=lambda c=hx: _set_color(c))
            btn.pack(side="left", padx=6)

        dc = ctk.CTkFrame(page, fg_color=SURFACE, corner_radius=16)
        dc.pack(fill="x", padx=24, pady=(0, 16))
        _label(dc, self.t("Output Folder"), font=FONT_MD).pack(anchor="w", padx=20, pady=(16, 8))
        ctk.CTkFrame(dc, fg_color=BORDER, height=1).pack(fill="x", padx=16)
        row = ctk.CTkFrame(dc, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=12)
        self.out_var = tk.StringVar(value=self._default_outdir)
        ctk.CTkEntry(row, textvariable=self.out_var, state="readonly", font=FONT_SM, fg_color=SURFACE2, border_color=BORDER, text_color=MUTED, corner_radius=8, height=36).pack(side="left", fill="x", expand=True, padx=(0, 12))
        _btn(row, self.t("Browse"), self._browse_out, fg=PRIMARY, width=80).pack(side="left")
        return page

    def _browse_out(self):
        folder = filedialog.askdirectory()
        if folder: self.out_var.set(folder)

    def _check_engine(self):
        self._engine_busy = True
        def _set_status(msg): self.after(0, lambda: self.status_var.set(msg))
        
        if not os.path.exists(self.ytdlp):
            _set_status("Downloading yt-dlp…")
            try:
                if self.is_win: dl_url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
                elif self.is_mac: dl_url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos"
                else: dl_url = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
                
                data = requests.get(dl_url, timeout=60).content
                with open(self.ytdlp, "wb") as f: f.write(data)
                if not self.is_win: os.chmod(self.ytdlp, 0o755)
            except Exception as e:
                _set_status(f"❌ yt-dlp dl error: {e}")
                self._engine_busy = False
                return

        ffmpeg_ver_file = os.path.join(self.appdata_dir, "ffmpeg_version.txt")
        if not os.path.exists(self.ffmpeg):
            _set_status("Downloading ffmpeg (~30MB)…")
            try:
                import zipfile, io, tarfile
                resp = requests.get("https://api.github.com/repos/yt-dlp/FFmpeg-Builds/releases/latest", timeout=10).json()
                tag = resp["tag_name"]
                
                if self.is_win: asset_name = "ffmpeg-master-latest-win64-gpl.zip"
                elif self.is_mac: asset_name = "ffmpeg-master-latest-mac64-gpl.zip"
                else: asset_name = "ffmpeg-master-latest-linux64-gpl.tar.xz"
                
                url = next(a["browser_download_url"] for a in resp["assets"] if a["name"] == asset_name)
                data = requests.get(url, timeout=120).content
                
                if asset_name.endswith(".zip"):
                    with zipfile.ZipFile(io.BytesIO(data)) as z:
                        exe_path = next(name for name in z.namelist() if name.endswith(f"bin/ffmpeg{self.exe_ext}"))
                        with open(self.ffmpeg, "wb") as f: f.write(z.read(exe_path))
                else:
                    with tarfile.open(fileobj=io.BytesIO(data), mode="r:xz") as t:
                        member = next(m for m in t.getmembers() if m.name.endswith("bin/ffmpeg"))
                        with open(self.ffmpeg, "wb") as f: f.write(t.extractfile(member).read())
                
                if not self.is_win: os.chmod(self.ffmpeg, 0o755)
                with open(ffmpeg_ver_file, "w") as f: f.write(tag)
            except Exception as e:
                _set_status(f"❌ ffmpeg dl error: {e}")
                self._engine_busy = False
                return

        _set_status("Engines ready ✅")
        self._engine_busy = False

    def _check_app_update(self):
        try:
            resp = requests.get(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest", timeout=8)
            if resp.status_code != 200: return
            data = resp.json()
            latest = data.get("tag_name", "").lstrip("v")
            if not latest or latest == VERSION: return
            
            asset_name = "NexusTube.exe" if self.is_win else "NexusTube"
            asset = next((a for a in data.get("assets", []) if a["name"].lower() == asset_name.lower()), None)
            
            self._pending_update_url = asset["browser_download_url"] if asset else None
            self._pending_update_ver = latest
            self.after(0, lambda: self._update_banner.pack(fill="x", pady=(4, 0)))
            self.after(0, lambda v=latest: self._update_btn.configure(text=f"🔄 v{v} available!"))
        except Exception:
            pass 

    def _do_app_update(self):
        ver = self._pending_update_ver or "?"
        if not self._exe_path or not self._pending_update_url:
            messagebox.showinfo("Update available", f"New version v{ver} available!\nhttps://github.com/{GITHUB_REPO}/releases/latest")
            return
        if not messagebox.askyesno("Update NexusTube", f"Found v{ver} — update and restart now?"): return
        threading.Thread(target=self._apply_update, daemon=True).start()

    def _apply_update(self):
        try:
            self.after(0, lambda: self._update_btn.configure(text="Downloading…", state="disabled"))
            tmp_exe = self._exe_path + ".new"
            with requests.get(self._pending_update_url, stream=True, timeout=120) as r:
                total = int(r.headers.get("content-length", 0))
                written = 0
                with open(tmp_exe, "wb") as f:
                    for chunk in r.iter_content(65536):
                        f.write(chunk)
                        written += len(chunk)
                        if total:
                            pct = written / total * 100
                            self.after(0, lambda p=pct: self.status_var.set(f"Downloading… {p:.0f}%"))

            if self.is_win:
                bat = self._exe_path + ".update.bat"
                lines = ["@echo off", "timeout /t 2 /nobreak >nul", f'move /y "{tmp_exe}" "{self._exe_path}"', f'start "" "{self._exe_path}"', 'del "%~f0"', ""]
                with open(bat, "w") as f: f.write("\n".join(lines))
                subprocess.Popen(["cmd", "/c", bat], creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                sh = self._exe_path + ".update.sh"
                lines = ["#!/bin/bash", "sleep 2", f'mv "{tmp_exe}" "{self._exe_path}"', f'chmod +x "{self._exe_path}"', f'"{self._exe_path}" &', f'rm "$0"']
                with open(sh, "w") as f: f.write("\n".join(lines))
                os.chmod(sh, 0o755)
                subprocess.Popen([sh])
                
            self.after(0, self.destroy)   
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Update failed", str(e)))
            self.after(0, lambda: self._update_btn.configure(text="🔄 Retry", state="normal"))

    def _download_worker(self, task):
        url, prog, stat, card = task["url"], task["prog"], task["stat"], task["card"]
        def ui(fn): self.after(0, fn)
        
        while getattr(self, "_engine_busy", False):
            ui(lambda: stat.configure(text="Waiting for engine setup…", text_color=WARN))
            import time; time.sleep(1)

        ui(lambda: stat.configure(text="Starting…", text_color=PRIMARY))
        ui(lambda: card.configure(border_color=PRIMARY))

        fmt, outdir = self.type_var.get(), os.path.abspath(self.out_var.get())
        os.makedirs(outdir, exist_ok=True)
        ffmpeg = self.ffmpeg if os.path.exists(self.ffmpeg) else "ffmpeg"

        cmd = [self.ytdlp, "--newline", "--no-warnings", "--ffmpeg-location", ffmpeg, "-o", outdir + "/%(title)s.%(ext)s", "--no-playlist" if not self.playlist_var.get() else "--yes-playlist"]
        if self.sponsor_var.get():  cmd += ["--sponsorblock-remove", "all"]
        if self.meta_var.get():     cmd += ["--embed-thumbnail", "--embed-metadata"]
        if self.lyrics_var.get():   cmd += ["--write-subs", "--sub-langs", "all", "--embed-subs"]
        
        if fmt == "audio": cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
        else: cmd += ["-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best", "--merge-output-format", "mp4"]
        cmd.append(url)

        ansi = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW if self.is_win else 0)
            title_dl = url
            for raw in proc.stdout:
                line = ansi.sub("", raw.decode("utf-8", errors="replace")).strip()
                if "[download] Destination:" in line:
                    title_dl = line.split("Destination: ")[-1].split(".")[0][:40]
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
                show_notify("Download Complete", f"Finished downloading: {title_dl}")
            else:
                ui(lambda: stat.configure(text="Failed ✗", text_color=ERROR))
                ui(lambda: card.configure(border_color=ERROR))
        except Exception as e:
            ui(lambda: stat.configure(text=f"Error: {str(e)[:40]}", text_color=ERROR))
            ui(lambda: card.configure(border_color=ERROR))

if __name__ == "__main__":
    App().mainloop()
