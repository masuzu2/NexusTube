/**
 * NexusTube — App Self-Updater (แบบเดียวกับ FLUX Launcher)
 * เช็ค version.json บน GitHub Releases → โหลด app-update.zip → แตก staging
 * → ก็อปทับตัวติดตั้ง → relaunch อัตโนมัติ ทำงานเงียบ ๆ ไม่ต้องกดอะไร
 *
 * รองรับ 2 layout:
 *  - asar (ปกติ): target คือ `resources/` — zip ข้างในมี `app.asar` ไฟล์เดียว
 *  - loose (เดิม): target คือ `resources/app/` — zip ข้างในเป็นไฟล์แอปหลวม ๆ
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
        headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) NexusTube/3.9.0' },
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

  // ── Layout helpers ────────────────────────────────────────────────
  static resourcesDir() {
    const exeDir = path.dirname(process.execPath);
    const res = path.join(exeDir, 'resources');
    return fs.existsSync(res) ? res : exeDir;
  }

  // asar = มี resources/app.asar (ไฟล์เดียว) · loose = มี resources/app/ (โฟลเดอร์)
  static appMode() {
    return fs.existsSync(path.join(AppUpdater.resourcesDir(), 'app.asar')) ? 'asar' : 'loose';
  }

  // โฟลเดอร์ที่ zip จะถูกคัดลอกทับ
  static targetDir() {
    return AppUpdater.appMode() === 'asar' ? AppUpdater.resourcesDir() : path.join(AppUpdater.resourcesDir(), 'app');
  }

  static backupDir() {
    return path.join(path.dirname(AppUpdater.resourcesDir()), 'update-backup');
  }

  static isPackagedLike() {
    return AppUpdater.appMode() === 'asar' || fs.existsSync(path.join(AppUpdater.resourcesDir(), 'app'));
  }

  /**
   * Rollback safety: ก่อนก็อปทับ เก็บสำเนาไฟล์เดิมไว้ใน update-backup
   * ตอนเปิดแอป: ถ้าไม่มี .update-success (อัปเดตครึ่งทาง/ถูกปิดกลางคัน) → คืนไฟล์จาก backup
   * เรียกตอน startup เท่านั้น
   */
  static startupIntegrityCheck() {
    try {
      if (!AppUpdater.isPackagedLike()) return false;
      const target = AppUpdater.targetDir();
      const backup = AppUpdater.backupDir();
      const marker = path.join(target, '.update-success');

      const backupKey = AppUpdater.appMode() === 'asar' ? 'app.asar' : 'package.json';
      if (!fs.existsSync(marker) && fs.existsSync(path.join(backup, backupKey))) {
        copyTreeSync(backup, target);
        fs.writeFileSync(marker, new Date().toISOString() + ' (restored)\n', 'utf8');
        return true;
      }
    } catch {}
    return false;
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
        fs.mkdirSync(staging, { recursive: true });
        const r = spawnSync('tar', ['-xf', zipPath, '-C', staging], { windowsHide: true, timeout: 120000 });
        extracted = r.status === 0;
      } catch {}
      if (!extracted) {
        fs.mkdirSync(staging, { recursive: true });
        spawnSync('powershell.exe', ['-NoProfile', '-Command',
          `Expand-Archive -LiteralPath '${zipPath}' -DestinationPath '${staging}' -Force`],
          { windowsHide: true, timeout: 180000 });
      }

      const target = AppUpdater.targetDir();
      const backup = AppUpdater.backupDir();

      report('installing', 0, 0);

      // Rollback safety: สำรองไฟล์แอปเดิมก่อนทับทุกครั้ง
      try {
        try { fs.rmSync(backup, { recursive: true, force: true }); } catch {}
        fs.mkdirSync(backup, { recursive: true });
        if (AppUpdater.appMode() === 'asar') {
          const asar = path.join(target, 'app.asar');
          if (fs.existsSync(asar)) fs.copyFileSync(asar, path.join(backup, 'app.asar'));
        } else {
          backupTreeSync(target, backup);
        }
      } catch {}

      copyTreeSync(staging, target);

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

function backupTreeSync(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const s = path.join(src, entry.name);
    const d = path.join(dest, entry.name);
    if (entry.isDirectory()) {
      backupTreeSync(s, d);
    } else {
      fs.copyFileSync(s, d);
    }
  }
}

function copyTreeSync(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const s = path.join(src, entry.name);
    const d = path.join(dest, entry.name);
    if (entry.isDirectory()) copyTreeSync(s, d);
    else {
      try { if (fs.existsSync(d)) fs.unlinkSync(d); } catch {}
      fs.copyFileSync(s, d);
    }
  }
}

module.exports = { AppUpdater, UPDATE_URL, isNewerVersion };
