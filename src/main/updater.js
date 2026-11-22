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
const crypto = require('crypto');
const { spawnSync } = require('child_process');
const https = require('https');
const http = require('http');

const UPDATE_URL = 'https://github.com/masuzu2/NexusTube/releases/latest/download/';
const BOOT_COUNTER_LIMIT = 3;      // บูตหลังอัปเดตแล้วล้ม ≥ 3 ครั้ง = อัปเดตเสีย → rollback
const STABLE_AFTER_MS = 90 * 1000; // รันเนียนครบเท่านี้ = ถือว่าอัปเดตใช้ได้

function sha256Hex(buf) {
  return crypto.createHash('sha256').update(buf).digest('hex');
}

/** ตรวจ hash ของ zip กับที่ version.json ประกาศ (ปลายเปิด: ไม่มี hash → ผ่านได้) */
function verifyZipHash(buffer, expectedHex) {
  if (!expectedHex) return true;
  return sha256Hex(buffer).toLowerCase() === String(expectedHex).toLowerCase();
}

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

/** ดาวน์โหลดแบบมี retry (กัน CDN cache/เน็ตสะดุดช่วงสั้น ๆ) */
async function fetchBufferRetry(url, timeoutMs = 120000, attempts = 3) {
  let lastErr;
  for (let i = 0; i < attempts; i++) {
    try {
      return await fetchBuffer(url, timeoutMs);
    } catch (err) {
      lastErr = err;
      await new Promise((r) => setTimeout(r, 2000 * (i + 1)));
    }
  }
  throw lastErr;
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

  /**
   * จับอัปเดตเสีย: นับจำนวนบูตหลังอัปเดต — ถ้าบูตแล้วล้มซ้ำ ≥ 3 ครั้ง
   * (แอปพังก่อนได้โอกาส mark stable) → คืนเวอร์ชันเดิมจาก backup อัตโนมัติ
   * เรียกตอน startup ต่อจาก startupIntegrityCheck()
   */
  static recordBoot() {
    try {
      if (!AppUpdater.isPackagedLike()) return 'clean';
      const target = AppUpdater.targetDir();
      const counterPath = path.join(target, '.update-bootcount');
      const marker = path.join(target, '.update-success');
      if (!fs.existsSync(counterPath) || !fs.existsSync(marker)) return 'clean';

      const count = parseInt(fs.readFileSync(counterPath, 'utf8').trim(), 10) || 0;
      if (count + 1 >= BOOT_COUNTER_LIMIT) {
        const backup = AppUpdater.backupDir();
        const backupKey = AppUpdater.appMode() === 'asar' ? 'app.asar' : 'package.json';
        if (fs.existsSync(path.join(backup, backupKey))) {
          copyTreeSync(backup, target);
          try { fs.unlinkSync(counterPath); } catch {}
          fs.writeFileSync(marker, new Date().toISOString() + ' (rollback — bad update)\n', 'utf8');
          return 'rolled-back';
        }
        return 'no-backup';
      }
      fs.writeFileSync(counterPath, String(count + 1), 'utf8');
      return 'counting';
    } catch {
      return 'clean';
    }
  }

  /**
   * แอปรันเนียนต่อเนื่องหลังอัปเดต → ยืนยันว่าอัปเดตดี (เคลียร์ boot counter + backup เก่า)
   * เรียกด้วย setTimeout ~90 วิ หลัง startup ในโหมด packaged
   */
  static markStable() {
    try {
      if (!AppUpdater.isPackagedLike()) return false;
      const target = AppUpdater.targetDir();
      if (!fs.existsSync(path.join(target, '.update-success'))) return false;
      try { fs.unlinkSync(path.join(target, '.update-bootcount')); } catch {}
      try { fs.rmSync(AppUpdater.backupDir(), { recursive: true, force: true }); } catch {}
      return true;
    } catch {}
    return false;
  }

  async check() {
    try {
      const { buffer } = await fetchBufferRetry(`${UPDATE_URL}version.json?v=${Date.now()}`, 15000, 2);
      const info = JSON.parse(buffer.toString('utf8'));
      const latest = String(info.version || '');
      this._expectedHash = String(info.zip_sha256 || '');
      this._latestVersion = latest;
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
      const { buffer, totalBytes } = await fetchBufferRetry(`${UPDATE_URL}app-update.zip?v=${Date.now()}`, 300000);
      report('downloading', buffer.length, totalBytes || buffer.length);

      // กันพังชั้นแรกของ updater: ตรวจ SHA-256 ก่อนแตะไฟล์แอปเลย (ถ้า version.json ประกาศ hash มา)
      const expected = this._expectedHash;
      if (!verifyZipHash(buffer, expected)) {
        this.busy = false;
        return { success: false, error: 'ไฟล์อัปเดตไม่ตรงลายเซ็น SHA-256 — ข้ามรอบนี้เพื่อความปลอดภัย จะลองใหม่อัตโนมัติ' };
      }

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

      // เก็บไว้เผื่อ relaunch + เตรียมนับบูตเพื่อจับอัปเดตเสีย
      fs.writeFileSync(path.join(target, '.update-success'), new Date().toISOString(), 'utf8');
      try { fs.writeFileSync(path.join(target, '.update-bootcount'), '0', 'utf8'); } catch {}

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

module.exports = { AppUpdater, UPDATE_URL, isNewerVersion, sha256Hex, verifyZipHash };
