/**
 * NexusTube — Robust Download Queue & Background Worker Engine
 * Orchestrates multi-platform media downloading via yt-dlp and ffmpeg,
 * parses real-time download telemetry (percent, speed, ETA), and tags audio.
 */

const fs = require('fs');
const path = require('path');
const os = require('os');
const { spawn } = require('child_process');
const fsp = require('fs').promises;
const NodeID3 = require('node-id3');
const { fetchLyrics, saveLrc } = require('./lyrics');
const R = require('./download-resilience');

class DownloadManager {
  constructor(engineManager, configManager) {
    this.engine = engineManager;
    this.config = configManager;
    this.tasks = [];
    this.taskCounter = 0;
    this.activeWorkers = 0;
    this.queuePath = path.join(this.config.appdataDir, 'queue.json');
    this._saveTimer = null;
    this.restoreQueue();
  }

  // จำนวนงานพร้อมกันอ่านจาก config ทุกครั้ง — ปรับได้สดจากหน้าเว็บ/ตั้งค่า (1–6)
  get maxConcurrent() {
    const n = Number(this.config.get('max_concurrent', 3));
    return Math.min(6, Math.max(1, Number.isFinite(n) ? Math.round(n) : 3));
  }

  // ── คิวอยู่รอดข้ามการปิดแอป ────────────────────────────────────────
  saveQueue() {
    if (this._saveTimer) return;
    this._saveTimer = setTimeout(() => {
      this._saveTimer = null;
      try {
        const snapshot = this.tasks.slice(-R.MAX_PERSISTED_TASKS).map((t) => ({
          id: t.id, url: t.url, title: t.title, format: t.format,
          options: t.options, metadata: t.metadata, status: t.status
        }));
        fs.writeFileSync(this.queuePath, JSON.stringify({ version: 1, tasks: snapshot }, null, 1), 'utf8');
      } catch {}
    }, 500);
  }

  restoreQueue() {
    try {
      if (!fs.existsSync(this.queuePath)) return;
      const data = JSON.parse(fs.readFileSync(this.queuePath, 'utf8'));
      const kept = [];
      for (const t of (Array.isArray(data.tasks) ? data.tasks : [])) {
        if (!t || !t.url) continue;
        if (t.status === 'completed') continue; // เสร็จแล้วไม่ต้องกู้
        // งานที่กำลังโหลดค้างตอนปิดแอป → ให้กลับมาเข้าคิวใหม่
        kept.push({
          ...t,
          status: t.status === 'failed' ? 'failed' : 'waiting',
          percent: 0, speed: '0 KiB/s', eta: '--:--',
          thumbnail: t.thumbnail || '', out_file: null, size_bytes: null,
          error: t.status === 'failed' ? (t.error || null) : null,
          proc: null, cancelled: false,
          _retryAttempts: {}
        });
      }
      if (kept.length) {
        this.tasks = kept;
        this.taskCounter = kept.length;
        // งานที่ติดค้างเดิมกลับเข้าคิวอัตโนมัติ
        setTimeout(() => this.processQueue(), 3000);
      }
    } catch {}
  }

  sanitizeFilename(name) {
    if (!name) return "track";
    return name
      .replace(/[\\/:*?"<>|]/g, '_')
      .replace(/\s+/g, ' ')
      .trim()
      .slice(0, 150);
  }

  // เทียบ URL แบบตัดพารามิเตอร์รบกวน (list=, si=) ออก — วิดีโอเดียวกันถือว่าซ้ำ
  static normalizeUrlForDedup(u) {
    return String(u || '').trim()
      .replace(/[?&]list=[^&]*/g, '')
      .replace(/[?&]si=[^&]*/g, '')
      .replace(/[?&]feature=[^&]*/g, '');
  }

  addToQueue(url, title = "", fmtChoice = "mp3_320", options = {}, metadata = null) {
    const cleanUrl = (url || '').trim();
    const normUrl = DownloadManager.normalizeUrlForDedup(cleanUrl);

    // กันซ้ำ: URL เดิม (เทียบแบบ normalize) ที่กำลังรอ/กำลังโหลด/เสร็จแล้ว → ไม่เพิ่มงานซ้ำ
    const dupe = this.tasks.find(t => DownloadManager.normalizeUrlForDedup(t.url) === normUrl &&
      ['waiting', 'downloading', 'processing', 'completed'].includes(t.status));
    if (dupe && normUrl) {
      return { task_id: dupe.id, duplicate: true };
    }

    this.taskCounter++;
    const taskId = `task_${Date.now()}_${this.taskCounter}`;

    const task = {
      id: taskId,
      url: cleanUrl,
      title: title || url,
      format: fmtChoice || this.config.get('format', 'mp3_320'),
      status: "waiting",
      percent: 0.0,
      speed: "0 KiB/s",
      eta: "--:--",
      thumbnail: (metadata && metadata.thumbnail) || "",
      out_file: null,
      size_bytes: null,
      error: null,
      options: {
        embed_thumb: options.embed_thumb !== undefined ? options.embed_thumb : this.config.get('embed_thumb', true),
        embed_meta: options.embed_meta !== undefined ? options.embed_meta : this.config.get('embed_meta', true),
        embed_lyrics: options.embed_lyrics !== undefined ? options.embed_lyrics : this.config.get('embed_lyrics', false),
        sponsorblock: options.sponsorblock !== undefined ? options.sponsorblock : this.config.get('sponsorblock', false),
        normalize: options.normalize !== undefined ? options.normalize : this.config.get('normalize', false)
      },
      metadata: metadata || {},
      proc: null,
      cancelled: false
    };

    this.tasks.push(task);
    this.saveQueue();
    this.processQueue();
    return { task_id: taskId, duplicate: false };
  }

  getQueueState() {
    return this.tasks.map(t => ({
      id: t.id,
      url: t.url,
      title: t.title,
      format: t.format,
      status: t.status,
      percent: t.percent,
      speed: t.speed,
      eta: t.eta,
      thumbnail: t.thumbnail,
      out_file: t.out_file,
      size_bytes: t.size_bytes,
      error: t.error
    }));
  }

  cancelTask(taskId) {
    const task = this.tasks.find(t => t.id === taskId);
    if (!task) return false;

    task.cancelled = true;
    task.status = "cancelled";

    if (task.proc) {
      try {
        if (process.platform === 'win32') {
          spawn('taskkill', ['/pid', String(task.proc.pid), '/f', '/t'], { windowsHide: true });
        } else {
          task.proc.kill('SIGTERM');
        }
      } catch {}
      task.proc = null;
    }
    this.processQueue();
    return true;
  }

  retryTask(taskId) {
    const task = this.tasks.find(t => t.id === taskId);
    if (!task) return false;

    task.status = "waiting";
    task.percent = 0.0;
    task.speed = "0 KiB/s";
    task.eta = "--:--";
    task.error = null;
    task.cancelled = false;
    task.out_file = null;
    task.size_bytes = null;
    task._retried = false;
    task._retryAttempts = {}; // กด retry เอง = เริ่มนับ auto-retry ใหม่

    this.saveQueue();
    this.processQueue();
    return true;
  }

  clearFinished() {
    this.tasks = this.tasks.filter(t => t.status === "waiting" || t.status === "downloading" || t.status === "processing");
    this.saveQueue();
    return true;
  }

  batchCancelAll() {
    let count = 0;
    for (const t of this.tasks) {
      if (t.status === "waiting" || t.status === "downloading" || t.status === "processing") {
        this.cancelTask(t.id);
        count++;
      }
    }
    return count;
  }

  processQueue() {
    if (this.activeWorkers >= this.maxConcurrent) return;

    // _holdUntil = งานที่จะถูกลองใหม่อัตโนมัติตาม backoff — ยังไม่ถึงเวลาไม่หยิบมาทำ
    const nextTask = this.tasks.find(t => t.status === "waiting" && !t.cancelled && !(t._holdUntil && t._holdUntil > Date.now()));
    if (!nextTask) return;

    this.activeWorkers++;
    this.runTask(nextTask)
      .finally(() => {
        this.activeWorkers--;
        this.processQueue();
      });
  }

  async runTask(task) {
    if (task.cancelled) {
      task.status = "cancelled";
      return;
    }

    const ytdlpBin = this.engine.getYtdlpBin();
    if (!this.engine.isValidBinary(ytdlpBin)) {
      task.status = "failed";
      task.error = "yt-dlp engine not available.";
      return;
    }

    const ffmpegBin = this.engine.getFfmpegBin();
    const hasFfmpeg = this.engine.isValidBinary(ffmpegBin);
    const ffmpegDir = hasFfmpeg ? path.dirname(ffmpegBin) : "";

    // Determine output directory
    let outdir = this.config.get('outdir') || path.join(os.homedir(), "Downloads", "NexusTube");
    try {
      fs.mkdirSync(outdir, { recursive: true });
    } catch {
      outdir = path.join(os.homedir(), "Downloads");
      try { fs.mkdirSync(outdir, { recursive: true }); } catch {}
    }

    task.status = "downloading";
    task.percent = 0.01;

    // ── กันพังชั้นที่ 1: เช็คพื้นที่ดิสก์ก่อนเริ่ม (เต็มแล้วรู้ตัวก่อน ไม่ให้ไฟล์เสียหาย)
    try {
      const stats = await fsp.statfs(outdir);
      const freeBytes = Number(stats.bavail) * Number(stats.bsize);
      if (freeBytes < R.MIN_FREE_BYTES) {
        task.status = "failed";
        task.error = "พื้นที่ดิสก์เหลือน้อยกว่า 250 MB — เคลียร์พื้นที่แล้วกดลองใหม่";
        this.saveQueue();
        return;
      }
    } catch {} // ระบบไฟล์ไม่รองรับ statfs → ข้ามไป ไม่ให้เป็นอุปสรรค

    // ── กันพังชั้นที่ 2: watchdog จับงานค้าง (เน็ตตาย/เซิร์ฟเวอร์ห้อย) — ไม่มีความคืบหน้า 90 วิ → ฆ่าแล้วลองใหม่
    task._lastProgress = Date.now();
    const watchdog = setInterval(() => {
      if (task.cancelled || task.status !== "downloading") return;
      if (Date.now() - (task._lastProgress || 0) > R.STALL_MS) {
        task._stalled = true;
        try { proc && proc.kill(); } catch {}
        clearInterval(watchdog);
      }
    }, R.STALL_CHECK_MS);
    if (typeof watchdog.unref === 'function') watchdog.unref();

    // Filename template
    let outTemplate;
    let safeTitle = this.sanitizeFilename(task.title);
    // กันไฟล์ชนกัน: มีงาน live อื่นชื่อเดียวกันอยู่แล้ว → เติมเลขท้าย
    const sameTitleLive = this.tasks.filter(t => t !== task &&
      ['waiting', 'downloading', 'processing'].includes(t.status) &&
      this.sanitizeFilename(t.title) === safeTitle);
    if (sameTitleLive.length > 0) {
      safeTitle = `${safeTitle} (${sameTitleLive.length + 1})`;
    }
    const trackNum = task.metadata?.track_num;
    const isPlaylistUrl = task.url.includes('list=') || task.url.includes('/playlist');
    if (!isPlaylistUrl && safeTitle && !task.title.startsWith("http")) {
      const prefix = trackNum ? `${String(trackNum).padStart(2, '0')} - ` : "";
      outTemplate = path.join(outdir, `${prefix}${safeTitle}.%(ext)s`);
    } else {
      outTemplate = path.join(outdir, "%(title)s.%(ext)s");
    }

    const cmdArgs = [
      '--newline',
      '--no-warnings',
      '--windows-filenames',
      '--retries', '10',
      '--fragment-retries', '10',
      '--socket-timeout', '30',
      // โหลด fragment ขนาน 4 เส้น — วิดีโอ/HLS เร็วขึ้นมาก, ไฟล์เดี่ยวไม่กระทบ
      '--concurrent-fragments', '4',
      '-o', outTemplate
    ];

    // ลิงก์แบบ watch?v=...&list=... → โหลดเฉพาะวิดีโอนั้น ไม่ใช่ทั้งเพลย์ลิสต์
    if (task.url.includes('watch?v=') && task.url.includes('list=')) {
      cmdArgs.push('--no-playlist');
    }

    if (ffmpegDir) {
      cmdArgs.push('--ffmpeg-location', ffmpegDir);
    }

    // Options
    const opts = task.options || {};
    if (opts.sponsorblock && hasFfmpeg) {
      cmdArgs.push('--sponsorblock-remove', 'sponsor,selfpromo');
    }
    if (opts.embed_meta && hasFfmpeg) {
      cmdArgs.push('--embed-metadata');
    }
    if (opts.embed_thumb && hasFfmpeg) {
      cmdArgs.push('--embed-thumbnail');
    }
    if (opts.embed_lyrics && hasFfmpeg) {
      cmdArgs.push('--write-subs', '--sub-langs', 'en.*,th.*', '--embed-subs');
    }

    // Format choices
    const fmt = task.format || "mp3_320";
    if (fmt === "mp3_320") {
      cmdArgs.push('-x', '--audio-format', 'mp3', '--audio-quality', '320K');
    } else if (fmt === "m4a_best") {
      cmdArgs.push('-x', '--audio-format', 'm4a', '--audio-quality', '0');
    } else if (fmt === "flac") {
      cmdArgs.push('-x', '--audio-format', 'flac', '--audio-quality', '0');
    } else if (fmt === "mp4_1080") {
      cmdArgs.push('-f', 'bestvideo[height<=1080]+bestaudio/best[height<=1080]/best', '--merge-output-format', 'mp4');
    } else if (fmt === "mp4_720") {
      cmdArgs.push('-f', 'bestvideo[height<=720]+bestaudio/best[height<=720]/best', '--merge-output-format', 'mp4');
    } else { // mp4_best
      cmdArgs.push('-f', 'bestvideo+bestaudio/best', '--merge-output-format', 'mp4');
    }

    // Normalization
    if (opts.normalize && hasFfmpeg) {
      const isAudio = ["mp3_320", "m4a_best", "flac"].includes(fmt);
      const postProc = isAudio ? 'ExtractAudio' : 'Merger';
      cmdArgs.push('--postprocessor-args', `${postProc}:-filter:a loudnorm=I=-14:LRA=11:TP=-1.5`);
    }

    // Cookies if set
    const cookieSource = this.config.get('cookie_source');
    const cookieFile = this.config.get('cookie_file');
    if (cookieFile && fs.existsSync(cookieFile)) {
      cmdArgs.push('--cookies', cookieFile);
    } else if (cookieSource && cookieSource !== 'none') {
      cmdArgs.push('--cookies-from-browser', cookieSource);
    }

    cmdArgs.push(task.url);

    // Regex matchers
    const pctRegex = /(\d+\.?\d*)%/;
    const speedRegex = /at\s+([~0-9\.]+\s*\w+\/s)/;
    const etaRegex = /ETA\s+(\d+:\d+(?::\d+)?)/;

    let destFile = null;
    let procOutput = [];

    return new Promise((resolve) => {
      const proc = spawn(ytdlpBin, cmdArgs, { windowsHide: true });
      task.proc = proc;

      const handleChunk = (data) => {
        if (task.cancelled) return;
        const text = data.toString('utf8');
        const lines = text.split(/\r?\n/);

        for (const line of lines) {
          if (!line.trim()) continue;
          procOutput.push(line);
          if (procOutput.length > 30) procOutput.shift();

          // Check percent
          const mPct = line.match(pctRegex);
          if (mPct) {
            task.percent = Math.min(0.99, parseFloat(mPct[1]) / 100);
            task._lastProgress = Date.now(); // ให้ watchdog รู้ว่ายังมีชีวิตอยู่
          }

          // Check speed
          const mSpeed = line.match(speedRegex);
          if (mSpeed) {
            task.speed = mSpeed[1];
          }

          // Check ETA
          const mEta = line.match(etaRegex);
          if (mEta) {
            task.eta = mEta[1];
          }

          // Check destination file
          if (line.includes('[download] Destination:')) {
            const p = line.split('[download] Destination:')[1].trim();
            if (!p.endsWith('.part') && !p.endsWith('.ytdl')) {
              destFile = p;
              task.out_file = destFile;
            }
          } else if (line.includes('Destination:')) {
            const p = line.split('Destination:')[1].trim();
            if (!p.endsWith('.part') && !p.endsWith('.ytdl')) {
              destFile = p;
              task.out_file = destFile;
            }
          } else if (line.includes('has already been downloaded')) {
            const m = line.match(/\[download\]\s+(.*?)\s+has already been downloaded/);
            if (m) {
              destFile = m[1].trim();
              task.out_file = destFile;
            }
          } else if (line.includes('Merging formats into "')) {
            const m = line.split('Merging formats into "')[1].replace(/"$/, '').trim();
            destFile = m;
            task.out_file = destFile;
          } else if (line.includes('[ExtractAudio] Destination:')) {
            const p = line.split('[ExtractAudio] Destination:')[1].trim();
            destFile = p;
            task.out_file = destFile;
          }
        }
      };

      proc.stdout.on('data', handleChunk);
      proc.stderr.on('data', handleChunk);

      proc.on('close', async (code) => {
        task.proc = null;
        clearInterval(watchdog);
        if (task.cancelled) {
          task.status = "cancelled";
          this.saveQueue();
          return resolve();
        }

        if (code === 0) {
          task.status = "processing";

          // If destFile not explicitly captured, scan directory for newest matching file
          if (!destFile || !fs.existsSync(destFile)) {
            try {
              const files = fs.readdirSync(outdir).map(f => path.join(outdir, f));
              const now = Date.now();
              const needle = (safeTitle || '').toLowerCase().slice(0, 40);
              const recent = files
                .map(f => {
                  try { return { file: f, mtime: fs.statSync(f).mtimeMs }; } catch { return null; }
                })
                .filter(Boolean)
                // จำกัดเฉพาะไฟล์ที่ชื่อตรงกับงานนี้ — กันหลอดไปชี้ไฟล์ของงานอื่นตอนโหลดพร้อมกัน
                .filter(f => !needle || path.basename(f.file).toLowerCase().includes(needle))
                .filter(f => (now - f.mtime) < 120000)
                .sort((a, b) => b.mtime - a.mtime);
              if (recent.length > 0) {
                destFile = recent[0].file;
                task.out_file = destFile;
              }
            } catch {}
          }

          // ตรวจว่าไฟล์มีจริง + ขนาดสมเหตุสมผล
          if (!destFile || !fs.existsSync(destFile) || fs.statSync(destFile).size < 10240) {
            return resolve(this._handleFailure(task, "incomplete download — missing output file (connection cut mid-way)"));
          }
          task.size_bytes = fs.statSync(destFile).size;

          // Post-process metadata tagging & lyrics
          if (destFile && fs.existsSync(destFile)) {
            const ext = path.extname(destFile).toLowerCase();
            const meta = task.metadata || {};

            // Embed ID3 tags for MP3 files
            if (ext === '.mp3') {
              try {
                const tags = {
                  title: meta.title || task.title,
                  artist: meta.artist || "Unknown Artist",
                  album: meta.album || "NexusTube Collection"
                };
                if (meta.track_num) tags.trackNumber = String(meta.track_num);

                // Cover art
                if (meta.thumbnail && meta.thumbnail.startsWith('http')) {
                  try {
                    const imgBuf = await this.downloadBuffer(meta.thumbnail);
                    if (imgBuf) {
                      tags.image = {
                        mime: "image/jpeg",
                        type: { id: 3, name: "front cover" },
                        description: "Album Art",
                        imageBuffer: imgBuf
                      };
                    }
                  } catch {}
                }

                NodeID3.write(tags, destFile);
              } catch (e) {
                console.warn("[Downloader] Tagging failed:", e.message);
              }
            }

            // Auto-fetch & save lyrics sidecar if enabled
            if (opts.embed_lyrics || this.config.get('embed_lyrics')) {
              try {
                const lyr = await fetchLyrics(meta.title || task.title, meta.artist || "", 0, destFile);
                if (lyr && lyr.synced_raw) {
                  saveLrc(destFile, lyr.synced_raw);
                } else if (lyr && lyr.plain) {
                  saveLrc(destFile, lyr.plain);
                }
              } catch {}
            }
          }

          task.percent = 1.0;
          task.status = "completed";
          task.speed = "Done";
          task.eta = "00:00";
          task.error = null;
          this.saveQueue();

          // Janitor: งานแบบ -x (แปลงเป็นไฟล์เสียง) → ลบ raw ต้นทาง (.webm/.m4a/…) ที่ตกค้าง
          const isAudioFmt = ["mp3_320", "m4a_best", "flac"].includes(task.format);
          if (isAudioFmt && destFile && fs.existsSync(destFile)) {
            const stem = destFile.slice(0, destFile.length - path.extname(destFile).length);
            for (const rawExt of ['.webm', '.mkv', '.mp4', '.m4a', '.opus', '.ogg', '.wav']) {
              if (rawExt === path.extname(destFile).toLowerCase()) continue;
              const rawPath = stem + rawExt;
              try {
                if (fs.existsSync(rawPath)) fs.unlinkSync(rawPath);
              } catch {}
            }
          }
        } else {
          // กันพังชั้นที่ 3: จำแนกสาเหตุ → auto-retry ตามนโยบาย / อัปเดต yt-dlp / สลับ format
          const cleanAnsi = s => String(s).replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '').trim();
          let rawErr = procOutput.slice(-3).map(cleanAnsi).filter(Boolean).join(' | ');
          if (task._stalled) {
            rawErr = "download stalled — no progress for 90s, killed by watchdog";
            task._stalled = false;
          }
          return resolve(this._handleFailure(task, rawErr || `Process exited with error code ${code}`));
        }
        resolve();
      });

      proc.on('error', (err) => {
        task.proc = null;
        clearInterval(watchdog);
        return resolve(this._handleFailure(task, `spawn failed: ${err && err.message || err}`));
      });
    });
  }

  /**
   * ศูนย์กลางจัดการงานที่ล้ม — พิจารณาจาก download-resilience ว่า:
   *  1. format ใช้ไม่ได้กับคลิป → สลับรูปแบบสำรอง (fallback chain) แล้วลองทันที
   *  2. yt-dlp เก่า (extractor error) → อัปเดตเครื่องมืออัตโนมัติ แล้วลองใหม่ 1 ครั้ง
   *  3. เครือข่าย/ชั่วคราว → ลองใหม่เองได้ถึง 3 ครั้ง ถอยหลัง 3s → 10s → 30s
   *  4. เสียถาวร (คลิปลบ/private/copyright) → รายงานเลย ไม่เปลืองเวลา
   */
  _handleFailure(task, rawErr) {
    const kind = R.classifyError(rawErr);
    task._retryAttempts = task._retryAttempts || {};
    const attempt = task._retryAttempts[kind] || 0;

    // ── format ไม่มีให้โหลด → สลับเป็นรูปแบบสำรอง (ไม่นับเป็น retry)
    if (kind === 'extractor' && /requested format is not available/i.test(String(rawErr))) {
      const nextFmt = R.nextFormatFallback(task.format);
      if (nextFmt) {
        task.format = nextFmt;
        task._retryAttempts = {};
        task.error = `รูปแบบเดิมไม่มีให้โหลด — สลับเป็น ${nextFmt} ให้อัตโนมัติ`;
        task.status = "waiting";
        task.percent = 0; task.speed = "0 KiB/s"; task.eta = "--:--"; task.out_file = null;
        task.note = task.error;
        this.saveQueue();
        setTimeout(() => this.processQueue(), 1000);
        return task;
      }
    }

    // ── เสียถาวร หรือหมดสิทธิ์ลองใหม่ → รายงานจริง
    if (kind === 'fatal' || !R.shouldAutoRetry(kind, attempt)) {
      const cleanAnsi = s => String(s).replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '').trim();
      const friendly = {
        fatal: "คลิปนี้โหลดไม่ได้ (อาจถูกลบ เป็นแบบ private หรือถูกจำกัดสิทธิ์)",
        extractor: "โหลดไม่สำเร็จแม้อัปเดตเครื่องมือแล้ว — รอ yt-dlp ออกเวอร์ชันแก้แล้วกดลองใหม่",
        transient: "เครือข่ายมีปัญหาซ้ำหลายครั้ง — ตรวจอินเทอร์เน็ตแล้วกดลองใหม่",
        unknown: "ดาวน์โหลดไม่สำเร็จ — กดลองใหม่ได้"
      }[kind];
      task.status = "failed";
      const detail = (String(rawErr).replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '').trim()).slice(-160);
      task.error = friendly + (detail ? ` (${detail})` : "");
      this.saveQueue();
      return task;
    }

    task._retryAttempts[kind] = attempt + 1;
    const waitMs = R.backoffMs(attempt);
    task.status = "waiting";
    task.percent = 0; task.speed = "0 KiB/s"; task.eta = "--:--"; task.out_file = null;

    if (kind === 'extractor') {
      // yt-dlp อาจเก่ากว่าที่ YouTube ต้องการ → อัปเดตก่อนแล้วลองใหม่
      task.error = "ตรวจพบเครื่องมืออาจเก่า — กำลังอัปเดต yt-dlp แล้วจะลองใหม่อัตโนมัติ";
      this.saveQueue();
      Promise.resolve(this.engine.ensureFreshYtdlp ? this.engine.ensureFreshYtdlp('extractor-error') : null)
        .catch(() => {})
        .finally(() => {
          setTimeout(() => { if (!task.cancelled) this.processQueue(); }, R.backoffMs(attempt));
        });
      return task;
    }

    // ── ชั่วคราว/ไม่ทราบสาเหตุ → ถอยหลังแล้วลองใหม่เอง
    const maxTries = kind === 'transient' ? R.MAX_TRANSIENT_RETRIES : 1;
    task.error = `ขัดข้องชั่วคราว — จะลองใหม่อัตโนมัติใน ${Math.round(waitMs / 1000)} วิ (ครั้งที่ ${attempt + 1}/${maxTries})`;
    this.saveQueue();
    task._holdUntil = Date.now() + waitMs;
    setTimeout(() => { if (!task.cancelled) this.processQueue(); }, waitMs);
    return task;
  }

  downloadBuffer(url) {
    return new Promise((resolve) => {
      const client = url.startsWith('https') ? require('https') : require('http');
      client.get(url, { headers: { 'User-Agent': 'NexusTube/3.4.0' } }, (res) => {
        if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          return resolve(this.downloadBuffer(res.headers.location));
        }
        if (res.statusCode !== 200) return resolve(null);
        const chunks = [];
        res.on('data', c => chunks.push(c));
        res.on('end', () => resolve(Buffer.concat(chunks)));
      }).on('error', () => resolve(null));
    });
  }
}

module.exports = { DownloadManager };
