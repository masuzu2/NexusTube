/**
 * NexusTube Electron Edition — Automated Verification & Contract Test Suite
 * Tests 100% of bridge contracts, resolvers, lyrics, library scanner, player, downloader & engines.
 */

const { test, describe, before, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const os = require('os');

const { ConfigManager, VERSION, DEFAULT_CONFIG, EQ_PRESETS, ACCENT_PALETTE, LOCALES } = require('../src/main/config');
const { EngineManager } = require('../src/main/engine');
const { cleanMusicTitle, parseMusicMetadata, detectPlatformUrl } = require('../src/main/resolver');
const { parseLrc, formatLrc, getActiveLyricIndex, saveLrc } = require('../src/main/lyrics');
const { scanLibrary, deleteFile, exportM3u8Playlist, extractMetadata } = require('../src/main/library');
const { PlayerManager } = require('../src/main/player');
const { DownloadManager } = require('../src/main/downloader');
const { NexusBridgeAPI } = require('../src/main/bridge');

describe('1. Web Assets & IPC Contract Parity', () => {
  const repoRoot = path.resolve(__dirname, '..');
  const webDir = path.join(repoRoot, 'web');

  test('Core web assets exist and have valid sizes', () => {
    const assets = [
      { file: 'index.html', minSize: 10 * 1024 },
      { file: 'app.js', minSize: 50 * 1024 },
      { file: 'styles.css', minSize: 10 * 1024 },
      { file: 'tailwind.js', minSize: 100 * 1024 }
    ];

    for (const a of assets) {
      const full = path.join(webDir, a.file);
      assert.ok(fs.existsSync(full), `Asset ${a.file} must exist`);
      const sz = fs.statSync(full).size;
      assert.ok(sz >= a.minSize, `Asset ${a.file} (${sz} bytes) must exceed ${a.minSize} bytes`);
    }
  });

  test('All window.pywebview.api calls in web/app.js are implemented on NexusBridgeAPI', () => {
    const appJsContent = fs.readFileSync(path.join(webDir, 'app.js'), 'utf8');
    const calledMethods = new Set();
    const regex = /window\.pywebview\.api\.([a-zA-Z0-9_]+)/g;
    let match;
    while ((match = regex.exec(appJsContent)) !== null) {
      calledMethods.add(match[1]);
    }

    assert.ok(calledMethods.size >= 40, `Expected at least 40 bridge API methods, found ${calledMethods.size}`);

    const config = new ConfigManager();
    const engine = new EngineManager(config.appdataDir);
    const downloader = new DownloadManager(engine, config);
    const player = new PlayerManager(config);
    const bridge = new NexusBridgeAPI({
      mainWindow: null,
      configManager: config,
      engineManager: engine,
      downloadManager: downloader,
      playerManager: player,
      trayManager: null
    });

    const missing = [];
    for (const m of calledMethods) {
      if (typeof bridge[m] !== 'function') {
        missing.push(m);
      }
    }

    assert.deepEqual(missing, [], `Missing bridge methods: ${missing.join(', ')}`);
  });
});

describe('2. Configuration & State Management', () => {
  let config;
  let tmpConfigDir;

  before(() => {
    tmpConfigDir = fs.mkdtempSync(path.join(os.tmpdir(), 'nexus_cfg_test_'));
    config = new ConfigManager();
    config.appdataDir = tmpConfigDir;
    config.configPath = path.join(tmpConfigDir, 'config.json');
    config.saveConfig({ ...DEFAULT_CONFIG });
  });

  after(() => {
    try { fs.rmSync(tmpConfigDir, { recursive: true, force: true }); } catch {}
  });

  test('Loads default configuration correctly', () => {
    assert.equal(config.get('lang'), 'th');
    assert.equal(config.get('format'), 'mp3_320');
    assert.equal(config.get('accent'), '#22C55E');
    assert.equal(typeof config.get('eq_bands'), 'object');
  });

  test('Updates and persists configuration', () => {
    config.saveConfig({ lang: 'en', accent: '#6366F1' });
    assert.equal(config.get('lang'), 'en');
    assert.equal(config.get('accent'), '#6366F1');

    // Reload from disk
    const reloaded = new ConfigManager();
    reloaded.configPath = config.configPath;
    reloaded.loadConfig();
    assert.equal(reloaded.get('lang'), 'en');
    assert.equal(reloaded.get('accent'), '#6366F1');
  });
});

describe('3. Multi-Platform Resolver & Sanitizer', () => {
  test('cleanMusicTitle strips video tags and remaster noise', () => {
    assert.equal(cleanMusicTitle("Artist - Song [Official Music Video]"), "Artist - Song");
    assert.equal(cleanMusicTitle("Song Title (Official Video HD)"), "Song Title");
    assert.equal(cleanMusicTitle("Track (Lyrics / Lyric Video)"), "Track");
    assert.equal(cleanMusicTitle("Classic Hit [Remastered 2024]"), "Classic Hit");
    assert.equal(cleanMusicTitle("Awesome Track [4K 60fps]"), "Awesome Track");
    assert.equal(cleanMusicTitle("Song Name | Official Audio"), "Song Name");
  });

  test('parseMusicMetadata extracts artist, title and track number', () => {
    const r1 = parseMusicMetadata("Artist Name - Track Title");
    assert.equal(r1.artist, "Artist Name");
    assert.equal(r1.title, "Track Title");

    const r2 = parseMusicMetadata("Track Title by Artist Name");
    assert.equal(r2.artist, "Artist Name");
    assert.equal(r2.title, "Track Title");

    const r3 = parseMusicMetadata("05 - Famous Artist - Cool Song");
    assert.equal(r3.track_num, 5);
    assert.equal(r3.artist, "Famous Artist");
    assert.equal(r3.title, "Cool Song");
  });

  test('detectPlatformUrl classifies URLs accurately', () => {
    const [p1, t1] = detectPlatformUrl("https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT");
    assert.equal(p1, "spotify");
    assert.equal(t1, "track");

    const [p2, t2] = detectPlatformUrl("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M");
    assert.equal(p2, "spotify");
    assert.equal(t2, "playlist");

    const [p3, t3] = detectPlatformUrl("https://music.apple.com/us/album/nevermind/1440783617");
    assert.equal(p3, "apple_music");
    assert.equal(t3, "album");

    const [p4, t4] = detectPlatformUrl("https://www.youtube.com/watch?v=dQw4w9WgXcQ");
    assert.equal(p4, "youtube");
    assert.equal(t4, "video");

    const [p5, t5] = detectPlatformUrl("https://soundcloud.com/artist/track-name");
    assert.equal(p5, "soundcloud");
    assert.equal(t5, "track");

    const [p6, t6] = detectPlatformUrl("Just a regular search query");
    assert.equal(p6, "search");
    assert.equal(t6, "query");
  });
});

describe('4. Synchronized Lyrics (LRC) Engine', () => {
  const sampleLrc = `[00:12.34] First lyric line
[00:25.50] Second lyric line
[01:05.12] Chorus begins here
[01:45.00] Outro line`;

  test('parseLrc parses timestamps and text accurately', () => {
    const parsed = parseLrc(sampleLrc);
    assert.equal(parsed.length, 4);
    assert.equal(parsed[0].time, 12.34);
    assert.equal(parsed[0].text, "First lyric line");
    assert.equal(parsed[2].time, 65.12);
    assert.equal(parsed[2].text, "Chorus begins here");
  });

  test('formatLrc reconstructs valid LRC lines', () => {
    const list = [
      { time: 10.5, text: "Line 1" },
      { time: 75.25, text: "Line 2" }
    ];
    const formatted = formatLrc(list);
    assert.ok(formatted.includes("[00:10.50] Line 1"));
    assert.ok(formatted.includes("[01:15.25] Line 2"));
  });

  test('getActiveLyricIndex tracks position correctly', () => {
    const parsed = parseLrc(sampleLrc);
    assert.equal(getActiveLyricIndex(parsed, 5.0), -1);
    assert.equal(getActiveLyricIndex(parsed, 15.0), 0);
    assert.equal(getActiveLyricIndex(parsed, 30.0), 1);
    assert.equal(getActiveLyricIndex(parsed, 70.0), 2);
    assert.equal(getActiveLyricIndex(parsed, 120.0), 3);
  });

  test('saveLrc creates a UTF-8 sidecar file', () => {
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'nexus_lrc_test_'));
    const dummyAudio = path.join(tmpDir, 'song.mp3');
    fs.writeFileSync(dummyAudio, 'dummy content');

    const ok = saveLrc(dummyAudio, sampleLrc);
    assert.ok(ok, "saveLrc should return true");
    const lrcPath = path.join(tmpDir, 'song.lrc');
    assert.ok(fs.existsSync(lrcPath), "Sidecar .lrc file must exist");
    assert.equal(fs.readFileSync(lrcPath, 'utf8'), sampleLrc);

    try { fs.rmSync(tmpDir, { recursive: true, force: true }); } catch {}
  });
});

describe('5. Library Scanner & Management', () => {
  let tmpLibraryDir;

  before(() => {
    tmpLibraryDir = fs.mkdtempSync(path.join(os.tmpdir(), 'nexus_lib_test_'));
    fs.writeFileSync(path.join(tmpLibraryDir, '01 - Artist One - Song Alpha.mp3'), 'audio-data-1');
    fs.writeFileSync(path.join(tmpLibraryDir, 'Artist Two - Song Beta.m4a'), 'audio-data-2');
    fs.writeFileSync(path.join(tmpLibraryDir, 'Song Gamma.flac'), 'audio-data-3');
    fs.writeFileSync(path.join(tmpLibraryDir, 'unrelated.txt'), 'not-media');
  });

  after(() => {
    try { fs.rmSync(tmpLibraryDir, { recursive: true, force: true }); } catch {}
  });

  test('scanLibrary detects supported media and ignores non-media files', async () => {
    const items = await scanLibrary(tmpLibraryDir);
    assert.equal(items.length, 3);
    const names = items.map(i => i.name).sort();
    assert.ok(names.includes('01 - Artist One - Song Alpha.mp3'));
    assert.ok(names.includes('Artist Two - Song Beta.m4a'));
    assert.ok(names.includes('Song Gamma.flac'));
  });

  test('scanLibrary filters by query keyword', async () => {
    const filtered = await scanLibrary(tmpLibraryDir, 'Alpha');
    assert.equal(filtered.length, 1);
    assert.ok(filtered[0].name.includes('Alpha'));
  });

  test('exportM3u8Playlist creates valid playlist file', async () => {
    const items = await scanLibrary(tmpLibraryDir);
    const paths = items.map(i => i.path);
    const res = await exportM3u8Playlist("Test_Playlist", paths, tmpLibraryDir);
    assert.ok(res.success);
    assert.ok(fs.existsSync(res.path));
    const content = fs.readFileSync(res.path, 'utf8');
    assert.ok(content.startsWith("#EXTM3U"));
    assert.ok(content.includes("#EXTINF:"));
  });

  test('deleteFile removes target file and cleans sidecars', () => {
    const testFile = path.join(tmpLibraryDir, 'to_delete.mp3');
    const testLrc = path.join(tmpLibraryDir, 'to_delete.lrc');
    fs.writeFileSync(testFile, 'dummy');
    fs.writeFileSync(testLrc, '[00:01.00] test');

    const ok = deleteFile(testFile);
    assert.ok(ok);
    assert.ok(!fs.existsSync(testFile), "File should be deleted");
    assert.ok(!fs.existsSync(testLrc), "LRC sidecar should be deleted");
  });
});

describe('6. Audio Player Controller & Equalizer', () => {
  let player;
  let config;

  before(() => {
    config = new ConfigManager();
    player = new PlayerManager(config);
  });

  test('Initial player state schema is correct', () => {
    const s = player.getPlayerState();
    assert.equal(s.is_playing, false);
    assert.equal(s.is_paused, false);
    assert.equal(s.volume, 1.0);
    assert.equal(s.repeat_mode, "off");
    assert.equal(s.is_shuffle, false);
    assert.ok(s.eq_bands);
  });

  test('Volume control and mute toggling', () => {
    player.playerControl("set_volume", 0.75);
    assert.equal(player.getPlayerState().volume, 0.75);

    player.playerControl("toggle_mute");
    assert.equal(player.getPlayerState().is_muted, true);

    player.playerControl("toggle_mute");
    assert.equal(player.getPlayerState().is_muted, false);
  });

  test('Repeat and shuffle mode transitions', () => {
    assert.equal(player.playerControl("toggle_repeat"), "all");
    assert.equal(player.playerControl("toggle_repeat"), "one");
    assert.equal(player.playerControl("toggle_repeat"), "off");

    assert.equal(player.playerControl("toggle_shuffle"), true);
    assert.equal(player.playerControl("toggle_shuffle"), false);
  });

  test('Equalizer presets apply correctly', () => {
    player.setEqPreset("Bass Boost");
    const s = player.getPlayerState();
    assert.equal(s.eq_preset, "Bass Boost");
    assert.equal(s.eq_bands.bass, EQ_PRESETS["Bass Boost"].bass);
  });

  test('Sleep timer sets and cancels properly', () => {
    const setRes = player.setSleepTimer(30);
    assert.ok(setRes.active);
    const s1 = player.getSleepTimerState();
    assert.ok(s1.active);
    assert.equal(s1.mode, "minutes");

    player.cancelSleepTimer();
    const s2 = player.getSleepTimerState();
    assert.equal(s2.active, false);
  });
});

describe('7. Download Queue Operations', () => {
  let downloader;
  let engine;
  let config;

  before(() => {
    config = new ConfigManager();
    engine = new EngineManager(config.appdataDir);
    downloader = new DownloadManager(engine, config);
  });

  test('addToQueue adds tasks to queue with default values', () => {
    const res = downloader.addToQueue("https://www.youtube.com/watch?v=test12345", "Test Track", "mp3_320");
    assert.ok(res.task_id);

    const q = downloader.getQueueState();
    assert.equal(q.length, 1);
    assert.equal(q[0].id, res.task_id);
    assert.equal(q[0].title, "Test Track");
    assert.equal(q[0].format, "mp3_320");
  });

  test('cancelTask marks task as cancelled', () => {
    const q = downloader.getQueueState();
    const taskId = q[0].id;
    const ok = downloader.cancelTask(taskId);
    assert.ok(ok);

    const updated = downloader.getQueueState();
    assert.equal(updated[0].status, "cancelled");
  });

  test('retryTask resets cancelled task to waiting', () => {
    const q = downloader.getQueueState();
    const taskId = q[0].id;
    const ok = downloader.retryTask(taskId);
    assert.ok(ok);

    const updated = downloader.getQueueState();
    assert.ok(['waiting', 'downloading'].includes(updated[0].status), `Expected waiting or downloading, got ${updated[0].status}`);
  });

  test('clearFinished purges non-active tasks', () => {
    const q = downloader.getQueueState();
    const taskId = q[0].id;
    downloader.cancelTask(taskId);

    downloader.clearFinished();
    assert.equal(downloader.getQueueState().length, 0);
  });
});

describe('8. Self-Healing Binary Engine Verification', () => {
  test('EngineManager reports ready external tools', () => {
    const config = new ConfigManager();
    const engine = new EngineManager(config.appdataDir);
    const status = engine.getStatus();

    assert.equal(status.ytdlp_ready, true, "yt-dlp must be ready");
    assert.equal(status.ffmpeg_ready, true, "ffmpeg must be ready");
    assert.equal(status.ffprobe_ready, true, "ffprobe must be ready");
    assert.equal(status.ffplay_ready, true, "ffplay must be ready");
  });
});

describe('9. Edge Cases & Boundary Value Robustness', () => {
  test('cleanMusicTitle and parseMusicMetadata handle empty and invalid inputs gracefully', () => {
    assert.equal(cleanMusicTitle(""), "");
    assert.equal(cleanMusicTitle(null), "");
    assert.equal(cleanMusicTitle(undefined), "");

    const pEmpty = parseMusicMetadata("");
    assert.equal(pEmpty.title, "Track");
    assert.equal(pEmpty.artist, "Unknown Artist");

    const pSlash = parseMusicMetadata("   -   ");
    assert.ok(pSlash.title);
  });

  test('detectPlatformUrl handles spotify URIs, malformed URLs and edge cases', () => {
    const [p1, t1, id1] = detectPlatformUrl("spotify:track:4cOdK2wGLETKBW3PvgPWqT");
    assert.equal(p1, "spotify");
    assert.equal(t1, "track");
    assert.equal(id1, "4cOdK2wGLETKBW3PvgPWqT");

    const [p2, t2, id2] = detectPlatformUrl("spotify:playlist:37i9dQZF1DXcBWIGoYBM5M");
    assert.equal(p2, "spotify");
    assert.equal(t2, "playlist");
    assert.equal(id2, "37i9dQZF1DXcBWIGoYBM5M");

    const [p3, t3] = detectPlatformUrl("");
    assert.equal(p3, "search");
    assert.equal(t3, "search");
  });

  test('parseLrc handles multi-timestamp lines and corrupt tags', () => {
    const multiLine = "[00:10.00][00:20.50] Echo echo";
    const res = parseLrc(multiLine);
    assert.equal(res.length, 2);
    assert.equal(res[0].time, 10.0);
    assert.equal(res[0].text, "Echo echo");
    assert.equal(res[1].time, 20.5);
    assert.equal(res[1].text, "Echo echo");

    // Corrupt lines
    assert.deepEqual(parseLrc("[invalid time] some lyrics"), []);
    assert.deepEqual(parseLrc(null), []);
    assert.deepEqual(parseLrc(""), []);
  });

  test('getActiveLyricIndex handles edge timestamps', () => {
    const sample = [{ time: 10, text: "A" }, { time: 20, text: "B" }];
    assert.equal(getActiveLyricIndex(sample, -5), -1);
    assert.equal(getActiveLyricIndex(sample, 0), -1);
    assert.equal(getActiveLyricIndex(sample, 10), 0);
    assert.equal(getActiveLyricIndex(sample, 19.99), 0);
    assert.equal(getActiveLyricIndex(sample, 20), 1);
    assert.equal(getActiveLyricIndex(sample, 999), 1);
    assert.equal(getActiveLyricIndex([], 15), -1);
  });

  test('PlayerManager clamps seek, volume, and playback speed to safe ranges', () => {
    const config = new ConfigManager();
    const player = new PlayerManager(config);
    player.state.duration = 180;

    // Seek clamping
    player.playerControl("seek", 9999);
    assert.equal(player.getPlayerState().current_pos, 180);

    player.playerControl("seek", -50);
    assert.equal(player.getPlayerState().current_pos, 0);

    // Volume clamping
    player.playerControl("set_volume", 2.5);
    assert.equal(player.getPlayerState().volume, 1.0);

    player.playerControl("set_volume", -1.0);
    assert.equal(player.getPlayerState().volume, 0.0);

    // Speed clamping (0.25 to 3.0)
    player.playerControl("set_speed", 10.0);
    assert.equal(player.getPlayerState().playback_speed, 3.0);

    player.playerControl("set_speed", 0.01);
    assert.equal(player.getPlayerState().playback_speed, 0.25);
  });

  test('DownloadManager safe handling of non-existent tasks and empty queue', () => {
    const config = new ConfigManager();
    const engine = new EngineManager(config.appdataDir);
    const downloader = new DownloadManager(engine, config);

    assert.equal(downloader.cancelTask("non_existent_id"), false);
    assert.equal(downloader.retryTask("non_existent_id"), false);
    assert.equal(downloader.clearFinished(), true);
    assert.equal(downloader.batchCancelAll(), 0);
  });

  test('scanLibrary handles empty and non-existent folders cleanly', async () => {
    assert.deepEqual(await scanLibrary("/non/existent/path/9999"), []);
    assert.deepEqual(await scanLibrary(null), []);
  });
});

describe('10. Protocol Handlers, Discord RPC, Audio Feedback & Streaming', () => {
  const { DiscordRPC } = require('../src/main/discord');

  test('local-media URL format parses query path correctly on Windows', () => {
    const rawFilePath = 'E:\\Music\\Test Artist - Song.mp3';
    const mediaUrl = `local-media://audio?path=${encodeURIComponent(rawFilePath)}`;
    const parsed = new URL(mediaUrl);
    const resolvedPath = parsed.searchParams.get('path');
    assert.equal(resolvedPath, rawFilePath);
  });

  test('PlayerManager.syncFromRenderer synchronizes real audio position and duration', () => {
    const config = new ConfigManager();
    const player = new PlayerManager(config);
    player.state.is_playing = true;

    player.syncFromRenderer({ current_pos: 75.4, duration: 240.0 });
    assert.equal(player.getPlayerState().current_pos, 75.4);
    assert.equal(player.getPlayerState().duration, 240.0);
    assert.equal(player.getPlayerState().info.duration, 240.0);

    // Track ended feedback
    player.state.repeat_mode = "off";
    player.syncFromRenderer({ ended: true });
    assert.equal(player.getPlayerState().is_playing, false);
    assert.equal(player.getPlayerState().current_pos, 0.0);
  });

  test('DiscordRPC initial state and packet serialization', () => {
    const rpc = new DiscordRPC("1251829037289013318", false);
    assert.equal(rpc.enabled, false);
    assert.equal(rpc.connected, false);

    rpc.setEnabled(true);
    assert.equal(rpc.enabled, true);

    // Mock socket to verify packet serialization format
    let sentBuffer = null;
    rpc.socket = {
      writable: true,
      write: (buf) => { sentBuffer = buf; return true; }
    };
    rpc.connected = true;

    rpc.setActivity({ details: "Song Title", state: "by Artist" });
    assert.ok(sentBuffer);
    assert.ok(sentBuffer.length >= 8);

    const opcode = sentBuffer.readUInt32LE(0);
    const length = sentBuffer.readUInt32LE(4);
    assert.equal(opcode, 1); // OP_FRAME
    const payload = JSON.parse(sentBuffer.slice(8, 8 + length).toString('utf8'));
    assert.equal(payload.cmd, 'SET_ACTIVITY');
    assert.equal(payload.args.activity.details, 'Song Title');
  });

  test('NexusBridgeAPI get_initial_state includes discord_rpc state', () => {
    const config = new ConfigManager();
    const engine = new EngineManager(config.appdataDir);
    const downloader = new DownloadManager(engine, config);
    const player = new PlayerManager(config);
    const bridge = new NexusBridgeAPI({
      mainWindow: null,
      configManager: config,
      engineManager: engine,
      downloadManager: downloader,
      playerManager: player,
      trayManager: null
    });

    const init = bridge.get_initial_state();
    assert.ok(init.discord_rpc, "Initial state must include discord_rpc property");
    assert.equal(typeof init.discord_rpc.enabled, "boolean");
    assert.equal(typeof init.discord_rpc.connected, "boolean");
  });

  test('DownloadManager completed status contract matches web UI', () => {
    const config = new ConfigManager();
    const engine = new EngineManager(config.appdataDir);
    const downloader = new DownloadManager(engine, config);

    const res = downloader.addToQueue("https://www.youtube.com/watch?v=done_test", "Done Song", "mp3_320");
    const task = downloader.tasks.find(t => t.id === res.task_id);
    assert.ok(task);

    // Simulate completion
    task.status = "completed";
    assert.equal(downloader.getQueueState()[0].status, "completed");

    // clearFinished must purge completed tasks
    downloader.clearFinished();
    assert.equal(downloader.getQueueState().length, 0);
  });
});

describe('YouTube playback continuity', () => {
  const fs = require('fs');
  const os = require('os');
  const path = require('path');
  const {
    isHealableFailure,
    isPermanentFailure,
    streamExpiryMs,
    findReadyCache,
    markCache
  } = require('../src/main/youtube');

  test('expired or challenged YouTube responses are healable, permanent takedowns are not', () => {
    assert.equal(isHealableFailure('ERROR: Signature extraction failed'), true);
    assert.equal(isHealableFailure('HTTP Error 403: Forbidden'), true);
    assert.equal(isHealableFailure('Sign in to confirm you’re not a bot'), true);
    assert.equal(isHealableFailure('This video is unavailable'), false);
    assert.equal(isPermanentFailure('Video unavailable'), true);
    assert.equal(isHealableFailure('private video'), false);
  });

  test('googlevideo expire parameter schedules refresh before the URL dies', () => {
    assert.equal(streamExpiryMs('https://rr3---sn.googlevideo.com/videoplayback?expire=1700000000&id=1'), 1700000000000);
    assert.equal(streamExpiryMs('https://example.com/audio.m4a'), 0);
    assert.equal(streamExpiryMs('not a url'), 0);
  });

  test('only a completed cache marker counts as a full track', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'nexustube-cache-'));
    const hash = 'abc123';
    const file = path.join(dir, `stream_${hash}.m4a`);
    fs.writeFileSync(file, Buffer.alloc(21000));
    assert.equal(findReadyCache(dir, hash), null);
    markCache(dir, hash, file);
    assert.equal(findReadyCache(dir, hash), file);
    fs.rmSync(dir, { recursive: true, force: true });
  });

  test('media errors on a local file do not restart playback', () => {
    const config = new ConfigManager();
    const player = new PlayerManager(config);
    player.state.current_path = 'E:\\Music\\song.mp3';
    player.state.source_url = 'E:\\Music\\song.mp3';
    player.state.is_playing = true;
    player.syncFromRenderer({ media_error: true, current_pos: 42 });
    assert.equal(player.getPlayerState().current_pos, 42);
    assert.equal(player.state.current_path, 'E:\\Music\\song.mp3');
    assert.equal(player.recoverAttempts, 0);
  });
});

