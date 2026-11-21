/**
 * NexusTube — Local download site (Local-first).
 * หน้าเว็บโหลดเพลงรันอยู่บนเครื่องผู้ใช้เท่านั้น (127.0.0.1) — ไม่มี tunnel แล้ว
 * - โหมดโมดูล: startWebServer({config, engine, downloads}) ถูกเรียกจาก index.js
 *   เพื่อใช้ DownloadManager ตัวเดียวกับแอป (ไม่ตีกันเอง)
 * - โหมด standalone: `node src/main/web-download.js` หรือ `NexusTube.exe --web-server`
 */

const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { spawn } = require('child_process');

const { ConfigManager } = require('./config');
const { EngineManager } = require('./engine');
const { DownloadManager } = require('./downloader');
const { searchYoutube } = require('./resolver');
const { isInsideDir } = require('./download-plan');

const VERSION = require('./config').VERSION || '3.9.0';

const PORT = Number(process.env.NEXUSTUBE_WEB_PORT) || 8787;
const HOST = '127.0.0.1';
const webDir = path.join(__dirname, '..', '..', 'web');
const FORMATS = new Set(['mp3_320', 'm4a_best', 'flac', 'mp4_1080', 'mp4_720', 'mp4_best']);

function send(res, code, body, type, extraHeaders) {
  const buf = Buffer.isBuffer(body) ? body : Buffer.from(String(body));
  const headers = Object.assign({
    'Content-Type': type,
    'Content-Length': buf.length,
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff'
  }, extraHeaders || {});
  res.writeHead(code, headers);
  res.end(buf);
}

function sendJson(res, code, data, extraHeaders) {
  send(res, code, JSON.stringify(data), 'application/json; charset=utf-8', extraHeaders);
}

function allowedHost(req) {
  const host = String(req.headers.host || '').toLowerCase();
  return host.startsWith('127.0.0.1') || host.startsWith('localhost');
}

async function readBody(req) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > 65536) {
      const err = new Error('large');
      err.status = 413;
      throw err;
    }
    chunks.push(chunk);
  }
  if (!chunks.length) return {};
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}

function startWebServer(options = {}) {
  const config = options.config || new ConfigManager();
  const engine = options.engine || new EngineManager(config.appdataDir);
  const downloads = options.downloads || new DownloadManager(engine, config);
  const token = options.token || crypto.randomBytes(16).toString('hex');
  if (typeof downloads.restoreQueue === 'function') downloads.restoreQueue();
  if (typeof engine.ensureEngines === 'function' && !options.engine) {
    engine.ensureEngines()
      .then(() => { if (typeof engine.ensureFreshYtdlp === 'function') return engine.ensureFreshYtdlp(); })
      .catch((err) => console.warn('[web] engine check failed:', err && err.message || err));
  }

  function sendCompletedFile(req, res) {
    let id = '';
    try { id = new URL(req.url, 'http://127.0.0.1').searchParams.get('id') || ''; } catch {}
    if (!/^task_[\w-]+$/.test(id)) {
      send(res, 404, 'not found', 'text/plain; charset=utf-8');
      return;
    }
    const task = downloads.getQueueState().find((item) => item.id === id);
    const file = task && task.out_file;
    const dir = config.get('outdir');
    if (!file || task.status !== 'completed' || !isInsideDir(file, dir) || !fs.existsSync(file)) {
      send(res, 404, 'not found', 'text/plain; charset=utf-8');
      return;
    }
    const stat = fs.statSync(file);
    const name = path.basename(file).replace(/[\r\n"]/g, '');
    res.writeHead(200, {
      'Content-Type': 'application/octet-stream',
      'Content-Length': stat.size,
      'Content-Disposition': `attachment; filename="${name}"`,
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff'
    });
    fs.createReadStream(file).pipe(res);
  }

  async function handleApi(req, res) {
    if (req.headers['x-nexus-token'] !== token) {
      sendJson(res, 403, { error: 'เปิดหน้าเว็บจากเครื่องนี้เท่านั้น' });
      return;
    }
    let body;
    try {
      body = await readBody(req);
    } catch (err) {
      sendJson(res, err.status || 400, { error: 'รูปแบบไม่ถูกต้อง' });
      return;
    }
    const op = String(body.op || '');
    try {
      if (op === 'state') {
        sendJson(res, 200, {
          format: FORMATS.has(config.get('format')) ? config.get('format') : 'mp3_320',
          engines: engine.getStatus(),
          outdir: config.get('outdir')
        });
        return;
      }
      if (op === 'search') {
        const query = String(body.query || '').trim().slice(0, 200);
        const items = query ? await searchYoutube(query, engine) : [];
        sendJson(res, 200, items.slice(0, 12).map((item) => ({
          title: item.title || '',
          channel: item.channel || '',
          url: item.url || '',
          thumbnail: /^https?:\/\//i.test(item.thumbnail || '') ? item.thumbnail : '',
          duration: Number(item.duration) || 0
        })));
        return;
      }
      if (op === 'add') {
        const format = FORMATS.has(body.format) ? body.format : 'mp3_320';
        const title = String(body.title || '').slice(0, 300);
        sendJson(res, 200, downloads.addToQueue(body.url, title, format, {}, null));
        return;
      }
      if (op === 'queue') {
        sendJson(res, 200, downloads.getQueueState());
        return;
      }
      if (op === 'cancel') {
        sendJson(res, 200, { ok: !!downloads.cancelTask(String(body.id || '')) });
        return;
      }
      if (op === 'retry') {
        sendJson(res, 200, { ok: !!downloads.retryTask(String(body.id || '')) });
        return;
      }
      if (op === 'clear') {
        sendJson(res, 200, { ok: !!downloads.clearFinished() });
        return;
      }
      if (op === 'folder') {
        const next = String(body.path || '').trim();
        if (!next || next.includes('\0') || !path.isAbsolute(next)) {
          sendJson(res, 400, { error: 'ใส่ที่อยู่โฟลเดอร์แบบเต็ม เช่น C:\\Downloads\\NexusTube' });
          return;
        }
        fs.mkdirSync(next, { recursive: true });
        if (!fs.statSync(next).isDirectory()) {
          sendJson(res, 400, { error: 'ไม่ใช่โฟลเดอร์' });
          return;
        }
        config.set('outdir', path.resolve(next));
        sendJson(res, 200, { outdir: config.get('outdir') });
        return;
      }
      if (op === 'open') {
        const dir = config.get('outdir');
        if (dir && fs.existsSync(dir)) {
          spawn('explorer', [dir], { windowsHide: true, detached: true, stdio: 'ignore' }).unref();
          sendJson(res, 200, { ok: true });
          return;
        }
        sendJson(res, 200, { ok: false });
        return;
      }
      if (op === 'reveal') {
        const file = String(body.path || '');
        const dir = config.get('outdir');
        if (file && isInsideDir(file, dir) && fs.existsSync(file)) {
          spawn('explorer', [`/select,${file}`], { windowsHide: true, detached: true, stdio: 'ignore' }).unref();
          sendJson(res, 200, { ok: true });
          return;
        }
        sendJson(res, 200, { ok: false });
        return;
      }
      sendJson(res, 404, { error: 'ไม่มีคำสั่งนี้' });
    } catch (err) {
      console.warn('[web]', op, err && err.message || err);
      sendJson(res, 500, { error: 'ทำไม่สำเร็จ' });
    }
  }

  const pages = {
    '/': 'download.html',
    '/download.js': 'download.js'
  };

  function servePage(res, name) {
    const full = path.join(webDir, name);
    fs.readFile(full, 'utf8', (err, text) => {
      if (err) {
        send(res, 404, 'not found', 'text/plain; charset=utf-8');
        return;
      }
      const type = name.endsWith('.js') ? 'text/javascript; charset=utf-8' : 'text/html; charset=utf-8';
      send(res, 200, text.replaceAll('__NEXUS_TOKEN__', token), type);
    });
  }

  const server = http.createServer((req, res) => {
    if (!allowedHost(req)) {
      send(res, 403, 'local only', 'text/plain; charset=utf-8');
      return;
    }
    let pathname = '/';
    try { pathname = new URL(req.url, `http://${HOST}`).pathname; } catch {}
    if (req.method === 'GET' && pathname === '/health') {
      let queue = { total: 0, active: 0, failed: 0 };
      try {
        const tasks = downloads.getQueueState();
        queue.total = tasks.length;
        queue.active = tasks.filter((t) => ['waiting', 'downloading', 'processing'].includes(t.status)).length;
        queue.failed = tasks.filter((t) => t.status === 'failed').length;
      } catch {}
      sendJson(res, 200, { ok: true, name: 'NexusTube', version: VERSION, engines: engine.getStatus(), queue }, {
        'Access-Control-Allow-Origin': '*'
      });
      return;
    }
    if (req.method === 'GET' && pathname === '/file') {
      sendCompletedFile(req, res);
      return;
    }
    if (req.method === 'POST' && pathname === '/api') {
      handleApi(req, res);
      return;
    }
    if (req.method === 'GET' && pages[pathname]) {
      servePage(res, pages[pathname]);
      return;
    }
    send(res, 404, 'not found', 'text/plain; charset=utf-8');
  });

  server.webContext = { config, engine, downloads };
  return server;
}

function openBrowser(page) {
  spawn('cmd', ['/c', 'start', '', page], { windowsHide: true, detached: true, stdio: 'ignore' }).unref();
}

module.exports = { startWebServer, PORT, HOST, openBrowser };

if (require.main === module) {
  const nodeDir = path.dirname(process.execPath);
  const pathText = process.env.PATH || '';
  if (!pathText.toLowerCase().includes(nodeDir.toLowerCase())) {
    process.env.PATH = nodeDir + path.delimiter + pathText;
  }

  const config = new ConfigManager();
  const engine = new EngineManager(config.appdataDir);
  const downloads = new DownloadManager(engine, config);
  const server = startWebServer({ config, engine, downloads });

  let stopping = false;
  function shutdown() {
    if (stopping) return;
    stopping = true;
    try { if (typeof downloads.release === 'function') downloads.release(); } catch {}
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(0), 400);
  }
  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);

  server.on('error', (err) => {
    if (err && err.code === 'EADDRINUSE') {
      const page = `http://${HOST}:${PORT}`;
      console.log(`เว็บโหลดเปิดอยู่แล้วที่ ${page}`);
      if (process.argv.includes('--open')) openBrowser(page);
      process.exit(0);
    }
    console.error(err);
    process.exit(1);
  });

  server.listen(PORT, HOST, () => {
    const page = `http://${HOST}:${PORT}`;
    console.log(`เว็บใช้โหลดอย่างเดียว: ${page}`);
    console.log('โปรแกรมเดสก์ท็อปยังเป็นแอปเต็ม');
    if (process.argv.includes('--open')) openBrowser(page);
  });
}
