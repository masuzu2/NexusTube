const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');
const {
  isDownloadUrl,
  isPlaylistDownload,
  buildStrategies,
  backoffMs,
  isStalled,
  outputIsUsable,
  pickRecoveredFile,
  isPostprocessFailure,
  publicDownloadError,
  shouldRetryLater,
  retryLaterMs,
  hasDiskSpace,
  isInsideDir,
  queueRecord,
  resumableRecords,
  STALL_MS,
  MIN_FILE_BYTES
} = require('../src/main/download-plan');

test('only plain http(s) media links can enter the download queue', () => {
  assert.equal(isDownloadUrl('https://www.youtube.com/watch?v=abc'), true);
  assert.equal(isDownloadUrl('http://example.com/audio.mp3'), true);
  assert.equal(isDownloadUrl('file:///C:/secret.mp3'), false);
  assert.equal(isDownloadUrl('javascript:alert(1)'), false);
  assert.equal(isDownloadUrl('https://user:pass@youtube.com/watch?v=abc'), false);
  assert.equal(isDownloadUrl(''), false);
  assert.equal(isDownloadUrl(null), false);
  assert.equal(isDownloadUrl(`https://example.com/${'a'.repeat(5000)}`), false);
});

test('a single video stays one file even when the link carries a playlist id', () => {
  assert.equal(isPlaylistDownload('https://www.youtube.com/watch?v=abc&list=PLxxxx'), false);
  assert.equal(isPlaylistDownload('https://youtu.be/abc?list=PLxxxx'), false);
  assert.equal(isPlaylistDownload('https://www.youtube.com/playlist?list=PLxxxx'), true);
  assert.equal(isPlaylistDownload('https://open.spotify.com/track/abc'), false);
  assert.equal(isPlaylistDownload('https://open.spotify.com/album/abc'), true);
  assert.equal(isPlaylistDownload('https://soundcloud.com/artist/sets/night'), true);
});

test('a finished audio file is kept when only the cover conversion failed', () => {
  const picked = pickRecoveredFile([
    { name: 'song.temp.mp3', size: 0 },
    { name: 'song.webp', size: 34916 },
    { name: 'song.mp3', size: 12133864 }
  ]);
  assert.equal(picked.name, 'song.mp3');
  assert.equal(isPostprocessFailure('ERROR: Postprocessing: Conversion failed!'), true);
  assert.equal(isPostprocessFailure('The page needs to be reloaded.'), false);
  assert.match(publicDownloadError('[youtube] EEocnHtllJ8: The page needs to be reloaded.'), /YouTube/);
  assert.equal(shouldRetryLater('The page needs to be reloaded.', 0), true);
  assert.equal(shouldRetryLater('The page needs to be reloaded.', 3), false);
  assert.equal(shouldRetryLater('Private video. This video is unavailable', 0), false);
  assert.equal(retryLaterMs(0), 20000);
  assert.equal(retryLaterMs(5), 120000);
});

test('download strategies end with a loose format after the client ladder', () => {
  const strategies = buildStrategies();
  assert.equal(strategies.length, 2);
  assert.equal(strategies[0].looseFormat, false);
  assert.equal(strategies[0].playerClient, null);
  assert.equal(strategies[1].looseFormat, true);
  assert.equal(strategies[1].plain, true);
});

test('retry backoff grows and then stays capped', () => {
  assert.equal(backoffMs(0), 1500);
  assert.equal(backoffMs(1), 3000);
  assert.ok(backoffMs(20) <= 15000);
});

test('a download is stalled only after the quiet threshold', () => {
  const start = 1_000_000;
  assert.equal(isStalled(start, start + STALL_MS - 1), false);
  assert.equal(isStalled(start, start + STALL_MS), true);
  assert.equal(isStalled(0, start), false);
});

test('tiny outputs are rejected and low disk stops a new attempt', () => {
  assert.equal(outputIsUsable(MIN_FILE_BYTES), true);
  assert.equal(outputIsUsable(MIN_FILE_BYTES - 1), false);
  assert.equal(hasDiskSpace({ bavail: 10, bsize: 4096 }), false);
  assert.equal(hasDiskSpace({ bavail: 1024 * 1024, bsize: 4096 }), true);
  assert.equal(hasDiskSpace(null), true);
});

test('finished files must stay inside the chosen download folder', () => {
  const dir = path.join('E:', 'Downloads', 'NexusTube');
  assert.equal(isInsideDir(path.join(dir, 'song.mp3'), dir), true);
  assert.equal(isInsideDir(path.join(dir, 'nested', 'song.mp3'), dir), true);
  assert.equal(isInsideDir(path.join('E:', 'Windows', 'song.mp3'), dir), false);
  assert.equal(isInsideDir('', dir), false);
});

test('an interrupted download is saved as waiting and resumes without the old process', () => {
  const saved = queueRecord({
    id: 'task_1',
    url: 'https://www.youtube.com/watch?v=abc',
    title: 'Song',
    format: 'mp3_320',
    status: 'downloading',
    percent: 0.4,
    out_file: 'E:\\Downloads\\NexusTube\\Song.mp3.part',
    error: 'temporary',
    proc: { pid: 99 }
  });
  assert.equal(saved.status, 'waiting');
  assert.equal(saved.percent, 0);
  assert.equal(saved.out_file, null);
  assert.equal(saved.error, null);
  assert.equal(saved.proc, undefined);

  const restored = resumableRecords([
    saved,
    { id: '', url: 'https://example.com/a', status: 'waiting' },
    { id: 'bad', url: 'file:///etc/passwd', status: 'waiting' },
    null
  ]);
  assert.equal(restored.length, 1);
  assert.equal(restored[0].id, 'task_1');
  assert.equal(restored[0].status, 'waiting');
});
