/**
 * Shared YouTube resilience helpers.
 * Keeps extraction working as YouTube rotates signatures, and keeps
 * playback alive after googlevideo URLs expire.
 */

const fs = require('fs');
const path = require('path');
const { spawn, spawnSync } = require('child_process');

const USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36';
const PLAYER_CLIENTS = 'default,tv_simply,web_safari,android_vr';

let streamHeaders = {
  Referer: 'https://www.youtube.com/',
  Origin: 'https://www.youtube.com',
  'User-Agent': USER_AGENT
};

function isYoutubeUrl(url) {
  const u = String(url || '');
  return u.includes('youtube.com') || u.includes('youtu.be') || u.startsWith('ytsearch');
}

function isPermanentFailure(text) {
  return /private video|copyright|has been removed|account associated with this video|members-only|not available in your country|video unavailable|this video is unavailable/i.test(String(text || ''));
}

function isHealableFailure(text) {
  const s = String(text || '');
  if (!s.trim() || isPermanentFailure(s)) return false;
  return /signature|n challenge|nsig|unable to extract|not a bot|HTTP Error 403|Precondition|decipher|Requested format is not available|page needs to be reloaded|Sign in to confirm|timed out|Temporary failure|Got error|Connection reset|challenge solver|javascript runtime|No supported JavaScript|EJS|fragment not found|SSL|EOF|no such option|unrecognized arguments/i.test(s);
}

function streamExpiryMs(url) {
  try {
    const exp = parseInt(new URL(url).searchParams.get('expire') || '0', 10);
    if (!Number.isFinite(exp) || exp <= 0) return 0;
    return exp * 1000;
  } catch {
    return 0;
  }
}

function setStreamHeaders(headers) {
  const next = {
    Referer: 'https://www.youtube.com/',
    Origin: 'https://www.youtube.com',
    'User-Agent': USER_AGENT
  };
  if (headers && typeof headers === 'object') {
    for (const [key, value] of Object.entries(headers)) {
      if (typeof value === 'string' && value.trim()) next[key] = value;
    }
  }
  streamHeaders = next;
}

function getStreamHeaders() {
  return streamHeaders;
}

function cookieArgs(config) {
  if (!config || typeof config.get !== 'function') return [];
  try {
    const cookieFile = config.get('cookie_file');
    const cookieSource = config.get('cookie_source');
    if (cookieFile && fs.existsSync(cookieFile)) return ['--cookies', cookieFile];
    if (cookieSource && cookieSource !== 'none') return ['--cookies-from-browser', String(cookieSource)];
  } catch {}
  return [];
}

function resilientArgs(engine, config, url, options = {}) {
  const args = [
    '--no-warnings',
    '--retries', '15',
    '--fragment-retries', '15',
    '--file-access-retries', '5',
    '--socket-timeout', '30',
    '--continue',
    '--remote-components', 'ejs:github'
  ];
  if (!options.playlist) args.push('--no-playlist');
  if (options.playlist) args.push('--ignore-errors');
  if (engine && typeof engine.ensureJsRuntime === 'function') {
    engine.ensureJsRuntime();
  }
  args.push('--js-runtimes', 'node');
  if (isYoutubeUrl(url)) {
    const client = options.playerClient || PLAYER_CLIENTS;
    args.push('--extractor-args', `youtube:player_client=${client};formats=missing_pot`);
  }
  args.push(...cookieArgs(config));
  return args;
}

function runTool(bin, args, env) {
  return new Promise((resolve) => {
    let stdout = '';
    let stderr = '';
    let proc;
    try {
      proc = spawn(bin, args, { windowsHide: true, env: env || process.env });
    } catch (err) {
      resolve({ code: 1, stdout: '', stderr: String(err && err.message || err) });
      return;
    }
    proc.stdout.on('data', (d) => { stdout += d.toString('utf8'); });
    proc.stderr.on('data', (d) => { stderr += d.toString('utf8'); });
    proc.on('error', (err) => resolve({ code: 1, stdout, stderr: stderr + String(err && err.message || err) }));
    proc.on('close', (code) => resolve({ code: code == null ? 1 : code, stdout, stderr }));
  });
}

function parseStreamDump(result) {
  const lines = String(result && result.stdout || '').split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  let streamUrl = '';
  let info = null;
  for (const line of lines) {
    if (line.startsWith('http://') || line.startsWith('https://')) streamUrl = line;
    else if (line.startsWith('{')) {
      try { info = JSON.parse(line); } catch {}
    }
  }
  return {
    streamUrl,
    info,
    ok: !!(result && result.code === 0 && streamUrl),
    log: `${result && result.stderr || ''}\n${result && result.stdout || ''}`
  };
}

function cacheMarkerPath(dir, hash) {
  return path.join(dir, `stream_${hash}.ok`);
}

function findReadyCache(dir, hash) {
  const marker = cacheMarkerPath(dir, hash);
  if (!fs.existsSync(marker)) return null;
  let name = '';
  try { name = fs.readFileSync(marker, 'utf8').trim(); } catch { return null; }
  if (!name || name.includes('..') || name.includes('/') || name.includes('\\')) return null;
  const file = path.join(dir, name);
  try {
    if (fs.existsSync(file) && fs.statSync(file).size > 20000) return file;
  } catch {}
  return null;
}

function clearIncomplete(dir, hash) {
  if (findReadyCache(dir, hash)) return;
  const prefix = `stream_${hash}`;
  let names = [];
  try { names = fs.readdirSync(dir); } catch { return; }
  for (const name of names) {
    if (!name.startsWith(prefix) || name === `${prefix}.ok`) continue;
    try { fs.unlinkSync(path.join(dir, name)); } catch {}
  }
}

function markCache(dir, hash, filename) {
  fs.writeFileSync(cacheMarkerPath(dir, hash), path.basename(filename), 'utf8');
}

function largestCacheFile(dir, hash) {
  const prefix = `stream_${hash}`;
  let names = [];
  try { names = fs.readdirSync(dir); } catch { return null; }
  let best = null;
  for (const name of names) {
    if (!name.startsWith(prefix)) continue;
    if (/\.(ok|part|ytdl|tmp)$/i.test(name)) continue;
    const full = path.join(dir, name);
    try {
      const size = fs.statSync(full).size;
      if (!best || size > best.size) best = { full, size };
    } catch {}
  }
  return best && best.size > 20000 ? best.full : null;
}

function pruneCache(dir, maxBytes = 1.5 * 1024 * 1024 * 1024) {
  try {
    const files = fs.readdirSync(dir).map((name) => {
      const full = path.join(dir, name);
      try {
        const st = fs.statSync(full);
        return { full, size: st.size, mtime: st.mtimeMs };
      } catch {
        return null;
      }
    }).filter(Boolean);
    let total = files.reduce((sum, file) => sum + file.size, 0);
    if (total <= maxBytes) return;
    files.sort((a, b) => a.mtime - b.mtime);
    for (const file of files) {
      if (total <= maxBytes * 0.8) break;
      try {
        fs.unlinkSync(file.full);
        total -= file.size;
      } catch {}
    }
  } catch {}
}

function findSystemNode() {
  try {
    const cmd = process.platform === 'win32' ? 'where' : 'which';
    const res = spawnSync(cmd, ['node'], { encoding: 'utf8', windowsHide: true, timeout: 4000 });
    if (!res || res.status !== 0 || !res.stdout) return null;
    let electronSize = -1;
    let electronDir = '';
    try {
      electronSize = fs.statSync(process.execPath).size;
      electronDir = path.resolve(path.dirname(process.execPath)).toLowerCase();
    } catch {}
    const lines = res.stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    for (const line of lines) {
      const lower = line.toLowerCase();
      if (lower.endsWith('node.cmd') || lower.endsWith('node.bat')) continue;
      if (!fs.existsSync(line)) continue;
      if (electronDir && path.resolve(path.dirname(line)).toLowerCase() === electronDir) continue;
      try {
        if (electronSize > 0 && fs.statSync(line).size === electronSize) continue;
      } catch {
        continue;
      }
      return line;
    }
  } catch {}
  return null;
}

module.exports = {
  USER_AGENT,
  isYoutubeUrl,
  isPermanentFailure,
  isHealableFailure,
  streamExpiryMs,
  setStreamHeaders,
  getStreamHeaders,
  cookieArgs,
  resilientArgs,
  runTool,
  parseStreamDump,
  findReadyCache,
  clearIncomplete,
  markCache,
  largestCacheFile,
  pruneCache,
  findSystemNode
};
