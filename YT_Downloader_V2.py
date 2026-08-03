"""
NexusTube — YT Downloader Pro
Design system: Dark OLED · Indigo/Green · Poppins · ui-ux-pro-max
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
import subprocess, threading, os, sys, re, json, requests
from concurrent.futures import ThreadPoolExecutor

# ── Design Tokens ────────────────────────────────────────────────────────────
BG        = "#0F0F23"   # OLED background
SURFACE   = "#1A1A35"   # card / panel
SURFACE2  = "#22223D"   # elevated card
BORDER    = "#312E81"   # indigo border
PRIMARY   = "#4338CA"   # indigo-700
ACCENT    = "#22C55E"   # green-500
ACCENT_HV = "#16A34A"   # green-600
TEXT      = "#F8FAFC"   # foreground
MUTED     = "#94A3B8"   # slate-400
ERROR     = "#EF4444"   # red-500
WARN      = "#F59E0B"   # amber-500
GLOW      = "#4338CA"   # glow colour

FONT_H   = ("Poppins", 18, "bold")
FONT_MD  = ("Poppins", 13, "bold")
FONT_SM  = ("Poppins", 11)
FONT_XS  = ("Poppins", 9)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ── Helpers ───────────────────────────────────────────────────────────────────
def _btn(parent, text, cmd, fg=PRIMARY, hv=None, width=120, **kw):
    return ctk.CTkButton(
        parent, text=text, command=cmd,
        fg_color=fg, hover_color=hv or fg,
        font=FONT_SM, corner_radius=8, width=width, **kw
    )

def _label(parent, text, font=FONT_SM, color=TEXT, **kw):
    return ctk.CTkLabel(parent, text=text, font=font, text_color=color, **kw)


# ── App ───────────────────────────────────────────────────────────────────────
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("NexusTube")
        self.geometry("780x580")
        self.minsize(700, 520)
        self.configure(fg_color=BG)

        # paths
        if getattr(sys, "frozen", False):
            base_dir = sys._MEIPASS
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))

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

        self.executor = ThreadPoolExecutor(max_workers=4)
        self._build_ui()
        threading.Thread(target=self._check_engine, daemon=True).start()

    # ── UI skeleton ────────────────────────────────────────────────────────
    def _build_ui(self):
        # ── sidebar ──────────────────────────────────────────────────────
        sidebar = ctk.CTkFrame(self, width=180, fg_color=SURFACE, corner_radius=0)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        # logo
        logo_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        logo_frame.pack(fill="x", pady=(24, 8), padx=16)
        _label(logo_frame, "▶  NexusTube", font=("Poppins", 15, "bold"), color=ACCENT).pack(anchor="w")
        _label(logo_frame, "Music Downloader", font=FONT_XS, color=MUTED).pack(anchor="w")
        _label(logo_frame, "by herlove", font=("Poppins", 8), color="#4338CA").pack(anchor="w")

        ctk.CTkFrame(sidebar, fg_color=BORDER, height=1).pack(fill="x", padx=12, pady=8)

        # nav buttons
        self._active_tab = tk.StringVar(value="search")
        nav_items = [
            ("  Search", "search", "🔍"),
            ("  Queue",  "queue",  "📋"),
            ("  Settings", "settings", "⚙"),
        ]
        self._nav_btns = {}
        for label, key, _ in nav_items:
            btn = ctk.CTkButton(
                sidebar, text=label, anchor="w",
                font=FONT_SM, corner_radius=8,
                fg_color="transparent", hover_color=SURFACE2,
                text_color=TEXT, height=40,
                command=lambda k=key: self._switch_tab(k),
            )
            btn.pack(fill="x", padx=8, pady=2)
            self._nav_btns[key] = btn

        # status at bottom
        ctk.CTkFrame(sidebar, fg_color="transparent").pack(expand=True)
        ctk.CTkFrame(sidebar, fg_color=BORDER, height=1).pack(fill="x", padx=12, pady=4)
        self.status_var = tk.StringVar(value="Ready")
        ctk.CTkLabel(
            sidebar, textvariable=self.status_var,
            font=FONT_XS, text_color=MUTED, wraplength=160,
        ).pack(padx=10, pady=(4, 16))

        # ── main area ─────────────────────────────────────────────────────
        self._main = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self._main.pack(side="left", fill="both", expand=True)

        self._pages = {}
        self._pages["search"]   = self._build_search_page(self._main)
        self._pages["queue"]    = self._build_queue_page(self._main)
        self._pages["settings"] = self._build_settings_page(self._main)

        self._switch_tab("search")

    def _switch_tab(self, key):
        self._active_tab.set(key)
        for k, page in self._pages.items():
            if k == key:
                page.pack(fill="both", expand=True)
            else:
                page.pack_forget()
        for k, btn in self._nav_btns.items():
            btn.configure(
                fg_color=SURFACE2 if k == key else "transparent",
                text_color=ACCENT if k == key else TEXT,
            )

    # ── Search page ────────────────────────────────────────────────────────
    def _build_search_page(self, parent):
        page = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)

        # header
        hdr = ctk.CTkFrame(page, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(20, 12))
        _label(hdr, "Search & Download", font=FONT_H).pack(anchor="w")
        _label(hdr, "Search YouTube or paste a link", font=FONT_XS, color=MUTED).pack(anchor="w")

        # search bar card
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

        # results
        _label(page, "Results", font=FONT_MD, color=MUTED).pack(anchor="w", padx=24, pady=(4, 4))
        self.results_scroll = ctk.CTkScrollableFrame(
            page, fg_color=BG, scrollbar_button_color=SURFACE2,
            scrollbar_button_hover_color=PRIMARY,
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

            card = ctk.CTkFrame(
                self.results_scroll, fg_color=SURFACE, corner_radius=10,
                border_width=1, border_color=BORDER,
            )
            card.pack(fill="x", pady=4, padx=4)

            info = ctk.CTkFrame(card, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True, padx=14, pady=10)

            _label(info, title[:72] + ("…" if len(title) > 72 else ""),
                   font=("Poppins", 11, "bold"), anchor="w").pack(anchor="w")
            _label(info, f"{uploader}  ·  {mins}:{secs:02d}",
                   font=FONT_XS, color=MUTED, anchor="w").pack(anchor="w", pady=(2, 0))

            _btn(card, "Download", lambda u=url, t=title: self.add_to_queue(u, t),
                 fg=ACCENT, hv=ACCENT_HV, width=88).pack(side="right", padx=12, pady=10)

    # ── Quick Add ──────────────────────────────────────────────────────────
    def _quick_add(self):
        url = self.search_entry.get().strip()
        if "youtu" not in url:
            messagebox.showerror("Error", "Please enter a valid YouTube URL.")
            return
        self.add_to_queue(url, url)
        self.search_entry.delete(0, "end")

    # ── Queue page ─────────────────────────────────────────────────────────
    def _build_queue_page(self, parent):
        page = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)

        hdr = ctk.CTkFrame(page, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(20, 12))
        _label(hdr, "Download Queue", font=FONT_H).pack(anchor="w")
        _label(hdr, "All downloads appear here", font=FONT_XS, color=MUTED).pack(anchor="w")

        self.queue_scroll = ctk.CTkScrollableFrame(
            page, fg_color=BG,
            scrollbar_button_color=SURFACE2,
            scrollbar_button_hover_color=PRIMARY,
        )
        self.queue_scroll.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        return page

    def add_to_queue(self, url, title=""):
        self._switch_tab("queue")
        card = ctk.CTkFrame(
            self.queue_scroll, fg_color=SURFACE, corner_radius=10,
            border_width=1, border_color=BORDER,
        )
        card.pack(fill="x", pady=5, padx=4)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(10, 4))

        lbl = _label(top, (title or url)[:70], font=("Poppins", 11, "bold"), anchor="w")
        lbl.pack(side="left", fill="x", expand=True)

        stat = _label(top, "Waiting…", font=FONT_XS, color=MUTED)
        stat.pack(side="right")

        prog = ctk.CTkProgressBar(
            card, mode="determinate",
            fg_color=SURFACE2, progress_color=PRIMARY,
            corner_radius=4, height=6,
        )
        prog.pack(fill="x", padx=14, pady=(0, 12))
        prog.set(0)

        self.executor.submit(
            self._download_worker,
            {"url": url, "lbl": lbl, "prog": prog, "stat": stat, "card": card}
        )

    # ── Settings page ──────────────────────────────────────────────────────
    def _build_settings_page(self, parent):
        page = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)

        hdr = ctk.CTkFrame(page, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(20, 12))
        _label(hdr, "Settings", font=FONT_H).pack(anchor="w")
        _label(hdr, "Customize your download preferences", font=FONT_XS, color=MUTED).pack(anchor="w")

        # Format card
        fc = ctk.CTkFrame(page, fg_color=SURFACE, corner_radius=12)
        fc.pack(fill="x", padx=24, pady=(0, 10))
        _label(fc, "Format", font=FONT_MD).pack(anchor="w", padx=16, pady=(12, 6))
        ctk.CTkFrame(fc, fg_color=BORDER, height=1).pack(fill="x", padx=12)

        self.type_var = tk.StringVar(value="audio")
        for val, txt, sub in [
            ("audio", "Audio  —  MP3 320kbps", "Best quality audio extraction"),
            ("video", "Video  —  MP4 Max",     "Best quality video + audio merge"),
        ]:
            row = ctk.CTkFrame(fc, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=6)
            ctk.CTkRadioButton(
                row, text=txt, variable=self.type_var, value=val,
                font=FONT_SM, text_color=TEXT,
                fg_color=ACCENT, hover_color=ACCENT_HV,
            ).pack(side="left")
            _label(row, sub, font=FONT_XS, color=MUTED).pack(side="left", padx=(8, 0))
        ctk.CTkFrame(fc, fg_color="transparent", height=6).pack()

        # Options card
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
            ctk.CTkCheckBox(
                oc, text=txt, variable=var,
                font=FONT_SM, text_color=TEXT,
                fg_color=ACCENT, hover_color=ACCENT_HV,
                checkmark_color=BG, corner_radius=4,
            ).pack(anchor="w", padx=16, pady=5)
        ctk.CTkFrame(oc, fg_color="transparent", height=4).pack()

        # Output folder card
        dc = ctk.CTkFrame(page, fg_color=SURFACE, corner_radius=12)
        dc.pack(fill="x", padx=24, pady=(0, 10))
        _label(dc, "Output Folder", font=FONT_MD).pack(anchor="w", padx=16, pady=(12, 6))
        ctk.CTkFrame(dc, fg_color=BORDER, height=1).pack(fill="x", padx=12)

        row = ctk.CTkFrame(dc, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=10)
        self.out_var = tk.StringVar(value=self._default_outdir)
        ctk.CTkEntry(
            row, textvariable=self.out_var, state="readonly",
            font=FONT_SM, fg_color=SURFACE2, border_color=BORDER,
            text_color=MUTED, corner_radius=8,
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        _btn(row, "Browse", self._browse_out, fg=PRIMARY, hv=GLOW, width=72).pack(side="left")

        return page

    def _browse_out(self):
        folder = filedialog.askdirectory()
        if folder: self.out_var.set(folder)

    # ── Engine update ──────────────────────────────────────────────────────
    def _check_engine(self):
        if not os.path.exists(self.ytdlp):
            self.after(0, lambda: self.status_var.set("Downloading yt-dlp…"))
            try:
                data = requests.get(
                    "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe",
                    timeout=60,
                ).content
                with open(self.ytdlp, "wb") as f: f.write(data)
            except Exception as e:
                self.after(0, lambda: self.status_var.set(f"❌ {e}"))
                return

        self.after(0, lambda: self.status_var.set("Checking engine…"))
        try:
            resp    = requests.get("https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest", timeout=8)
            latest  = resp.json()["tag_name"]
            current = subprocess.check_output([self.ytdlp, "--version"], text=True).strip()
            if current != latest:
                self.after(0, lambda: self.status_var.set(f"Updating to {latest}…"))
                url = next(a["browser_download_url"] for a in resp.json()["assets"] if a["name"] == "yt-dlp.exe")
                with open(self.ytdlp, "wb") as f: f.write(requests.get(url, timeout=60).content)
                self.after(0, lambda: self.status_var.set("Engine updated ✅"))
            else:
                self.after(0, lambda: self.status_var.set("Up to date ✅"))
        except Exception:
            self.after(0, lambda: self.status_var.set("Offline mode ⚠️"))

    # ── Download worker ────────────────────────────────────────────────────
    def _download_worker(self, task):
        url  = task["url"]
        prog = task["prog"]
        stat = task["stat"]
        card = task["card"]

        def ui(fn): self.after(0, fn)

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
                        ui(lambda p=pct: prog.configure(
                            progress_color=ACCENT if p >= 1 else PRIMARY
                        ))
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
