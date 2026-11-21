/**
 * Pure download planning helpers.
 * Kept free of yt-dlp and network calls so the queue policy can be tested alone.
 */

const path = require('path');
const STALL_MS = 90000;
const MIN_FILE_BYTES = 8000;
const MIN_FREE_BYTES = 200 * 1024 * 1024;
const MAX_URL_LENGTH = 4096;

function isDownloadUrl(url) {
  const raw = String(url ?? '').trim();
  if (!raw || raw.length > MAX_URL_LENGTH) return false;
  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    return false;
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return false;
  if (parsed.username || parsed.password) return false;
  return true;
}

function isPlaylistDownload(url) {
  let parsed;
  try {
    parsed = new URL(String(url || '').trim());
  } catch {
    return false;
  }
  const host = parsed.hostname.toLowerCase().replace(/^www\./, '');
  const pathName = parsed.pathname.toLowerCase();
  const videoId = parsed.searchParams.get('v');
  const isYoutube = host === 'youtu.be' || host === 'youtube.com' || host.endsWith('.youtube.com');
  if (isYoutube && (host === 'youtu.be' || videoId)) return false;
  if (isYoutube && parsed.searchParams.get('list')) return true;
  return /\/(?:playlist|album|sets)(?:\/|$)/.test(pathName);
}

function buildStrategies() {
  // ponytail: two tries, not seven clients. ceiling: default extract, then one plain loose pass. upgrade: a yt-dlp release note names one player client that fixes an error still in download.log.
  return [
    { playerClient: null, looseFormat: false, plain: false },
    { playerClient: null, looseFormat: true, plain: true }
  ];
}

function backoffMs(attemptIndex) {
  const index = Number(attemptIndex) || 0;
  return Math.min(15000, 1500 * (index + 1));
}

function isStalled(lastOutputAt, now, stallMs = STALL_MS) {
  if (!lastOutputAt || !now) return false;
  return (now - lastOutputAt) >= stallMs;
}

function outputIsUsable(size) {
  return Number(size) >= MIN_FILE_BYTES;
}

const MEDIA_EXTENSIONS = ['.mp3', '.m4a', '.flac', '.opus', '.ogg', '.wav', '.mp4', '.mkv', '.webm', '.m4v'];

function isRecoverableMedia(name) {
  const lower = String(name || '').toLowerCase();
  if (!lower || lower.endsWith('.part') || lower.endsWith('.ytdl') || lower.includes('.temp.')) return false;
  return MEDIA_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

function isPostprocessFailure(text) {
  return /postprocessing|conversion failed|unable to embed/i.test(String(text || ''));
}

function pickRecoveredFile(entries) {
  const ranked = (entries || [])
    .filter((entry) => entry && isRecoverableMedia(entry.name) && outputIsUsable(entry.size))
    .sort((a, b) => b.size - a.size);
  return ranked[0] || null;
}

function publicDownloadError(text) {
  const raw = String(text || '');
  if (/page needs to be reloaded/i.test(raw)) return 'YouTube ปฏิเสธหน้านี้ ระบบลองครบรอบแล้ว';
  if (/requested format is not available/i.test(raw)) return 'คลิปนี้ไม่มีรูปแบบที่เลือก ระบบลองครบรอบแล้ว';
  if (isPostprocessFailure(raw)) return 'โหลดมาแล้วแต่แปลงไฟล์ไม่สำเร็จ';
  const line = raw.split(/\r?\n/).map((part) => part.trim()).filter(Boolean).pop() || 'โหลดไม่สำเร็จ';
  return line.slice(0, 180);
}

function shouldRetryLater(text, rounds, maxRounds = 3) {
  const raw = String(text || '');
  if ((Number(rounds) || 0) >= maxRounds) return false;
  if (/private video|copyright|has been removed|members-only|video unavailable|this video is unavailable/i.test(raw)) return false;
  if (isPostprocessFailure(raw)) return false;
  return /page needs to be reloaded|format is not available|timed out|Temporary failure|HTTP Error 403|Connection reset|fragment not found|EJS|javascript runtime|socket|network/i.test(raw);
}

function retryLaterMs(rounds) {
  const n = Number(rounds) || 0;
  return Math.min(120000, 20000 * (n + 1));
}

function hasDiskSpace(stat, minBytes = MIN_FREE_BYTES) {
  if (!stat || !Number.isFinite(stat.bavail) || !Number.isFinite(stat.bsize)) return true;
  return stat.bavail * stat.bsize >= minBytes;
}

function isInsideDir(file, dir) {
  if (!file || !dir) return false;
  const resolved = path.resolve(file);
  const root = path.resolve(dir);
  return resolved === root || resolved.startsWith(root + path.sep);
}

function persistedStatus(status) {
  if (status === 'completed' || status === 'failed' || status === 'cancelled') return status;
  return 'waiting';
}

function queueRecord(task) {
  const status = persistedStatus(task?.status);
  return {
    id: task?.id || '',
    url: task?.url || '',
    title: task?.title || '',
    format: task?.format || 'mp3_320',
    status,
    percent: status === 'completed' ? 1 : 0,
    speed: status === 'completed' ? 'Done' : '0 KiB/s',
    eta: status === 'completed' ? '00:00' : '--:--',
    thumbnail: task?.thumbnail || '',
    out_file: status === 'completed' ? (task?.out_file || null) : null,
    error: status === 'failed' ? (task?.error || null) : null,
    options: task?.options || {},
    metadata: task?.metadata || {},
    cancelled: status === 'cancelled',
    healed: false,
    rounds: Number(task?.rounds) || 0
  };
}

function resumableRecords(records) {
  if (!Array.isArray(records)) return [];
  return records
    .filter((record) => record && isDownloadUrl(record.url) && record.id)
    .map((record) => queueRecord(record));
}

module.exports = {
  STALL_MS,
  MIN_FILE_BYTES,
  MIN_FREE_BYTES,
  isDownloadUrl,
  isPlaylistDownload,
  buildStrategies,
  backoffMs,
  isStalled,
  outputIsUsable,
  isRecoverableMedia,
  isPostprocessFailure,
  pickRecoveredFile,
  publicDownloadError,
  shouldRetryLater,
  retryLaterMs,
  hasDiskSpace,
  isInsideDir,
  queueRecord,
  resumableRecords
};
