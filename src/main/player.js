/**
 * NexusTube — Audio Player Controller, Equalizer & Sleep Timer Subsystem
 * Manages playback state, playlist progression, volume, 5-band EQ presets,
 * sleep timer countdown, and trim previews.
 */

const fs = require('fs');
const path = require('path');
const { extractMetadata } = require('./library');
const { EQ_PRESETS } = require('./config');
const {
  resilientArgs,
  runTool,
  parseStreamDump,
  isHealableFailure,
  isPermanentFailure,
  streamExpiryMs,
  setStreamHeaders,
  findReadyCache,
  clearIncomplete,
  markCache,
  largestCacheFile,
  pruneCache
} = require('./youtube');

class PlayerManager {
  constructor(configManager, sendToRenderer = null) {
    this.config = configManager;
    this.sendToRenderer = sendToRenderer;

    this.state = {
      is_playing: false,
      is_paused: false,
      current_pos: 0.0,
      duration: 0.0,
      volume: 1.0,
      is_muted: false,
      playback_speed: 1.0,
      repeat_mode: "off", // "off" | "all" | "one"
      is_shuffle: false,
      current_path: null,
      source_url: null,
      eq_preset: "Flat",
      eq_bands: { bass: 0.0, low_mid: 0.0, mid: 0.0, high_mid: 0.0, treble: 0.0 },
      dsp_effects: { preamp: 0.0, bass_boost: 0.0, surround: false },
      normalize: false,
      info: {
        title: "",
        artist: "",
        album: "",
        duration: 0,
        cover_path: "",
        cover_base64: ""
      }
    };

    this.sleepTimer = {
      active: false,
      mode: "minutes", // "minutes" | "end_of_track"
      targetTime: 0,
      totalMinutes: 0,
      timerId: null,
      intervalId: null
    };

    this.trimPreview = {
      active: false,
      timerId: null
    };

    this.ticker = null;
    this.lastTick = Date.now();
    this.library = [];
    this.discord = null;
    this.playGen = 0;
    this.readyCache = null;
    this.recoverAttempts = 0;
    this._refreshTimer = null;
    this._recovering = false;
    this._lastRecover = 0;
    this.engine = null;
    this.cacheDir = null;
    this.cacheHash = null;
    this._cachePromise = null;
    this.startTicker();
  }

  setDiscord(discordRpc) {
    this.discord = discordRpc;
  }

  syncFromRenderer(syncData) {
    if (!syncData) return;
    if (syncData.media_error) {
      if (typeof syncData.current_pos === 'number' && !isNaN(syncData.current_pos)) {
        this.state.current_pos = Math.max(0, syncData.current_pos);
        this.lastTick = Date.now();
      }
      this.recoverPlayback();
      return;
    }
    if (syncData.ended) {
      this.handleTrackEnded();
      return;
    }
    if (syncData.current_pos !== undefined && typeof syncData.current_pos === 'number' && !isNaN(syncData.current_pos)) {
      this.state.current_pos = Math.max(0, syncData.current_pos);
      this.lastTick = Date.now();
    }
    if (syncData.duration !== undefined && typeof syncData.duration === 'number' && !isNaN(syncData.duration) && syncData.duration > 0) {
      this.state.duration = syncData.duration;
      if (this.state.info) {
        this.state.info.duration = syncData.duration;
      }
    }
  }

  setLibrary(items) {
    this.library = (Array.isArray(items) ? items : []).map((item) => ({
      path: item && item.path,
      url: item && item.url
    })).filter((item) => item.path || item.url);
  }

  release() {
    this.clearRefreshTimer();
    if (this.ticker) clearInterval(this.ticker);
    this.ticker = null;
    if (this.sleepTimer) {
      if (this.sleepTimer.timerId) clearTimeout(this.sleepTimer.timerId);
      if (this.sleepTimer.intervalId) clearInterval(this.sleepTimer.intervalId);
      this.sleepTimer.active = false;
    }
    if (this.trimPreview && this.trimPreview.timerId) clearTimeout(this.trimPreview.timerId);
    this.playGen = (this.playGen || 0) + 1;
    this.state.is_playing = false;
    this.state.is_paused = false;
    this.state.current_path = null;
    this.state.info = null;
    this.library = [];
    this._cachePromise = null;
    this.notifyRenderer('stop');
  }

  startTicker() {
    if (this.ticker) clearInterval(this.ticker);
    this.ticker = setInterval(() => {
      const now = Date.now();
      const dt = (now - this.lastTick) / 1000.0;
      this.lastTick = now;

      if (this.state.is_playing && !this.state.is_paused) {
        this.state.current_pos += dt * (this.state.playback_speed || 1.0);

        if (this.state.duration > 0 && this.state.current_pos >= this.state.duration) {
          this.handleTrackEnded();
        }
      }
    }, 250);
    if (typeof this.ticker.unref === 'function') this.ticker.unref();
  }

  handleTrackEnded() {
    // Check end-of-track sleep timer
    if (this.sleepTimer.active && this.sleepTimer.mode === "end_of_track") {
      this.cancelSleepTimer();
      this.playerControl("pause");
      return;
    }

    if (this.state.repeat_mode === "one") {
      this.state.current_pos = 0.0;
      this.notifyRenderer("seek", 0);
      return;
    }

    if (this.state.repeat_mode === "all") {
      this.next();
      return;
    }

    // Default off: stop
    this.state.is_playing = false;
    this.state.is_paused = false;
    this.state.current_pos = 0.0;
    this.notifyRenderer("stop");
    if (this.discord) this.discord.updatePlayback(this.state);
  }

  notifyRenderer(action, data = null) {
    if (typeof this.sendToRenderer === 'function') {
      try {
        this.sendToRenderer('nexus:player-action', { action, data, state: this.state });
      } catch {}
    }
  }

  async playTrack(filePath, sourceUrl = null) {
    if (!filePath) return null;
    this.playGen = (this.playGen || 0) + 1;
    this.clearRefreshTimer();
    this.readyCache = null;
    this.state.source_url = sourceUrl || filePath;
    if (!fs.existsSync(filePath)) {
      if (filePath.startsWith('http://') || filePath.startsWith('https://')) {
        this.state.current_path = filePath;
        this.state.current_pos = 0.0;
        this.state.is_playing = true;
        this.state.is_paused = false;
        this.lastTick = Date.now();
        this.notifyRenderer("play", {
          path: filePath,
          info: this.state.info,
          volume: this.state.is_muted ? 0 : this.state.volume,
          speed: this.state.playback_speed,
          eq: this.state.eq_bands
        });
        if (this.discord) this.discord.updatePlayback(this.state);
        return this.state.info;
      }
      return null;
    }

    try {
      const meta = await extractMetadata(filePath, { covers: true });
      this.state.current_path = filePath;
      this.state.duration = meta.duration || 0;
      this.state.current_pos = 0.0;
      this.state.is_playing = true;
      this.state.is_paused = false;
      this.state.info = {
        title: meta.title || path.basename(filePath),
        artist: meta.artist || "Unknown Artist",
        album: meta.album || "NexusTube Collection",
        duration: meta.duration || 0,
        cover_path: meta.coverPath || "",
        cover_base64: ""
      };
      this.lastTick = Date.now();

      this.notifyRenderer("play", {
        path: filePath,
        info: this.state.info,
        volume: this.state.is_muted ? 0 : this.state.volume,
        speed: this.state.playback_speed,
        eq: this.state.eq_bands
      });

      if (this.discord) this.discord.updatePlayback(this.state);
      return this.state.info;
    } catch (err) {
      console.error("[Player] playTrack error:", err);
      return null;
    }
  }

  async streamOnline(urlOrPath, engineManager) {
    if (!urlOrPath) return null;
    if (fs.existsSync(urlOrPath)) {
      return this.playTrack(urlOrPath);
    }
    if (!engineManager) return null;

    this.engine = engineManager;
    this.recoverAttempts = 0;
    this.clearRefreshTimer();

    if (!engineManager.isValidBinary(engineManager.getYtdlpBin())) {
      try { await engineManager.ensureEngines(); } catch {}
    }

    const os = require('os');
    const crypto = require('crypto');
    const cacheDir = path.join(os.tmpdir(), 'nexustube_cache');
    try { fs.mkdirSync(cacheDir, { recursive: true }); } catch {}
    const hash = crypto.createHash('md5').update(String(urlOrPath)).digest('hex');
    this.cacheDir = cacheDir;
    this.cacheHash = hash;

    const cached = findReadyCache(cacheDir, hash);
    if (cached) {
      const played = await this.playTrack(cached, urlOrPath);
      this.readyCache = cached;
      this.cacheDir = cacheDir;
      this.cacheHash = hash;
      return played;
    }

    this.playGen = (this.playGen || 0) + 1;
    const gen = this.playGen;
    this.state.source_url = urlOrPath;

    const direct = await this.resolveDirect(urlOrPath);
    if (this.playGen !== gen) return this.state.info;
    if (direct && direct.ok && direct.streamUrl) {
      this.beginRemotePlayback(direct, gen);
      this.cacheFullTrack(urlOrPath, gen);
      return this.state.info;
    }
    if (direct && isPermanentFailure(direct.log)) return null;

    const file = await this.cacheFullTrack(urlOrPath, gen);
    if (this.playGen !== gen) return this.state.info;
    if (file) {
      const played = await this.playTrack(file, urlOrPath);
      this.readyCache = file;
      this.cacheDir = cacheDir;
      this.cacheHash = hash;
      return played;
    }
    return null;
  }

  async resolveDirect(url) {
    const engine = this.engine;
    if (!engine || !engine.isValidBinary(engine.getYtdlpBin())) return null;
    const args = [
      ...resilientArgs(engine, this.config, url),
      '--dump-json',
      '-g',
      '-f', 'bestaudio[ext=m4a]/bestaudio/best',
      url
    ];
    let result = await runTool(engine.getYtdlpBin(), args, engine.toolEnv());
    let parsed = parseStreamDump(result);
    if (!parsed.ok && isHealableFailure(parsed.log) && typeof engine.healYoutubeEngine === 'function') {
      const healed = await engine.healYoutubeEngine();
      if (healed && healed.success) {
        result = await runTool(engine.getYtdlpBin(), args, engine.toolEnv());
        parsed = parseStreamDump(result);
      }
    }
    return parsed;
  }

  beginRemotePlayback(direct, gen) {
    const info = this.metadataFromDump(direct.info);
    if (direct.info && direct.info.http_headers) setStreamHeaders(direct.info.http_headers);
    this.state.current_path = direct.streamUrl;
    this.state.duration = info.duration || 0;
    this.state.current_pos = 0;
    this.state.is_playing = true;
    this.state.is_paused = false;
    this.state.info = info;
    this.lastTick = Date.now();
    this.notifyRenderer('play', this.playPayload(direct.streamUrl, 0));
    if (this.discord) this.discord.updatePlayback(this.state);
    this.scheduleRefresh(direct.streamUrl, gen);
  }

  metadataFromDump(data) {
    const info = {
      title: 'Online Stream',
      artist: 'NexusTube',
      album: 'Online Stream',
      duration: 0,
      cover_path: '',
      cover_base64: ''
    };
    if (!data) return info;
    info.title = data.title || info.title;
    info.artist = data.uploader || data.channel || data.artist || info.artist;
    info.duration = data.duration || 0;
    if (data.thumbnail && /^https?:\/\//i.test(String(data.thumbnail))) info.cover_path = data.thumbnail;
    return info;
  }

  playPayload(mediaPath, startAt) {
    return {
      path: mediaPath,
      startAt: startAt || 0,
      autoplay: !!(this.state.is_playing && !this.state.is_paused),
      info: this.state.info,
      volume: this.state.is_muted ? 0 : this.state.volume,
      speed: this.state.playback_speed,
      eq: this.state.eq_bands
    };
  }

  cacheFullTrack(url, gen) {
    if (this._cachePromise && this._cacheGen === gen) return this._cachePromise;
    this._cacheGen = gen;
    this._cachePromise = this.downloadFullTrack(url, gen);
    return this._cachePromise;
  }

  async downloadFullTrack(url, gen) {
    const engine = this.engine;
    const dir = this.cacheDir;
    const hash = this.cacheHash;
    if (!engine || !dir || !hash) return null;
    try {
      clearIncomplete(dir, hash);
      const ffmpegBin = engine.getFfmpegBin();
      const hasFfmpeg = engine.isValidBinary(ffmpegBin);
      const outTemplate = hasFfmpeg
        ? path.join(dir, `stream_${hash}.m4a`)
        : path.join(dir, `stream_${hash}.%(ext)s`);
      const args = [...resilientArgs(engine, this.config, url)];
      if (hasFfmpeg) {
        args.push('--ffmpeg-location', path.dirname(ffmpegBin));
        args.push('-x', '--audio-format', 'm4a', '--audio-quality', '0');
      } else {
        args.push('-f', 'bestaudio[ext=m4a]/bestaudio/best');
      }
      args.push('-o', outTemplate, url);

      let result = await runTool(engine.getYtdlpBin(), args, engine.toolEnv());
      if (result.code !== 0 && isHealableFailure(`${result.stderr}\n${result.stdout}`) && typeof engine.healYoutubeEngine === 'function') {
        const healed = await engine.healYoutubeEngine();
        if (healed && healed.success && this.playGen === gen) {
          result = await runTool(engine.getYtdlpBin(), args, engine.toolEnv());
        }
      }
      if (result.code !== 0) return null;
      const file = largestCacheFile(dir, hash);
      if (!file) return null;
      markCache(dir, hash, file);
      pruneCache(dir);
      if (this.playGen !== gen) return file;
      this.readyCache = file;
      const remote = /^https?:\/\//.test(String(this.state.current_path || ''));
      if (remote && this.cacheHash === hash) this.handoffToFile(file, gen);
      return file;
    } catch (err) {
      console.warn('[Player] full-track cache failed:', err.message);
      return null;
    }
  }

  handoffToFile(file, gen) {
    if (this.playGen !== gen || !file || this.state.current_path === file) return;
    const pos = this.state.current_pos || 0;
    this.state.current_path = file;
    this.readyCache = file;
    this.clearRefreshTimer();
    this.notifyRenderer('play', this.playPayload(file, pos));
  }

  scheduleRefresh(streamUrl, gen) {
    this.clearRefreshTimer();
    const exp = streamExpiryMs(streamUrl);
    const delay = exp
      ? Math.min(Math.max(20000, exp - Date.now() - 90000), 2147483647)
      : 5 * 60 * 60 * 1000;
    this._refreshTimer = setTimeout(() => {
      if (this.playGen !== gen) return;
      if (!this.state.is_playing && !this.state.is_paused) return;
      if (this.readyCache && fs.existsSync(this.readyCache)) {
        this.handoffToFile(this.readyCache, gen);
        return;
      }
      this.recoverPlayback();
    }, delay);
    if (typeof this._refreshTimer.unref === 'function') this._refreshTimer.unref();
  }

  clearRefreshTimer() {
    if (this._refreshTimer) {
      clearTimeout(this._refreshTimer);
      this._refreshTimer = null;
    }
  }

  async recoverPlayback() {
    if (this._recovering) return;
    const gen = this.playGen;
    const source = this.state.source_url;
    if (!source || !this.engine) return;
    const current = String(this.state.current_path || '');
    const remote = current.startsWith('http://') || current.startsWith('https://');
    if (!remote) return;
    if (this.readyCache && fs.existsSync(this.readyCache)) {
      this.handoffToFile(this.readyCache, gen);
      return;
    }
    if (this.recoverAttempts >= 4) return;
    const now = Date.now();
    if (now - (this._lastRecover || 0) < 4000) return;
    this._lastRecover = now;
    this.recoverAttempts += 1;
    this._recovering = true;
    try {
      const pos = this.state.current_pos || 0;
      const direct = await this.resolveDirect(source);
      if (this.playGen !== gen || !direct || !direct.streamUrl) {
        const file = this._cachePromise ? await this._cachePromise : null;
        if (this.playGen === gen && file) this.handoffToFile(file, gen);
        return;
      }
      if (direct.info && direct.info.http_headers) setStreamHeaders(direct.info.http_headers);
      this.state.current_path = direct.streamUrl;
      this.notifyRenderer('play', this.playPayload(direct.streamUrl, pos));
      this.scheduleRefresh(direct.streamUrl, gen);
    } finally {
      this._recovering = false;
    }
  }

  playerControl(action, param = null) {
    switch (action) {
      case "play_pause": {
        if (!this.state.current_path) {
          if (this.library.length > 0) {
            this.playTrack(this.library[0].path);
          }
          return this.state.is_playing;
        }
        if (this.state.is_playing && !this.state.is_paused) {
          this.state.is_paused = true;
          this.notifyRenderer("pause");
        } else {
          this.state.is_playing = true;
          this.state.is_paused = false;
          this.lastTick = Date.now();
          this.notifyRenderer("resume");
        }
        if (this.discord) this.discord.updatePlayback(this.state);
        return this.state.is_playing && !this.state.is_paused;
      }

      case "pause": {
        this.state.is_paused = true;
        this.notifyRenderer("pause");
        if (this.discord) this.discord.updatePlayback(this.state);
        return true;
      }

      case "stop": {
        this.clearRefreshTimer();
        this.state.is_playing = false;
        this.state.is_paused = false;
        this.state.current_pos = 0.0;
        this.notifyRenderer("stop");
        if (this.discord) this.discord.updatePlayback(this.state);
        return true;
      }

      case "seek": {
        const target = Math.max(0, Math.min(this.state.duration || 999999, Number(param) || 0));
        this.state.current_pos = target;
        this.lastTick = Date.now();
        this.notifyRenderer("seek", target);
        if (this.discord) this.discord.updatePlayback(this.state);
        return target;
      }

      case "set_volume": {
        const v = Math.max(0, Math.min(1, Number(param)));
        this.state.volume = v;
        this.state.is_muted = false;
        this.notifyRenderer("set_volume", v);
        return v;
      }

      case "toggle_mute": {
        this.state.is_muted = !this.state.is_muted;
        this.notifyRenderer("set_volume", this.state.is_muted ? 0 : this.state.volume);
        return this.state.is_muted;
      }

      case "set_speed": {
        const s = Math.max(0.25, Math.min(3.0, Number(param) || 1.0));
        this.state.playback_speed = s;
        this.notifyRenderer("set_speed", s);
        return s;
      }

      case "toggle_shuffle": {
        if (typeof param === 'boolean') {
          this.state.is_shuffle = param;
        } else {
          this.state.is_shuffle = !this.state.is_shuffle;
        }
        return this.state.is_shuffle;
      }

      case "toggle_repeat": {
        const modes = ["off", "all", "one"];
        const curIdx = modes.indexOf(this.state.repeat_mode);
        this.state.repeat_mode = modes[(curIdx + 1) % modes.length];
        return this.state.repeat_mode;
      }

      case "next": {
        return this.next();
      }

      case "prev": {
        return this.prev();
      }

      default:
        return null;
    }
  }

  next() {
    if (!this.library || this.library.length === 0) return null;
    let nextIdx = 0;
    const curIdx = this.libraryIndex();

    if (this.state.is_shuffle) {
      nextIdx = Math.floor(Math.random() * this.library.length);
    } else if (curIdx !== -1) {
      nextIdx = (curIdx + 1) % this.library.length;
    }

    const nextTrack = this.library[nextIdx];
    if (nextTrack) {
      return this.playTrack(nextTrack.path);
    }
    return null;
  }

  prev() {
    if (this.state.current_pos > 3.0) {
      this.state.current_pos = 0.0;
      this.notifyRenderer("seek", 0);
      return this.state.info;
    }

    if (!this.library || this.library.length === 0) return null;
    let prevIdx = 0;
    const curIdx = this.libraryIndex();

    if (this.state.is_shuffle) {
      prevIdx = Math.floor(Math.random() * this.library.length);
    } else if (curIdx !== -1) {
      prevIdx = (curIdx - 1 + this.library.length) % this.library.length;
    }

    const prevTrack = this.library[prevIdx];
    if (prevTrack) {
      return this.playTrack(prevTrack.path);
    }
    return null;
  }

  libraryIndex() {
    const keys = [this.state.source_url, this.state.current_path].filter(Boolean);
    return this.library.findIndex((item) => keys.includes(item.path) || keys.includes(item.url));
  }

  getPlayerState() {
    return {
      is_playing: this.state.is_playing && !this.state.is_paused,
      is_paused: this.state.is_paused,
      current_pos: Math.round(this.state.current_pos * 100) / 100,
      duration: Math.round(this.state.duration * 100) / 100,
      volume: this.state.volume,
      is_muted: this.state.is_muted,
      playback_speed: this.state.playback_speed,
      repeat_mode: this.state.repeat_mode,
      is_shuffle: this.state.is_shuffle,
      current_path: this.state.current_path,
      eq_preset: this.state.eq_preset,
      eq_bands: this.state.eq_bands,
      dsp_effects: this.state.dsp_effects,
      info: this.state.info
    };
  }

  setEqBands(bands = {}) {
    this.state.eq_bands = { ...this.state.eq_bands, ...bands };
    this.notifyRenderer("set_eq", this.state.eq_bands);
    return this.state.eq_bands;
  }

  setEqPreset(presetName) {
    if (EQ_PRESETS[presetName]) {
      const p = EQ_PRESETS[presetName];
      this.state.eq_preset = presetName;
      this.state.eq_bands = {
        bass: p.bass,
        low_mid: p.low_mid,
        mid: p.mid,
        high_mid: p.high_mid,
        treble: p.treble
      };
      this.notifyRenderer("set_eq", this.state.eq_bands);
      return this.state.eq_bands;
    }
    return this.state.eq_bands;
  }

  setDspEffects(effectsOrPreamp, bassBoost, surround) {
    if (typeof effectsOrPreamp === 'object' && effectsOrPreamp !== null) {
      this.state.dsp_effects = { ...this.state.dsp_effects, ...effectsOrPreamp };
    } else {
      if (effectsOrPreamp !== undefined) this.state.dsp_effects.preamp = Number(effectsOrPreamp) || 0;
      if (bassBoost !== undefined) this.state.dsp_effects.bass_boost = Number(bassBoost) || 0;
      if (surround !== undefined) this.state.dsp_effects.surround = Boolean(surround);
    }
    this.notifyRenderer("set_dsp", this.state.dsp_effects);
    return this.state.dsp_effects;
  }

  toggleNormalization(enabled = null) {
    this.state.normalize = enabled !== null ? Boolean(enabled) : !this.state.normalize;
    return this.state.normalize;
  }

  setSleepTimer(minutesOrMode, fadeOutSec = 30) {
    this.cancelSleepTimer();

    if (minutesOrMode === "end_of_track") {
      this.sleepTimer = {
        active: true,
        mode: "end_of_track",
        targetTime: 0,
        totalMinutes: 0,
        timerId: null,
        intervalId: null
      };
      return { active: true, mode: "end_of_track" };
    }

    const mins = Math.max(1, parseInt(minutesOrMode, 10) || 15);
    const ms = mins * 60 * 1000;
    const target = Date.now() + ms;

    const timerId = setTimeout(() => {
      this.cancelSleepTimer();
      this.playerControl("pause");
    }, ms);

    this.sleepTimer = {
      active: true,
      mode: "minutes",
      targetTime: target,
      totalMinutes: mins,
      timerId,
      intervalId: null
    };

    return { active: true, minutes: mins };
  }

  cancelSleepTimer() {
    if (this.sleepTimer.timerId) clearTimeout(this.sleepTimer.timerId);
    if (this.sleepTimer.intervalId) clearInterval(this.sleepTimer.intervalId);
    this.sleepTimer = {
      active: false,
      mode: "minutes",
      targetTime: 0,
      totalMinutes: 0,
      timerId: null,
      intervalId: null
    };
    return true;
  }

  getSleepTimerState() {
    if (!this.sleepTimer.active) {
      return { active: false, minutes_left: 0, seconds_left: 0, mode: "off" };
    }
    if (this.sleepTimer.mode === "end_of_track") {
      return { active: true, minutes_left: 0, seconds_left: 0, mode: "end_of_track" };
    }
    const leftMs = Math.max(0, this.sleepTimer.targetTime - Date.now());
    return {
      active: true,
      minutes_left: Math.ceil(leftMs / 60000),
      seconds_left: Math.ceil(leftMs / 1000),
      mode: "minutes"
    };
  }

  async previewTrim(filePath, startSec, endSec) {
    this.stopTrimPreview();
    if (!filePath || !fs.existsSync(filePath)) return false;

    this.trimPreview.active = true;
    await this.playTrack(filePath);
    this.playerControl("seek", startSec);

    const dur = Math.max(0.5, (endSec - startSec)) * 1000;
    this.trimPreview.timerId = setTimeout(() => {
      this.stopTrimPreview();
    }, dur);

    return true;
  }

  stopTrimPreview() {
    if (this.trimPreview.timerId) {
      clearTimeout(this.trimPreview.timerId);
      this.trimPreview.timerId = null;
    }
    this.trimPreview.active = false;
    this.playerControl("pause");
    return true;
  }
}

module.exports = { PlayerManager };
