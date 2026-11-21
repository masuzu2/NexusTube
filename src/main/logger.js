/**
 * NexusTube — File Logger
 * เขียน log ลง %APPDATA%\NexusTube\logs\app-YYYY-MM-DD.log (ตัด log เก่าเกิน 7 วัน)
 * ใช้สำหรับวินิจฉัยปัญหาแบบระยะไกล (เช่น เครื่องเพื่อนเปิดไม่ขึ้น)
 */

const fs = require('fs');
const path = require('path');

class Logger {
  constructor(logsDir) {
    this.logsDir = logsDir || path.join(process.env.APPDATA || os.homedir(), 'NexusTube', 'logs');
    try { fs.mkdirSync(this.logsDir, { recursive: true }); } catch {}
    this.pruneOldLogs();
  }

  logFile() {
    const d = new Date();
    const ymd = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    return path.join(this.logsDir, `app-${ymd}.log`);
  }

  write(level, msg) {
    try {
      const ts = new Date().toISOString();
      fs.appendFileSync(this.logFile(), `[${ts}] [${level}] ${msg}\n`, 'utf8');
    } catch {}
  }

  info(msg) { this.write('INFO', msg); }
  warn(msg) { this.write('WARN', msg); }
  error(msg) { this.write('ERROR', msg); }

  pruneOldLogs() {
    try {
      const cutoff = Date.now() - 7 * 24 * 60 * 60 * 1000;
      for (const f of fs.readdirSync(this.logsDir)) {
        const full = path.join(this.logsDir, f);
        try {
          if (fs.statSync(full).mtimeMs < cutoff) fs.unlinkSync(full);
        } catch {}
      }
    } catch {}
  }
}

module.exports = { Logger };
