/**
 * NexusTube — Robust Download Queue & Background Worker Engine
 * Orchestrates multi-platform media downloading via yt-dlp and ffmpeg,
 * parses real-time download telemetry (percent, speed, ETA), and tags audio.
 */

const fs = require('fs');
const path = require('path');
const os = require('os');
const { spawn, spawnSync } = require('child_process');
let NodeID3 = null;
try { NodeID3 = require('node-id3'); } catch {}
const { fetchLyrics, saveLrc } = require('./lyrics');
const { resilientArgs, isHealableFailure, isPermanentFailure } = require('./youtube');
const {
  isDownloadUrl,
  isPlaylistDownload,
  buildStrategies,
  backoffMs,
  isStalled,
  outputIsUsable,
  isRecoverableMedia,
  isPostprocessFailure,
  pickRecoveredFile,
  publicDownloadError,
  shouldRetryLater,
  retryLaterMs,
  hasDiskSpace,
  isInsideDir,
  queueRecord,
  resumableRecords,
  STALL_MS
} = require('./download-plan');

class DownloadManager {
  constructor(engineManager, configManager) {
    this.engine = engineManager;
    this.config = configManager;
    this.tasks = [];
    this.taskCounter = 0;
    this.maxConcurrent = 2;
    this.activeWorkers = 0;
    this.persistence = false;
    this.persistTimer = null;
    this.released = false;
  }

  sanitizeFilename(name) {
    if (!name) return "track";
    const cleaned = name
      .replace(/[\u0000-\u001f]/g, '')
      .replace(/[\\/:*?"<>|]/g, '_')
      .replace(/\s+/g, ' ')
      .replace(/^\.+/, '')
      .replace(/[. ]+$/g, '')
      .trim()
      .slice(0, 150);
    return cleaned || 'track';
  }

  usableOutput(file) {
    try {
      return !!file && isRecoverableMedia(path.basename(file)) && fs.existsSync(file) && outputIsUsable(fs.statSync(file).size);
    } catch {
      return false;
    }
  }

  recoveredMedia(outdir, sinceMs) {
    try {
      const entries = fs.readdirSync(outdir).map((name) => {
        const file = path.join(outdir, name);
        try {
          const stat = fs.statSync(file);
          if (stat.mtimeMs < sinceMs - 5000) return null;
          return { name, file, size: stat.size };
        } catch {
          return null;
        }
      }).filter(Boolean);
      const picked = pickRecoveredFile(entries);
      return picked ? picked.file : null;
    } catch {
      return null;
    }
  }

  addToQueue(url, title = "", fmtChoice = "mp3_320", options = {}, metadata = null) {
    const cleanUrl = String(url || '').trim();
    if (!isDownloadUrl(cleanUrl)) {
      return { task_id: null, error: "ใช้ได้เฉพาะลิงก์ http หรือ https" };
    }

    const existing = this.tasks.find((task) => task.url === cleanUrl && (task.status === "waiting" || task.status === "downloading" || task.status === "processing"));
    if (existing) {
      return { task_id: existing.id, duplicate: true };
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
    this.processQueue();
    this.schedulePersist();
    return { task_id: taskId };
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
    this.schedulePersist();
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
    task.healed = false;
    task.rounds = 0;
    task.cooldownUntil = 0;
    task.out_file = null;

    this.processQueue();
    this.schedulePersist();
    return true;
  }

  clearFinished() {
    this.tasks = this.tasks.filter(t => t.status === "waiting" || t.status === "downloading" || t.status === "processing");
    this.schedulePersist();
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
    if (this.released) return;
    if (this.activeWorkers >= this.maxConcurrent) return;

    const nextTask = this.tasks.find(t => t.status === "waiting" && !t.cancelled && !(t.cooldownUntil > Date.now()));
    if (!nextTask) return;

    this.activeWorkers++;
    this.runTask(nextTask)
      .catch((err) => {
        nextTask.status = 'failed';
        nextTask.error = publicDownloadError(err && err.message);
        this.schedulePersist();
      })
      .finally(() => {
        this.activeWorkers--;
        this.processQueue();
      });
  }

  downloadStrategies() {
    return buildStrategies();
  }

  async runTask(task) {
    if (task.cancelled) {
      task.status = "cancelled";
      return;
    }

    let ytdlpBin = this.engine.getYtdlpBin();
    if (!this.engine.isValidBinary(ytdlpBin) && typeof this.engine.ensureEngines === 'function') {
      try { await this.engine.ensureEngines(); } catch {}
      ytdlpBin = this.engine.getYtdlpBin();
    }
    if (!this.engine.isValidBinary(ytdlpBin)) {
      task.status = "failed";
      task.error = "yt-dlp engine not available.";
      this.schedulePersist();
      return;
    }

    if (!this.engine.isValidBinary(this.engine.getFfmpegBin()) && typeof this.engine.ensureEngines === 'function') {
      try { await this.engine.ensureEngines(); } catch {}
    }

    const outdir = this.config.get('outdir') || path.join(os.homedir(), "Downloads", "NexusTube");
    try {
      const stat = fs.statfsSync(outdir);
      if (!hasDiskSpace(stat)) {
        task.status = "failed";
        task.error = "พื้นที่ดิสก์ไม่พอสำหรับการโหลด";
        this.schedulePersist();
        return;
      }
    } catch {}

    const strategies = this.downloadStrategies();
    let lastError = "Download failed.";
    let healed = !!task.healed;

    for (let i = 0; i < strategies.length; i++) {
      if (task.cancelled) {
        task.status = "cancelled";
        this.schedulePersist();
        return;
      }
      if (i > 0) {
        await new Promise((resolve) => {
          const timer = setTimeout(resolve, backoffMs(i - 1));
          if (typeof timer.unref === 'function') timer.unref();
        });
      }
      if (task.cancelled) {
        task.status = "cancelled";
        this.schedulePersist();
        return;
      }
      task.status = "downloading";
      task.error = null;
      task.percent = 0.01;
      task.speed = `ลองวิธี ${i + 1}/${strategies.length}`;
      this.schedulePersist();
      let result;
      try {
        result = await this.executeDownload(task, strategies[i]);
      } catch (err) {
        result = { ok: false, error: String(err && err.message || err) };
      }
      if (result.cancelled || task.cancelled) {
        task.status = "cancelled";
        this.schedulePersist();
        return;
      }
      if (result.ok) {
        await this.finishDownload(task, result);
        this.schedulePersist();
        return;
      }
      lastError = result.error || lastError;
      this.appendLog(`${task.id} attempt ${i + 1} failed: ${lastError}`);
      if (isPostprocessFailure(lastError) && !(strategies[i] && strategies[i].plain)) {
        task.speed = 'แปลงไฟล์อีกครั้งแบบไม่ฝังปก';
        const plainResult = await this.executeDownload(task, { ...strategies[i], plain: true });
        if (plainResult.cancelled || task.cancelled) {
          task.status = 'cancelled';
          this.schedulePersist();
          return;
        }
        if (plainResult.ok) {
          await this.finishDownload(task, plainResult);
          this.schedulePersist();
          return;
        }
        lastError = plainResult.error || lastError;
        this.appendLog(`${task.id} plain retry failed: ${lastError}`);
      }
      if (isPermanentFailure(lastError)) break;
      if (!healed && isHealableFailure(lastError) && typeof this.engine.healYoutubeEngine === 'function') {
        healed = true;
        task.healed = true;
        const healedResult = await this.engine.healYoutubeEngine();
        if (healedResult && healedResult.success && !task.cancelled) {
          i = -1;
        }
      }
    }

    const rounds = Number(task.rounds) || 0;
    if (shouldRetryLater(lastError, rounds)) {
      task.rounds = rounds + 1;
      task.status = "waiting";
      task.percent = 0;
      task.error = null;
      task.cooldownUntil = Date.now() + retryLaterMs(rounds);
      task.speed = `พักแล้วลองใหม่ (${task.rounds}/3)`;
      this.schedulePersist();
      const timer = setTimeout(() => {
        if (!task.cancelled && task.status === "waiting") this.processQueue();
      }, retryLaterMs(rounds));
      if (typeof timer.unref === "function") timer.unref();
      return;
    }

    task.status = "failed";
    task.error = publicDownloadError(lastError);
    this.schedulePersist();
  }

  async executeDownload(task, strategy) {
    const ytdlpBin = this.engine.getYtdlpBin();
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

    // Filename template
    let outTemplate;
    const safeTitle = this.sanitizeFilename(task.title);
    const trackNum = task.metadata?.track_num;
    const isPlaylistUrl = isPlaylistDownload(task.url);
    if (!isPlaylistUrl && safeTitle && !String(task.title || '').startsWith("http")) {
      const prefix = trackNum ? `${String(trackNum).padStart(2, '0')} - ` : "";
      outTemplate = `${prefix}${safeTitle}.%(ext)s`;
    } else {
      outTemplate = "%(title)s.%(ext)s";
    }

    const cmdArgs = [
      '--newline',
      '--windows-filenames',
      ...resilientArgs(this.engine, this.config, task.url, {
        playlist: isPlaylistUrl,
        playerClient: strategy && strategy.playerClient
      }),
      '-o', outTemplate
    ];

    if (ffmpegDir) {
      cmdArgs.push('--ffmpeg-location', ffmpegDir);
    }

    // Options
    const opts = task.options || {};
    const plain = !!(strategy && strategy.plain);
    if (!plain && opts.sponsorblock && hasFfmpeg) {
      cmdArgs.push('--sponsorblock-remove', 'sponsor,selfpromo');
    }
    if (!plain && opts.embed_lyrics && hasFfmpeg) {
      cmdArgs.push('--write-subs', '--sub-langs', 'en.*,th.*', '--embed-subs');
    }

    // Format choices. A loose pass still saves a playable file when the exact format is gone.
    const fmt = task.format || "mp3_320";
    const loose = strategy && strategy.looseFormat;
    if (loose) {
      const audio = ["mp3_320", "m4a_best", "flac"].includes(fmt);
      if (audio && hasFfmpeg) {
        cmdArgs.push('-x', '--audio-format', 'mp3', '--audio-quality', '192K');
      } else if (audio) {
        cmdArgs.push('-f', 'bestaudio/best');
      } else {
        cmdArgs.push('-f', 'bestvideo+bestaudio/best', '--merge-output-format', 'mp4');
      }
    } else if (fmt === "mp3_320") {
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
    if (!plain && opts.normalize && hasFfmpeg) {
      const isAudio = ["mp3_320", "m4a_best", "flac"].includes(fmt);
      const postProc = isAudio ? 'ExtractAudio' : 'Merger';
      cmdArgs.push('--postprocessor-args', `${postProc}:-filter:a loudnorm=I=-14:LRA=11:TP=-1.5`);
    }

    cmdArgs.push(task.url);

    // Regex matchers
    const pctRegex = /(\d+\.?\d*)%/;
    const speedRegex = /at\s+([~0-9\.]+\s*\w+\/s)/;
    const etaRegex = /ETA\s+(\d+:\d+(?::\d+)?)/;

    let destFile = null;
    let procOutput = [];
    let stalled = false;
    let lastOutputAt = Date.now();
    const attemptStarted = Date.now();

    return new Promise((resolve) => {
      const proc = spawn(ytdlpBin, cmdArgs, {
        windowsHide: true,
        cwd: outdir,
        env: this.engine.toolEnv()
      });
      task.proc = proc;

      const stopWatch = (timer) => {
        clearInterval(timer);
      };
      const stallTimer = setInterval(() => {
        if (!isStalled(lastOutputAt, Date.now(), STALL_MS) || !task.proc) return;
        stalled = true;
        try {
          if (process.platform === 'win32') {
            spawn('taskkill', ['/pid', String(task.proc.pid), '/f', '/t'], { windowsHide: true });
          } else {
            task.proc.kill('SIGTERM');
          }
        } catch {}
      }, 5000);
      if (typeof stallTimer.unref === 'function') stallTimer.unref();

      const handleChunk = (data) => {
        if (task.cancelled) return;
        const text = data.toString('utf8');
        const lines = text.split(/\r?\n/);

        for (const line of lines) {
          if (!line.trim()) continue;
          lastOutputAt = Date.now();
          procOutput.push(line);
          if (procOutput.length > 30) procOutput.shift();

          // Check percent
          const mPct = line.match(pctRegex);
          if (mPct) {
            task.percent = Math.min(0.99, parseFloat(mPct[1]) / 100);
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
        stopWatch(stallTimer);
        task.proc = null;
        if (task.cancelled) {
          return resolve({ cancelled: true });
        }
        if (stalled) {
          return resolve({ ok: false, error: "โหลดค้าง ไม่มีข้อมูลใหม่ กำลังลองวิธีอื่น" });
        }
        let failure = null;
        if (code !== 0) {
          const blob = procOutput.join('\n').trim();
          failure = blob.split(/\r?\n/).slice(-3).join(' ') || `Process exited with error code ${code}`;
        }

        if (!destFile || !this.usableOutput(destFile)) {
          const recovered = this.recoveredMedia(outdir, attemptStarted);
          if (recovered) {
            destFile = recovered;
            task.out_file = recovered;
          }
        }
        if (failure && this.usableOutput(destFile)) failure = null;
        if (failure) {
          return resolve({ ok: false, error: failure });
        }
        const playlist = isPlaylistDownload(task.url);
        if (destFile && !path.isAbsolute(destFile)) {
          destFile = path.resolve(outdir, destFile);
          task.out_file = destFile;
        }
        if (destFile && !isInsideDir(destFile, outdir)) {
          return resolve({ ok: false, error: "ไฟล์ผลลัพธ์อยู่นอกโฟลเดอร์ดาวน์โหลด" });
        }
        if (!playlist && destFile && fs.existsSync(destFile) && !outputIsUsable(fs.statSync(destFile).size)) {
          return resolve({ ok: false, error: "ไฟล์ที่โหลดได้เล็กเกินไป กำลังลองวิธีอื่น" });
        }
        if (!playlist && (!destFile || !fs.existsSync(destFile))) {
          return resolve({ ok: false, error: "โหลดจบแต่ไม่พบไฟล์ กำลังลองวิธีอื่น" });
        }
        resolve({ ok: true, destFile, outdir, opts });
      });

      proc.on('error', (err) => {
        stopWatch(stallTimer);
        task.proc = null;
        resolve({ ok: false, error: String(err.message || err) });
      });
    });
  }

  async finishDownload(task, result) {
    const destFile = result.destFile;
    const opts = result.opts || task.options || {};
    task.status = "processing";
    task.out_file = destFile || task.out_file;

    if (destFile && fs.existsSync(destFile)) {
      const ext = path.extname(destFile).toLowerCase();
      const meta = task.metadata || {};

      if (ext === '.mp3') {
        try {
          const tags = {
            title: meta.title || task.title,
            artist: meta.artist || "Unknown Artist",
            album: meta.album || "NexusTube Collection"
          };
          if (meta.track_num) tags.trackNumber = String(meta.track_num);

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

          if (NodeID3) NodeID3.write(tags, destFile);
        } catch (e) {
          console.warn("[Downloader] Tagging failed:", e.message);
        }
      }

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
  }

  release() {
    // ponytail: quit kills the download tools and writes the queue. ceiling: waiting tasks resume on the next launch. upgrade: keep a download running only if a future build uses a separate service process.
    this.released = true;
    if (this.persistTimer) clearTimeout(this.persistTimer);
    this.persistTimer = null;
    for (const task of this.tasks) {
      if (task.proc && task.proc.pid) {
        try {
          if (process.platform === 'win32') {
            spawnSync('taskkill', ['/pid', String(task.proc.pid), '/f', '/t'], { windowsHide: true });
          } else {
            task.proc.kill('SIGTERM');
          }
        } catch {}
        task.proc = null;
      }
      if (task.status === 'downloading' || task.status === 'processing') {
        task.status = 'waiting';
        task.speed = '';
        task.eta = '';
      }
    }
    this.activeWorkers = 0;
    if (this.persistence) this.writeQueue();
  }

  queueFilePath() {
    const dir = this.config?.appdataDir || path.join(os.homedir(), 'AppData', 'Roaming', 'NexusTube');
    return path.join(dir, 'download-queue.json');
  }

  restoreQueue() {
    this.persistence = true;
    try {
      const file = this.queueFilePath();
      if (!fs.existsSync(file)) return;
      const parsed = JSON.parse(fs.readFileSync(file, 'utf8'));
      const records = resumableRecords(parsed);
      if (!records.length) return;
      this.tasks = records.map((record) => ({ ...record, proc: null }));
      const maxCounter = this.tasks.reduce((max, task) => {
        const match = String(task.id).match(/_(\d+)$/);
        return Math.max(max, match ? Number(match[1]) : 0);
      }, 0);
      this.taskCounter = Math.max(this.taskCounter, maxCounter);
      this.processQueue();
    } catch (err) {
      this.appendLog(`restore failed: ${err.message}`);
    }
  }

  schedulePersist() {
    if (!this.persistence) return;
    if (this.persistTimer) clearTimeout(this.persistTimer);
    this.persistTimer = setTimeout(() => {
      this.persistTimer = null;
      this.writeQueue();
    }, 250);
    if (typeof this.persistTimer.unref === 'function') this.persistTimer.unref();
  }

  writeQueue() {
    try {
      const file = this.queueFilePath();
      fs.mkdirSync(path.dirname(file), { recursive: true });
      const body = JSON.stringify(this.tasks.map((task) => queueRecord(task)));
      fs.writeFileSync(file, body);
    } catch (err) {
      this.appendLog(`persist failed: ${err.message}`);
    }
  }

  appendLog(line) {
    try {
      const dir = this.config?.appdataDir;
      if (!dir) return;
      const file = path.join(dir, 'download.log');
      fs.mkdirSync(dir, { recursive: true });
      if (fs.existsSync(file) && fs.statSync(file).size > 262144) {
        try { fs.renameSync(file, `${file}.old`); } catch {}
      }
      fs.appendFileSync(file, `${new Date().toISOString()} ${String(line).slice(0, 500)}\n`);
    } catch {}
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
