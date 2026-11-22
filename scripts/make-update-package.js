#!/usr/bin/env node
/**
 * make-update-package — ประกอบ app-update.zip สำหรับระบบ self-update ของ NexusTube
 * ใช้หลัง `npm run dist` (ต้องมี dist_electron/win-unpacked/resources/app.asar)
 *
 * ผลลัพธ์ใน update-package/:
 *   app-update.zip  — ข้างในมี app.asar ตัวเดียว (โครงแบบ asar)
 *   version.json    — { version, notes, zip_sha256 } ← updater ใช้ตรวจลายเซ็นก่อนติดตั้ง
 *
 * วิธีปล่อยอัปเดต: gh release upload vX.Y.Z update-package/app-update.zip update-package/version.json --clobber
 */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { spawnSync } = require('child_process');

const root = path.join(__dirname, '..');
const asarPath = path.join(root, 'dist_electron', 'win-unpacked', 'resources', 'app.asar');
const outDir = path.join(root, 'update-package');

if (!fs.existsSync(asarPath)) {
  console.error('ไม่พบ app.asar — รัน `npm run dist` ก่อน');
  process.exit(1);
}

const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
const version = pkg.version;

fs.mkdirSync(outDir, { recursive: true });
const zipPath = path.join(outDir, 'app-update.zip');
try { fs.unlinkSync(zipPath); } catch {}

// แพ็ก app.asar ไฟล์เดียวเป็น zip (ใช้ tar ก่อน fallback PowerShell — ทั้งคู่มีใน Windows สมัยใหม่)
const staging = path.join(outDir, '_stage');
fs.rmSync(staging, { recursive: true, force: true });
fs.mkdirSync(staging, { recursive: true });
fs.copyFileSync(asarPath, path.join(staging, 'app.asar'));

let packed = false;
{
  const r = spawnSync('tar', ['-caf', zipPath, '-C', staging, 'app.asar'], { windowsHide: true, timeout: 60000 });
  packed = r.status === 0 && fs.existsSync(zipPath) && fs.statSync(zipPath).size > 1000;
}
if (!packed) {
  const r = spawnSync('powershell.exe', ['-NoProfile', '-Command',
    `Compress-Archive -Path '${staging}\\app.asar' -DestinationPath '${zipPath}' -Force`],
    { windowsHide: true, timeout: 120000 });
  packed = r.status === 0 && fs.existsSync(zipPath);
}
fs.rmSync(staging, { recursive: true, force: true });
if (!packed) {
  console.error('แพ็ก zip ไม่สำเร็จ');
  process.exit(1);
}

const zipBuf = fs.readFileSync(zipPath);
const zipSha = crypto.createHash('sha256').update(zipBuf).digest('hex');

const versionJson = {
  version,
  notes: `NexusTube ${version} — ดาวน์โหลดอัตโนมัติผ่านระบบ self-update`,
  zip_sha256: zipSha,
  published: new Date().toISOString()
};
fs.writeFileSync(path.join(outDir, 'version.json'), JSON.stringify(versionJson, null, 2), 'utf8');

console.log(`✓ update-package/app-update.zip  (${(zipBuf.length / 1024).toFixed(0)} KB)`);
console.log(`✓ update-package/version.json    version=${version} sha256=${zipSha.slice(0, 16)}…`);
console.log('อัปขึ้น release: gh release upload vX.Y.Z update-package/app-update.zip update-package/version.json --clobber');
