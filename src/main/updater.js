/**
 * NexusTube — App Self-Updater (แบบเดียวกับ FLUX Launcher)
 * เช็ค version.json บน GitHub Releases → โหลด app-update.zip → แตก staging
 * → ก็อปทับตัวติดตั้ง → relaunch อัตโนมัติ ทำงานเงียบ ๆ ไม่ต้องกดอะไร
 */

const fs = require('fs');
const path = require('path');
const os = require('os');
const { spawnSync } = require('child_process');
const https = require('https');
const http = require('http');

const UPDATE_URL = 'https://github.com/masuzu2/NexusTube/releases/latest/download/';

function isNewerVersion(a, b) {
  const pa = String(a || '').split('.').map(Number);
  const pb = String(b || '').split('.').map(Number);
  for (let i = 0; i < 3; i++) {
    if ((pa[i] || 0) > (pb[i] || 0)) return true;
    if ((pa[i] || 0) < (pb[i] || 0)) return false;
  }
  return false;
}

function fetchBuffer(url, timeoutMs = 120000) {
  return new Promise((resolve, reject) => {
    const request = (targetUrl, redirects = 0) => {
      if (redirects > 5) return reject(new Error('Too many HTTP redirects'));
      const client = targetUrl.startsWith('https') ? https : http;
      const req = client.get(targetUrl, {
        headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) NexusTube/3.5.0' },
        timeout: timeoutMs
      }, (res) => {
        if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          return request(res.headers.location, redirects + 1);
        }
        if (res.statusCode !== 200) {
          return reject(new Error(`HTTP ${res.statusCode}`));
        }
        const total = parseInt(res.headers['content-length'] || '0', 10);
        const chunks = [];
        let done = 0;
        res.on('data', (c) => { done += c.length; chunks.push(c); });
        res.on('end', () => resolve({ buffer: Buffer.concat(chunks), totalBytes: total }));
      });
      req.on('error', reject);
      req.on('timeout', () => { req.destroy(); reject(new Error('Connection timed out')); });
    };
    request(url);
  });
}

class AppUpdater {
  constructor(currentVersion) {
    this.currentVersion = currentVersion;
    this.busy = false;
  }

  // โฟลเดอร์แอปจริง (installed = resources/app, dev = โฟลเดอร์ electron)
  static appDir() {
    const exeDir = path.dirname(process.execPath);
    return fs.existsSync(path.join(exeDir, 'resources', 'app'))
      ? path.join(exeDir, 'resources', 'app')
      : exeDir;
  }

  /**
   * Rollback safety: ก่อนก็อปทับ เก็บสำเนาไฟล์เดิมไว้ใน update-backup
   * ตอนเปิดแอป: ถ้าไม่มี .update-success (อัปเดตครึ่งทาง/ถูกปิดกลางคัน) → คืนไฟล์จาก backup
   * เรียกตอน startup เท่านั้น
   */
  static startupIntegrityCheck() {
    try {
      const appDir = AppUpdater.appDir();
      if (!app.isPackagedLike()) return false;
      const backupDir = path.join(path.dirname(appDir), 'update-backup');
      const marker = path.join(appDir, '.update-success');

      if (!fs.existsSync(marker) && fs.existsSync(path.join(backupDir, 'package.json'))) {
        // อัปเดตครั้งก่อนไม่สมบูรณ์ → คืนไฟล์เดิม
        const copyTree = (src, dest) => {
          fs.mkdirSync(dest, { recursive: true });
          for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
            const s = path.join(src, entry.name);
            const d = path.join(dest, entry.name);
            if (entry.isDirectory()) copyTree(s, d);
            else {
              try { if (fs.existsSync(d)) fs.unlinkSync(d); } catch {}
              fs.copyFileSync(s, d);
            }
          }
        };
        copyTree(backupDir, appDir);
        fs.writeFileSync(marker, new Date().toISOString() + ' (restored)\n', 'utf8');
        return true;
      }
    } catch {}
    return false;
  }

  static isPackagedLike() {
    const exeDir = path.dirname(process.execPath);
    return fs.existsSync(path.join(exeDir, 'resources', 'app'));
  }

  async check() {
    try {
      const { buffer } = await fetchBuffer(`${UPDATE_URL}version.json?v=${Date.now()}`, 15000);
      const info = JSON.parse(buffer.toString('utf8'));
      const latest = String(info.version || '');
      return {
        current: this.currentVersion,
        latest,
        hasUpdate: isNewerVersion(latest, this.currentVersion),
        notes: String(info.notes || '')
      };
    } catch (e) {
      return { current: this.currentVersion, latest: null, hasUpdate: false, error: String(e.message || e) };
    }
  }

  async apply(onProgress = null) {
    if (this.busy) return { success: false, error: 'Updater is busy' };
    this.busy = true;
    const report = (phase, done, total) => { if (onProgress) onProgress(phase, done, total); };
    try {
      report('downloading', 0, 0);
      const { buffer, totalBytes } = await fetchBuffer(`${UPDATE_URL}app-update.zip?v=${Date.now()}`, 300000);
      report('downloading', buffer.length, totalBytes || buffer.length);

      // เก็บ zip + แตกเป็น staging ใน temp
      const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'nexus-update-'));
      const zipPath = path.join(tmpDir, 'app-update.zip');
      const staging = path.join(tmpDir, 'staging');
      fs.writeFileSync(zipPath, buffer);

      report('extracting', 0, 0);
      let extracted = false;
      try {
        const r = spawnSync('tar', ['-xf', zipPath, '-C', staging], { windowsHide: true, timeout: 120000 });
        extracted = r.status === 0;
      } catch {}
      if (!extracted) {
        fs.mkdirSync(staging, { recursive: true });
        spawnSync('powershell.exe', ['-NoProfile', '-Command',
          `Expand-Archive -LiteralPath '${zipPath}' -DestinationPath '${staging}' -Force`],
          { windowsHide: true, timeout: 180000 });
      }

      // ก็อปทับโฟลเดอร์แอปจริง (installed = resources/app)
      const target = AppUpdater.appDir();

      report('installing', 0, 0);

      // Rollback safety: สำรองไฟล์เดิมก่อนทับทุกครั้ง
      try {
        const backupDir = path.join(path.dirname(target), 'update-backup');
        try { fs.rmSync(backupDir, { recursive: true, force: true }); } catch {}
        const backupTree = (src, dest) => {
          fs.mkdirSync(dest, { recursive: true });
          for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
            const s = path.join(src, entry.name);
            const d = path.join(dest, entry.name);
            if (entry.isDirectory()) {
              // ข้าม backup ของตัวเอง + node_modules ที่ไม่ได้อยู่ใน zip จะถูก zip ใหม่ทับอยู่แล้ว
              backupTree(s, d);
            } else {
              fs.copyFileSync(s, d);
            }
          }
        };
        backupTree(target, backupDir);
      } catch {}
      const copyTree = (src, dest) => {
        fs.mkdirSync(dest, { recursive: true });
        for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
          const s = path.join(src, entry.name);
          const d = path.join(dest, entry.name);
          if (entry.isDirectory()) copyTree(s, d);
          else {
            try { if (fs.existsSync(d)) fs.unlinkSync(d); } catch {}
            fs.copyFileSync(s, d);
          }
        }
      };
      copyTree(staging, target);

      // เก็บไว้เผื่อ relaunch
      fs.writeFileSync(path.join(target, '.update-success'), new Date().toISOString(), 'utf8');

      try { fs.rmSync(tmpDir, { recursive: true, force: true }); } catch {}
      this.busy = false;
      return { success: true, message: 'Update installed — จะรีสตาร์ทเอง' };
    } catch (e) {
      this.busy = false;
      return { success: false, error: String(e.message || e) };
    }
  }
}

module.exports = { AppUpdater, UPDATE_URL, isNewerVersion };
