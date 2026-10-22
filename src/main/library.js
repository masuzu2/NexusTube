/**
 * NexusTube — Music Library, Tag Extraction, Converter & Trimmer
 * Scans local media directory, parses ID3/MP4/FLAC metadata with embedded album covers,
 * manages favorites, exports M3U8 playlists, and performs audio trimming & conversions.
 */

const fs = require('fs');
const path = require('path');
const os = require('os');
const crypto = require('crypto');
const { spawnSync, spawn } = require('child_process');
const { cleanMusicTitle, parseMusicMetadata } = require('./resolver');

const SUPPORTED_EXTS = new Set(['.mp3', '.m4a', '.flac', '.wav', '.ogg', '.opus', '.mp4', '.mkv', '.webm']);

function coverDir() {
  const base = process.env.APPDATA
    ? path.join(process.env.APPDATA, 'NexusTube', 'covers')
    : path.join(os.tmpdir(), 'nexustube_covers');
  return base;
}

function storeCover(filePath, pic) {
  if (!pic || !pic.data) return '';
  try {
    const dir = coverDir();
    fs.mkdirSync(dir, { recursive: true });
    const ext = /png/i.test(String(pic.format || '')) ? '.png' : '.jpg';
    const id = crypto.createHash('sha1').update(String(filePath)).digest('hex').slice(0, 20);
    const dest = path.join(dir, id + ext);
    let fresh = false;
    try {
      const media = fs.statSync(filePath);
      const cached = fs.statSync(dest);
      fresh = cached.size > 0 && cached.mtimeMs >= media.mtimeMs;
    } catch {}
    if (!fresh) fs.writeFileSync(dest, pic.data);
    return dest;
  } catch {
    return '';
  }
}

function sidecarCover(filePath) {
  const ext = path.extname(filePath);
  const baseNoExt = filePath.slice(0, filePath.length - ext.length);
  const sidecars = [
    `${baseNoExt}.jpg`,
    `${baseNoExt}.png`,
    `${baseNoExt}.webp`,
    path.join(path.dirname(filePath), 'cover.jpg'),
    path.join(path.dirname(filePath), 'folder.jpg'),
  ];
  for (const sc of sidecars) {
    if (fs.existsSync(sc)) return sc;
  }
  return '';
}

/**
 * Extracts metadata. Cover art is a file path, never a base64 string in the library list.
 */
async function extractMetadata(filePath, options = {}) {
  let title = path.basename(filePath, path.extname(filePath));
  let artist = "Unknown Artist";
  let album = "NexusTube Collection";
  let duration = 0;
  let coverPath = '';
  const withCover = options.covers === true;

  try {
    const mm = require('music-metadata');
    const metadata = await mm.parseFile(filePath, { duration: true, skipCovers: !withCover });
    if (metadata) {
      if (metadata.common) {
        if (metadata.common.title) title = metadata.common.title;
        if (metadata.common.artist) artist = metadata.common.artist;
        if (metadata.common.album) album = metadata.common.album;
        if (withCover && metadata.common.picture && metadata.common.picture.length > 0) {
          coverPath = storeCover(filePath, metadata.common.picture[0]);
        }
      }
      if (metadata.format && metadata.format.duration) {
        duration = metadata.format.duration;
      }
    }
  } catch {
    const parsed = parseMusicMetadata(title);
    title = parsed.title;
    artist = parsed.artist;
  }

  if (withCover && !coverPath) coverPath = sidecarCover(filePath);
  return { title, artist, album, duration, coverPath };
}

/**
 * Scans library folder and returns structured list of items
 */
async function scanLibrary(outdir, query = "", sortBy = "date", favorites = []) {
  if (!outdir || !fs.existsSync(outdir)) return [];
  const items = [];
  const favSet = new Set(Array.isArray(favorites) ? favorites.map(p => path.resolve(p)) : []);

  let entries = [];
  try {
    entries = fs.readdirSync(outdir, { withFileTypes: true });
  } catch {
    return [];
  }

  for (const entry of entries) {
    if (!entry.isFile()) continue;
    const ext = path.extname(entry.name).toLowerCase();
    if (!SUPPORTED_EXTS.has(ext)) continue;

    const fullPath = path.join(outdir, entry.name);
    let stat;
    try {
      stat = fs.statSync(fullPath);
    } catch {
      continue;
    }

    const resolvedPath = path.resolve(fullPath);
    const isFav = favSet.has(resolvedPath);
    const baseNoExt = fullPath.slice(0, fullPath.length - ext.length);
    const hasLrc = fs.existsSync(`${baseNoExt}.lrc`);

    const meta = await extractMetadata(fullPath, { covers: true });

    items.push({
      path: fullPath,
      name: entry.name,
      title: meta.title,
      artist: meta.artist,
      album: meta.album,
      duration: meta.duration || 0,
      size_bytes: stat.size,
      mtime: stat.mtimeMs,
      format: ext.replace(/^\./, ''),
      cover_path: meta.coverPath || '',
      is_favorite: isFav,
      has_lrc: hasLrc
    });
  }

  // Filter query
  let filtered = items;
  if (query && typeof query === 'string') {
    const q = query.toLowerCase().trim();
    filtered = items.filter(item =>
      (item.title && item.title.toLowerCase().includes(q)) ||
      (item.artist && item.artist.toLowerCase().includes(q)) ||
      (item.album && item.album.toLowerCase().includes(q)) ||
      (item.name && item.name.toLowerCase().includes(q))
    );
  }

  // Sort
  filtered.sort((a, b) => {
    switch (sortBy) {
      case 'title':
        return (a.title || '').localeCompare(b.title || '');
      case 'artist':
        return (a.artist || '').localeCompare(b.artist || '');
      case 'duration':
        return (b.duration || 0) - (a.duration || 0);
      case 'size':
        return (b.size_bytes || 0) - (a.size_bytes || 0);
      case 'date':
      default:
        return (b.mtime || 0) - (a.mtime || 0);
    }
  });

  return filtered;
}

/**
 * Permanently deletes audio file and associated .lrc and image sidecars
 */
function deleteFile(filePath, configManager = null) {
  if (!filePath) return false;
  let deleted = false;
  try {
    if (fs.existsSync(filePath)) {
      fs.unlinkSync(filePath);
      deleted = true;
    }
    const ext = path.extname(filePath);
    const baseNoExt = filePath.slice(0, filePath.length - ext.length);
    const sidecars = [`${baseNoExt}.lrc`, `${baseNoExt}.jpg`, `${baseNoExt}.png`, `${baseNoExt}.webp`];
    for (const sc of sidecars) {
      if (fs.existsSync(sc)) {
        try { fs.unlinkSync(sc); } catch {}
      }
    }

    if (configManager) {
      const favs = configManager.get('favorites', []);
      const resolved = path.resolve(filePath);
      const updated = favs.filter(p => path.resolve(p) !== resolved);
      if (updated.length !== favs.length) {
        configManager.set('favorites', updated);
      }
    }
  } catch (err) {
    console.error("[Library] Failed to delete file:", err);
  }
  return deleted;
}

/**
 * Exports an M3U8 playlist from track paths
 */
async function exportM3u8Playlist(playlistName = "NexusTube_Playlist", trackPaths = [], outdir = "") {
  try {
    const targetDir = outdir && fs.existsSync(outdir) ? outdir : process.cwd();
    const safeName = (playlistName || "NexusTube_Playlist").replace(/[\\/:*?"<>|]/g, '_');
    const dest = path.join(targetDir, `${safeName}.m3u8`);

    const lines = ["#EXTM3U"];
    for (const p of trackPaths) {
      if (fs.existsSync(p)) {
        let title = path.basename(p, path.extname(p));
        let artist = "NexusTube";
        let duration = -1;
        try {
          const meta = await extractMetadata(p);
          title = meta.title || title;
          artist = meta.artist || artist;
          duration = Math.round(meta.duration || -1);
        } catch {}
        lines.push(`#EXTINF:${duration},${artist} - ${title}`);
        lines.push(p);
      }
    }

    fs.writeFileSync(dest, lines.join('\n'), 'utf8');
    return { success: true, path: dest, count: trackPaths.length };
  } catch (err) {
    return { success: false, error: String(err.message || err) };
  }
}

/**
 * Trims an audio file to the specified time window
 */
function trimAudioFile(filePath, startSec, endSec, outFormat = "mp3", ffmpegBin = "ffmpeg") {
  if (!filePath || !fs.existsSync(filePath)) return false;
  try {
    const ext = `.${outFormat || 'mp3'}`.toLowerCase();
    const dir = path.dirname(filePath);
    const base = path.basename(filePath, path.extname(filePath));
    const dest = path.join(dir, `${base}_trim_${Math.round(startSec)}-${Math.round(endSec)}${ext}`);

    const args = [
      '-y',
      '-ss', String(startSec),
      '-to', String(endSec),
      '-i', filePath,
    ];

    if (ext === '.mp3') {
      args.push('-c:a', 'libmp3lame', '-b:a', '320k');
    } else if (ext === '.m4a') {
      args.push('-c:a', 'aac', '-b:a', '256k');
    } else if (ext === '.flac') {
      args.push('-c:a', 'flac');
    } else {
      args.push('-c:a', 'copy');
    }
    args.push(dest);

    const res = spawnSync(ffmpegBin, args, { windowsHide: true, timeout: 60000 });
    return res.status === 0 && fs.existsSync(dest);
  } catch (err) {
    console.error("[Library] Trim failed:", err);
    return false;
  }
}

/**
 * Converts audio file to target format with optional normalization
 */
function convertTrack(inputPath, targetFormat = "mp3", bitrate = "320k", normalize = false, ffmpegBin = "ffmpeg") {
  if (!inputPath || !fs.existsSync(inputPath)) return { success: false, error: "Input file not found." };
  try {
    const dir = path.dirname(inputPath);
    const base = path.basename(inputPath, path.extname(inputPath));
    const ext = `.${targetFormat || 'mp3'}`.toLowerCase();
    const dest = path.join(dir, `${base}_converted${ext}`);

    const args = ['-y', '-i', inputPath];
    if (normalize) {
      args.push('-af', 'loudnorm=I=-14:LRA=11:TP=-1.5');
    }

    if (ext === '.mp3') {
      args.push('-c:a', 'libmp3lame', '-b:a', bitrate || '320k');
    } else if (ext === '.m4a') {
      args.push('-c:a', 'aac', '-b:a', bitrate || '256k');
    } else if (ext === '.flac') {
      args.push('-c:a', 'flac');
    } else if (ext === '.wav') {
      args.push('-c:a', 'pcm_s16le');
    }
    args.push(dest);

    const res = spawnSync(ffmpegBin, args, { windowsHide: true, timeout: 120000 });
    if (res.status === 0 && fs.existsSync(dest)) {
      return { success: true, path: dest };
    }
    return { success: false, error: "FFmpeg conversion process exited with error." };
  } catch (err) {
    return { success: false, error: String(err.message || err) };
  }
}

module.exports = {
  extractMetadata,
  scanLibrary,
  deleteFile,
  exportM3u8Playlist,
  trimAudioFile,
  convertTrack
};
