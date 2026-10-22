/**
 * NexusTube — Self-Healing Engine & Binary Doctor
 * Locates, verifies, downloads, and updates yt-dlp, ffmpeg, ffprobe, and ffplay binaries.
 */

const fs = require('fs');
const path = require('path');
const os = require('os');
const { spawnSync, spawn } = require('child_process');
const https = require('https');
const http = require('http');
const { findSystemNode } = require('./youtube');

class EngineManager {
  constructor(appdataDir) {
    this.isWin = process.platform === 'win32';
    this.isMac = process.platform === 'darwin';
    this.exeExt = this.isWin ? '.exe' : '';

    const appdataBase = process.env.APPDATA || (this.isMac ? path.join(os.homedir(), 'Library', 'Preferences') : os.homedir());
    this.appdataDir = appdataDir || path.join(appdataBase, 'NexusTube');
    this.binDir = path.join(this.appdataDir, 'bin');
    this.legacyDir = path.join(appdataBase, 'YTDownloaderPro');
    this.repoRoot = path.resolve(__dirname, '..', '..');

    try { fs.mkdirSync(this.binDir, { recursive: true }); } catch {}

    this.shippedBin = path.join(path.dirname(process.execPath), 'bin');
    this.ytdlp = this.findBinary('yt-dlp');
    this.ffmpeg = this.findBinary('ffmpeg');
    this.ffprobe = this.findBinary('ffprobe');
    this.ffplay = this.findBinary('ffplay');

    this.ytdlpVer = "Checking...";
    this.isBusy = false;

    this.registerPath();
    this.detectYtdlpVersion();
  }

  isValidBinary(filePath, minSize = 500000) {
    if (!filePath || !fs.existsSync(filePath)) return false;
    try {
      const stat = fs.statSync(filePath);
      if (stat.size < minSize) return false;
      const buf = Buffer.alloc(4);
      const fd = fs.openSync(filePath, 'r');
      fs.readSync(fd, buf, 0, 4, 0);
      fs.closeSync(fd);
      if (this.isWin) {
        return buf[0] === 0x4D && buf[1] === 0x5A; // MZ header
      }
      return (buf[0] === 0x7F && buf[1] === 0x45 && buf[2] === 0x4C && buf[3] === 0x46) || // ELF
             (buf[0] === 0xCF && buf[1] === 0xFA && buf[2] === 0xED && buf[3] === 0xFE) || // Mach-O 64
             (buf[0] === 0xCA && buf[1] === 0xFE && buf[2] === 0xBA && buf[3] === 0xBE);   // Mach-O Universal
    } catch {
      return false;
    }
  }

  preferredBinary(name) {
    const target = `${name}${this.exeExt}`;
    let best = null;
    let bestMtime = -1;
    for (const dir of [this.binDir, this.shippedBin]) {
      if (!dir) continue;
      const candidate = path.join(dir, target);
      if (!this.isValidBinary(candidate)) continue;
      let mtime = 0;
      try { mtime = fs.statSync(candidate).mtimeMs; } catch { continue; }
      if (mtime >= bestMtime) {
        best = candidate;
        bestMtime = mtime;
      }
    }
    return best;
  }

  findBinary(name) {
    const preferred = this.preferredBinary(name);
    if (preferred) return preferred;
    const target = `${name}${this.exeExt}`;
    const searchDirs = [
      this.binDir,
      this.shippedBin,
      this.appdataDir,
      path.join(this.repoRoot, 'bin'),
      this.repoRoot,
      this.legacyDir
    ];

    for (const dir of searchDirs) {
      if (dir && fs.existsSync(dir)) {
        const candidate = path.join(dir, target);
        if (this.isValidBinary(candidate)) {
          return candidate;
        }
      }
    }

    // Check system PATH
    const pathDirs = (process.env.PATH || '').split(path.delimiter);
    for (const p of pathDirs) {
      if (p && fs.existsSync(p)) {
        const candidate = path.join(p, target);
        if (this.isValidBinary(candidate)) {
          return candidate;
        }
      }
    }

    // Fallback default destination in binDir
    return path.join(this.binDir, target);
  }

  registerPath() {
    const currentPath = process.env.PATH || '';
    const toAdd = [this.binDir, this.shippedBin, this.appdataDir, this.legacyDir].filter(d => d && fs.existsSync(d) && !currentPath.includes(d));
    if (toAdd.length > 0) {
      process.env.PATH = toAdd.join(path.delimiter) + path.delimiter + currentPath;
    }
  }

  detectYtdlpVersion() {
    const bin = this.getYtdlpBin();
    if (!this.isValidBinary(bin)) {
      this.ytdlpVer = "Missing";
      return;
    }
    try {
      const res = spawnSync(bin, ['--version'], { encoding: 'utf8', timeout: 5000, windowsHide: true });
      if (res.status === 0 && res.stdout) {
        this.ytdlpVer = res.stdout.trim().split('\n')[0];
      } else {
        this.ytdlpVer = "Installed";
      }
    } catch {
      this.ytdlpVer = "Installed";
    }
  }

  getYtdlpBin() {
    if (this.isValidBinary(this.ytdlp)) return this.ytdlp;
    const found = this.findBinary('yt-dlp');
    if (this.isValidBinary(found)) {
      this.ytdlp = found;
      return found;
    }
    return this.ytdlp;
  }

  getFfmpegBin() {
    if (this.isValidBinary(this.ffmpeg)) return this.ffmpeg;
    const found = this.findBinary('ffmpeg');
    if (this.isValidBinary(found)) {
      this.ffmpeg = found;
      return found;
    }
    return this.ffmpeg;
  }

  getStatus() {
    const ytdlpBin = this.getYtdlpBin();
    const ffmpegBin = this.getFfmpegBin();
    const ffprobeBin = this.findBinary('ffprobe');
    const ffplayBin = this.findBinary('ffplay');

    return {
      ytdlp_ready: this.isValidBinary(ytdlpBin),
      ytdlp_version: this.ytdlpVer,
      ffmpeg_ready: this.isValidBinary(ffmpegBin),
      ffprobe_ready: this.isValidBinary(ffprobeBin),
      ffplay_ready: this.isValidBinary(ffplayBin),
    };
  }

  async downloadFile(url, destPath, minSize = 500000, onProgress = null) {
    const tmpPath = `${destPath}.tmp`;
    try { if (fs.existsSync(tmpPath)) fs.unlinkSync(tmpPath); } catch {}

    return new Promise((resolve, reject) => {
      const request = (targetUrl, redirectCount = 0) => {
        if (redirectCount > 5) {
          return reject(new Error("Too many HTTP redirects"));
        }
        const client = targetUrl.startsWith('https') ? https : http;
        const req = client.get(targetUrl, {
          headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) NexusTube/3.4.0' },
          timeout: 60000
        }, (res) => {
          if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
            return request(res.headers.location, redirectCount + 1);
          }
          if (res.statusCode !== 200) {
            return reject(new Error(`HTTP status ${res.statusCode}`));
          }

          const totalBytes = parseInt(res.headers['content-length'] || '0', 10);
          let downloaded = 0;
          const file = fs.createWriteStream(tmpPath);

          res.on('data', (chunk) => {
            downloaded += chunk.length;
            if (onProgress) onProgress(downloaded, totalBytes);
          });

          res.pipe(file);

          file.on('finish', () => {
            file.close(() => {
              let valid = false;
              if (destPath.endsWith('.zip')) {
                try {
                  const stat = fs.statSync(tmpPath);
                  if (stat.size >= minSize) {
                    const buf = Buffer.alloc(2);
                    const fd = fs.openSync(tmpPath, 'r');
                    fs.readSync(fd, buf, 0, 2, 0);
                    fs.closeSync(fd);
                    valid = buf[0] === 0x50 && buf[1] === 0x4B; // PK zip magic
                  }
                } catch {}
              } else {
                valid = this.isValidBinary(tmpPath, minSize);
              }

              if (valid) {
                if (!this.isWin && !destPath.endsWith('.zip')) {
                  try { fs.chmodSync(tmpPath, 0o755); } catch {}
                }
                try {
                  if (fs.existsSync(destPath)) fs.unlinkSync(destPath);
                  fs.renameSync(tmpPath, destPath);
                  resolve(destPath);
                } catch (err) {
                  reject(err);
                }
              } else {
                try { fs.unlinkSync(tmpPath); } catch {}
                reject(new Error("Downloaded binary failed size/integrity check."));
              }
            });
          });
        });

        req.on('error', (err) => {
          try { fs.unlinkSync(tmpPath); } catch {}
          reject(err);
        });

        req.on('timeout', () => {
          req.destroy();
          try { fs.unlinkSync(tmpPath); } catch {}
          reject(new Error("Download connection timed out."));
        });
      };

      request(url);
    });
  }

  async checkYtdlpUpdate() {
    try {
      const url = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest";
      const data = await new Promise((resolve, reject) => {
        https.get(url, {
          headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) NexusTube/3.4.0' }
        }, (res) => {
          let body = '';
          res.on('data', chunk => body += chunk);
          res.on('end', () => {
            try { resolve(JSON.parse(body)); } catch (e) { reject(e); }
          });
        }).on('error', reject);
      });

      const latestVer = (data.tag_name || '').replace(/^v/, '');
      const curVer = this.ytdlpVer;
      const hasUpdate = Boolean(latestVer && curVer !== latestVer && !curVer.includes("Checking"));

      return {
        current_version: curVer,
        latest_version: latestVer || "Unknown",
        has_update: hasUpdate,
        release_notes: (data.body || '').slice(0, 300),
        release_url: data.html_url || "https://github.com/yt-dlp/yt-dlp/releases/latest"
      };
    } catch (e) {
      return {
        current_version: this.ytdlpVer,
        latest_version: "Unknown",
        has_update: false,
        error: String(e.message || e)
      };
    }
  }

  async updateYtdlp(onProgress = null) {
    if (this.isBusy) {
      return { success: false, error: "Engine manager is currently busy." };
    }
    this.isBusy = true;
    try {
      const url = this.isWin
        ? "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
        : "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp";
      const dest = path.join(this.binDir, `yt-dlp${this.exeExt}`);
      await this.downloadFile(url, dest, 500000, onProgress);
      this.ytdlp = dest;
      this.detectYtdlpVersion();
      this.isBusy = false;
      return { success: true, message: `yt-dlp updated successfully to v${this.ytdlpVer}.` };
    } catch (err) {
      this.isBusy = false;
      return { success: false, error: String(err.message || err) };
    }
  }

  async updateFfmpeg(onProgress = null) {
    if (!this.isWin) {
      return { success: false, error: "Auto-download of FFmpeg is only pre-configured for Windows. Please install ffmpeg via your package manager." };
    }
    const zipUrl = "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip";
    const zipPath = path.join(this.binDir, "ffmpeg_download.zip");
    const tempExtract = path.join(this.binDir, "ffmpeg_temp");

    try {
      await this.downloadFile(zipUrl, zipPath, 10000000, onProgress);
      if (fs.existsSync(tempExtract)) {
        try { fs.rmSync(tempExtract, { recursive: true, force: true }); } catch {}
      }
      fs.mkdirSync(tempExtract, { recursive: true });

      // Extract using tar (standard in modern Windows) or powershell
      let extracted = false;
      try {
        const tarRes = spawnSync('tar', ['-xf', zipPath, '-C', tempExtract], { windowsHide: true, timeout: 60000 });
        if (tarRes.status === 0) extracted = true;
      } catch {}

      if (!extracted) {
        spawnSync('powershell', ['-NoProfile', '-Command', `Expand-Archive -Path '${zipPath}' -DestinationPath '${tempExtract}' -Force`], { windowsHide: true, timeout: 120000 });
      }

      // Find and copy binaries
      const findAndCopy = (dir) => {
        const entries = fs.readdirSync(dir, { withFileTypes: true });
        for (const e of entries) {
          const full = path.join(dir, e.name);
          if (e.isDirectory()) {
            findAndCopy(full);
          } else if (['ffmpeg.exe', 'ffprobe.exe', 'ffplay.exe'].includes(e.name.toLowerCase())) {
            const dest = path.join(this.binDir, e.name.toLowerCase());
            try {
              if (fs.existsSync(dest)) fs.unlinkSync(dest);
              fs.copyFileSync(full, dest);
            } catch {}
          }
        }
      };

      findAndCopy(tempExtract);

      // Cleanup
      try { fs.unlinkSync(zipPath); } catch {}
      try { fs.rmSync(tempExtract, { recursive: true, force: true }); } catch {}

      this.ffmpeg = this.findBinary('ffmpeg');
      this.ffprobe = this.findBinary('ffprobe');
      this.ffplay = this.findBinary('ffplay');

      const status = this.getStatus();
      return {
        success: status.ffmpeg_ready,
        message: status.ffmpeg_ready ? "FFmpeg audio suite installed successfully." : "FFmpeg extraction failed."
      };
    } catch (err) {
      try { if (fs.existsSync(zipPath)) fs.unlinkSync(zipPath); } catch {}
      try { if (fs.existsSync(tempExtract)) fs.rmSync(tempExtract, { recursive: true, force: true }); } catch {}
      return { success: false, error: String(err.message || err) };
    }
  }

  async ensureEngines(onProgress = null) {
    let status = this.getStatus();
    if (!status.ytdlp_ready) {
      await this.updateYtdlp(onProgress);
    }
    status = this.getStatus();
    if (!status.ffmpeg_ready && this.isWin) {
      await this.updateFfmpeg(onProgress);
    }
    this.ensureJsRuntime();
    return this.getStatus();
  }

  /**
   * yt-dlp needs a JavaScript runtime to solve YouTube signature challenges.
   * Prefer a real Node install. Otherwise hardlink Electron as node.exe and
   * run it with ELECTRON_RUN_AS_NODE in the yt-dlp child environment.
   */
  ensureJsRuntime() {
    if (this._jsRuntimeChecked) return this._jsRuntime;

    const system = findSystemNode();
    if (system) {
      this._jsRuntime = system;
      this._jsRuntimeShim = false;
      this._jsRuntimeChecked = true;
      return system;
    }

    const dest = path.join(path.dirname(process.execPath), this.isWin ? 'node.exe' : 'node');
    const src = process.execPath;
    let ready = false;
    if (path.resolve(dest) !== path.resolve(src) && fs.existsSync(dest)) {
      try {
        ready = fs.statSync(dest).size === fs.statSync(src).size;
      } catch {
        ready = false;
      }
    }
    if (!ready && path.resolve(dest) !== path.resolve(src)) {
      try { if (fs.existsSync(dest)) fs.unlinkSync(dest); } catch {}
      try {
        fs.linkSync(src, dest);
        ready = true;
      } catch {
        try {
          fs.symlinkSync(src, dest);
          ready = true;
        } catch {
          ready = false;
        }
      }
    }

    this._jsRuntime = ready ? dest : null;
    this._jsRuntimeShim = ready;
    this._jsRuntimeChecked = true;
    if (ready) {
      const dir = path.dirname(dest);
      const current = process.env.PATH || '';
      if (!current.toLowerCase().includes(dir.toLowerCase())) {
        process.env.PATH = dir + path.delimiter + current;
      }
    }
    return this._jsRuntime;
  }

  toolEnv() {
    const env = { ...process.env };
    const runtime = this.ensureJsRuntime();
    if (this._jsRuntimeShim && runtime) {
      env.ELECTRON_RUN_AS_NODE = '1';
      const dir = path.dirname(runtime);
      env.PATH = dir + path.delimiter + (env.PATH || '');
    }
    return env;
  }

  async healYoutubeEngine() {
    this.ensureJsRuntime();
    if (this._lastHealAt && (Date.now() - this._lastHealAt) < 30 * 60 * 1000) {
      return { success: false, skipped: true };
    }
    const result = await this.updateYtdlp();
    this._lastHealAt = Date.now();
    return result;
  }

  async ensureFreshYtdlp() {
    this.ensureJsRuntime();
    const bin = this.getYtdlpBin();
    if (!this.isValidBinary(bin)) return this.updateYtdlp();

    let ageDays = 999;
    try {
      ageDays = (Date.now() - fs.statSync(bin).mtimeMs) / 86400000;
    } catch {}

    const known = this.ytdlpVer && !['Missing', 'Installed', 'Checking...'].includes(this.ytdlpVer);
    if (ageDays < 2 && known) return { success: true, skipped: true };

    const check = await this.checkYtdlpUpdate();
    if (check.has_update || (ageDays > 7 && check.error)) {
      const updated = await this.updateYtdlp();
      this._lastHealAt = Date.now();
      return updated;
    }
    return { success: true, skipped: true };
  }
}

module.exports = { EngineManager };
