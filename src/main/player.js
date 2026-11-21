/**
 * NexusTube — Audio Player Controller, Equalizer & Sleep Timer Subsystem
 * Manages playback state, playlist progression, volume, 5-band EQ presets,
 * sleep timer countdown, and trim previews.
 */

const fs = require('fs');
const path = require('path');
const { extractMetadata } = require('./library');
const { EQ_PRESETS } = require('./config');

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
      eq_preset: "Flat",
      eq_bands: { bass: 0.0, low_mid: 0.0, mid: 0.0, high_mid: 0.0, treble: 0.0 },
      dsp_effects: { preamp: 0.0, bass_boost: 0.0, surround: false },
      normalize: false,
      info: {
        title: "",
        artist: "",
        album: "",
        duration: 0,
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
    this.startTicker();
  }

  setDiscord(discordRpc) {
    this.discord = discordRpc;
  }

  syncFromRenderer(syncData) {
    if (!syncData) return;
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
    this.library = Array.isArray(items) ? items : [];
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
    // ไม่ให้ ticker ตัวนี้ lock process ไว้ (สำคัญตอนรัน node --test)
    if (this.ticker.unref) this.ticker.unref();
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

  async playTrack(filePath) {
    if (!filePath) return null;
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
      const meta = await extractMetadata(filePath);
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
        cover_base64: meta.coverBase64 || ""
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

    const ytdlpBin = engineManager ? engineManager.getYtdlpBin() : 'yt-dlp';
    const ffmpegBin = engineManager ? engineManager.getFfmpegBin() : 'ffmpeg';
    const ffmpegDir = ffmpegBin && fs.existsSync(ffmpegBin) ? path.dirname(ffmpegBin) : '';

    const os = require('os');
    const cacheDir = path.join(os.tmpdir(), 'nexustube_cache');
    try { fs.mkdirSync(cacheDir, { recursive: true }); } catch {}

    const crypto = require('crypto');
    const hash = crypto.createHash('md5').update(urlOrPath).digest('hex');
    const cachedFile = path.join(cacheDir, `stream_${hash}.mp3`);

    let info = {
      title: "Online Stream",
      artist: "NexusTube",
      album: "Online Stream",
      duration: 0,
      cover_base64: ""
    };

    if (fs.existsSync(cachedFile) && fs.statSync(cachedFile).size > 10000) {
      return this.playTrack(cachedFile);
    }

    return new Promise((resolve) => {
      const { spawn } = require('child_process');
      const getStreamCmd = [
        ytdlpBin,
        '--no-warnings',
        '--dump-json',
        '-g',
        '-f', 'bestaudio[ext=m4a]/bestaudio/best',
        urlOrPath
      ];

      const proc = spawn(getStreamCmd[0], getStreamCmd.slice(1), { windowsHide: true });
      let stdout = '';
      proc.stdout.on('data', d => stdout += d.toString('utf8'));
      proc.on('close', async (code) => {
        if (code === 0 && stdout.trim()) {
          const lines = stdout.trim().split('\n').filter(l => l.trim());
          let streamUrl = '';
          for (const line of lines) {
            if (line.startsWith('http://') || line.startsWith('https://')) {
              streamUrl = line.trim();
            } else if (line.startsWith('{')) {
              try {
                const d = JSON.parse(line);
                info.title = d.title || info.title;
                info.artist = d.uploader || d.channel || info.artist;
                info.duration = d.duration || info.duration;
                if (d.thumbnail) {
                  info.cover_base64 = d.thumbnail;
                }
              } catch {}
            }
          }

          if (streamUrl) {
            this.state.current_path = streamUrl;
            this.state.duration = info.duration || 0;
            this.state.current_pos = 0.0;
            this.state.is_playing = true;
            this.state.is_paused = false;
            this.state.info = info;
            this.lastTick = Date.now();

            this.notifyRenderer("play", {
              path: streamUrl,
              info: this.state.info,
              volume: this.state.is_muted ? 0 : this.state.volume,
              speed: this.state.playback_speed,
              eq: this.state.eq_bands
            });

            if (this.discord) this.discord.updatePlayback(this.state);
            return resolve(info);
          }
        }

        // Fallback: Download preview slice
        const sliceCmd = [
          ytdlpBin,
          '--no-warnings',
          '--download-sections', '*0-180',
          '-x',
          '--audio-format', 'mp3',
          '--audio-quality', '192K',
          '-o', cachedFile
        ];
        if (ffmpegDir) sliceCmd.push('--ffmpeg-location', ffmpegDir);
        sliceCmd.push(urlOrPath);

        const dlProc = spawn(sliceCmd[0], sliceCmd.slice(1), { windowsHide: true });
        dlProc.on('close', async (dlCode) => {
          if (dlCode === 0 && fs.existsSync(cachedFile)) {
            const played = await this.playTrack(cachedFile);
            return resolve(played);
          }
          resolve(null);
        });
        dlProc.on('error', () => resolve(null));
      });
      proc.on('error', () => resolve(null));
    });
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
    const curIdx = this.library.findIndex(item => item.path === this.state.current_path);

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
    const curIdx = this.library.findIndex(item => item.path === this.state.current_path);

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
