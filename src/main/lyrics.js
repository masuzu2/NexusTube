/**
 * NexusTube — Synchronized Lyrics (LRC) & LRCLIB Engine
 * Handles LRC parsing, formatting, LRCLIB API queries, local sidecar storage, and tag extraction.
 */

const fs = require('fs');
const path = require('path');
const https = require('https');
const http = require('http');
const { cleanMusicTitle } = require('./resolver');

const USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) NexusTube/3.4.0";

function fetchJson(url, headers = {}, timeout = 6000) {
  return new Promise((resolve) => {
    try {
      const u = new URL(url);
      const client = u.protocol === 'https:' ? https : http;
      const req = client.get(url, {
        headers: { 'User-Agent': USER_AGENT, ...headers },
        timeout
      }, (res) => {
        if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          return resolve(fetchJson(res.headers.location, headers, timeout));
        }
        if (res.statusCode !== 200) return resolve(null);
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => {
          try {
            resolve(JSON.parse(data));
          } catch {
            resolve(null);
          }
        });
      });
      req.on('error', () => resolve(null));
      req.on('timeout', () => { req.destroy(); resolve(null); });
    } catch {
      resolve(null);
    }
  });
}

/**
 * Parses LRC formatted text into structured array: [{ time: seconds, text: string }]
 */
function parseLrc(lrcText) {
  if (!lrcText || typeof lrcText !== 'string') return [];
  const lines = lrcText.split(/\r?\n/);
  const result = [];
  const timeRegex = /\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\]/g;

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;

    timeRegex.lastIndex = 0;
    const timestamps = [];
    let match;
    let lastIndex = 0;

    while ((match = timeRegex.exec(trimmed)) !== null) {
      const mins = parseInt(match[1], 10);
      const secs = parseInt(match[2], 10);
      let frac = 0;
      if (match[3]) {
        frac = match[3].length === 3 ? parseInt(match[3], 10) / 1000 : parseInt(match[3], 10) / 100;
      }
      timestamps.push(mins * 60 + secs + frac);
      lastIndex = timeRegex.lastIndex;
    }

    if (timestamps.length > 0) {
      const lyricText = trimmed.slice(lastIndex).trim();
      for (const t of timestamps) {
        result.push({ time: Math.round(t * 100) / 100, text: lyricText });
      }
    }
  }

  result.sort((a, b) => a.time - b.time);
  return result;
}

/**
 * Formats structured lyrics list back into LRC string
 */
function formatLrc(lyricsList) {
  if (!Array.isArray(lyricsList)) return "";
  return lyricsList.map(item => {
    const totalSecs = Math.max(0, item.time || 0);
    const mins = Math.floor(totalSecs / 60);
    const secs = Math.floor(totalSecs % 60);
    const hundredths = Math.floor((totalSecs % 1) * 100);
    const mStr = String(mins).padStart(2, '0');
    const sStr = String(secs).padStart(2, '0');
    const hStr = String(hundredths).padStart(2, '0');
    return `[${mStr}:${sStr}.${hStr}] ${item.text || ''}`;
  }).join('\n');
}

/**
 * Finds the index of currently active lyric line for playback position
 */
function getActiveLyricIndex(lyricsList, currentSeconds) {
  if (!Array.isArray(lyricsList) || lyricsList.length === 0) return -1;
  const pos = Number(currentSeconds) || 0;
  let idx = -1;
  for (let i = 0; i < lyricsList.length; i++) {
    if (lyricsList[i].time <= pos) {
      idx = i;
    } else {
      break;
    }
  }
  return idx;
}

/**
 * Fetches lyrics from local sidecar .lrc, embedded audio tags, or LRCLIB
 */
async function fetchLyrics(title, artist = "", duration = 0, filePath = null) {
  const result = { synced: [], synced_raw: "", plain: "", source: "none" };

  // 1. Check local .lrc sidecar file
  if (filePath && typeof filePath === 'string') {
    try {
      const ext = path.extname(filePath);
      const baseNoExt = filePath.slice(0, filePath.length - ext.length);
      const candidates = [`${baseNoExt}.lrc`, `${filePath}.lrc`];

      for (const candidate of candidates) {
        if (fs.existsSync(candidate)) {
          const raw = fs.readFileSync(candidate, 'utf8');
          const parsed = parseLrc(raw);
          if (parsed && parsed.length > 0) {
            result.synced = parsed;
            result.synced_raw = raw;
            result.plain = parsed.map(p => p.text).filter(Boolean).join('\n');
            result.source = "local_lrc";
            return result;
          }
        }
      }
    } catch {}
  }

  // 2. Check embedded audio tags (using music-metadata if installed)
  if (filePath && fs.existsSync(filePath)) {
    try {
      const mm = require('music-metadata');
      const meta = await mm.parseFile(filePath, { duration: false });
      let embLyrics = "";

      if (meta && meta.common) {
        if (meta.common.lyrics && meta.common.lyrics.length > 0) {
          embLyrics = meta.common.lyrics.map(l => (typeof l === 'string' ? l : l.text)).join('\n');
        }
      }

      if (embLyrics) {
        const parsed = parseLrc(embLyrics);
        result.synced = parsed;
        result.synced_raw = parsed.length > 0 ? embLyrics : "";
        result.plain = parsed.length > 0 ? parsed.map(p => p.text).filter(Boolean).join('\n') : embLyrics;
        result.source = "embedded";
        if (parsed.length > 0) return result;
      }
    } catch {}
  }

  // 3. Query LRCLIB API
  let cleanT = cleanMusicTitle(title);
  let cleanA = cleanMusicTitle(artist);

  if (!cleanA && cleanT.includes(" - ")) {
    const parts = cleanT.split(" - ");
    cleanA = cleanMusicTitle(parts[0]);
    cleanT = cleanMusicTitle(parts.slice(1).join(" - "));
  }

  if (!cleanT) return result;

  const urlBase = "https://lrclib.net/api";

  try {
    // Attempt 1: Exact lookup
    const params = new URLSearchParams();
    params.set('track_name', cleanT);
    if (cleanA) params.set('artist_name', cleanA);
    if (duration && duration > 0) params.set('duration', String(Math.round(duration)));

    const exactData = await fetchJson(`${urlBase}/get?${params.toString()}`);
    if (exactData) {
      const syncedRaw = exactData.syncedLyrics || "";
      const plain = exactData.plainLyrics || "";
      if (syncedRaw) {
        const parsed = parseLrc(syncedRaw);
        if (parsed.length > 0) {
          result.synced = parsed;
          result.synced_raw = syncedRaw;
          result.plain = plain || parsed.map(p => p.text).filter(Boolean).join('\n');
          result.source = "lrclib_exact";
          return result;
        }
      } else if (plain) {
        result.plain = plain;
        result.source = "lrclib_plain";
        return result;
      }
    }

    // Attempt 2: Search query
    const qStr = cleanA ? `${cleanA} ${cleanT}`.trim() : cleanT;
    const searchData = await fetchJson(`${urlBase}/search?q=${encodeURIComponent(qStr)}`);
    if (Array.isArray(searchData) && searchData.length > 0) {
      const best = searchData.find(item => item && item.syncedLyrics) || searchData[0];
      if (best) {
        const syncedRaw = best.syncedLyrics || "";
        const plain = best.plainLyrics || "";
        if (syncedRaw) {
          const parsed = parseLrc(syncedRaw);
          result.synced = parsed;
          result.synced_raw = syncedRaw;
          result.plain = plain || parsed.map(p => p.text).filter(Boolean).join('\n');
          result.source = "lrclib_search";
          return result;
        } else if (plain) {
          result.plain = plain;
          result.source = "lrclib_plain";
          return result;
        }
      }
    }
  } catch {}

  return result;
}

/**
 * Searches LRCLIB for lyrics matching query
 */
async function searchLyrics(title, artist = "") {
  let cleanT = cleanMusicTitle(title);
  let cleanA = cleanMusicTitle(artist);
  if (!cleanA && cleanT.includes(" - ")) {
    const parts = cleanT.split(" - ");
    cleanA = cleanMusicTitle(parts[0]);
    cleanT = cleanMusicTitle(parts.slice(1).join(" - "));
  }
  const qStr = cleanA ? `${cleanA} ${cleanT}`.trim() : cleanT;
  if (!qStr) return [];

  const url = `https://lrclib.net/api/search?q=${encodeURIComponent(qStr)}`;
  const data = await fetchJson(url);
  if (Array.isArray(data)) {
    return data.map(item => ({
      id: item.id,
      title: item.trackName || item.name,
      artist: item.artistName,
      album: item.albumName,
      duration: item.duration,
      syncedLyrics: item.syncedLyrics,
      plainLyrics: item.plainLyrics,
      has_synced: Boolean(item.syncedLyrics)
    }));
  }
  return [];
}

/**
 * Saves plain LRC string next to target audio file
 */
function saveLrc(filePath, content) {
  if (!filePath || !content) return false;
  try {
    const ext = path.extname(filePath);
    const baseNoExt = filePath.slice(0, filePath.length - ext.length);
    const lrcPath = `${baseNoExt}.lrc`;
    fs.writeFileSync(lrcPath, content, 'utf8');
    return true;
  } catch (err) {
    console.error("[Lyrics] Failed to save LRC:", err);
    return false;
  }
}

module.exports = {
  parseLrc,
  formatLrc,
  getActiveLyricIndex,
  fetchLyrics,
  searchLyrics,
  saveLrc
};
