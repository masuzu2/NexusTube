/**
 * NexusTube — Comprehensive Desktop Bridge API
 * Implements 100% of NexusBridgeAPI contract methods in pure JavaScript / Node.js
 * for seamless interaction with web/app.js.
 */

const { clipboard, shell, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const { searchYoutube, resolveUrl } = require('./resolver');
const { scanLibrary, deleteFile, exportM3u8Playlist, trimAudioFile, convertTrack } = require('./library');
const { fetchLyrics, searchLyrics, saveLrc } = require('./lyrics');
const { VERSION, LOCALES, ACCENT_PALETTE, EQ_PRESETS } = require('./config');
const { DiscordRPC } = require('./discord');

class NexusBridgeAPI {
  constructor({ mainWindow, configManager, engineManager, downloadManager, playerManager, trayManager }) {
    this.win = mainWindow;
    this.config = configManager;
    this.engine = engineManager;
    this.downloader = downloadManager;
    this.player = playerManager;
    this.tray = trayManager;

    this.miniPlayerState = {
      active: false,
      prevBounds: null,
      wasMaximized: false
    };

    this.discordRpcEnabled = this.config.get('discord_rpc', true);
    this.discord = new DiscordRPC(undefined, this.discordRpcEnabled);
    if (this.player && typeof this.player.setDiscord === 'function') {
      this.player.setDiscord(this.discord);
    }
    if (this.discordRpcEnabled) {
      this.discord.connect();
    }
  }

  setWindow(win) {
    this.win = win;
  }

  // ── 1. Application State & Config ──────────────────────────────────────────

  get_initial_state() {
    const status = this.engine.getStatus();
    const cfg = this.config.config;
    return {
      version: VERSION,
      config: cfg,
      locales: LOCALES,
      accents: ACCENT_PALETTE,
      eq_presets: EQ_PRESETS,
      eq_bands: this.player.state.eq_bands,
      engine_status: status,
      discord_rpc: {
        enabled: this.discord ? this.discord.enabled : this.discordRpcEnabled,
        connected: this.discord ? this.discord.connected : false
      }
    };
  }

  get_clipboard() {
    try {
      return clipboard.readText() || "";
    } catch {
      return "";
    }
  }

  save_config(updates = {}) {
    return this.config.saveConfig(updates);
  }

  get_engine_status() {
    return this.engine.getStatus();
  }

  async update_engines_now() {
    return this.update_engines();
  }

  async update_engines() {
    const res = await this.engine.ensureEngines();
    return {
      ...res,
      success: !!(res.ytdlp_ready && res.ffmpeg_ready),
      message: res.ytdlp_ready && res.ffmpeg_ready ? "Engines ready and up to date." : "Engine update check finished.",
      status: res
    };
  }

  async check_ytdlp_update() {
    return this.engine.checkYtdlpUpdate();
  }

  async update_ytdlp() {
    return this.engine.updateYtdlp();
  }

  // ── 2. Search & URL Resolvers ──────────────────────────────────────────────

  async search_youtube(query) {
    return searchYoutube(query, this.engine);
  }

  async resolve_url(url) {
    return resolveUrl(url, this.engine);
  }

  // ── 3. Download Queue Operations ───────────────────────────────────────────

  add_to_queue(url, title = "", fmt_choice = "mp3_320", options = {}, metadata = null) {
    return this.downloader.addToQueue(url, title, fmt_choice, options, metadata);
  }

  get_queue_state() {
    return this.downloader.getQueueState();
  }

  cancel_task(taskId) {
    return this.downloader.cancelTask(taskId);
  }

  retry_task(taskId) {
    return this.downloader.retryTask(taskId);
  }

  clear_finished() {
    return this.downloader.clearFinished();
  }

  batch_cancel_all() {
    return this.downloader.batchCancelAll();
  }

  // ── 4. Library Management ──────────────────────────────────────────────────

  async get_library(query = "", sortBy = "date") {
    const outdir = this.config.get('outdir');
    const favs = this.config.get('favorites', []);
    const items = await scanLibrary(outdir, query, sortBy, favs);
    this.player.setLibrary(items);
    return items;
  }

  toggle_favorite(filePath) {
    if (!filePath) return false;
    const favs = this.config.get('favorites', []);
    const resolved = path.resolve(filePath);
    const idx = favs.findIndex(p => path.resolve(p) === resolved);
    let isFav = false;
    if (idx === -1) {
      favs.push(resolved);
      isFav = true;
    } else {
      favs.splice(idx, 1);
      isFav = false;
    }
    this.config.set('favorites', favs);
    return isFav;
  }

  get_favorites() {
    return this.config.get('favorites', []);
  }

  delete_file(filePath) {
    return deleteFile(filePath, this.config);
  }

  async export_library_playlist(playlistName = "NexusTube_Library", trackPaths = null) {
    let paths = trackPaths;
    if (!paths || paths.length === 0) {
      const items = await this.get_library();
      paths = items.map(i => i.path);
    }
    const outdir = this.config.get('outdir');
    return exportM3u8Playlist(playlistName, paths, outdir);
  }

  trim_audio_file(filePath, startSec, endSec, outFormat = "mp3") {
    const ffmpegBin = this.engine.getFfmpegBin();
    return trimAudioFile(filePath, startSec, endSec, outFormat, ffmpegBin);
  }

  convert_track(inputPath, targetFormat = "mp3", bitrate = "320k", normalize = false) {
    const ffmpegBin = this.engine.getFfmpegBin();
    return convertTrack(inputPath, targetFormat, bitrate, normalize, ffmpegBin);
  }

  // ── 5. Audio Player & Equalizer ────────────────────────────────────────────

  async play_track(filePath) {
    const res = await this.player.playTrack(filePath);
    return res;
  }

  player_control(action, param = null) {
    return this.player.playerControl(action, param);
  }

  get_player_state() {
    return this.player.getPlayerState();
  }

  set_eq_bands(bands) {
    this.config.set('eq_bands', bands);
    return this.player.setEqBands(bands);
  }

  set_eq_preset(presetName) {
    this.config.set('eq_preset', presetName);
    return this.player.setEqPreset(presetName);
  }

  set_dsp_effects(effectsOrPreamp, bassBoost, surround) {
    const res = this.player.setDspEffects(effectsOrPreamp, bassBoost, surround);
    this.config.set('dsp_effects', res);
    return res;
  }

  toggle_normalization(enabled = null) {
    const res = this.player.toggleNormalization(enabled);
    this.config.set('normalize', res);
    return res;
  }

  async stream_track(urlOrPath) {
    if (!urlOrPath) return null;
    if (fs.existsSync(urlOrPath)) {
      return this.play_track(urlOrPath);
    }
    return this.player.streamOnline(urlOrPath, this.engine);
  }

  async preview_trim(filePath, startSec, endSec) {
    return this.player.previewTrim(filePath, startSec, endSec);
  }

  stop_trim_preview() {
    return this.player.stopTrimPreview();
  }

  // ── 6. Lyrics Engine ───────────────────────────────────────────────────────

  async fetch_lyrics_data(title, artist = "", duration = 0, filePath = null) {
    return fetchLyrics(title, artist, duration, filePath);
  }

  async search_lyrics(title, artist = "") {
    return searchLyrics(title, artist);
  }

  save_lrc(filePath, content) {
    return saveLrc(filePath, content);
  }

  // ── 7. Sleep Timer ─────────────────────────────────────────────────────────

  set_sleep_timer(minutesOrMode, fadeOutSec = 30) {
    return this.player.setSleepTimer(minutesOrMode, fadeOutSec);
  }

  cancel_sleep_timer() {
    return this.player.cancelSleepTimer();
  }

  get_sleep_timer_state() {
    return this.player.getSleepTimerState();
  }

  // ── 8. System Dialogs & File Shell ─────────────────────────────────────────

  async select_folder() {
    if (!this.win) return null;
    const res = await dialog.showOpenDialog(this.win, {
      title: "Select NexusTube Downloads Directory",
      defaultPath: this.config.get('outdir'),
      properties: ['openDirectory', 'createDirectory']
    });
    if (!res.canceled && res.filePaths.length > 0) {
      const selected = res.filePaths[0];
      this.config.set('outdir', selected);
      return selected;
    }
    return null;
  }

  async browse_folder() {
    return this.select_folder();
  }

  open_folder(folderPath = null) {
    const target = folderPath || this.config.get('outdir');
    if (target && fs.existsSync(target)) {
      shell.openPath(target);
      return true;
    }
    return false;
  }

  reveal_file(filePath) {
    if (filePath && fs.existsSync(filePath)) {
      shell.showItemInFolder(filePath);
      return true;
    }
    return false;
  }

  // ── 9. Window Controls & Mini-Player ───────────────────────────────────────

  window_control(action) {
    if (!this.win) return false;
    switch (action) {
      case "minimize":
        this.win.minimize();
        return true;
      case "maximize":
        if (this.win.isMaximized()) {
          this.win.unmaximize();
        } else {
          this.win.maximize();
        }
        return true;
      case "close": {
        const stay = this.config.get('minimize_to_tray', false) && this.config.get('system_tray', false);
        if (stay && !this.win.isQuitting) {
          this.win.hide();
        } else {
          this.win.isQuitting = true;
          this.win.close();
        }
        return true;
      }
      default:
        return false;
    }
  }

  toggle_mini_player(enable = null, width = null, height = null, x = null, y = null, isMaximized = null) {
    if (!this.win) return { success: false, mini_player: false };

    const shouldEnable = enable !== null ? Boolean(enable) : !this.miniPlayerState.active;

    if (shouldEnable && !this.miniPlayerState.active) {
      this.miniPlayerState.wasMaximized = this.win.isMaximized();
      this.miniPlayerState.prevBounds = this.win.getBounds();
      this.miniPlayerState.active = true;

      if (this.miniPlayerState.wasMaximized) {
        this.win.unmaximize();
      }

      this.win.setAlwaysOnTop(true, 'screen-saver');
      this.win.setMinimumSize(320, 160);
      this.win.setSize(380, 200);

      // Move to bottom-right corner of screen
      try {
        const { screen } = require('electron');
        const primary = screen.getPrimaryDisplay();
        const { width: sw, height: sh } = primary.workAreaSize;
        this.win.setPosition(sw - 400, sh - 220);
      } catch {}

      return { success: true, mini_player: true };
    } else if (!shouldEnable && this.miniPlayerState.active) {
      this.miniPlayerState.active = false;
      this.win.setAlwaysOnTop(false);
      this.win.setMinimumSize(960, 600);

      if (this.miniPlayerState.prevBounds) {
        this.win.setBounds(this.miniPlayerState.prevBounds);
      } else {
        this.win.setSize(1280, 800);
        this.win.center();
      }

      if (this.miniPlayerState.wasMaximized) {
        this.win.maximize();
      }

      return { success: true, mini_player: false };
    }

    return { success: true, mini_player: this.miniPlayerState.active };
  }

  get_mini_player_state() {
    return { mini_player: this.miniPlayerState.active };
  }

  // ── 10. Desktop Integrations & Preferences ─────────────────────────────────

  toggle_discord_rpc(enabled = null) {
    const next = enabled !== null ? Boolean(enabled) : !(this.discord ? this.discord.enabled : this.discordRpcEnabled);
    if (this.discord) {
      this.discord.setEnabled(next);
    }
    this.discordRpcEnabled = next;
    this.config.set('discord_rpc', next);
    return next;
  }

  toggle_global_hotkeys(enabled = null) {
    if (this.tray) {
      return this.tray.toggleGlobalHotkeys(enabled);
    }
    const next = enabled !== null ? Boolean(enabled) : !this.config.get('global_hotkeys', true);
    this.config.set('global_hotkeys', next);
    return next;
  }

  toggle_system_tray(enabled = null) {
    if (this.tray) {
      return this.tray.toggleSystemTray(enabled);
    }
    const next = enabled !== null ? Boolean(enabled) : !this.config.get('system_tray', true);
    this.config.set('system_tray', next);
    return next;
  }

  toggle_minimize_to_tray(enabled = null) {
    if (this.tray) {
      return this.tray.toggleMinimizeToTray(enabled);
    }
    const next = enabled !== null ? Boolean(enabled) : !this.config.get('minimize_to_tray', false);
    this.config.set('minimize_to_tray', next);
    return next;
  }

  // Cookies
  get_cookie_config() {
    return {
      cookie_source: this.config.get('cookie_source'),
      cookie_file: this.config.get('cookie_file')
    };
  }

  set_cookie_source(source) {
    this.config.set('cookie_source', source);
    return true;
  }

  set_cookie_file(filePath) {
    this.config.set('cookie_file', filePath);
    return true;
  }

  clear_cookies() {
    this.config.set('cookie_source', null);
    this.config.set('cookie_file', null);
    return true;
  }
}

module.exports = { NexusBridgeAPI };
