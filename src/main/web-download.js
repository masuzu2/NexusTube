/**
 * Local download site. The desktop program stays the full app.
 * ponytail: one page on 127.0.0.1 that only queues downloads. ceiling: this machine. upgrade: a public site only if a host is meant to run yt-dlp for other people.
 */

const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { spawn } = require('child_process');

const nodeDir = path.dirname(process.execPath);
const pathText = process.env.PATH || '';
if (!pathText.toLowerCase().includes(nodeDir.toLowerCase())) {
  process.env.PATH = nodeDir + path.delimiter + pathText;
}

const { ConfigManager } = require('./config');
const { EngineManager } = require('./engine');
const { DownloadManager } = require('./downloader');
const { searchYoutube } = require('./resolver');
const { isInsideDir } = require('./download-plan');

const PORT = Number(process.env.NEXUSTUBE_WEB_PORT) || 8787;
const HOST = '127.0.0.1';
const webDir = path.join(__dirname, '..', '..', 'web');
const token = crypto.randomBytes(16).toString('hex');
const FORMATS = new Set(['mp3_320', 'm4a_best', 'flac', 'mp4_1080', 'mp4_720', 'mp4_best']);

const config = new ConfigManager();
const engine = new EngineManager(config.appdataDir);
const downloads = new DownloadManager(engine, config);
if (typeof downloads.restoreQueue === 'function') downloads.restoreQueue();

engine.ensureEngines()
  .then(() => engine.ensureFreshYtdlp())
  .catch((err) => console.warn('[web] engine check failed:', err && err.message || err));

function send(res, code, body, type) {
  const buf = Buffer.isBuffer(body) ? body : Buffer.from(String(body));
  const headers = {
    'Content-Type': type,
    'Content-Length': buf.length,
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff'
  };
  if (res.cors) Object.assign(headers, res.cors);
  res.writeHead(code, headers);
  res.end(buf);
}

function sendJson(res, code, data) {
  send(res, code, JSON.stringify(data), 'application/json; charset=utf-8');
}

function allowedHost(req) {
  const host = String(req.headers.host || '').toLowerCase();
  return host.startsWith('127.0.0.1') || host.startsWith('localhost') || host.endsWith('.trycloudflare.com');
}

function fromSite(req) {
  const origin = String(req.headers.origin || '');
  const referer = String(req.headers.referer || req.headers.referrer || '');
  return origin === 'https://masuzu2.github.io' || referer.startsWith('https://masuzu2.github.io/');
}

function corsHeaders(req) {
  if (String(req.headers.origin || '') !== 'https://masuzu2.github.io') return null;
  return {
    'Access-Control-Allow-Origin': 'https://masuzu2.github.io',
    'Vary': 'Origin',
    'Access-Control-Allow-Headers': 'content-type, x-nexus-token',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS'
  };
}

function publicMediaUrl(url) {
  let parsed;
  try { parsed = new URL(String(url || '').trim()); } catch { return false; }
  if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') return false;
  if (parsed.username || parsed.password) return false;
  const host = parsed.hostname.toLowerCase().replace(/\.$/, '');
  const names = ['youtube.com', 'youtu.be', 'spotify.com', 'music.apple.com', 'soundcloud.com'];
  return names.some((name) => host === name || host.endsWith('.' + name));
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

function callerKind(req) {
  if (req.headers['x-nexus-token'] === token) return 'local';
  if (fromSite(req)) return 'site';
  return '';
}

function publicQueue(tasks) {
  return tasks.map((task) => ({
    id: task.id,
    url: task.url,
    title: task.title,
    format: task.format,
    status: task.status,
    percent: task.percent,
    speed: task.speed,
    eta: task.eta,
    thumbnail: task.thumbnail,
    error: task.error,
    out_file: task.status === 'completed' && task.out_file ? true : null
  }));
}

function sendCompletedFile(req, res) {
  if (callerKind(req) === '') {
    send(res, 403, 'forbidden', 'text/plain; charset=utf-8');
    return;
  }
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
  const headers = {
    'Content-Type': 'application/octet-stream',
    'Content-Length': stat.size,
    'Content-Disposition': `attachment; filename="${name}"`,
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff'
  };
  if (res.cors) Object.assign(headers, res.cors);
  res.writeHead(200, headers);
  fs.createReadStream(file).pipe(res);
}

async function handleApi(req, res) {
  const kind = callerKind(req);
  if (!kind) {
    sendJson(res, 403, { error: 'เปิดหน้าเว็บจากเครื่องนี้หรือจากหน้า GitHub เท่านั้น' });
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
      const state = {
        format: FORMATS.has(config.get('format')) ? config.get('format') : 'mp3_320',
        engines: engine.getStatus(),
        public: kind === 'site'
      };
      if (kind === 'local') state.outdir = config.get('outdir');
      sendJson(res, 200, state);
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
      if (kind === 'site' && !publicMediaUrl(body.url)) {
        sendJson(res, 400, { error: 'หน้าเว็บโหลดได้จาก YouTube, Spotify, Apple Music และ SoundCloud' });
        return;
      }
      if (kind === 'site') {
        const busy = downloads.getQueueState().filter((task) => task.status === 'waiting' || task.status === 'downloading' || task.status === 'processing');
        if (busy.length >= 6) {
          sendJson(res, 429, { error: 'คิวเต็ม รอให้งานที่กำลังโหลดเสร็จก่อน' });
          return;
        }
      }
      sendJson(res, 200, downloads.addToQueue(body.url, title, format, {}, null));
      return;
    }
    if (op === 'queue') {
      const tasks = downloads.getQueueState();
      sendJson(res, 200, kind === 'site' ? publicQueue(tasks) : tasks);
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
    if (kind === 'site' && (op === 'folder' || op === 'open' || op === 'reveal')) {
      sendJson(res, 400, { error: 'บนหน้าเว็บให้กดดาวน์โหลดเมื่อไฟล์พร้อม' });
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
  res.cors = corsHeaders(req);
  if (!allowedHost(req)) {
    send(res, 403, 'local only', 'text/plain; charset=utf-8');
    return;
  }
  if (req.method === 'OPTIONS') {
    res.writeHead(204, res.cors || {});
    res.end();
    return;
  }
  let pathname = '/';
  try { pathname = new URL(req.url, `http://${HOST}`).pathname; } catch {}
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

let stopping = false;
function shutdown() {
  if (stopping) return;
  stopping = true;
  try { downloads.release(); } catch {}
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(0), 400);
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

function openBrowser(page) {
  spawn('cmd', ['/c', 'start', '', page], { windowsHide: true, detached: true, stdio: 'ignore' }).unref();
}

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
  console.log('โปรแกรมเดสก์ท็อปยังเป็นแอปเต็ม อย่าเปิดทั้งสองอย่างพร้อมกัน');
  if (process.argv.includes('--open')) openBrowser(page);
});
