/**
 * NexusTube — Download Resilience Policy (pure logic, no I/O)
 * ศูนย์กลางกติกา "ทำให้ระบบโหลดไม่มีวันพัง" — จำแนก error, ตัดสินใจ retry,
 * ถอยหลังเวลา (backoff), และห่วงโซ่ format สำรอง — แยกไว้แบบ pure เพื่อเทสต์ได้ครบ
 */

// ── จำแนกประเภท error จากข้อความของ yt-dlp ──────────────────────────
const TRANSIENT_PATTERNS = [
  'timed out', 'timeout', 'temporary failure', 'connection reset', 'connection aborted',
  'connection refused', 'network', 'unreachable', 'econnreset', 'econnaborted', 'etimedout',
  'getaddrinfo', 'dns', 'http error 5', 'http error 429', 'fragment', 'incomplete read',
  'chunked', 'premature', 'connection was closed', 'remote end closed', 'ssl', 'handshake',
  'read timed out', 'unable to download', 'giving up after', 'http 500', 'http 502', 'http 503',
  'stall'
];

const EXTRACTOR_PATTERNS = [
  'unable to extract', 'nsig', 'signature extraction', 'player response', 'watch page',
  'no video formats', 'requested format is not available', 'precondition check failed',
  'player_config', 'json decoder', 'signature', 'sabr', 'http error 403'
];

const FATAL_PATTERNS = [
  'private video', 'video unavailable', 'video has been removed', 'removed by the uploader',
  'copyright', 'not available in your country', 'geo', 'account terminated',
  'sign in to confirm you', 'age', 'members-only', 'this video is unavailable',
  'does not exist', 'invalid url', 'unsupported url', 'is not a valid url'
];

/**
 * @param {string} rawError ข้อความ error จาก stdout/stderr ของ yt-dlp
 * @returns {'transient'|'extractor'|'fatal'|'unknown'}
 */
function classifyError(rawError) {
  const text = String(rawError || '').toLowerCase();
  if (!text) return 'unknown';
  if (FATAL_PATTERNS.some((p) => text.includes(p))) return 'fatal';
  if (EXTRACTOR_PATTERNS.some((p) => text.includes(p))) return 'extractor';
  if (TRANSIENT_PATTERNS.some((p) => text.includes(p))) return 'transient';
  return 'unknown';
}

// ── นโยบาย auto-retry ────────────────────────────────────────────────
const MAX_TRANSIENT_RETRIES = 3;   // network ล่ม/ชั่วคราว → ลองใหม่ได้ 3 ครั้ง
const MAX_EXTRACTOR_RETRIES = 1;   // yt-dlp เก่า → อัปเดตเครื่องมือแล้วลองใหม่ 1 ครั้ง

/**
 * ตัดสินใจว่าควร auto-retry อีกไหม (ไม่ต้องให้ผู้ใช้กดเอง)
 * @param {'transient'|'extractor'|'fatal'|'unknown'} kind
 * @param {number} attempt จำนวนครั้งที่ลองไปแล้วของประเภทนี้ (0 = ยังไม่เคย retry)
 */
function shouldAutoRetry(kind, attempt) {
  if (kind === 'transient') return attempt < MAX_TRANSIENT_RETRIES;
  if (kind === 'extractor') return attempt < MAX_EXTRACTOR_RETRIES;
  if (kind === 'unknown') return attempt < 1; // ไม่รู้สาเหตุ → ลองใหม่ครั้งเดียวพอ
  return false; // fatal — ลองกี่ครั้งก็ไม่ผ่าน รายงานเลย
}

/** ถอยหลังเวลาแบบ exponential: 3s → 10s → 30s */
function backoffMs(attempt) {
  const ladder = [3000, 10000, 30000];
  return ladder[Math.min(Math.max(attempt, 0), ladder.length - 1)];
}

// ── ห่วงโซ่ format สำรอง ─────────────────────────────────────────────
const FORMAT_FALLBACKS = {
  mp3_320: ['m4a_best'],
  m4a_best: ['mp3_320'],
  flac: ['mp3_320', 'm4a_best'],
  mp4_1080: ['mp4_720', 'mp4_best'],
  mp4_720: ['mp4_best'],
  mp4_best: []
};

/** รูปแบบถัดไปที่ควรลองเมื่อ format ปัจจุบันใช้ไม่ได้กับคลิปนี้ (null = ไม่มีให้ลอง) */
function nextFormatFallback(format) {
  const chain = FORMAT_FALLBACKS[String(format || '')] || [];
  return chain.length ? chain[0] : null;
}

/** ย่อ format เป็นสายเสียง/วิดีโอ — ใช้เลือกพฤติกรรม post-processing ให้ตรง */
function isAudioFormat(format) {
  return ['mp3_320', 'm4a_best', 'flac'].includes(String(format || ''));
}

/** ต่ำสุดของพื้นที่ว่างในดิสก์ที่ยอมให้เริ่มงาน (bytes) */
const MIN_FREE_BYTES = 250 * 1024 * 1024;

/** งานค้างไม่มีความคืบหน้านานเท่านี้ (ms) ถือว่า stalled → ฆ่าแล้ว retry */
const STALL_MS = 90 * 1000;

/** ตรวจทุกช่วงเท่านี้ว่ามีความคืบหน้าไหม (ms) */
const STALL_CHECK_MS = 15 * 1000;

/** คิวค้างบนดิสก์เกินเท่านี้ (รายการ) ให้ตัดของเก่าทิ้ง */
const MAX_PERSISTED_TASKS = 200;

module.exports = {
  classifyError,
  shouldAutoRetry,
  backoffMs,
  nextFormatFallback,
  isAudioFormat,
  FORMAT_FALLBACKS,
  MAX_TRANSIENT_RETRIES,
  MAX_EXTRACTOR_RETRIES,
  MIN_FREE_BYTES,
  STALL_MS,
  STALL_CHECK_MS,
  MAX_PERSISTED_TASKS
};
