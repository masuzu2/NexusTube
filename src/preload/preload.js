/**
 * NexusTube — Preload Script
 * Seamlessly bridges Electron IPC to window.pywebview.api and window.electronAPI.
 * Features native Chromium Web Audio API with 5-band biquad equalizer and range-based audio streaming.
 */

const { contextBridge, ipcRenderer } = require('electron');

// List of all bridge methods matching NexusBridgeAPI
const BRIDGE_METHODS = [
  'get_initial_state',
  'get_clipboard',
  'save_config',
  'get_engine_status',
  'update_engines_now',
  'update_engines',
  'check_ytdlp_update',
  'update_ytdlp',
  'search_youtube',
  'resolve_url',
  'add_to_queue',
  'get_queue_state',
  'cancel_task',
  'retry_task',
  'clear_finished',
  'batch_cancel_all',
  'get_library',
  'toggle_favorite',
  'get_favorites',
  'delete_file',
  'export_library_playlist',
  'trim_audio_file',
  'convert_track',
  'play_track',
  'player_control',
  'get_player_state',
  'set_eq_bands',
  'set_eq_preset',
  'set_dsp_effects',
  'toggle_normalization',
  'stream_track',
  'preview_trim',
  'stop_trim_preview',
  'fetch_lyrics_data',
  'search_lyrics',
  'save_lrc',
  'set_sleep_timer',
  'cancel_sleep_timer',
  'get_sleep_timer_state',
  'select_folder',
  'browse_folder',
  'open_folder',
  'reveal_file',
  'window_control',
  'toggle_mini_player',
  'get_mini_player_state',
  'toggle_discord_rpc',
  'toggle_global_hotkeys',
  'toggle_system_tray',
  'toggle_minimize_to_tray',
  'get_cookie_config',
  'set_cookie_source',
  'set_cookie_file',
  'clear_cookies'
];

// Build API dictionary
const api = {};
for (const method of BRIDGE_METHODS) {
  api[method] = (...args) => ipcRenderer.invoke('nexus:api', method, ...args);
}

// Expose on window
try {
  contextBridge.exposeInMainWorld('pywebview', { api });
  contextBridge.exposeInMainWorld('electronAPI', api);
} catch {
  window.pywebview = { api };
  window.electronAPI = api;
}

// Native HTML5 & Web Audio subsystem inside renderer
let audioElement = null;
let audioContext = null;
let eqNodes = null;
let stallTimer = null;

function reportMediaError() {
  if (!audioElement || !audioElement.src) return;
  ipcRenderer.send('nexus:player-sync', {
    media_error: true,
    current_pos: audioElement.currentTime || 0
  });
}

function initAudioSystem() {
  if (audioElement) return;

  try {
    audioElement = new Audio();
    audioElement.crossOrigin = "anonymous";

    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (AudioContextClass) {
      audioContext = new AudioContextClass();
      const source = audioContext.createMediaElementSource(audioElement);

      // 5-Band Biquad Filters (60Hz, 250Hz, 1kHz, 4kHz, 12kHz)
      const f60 = audioContext.createBiquadFilter();
      f60.type = 'peaking';
      f60.frequency.value = 60;
      f60.Q.value = 1.0;

      const f250 = audioContext.createBiquadFilter();
      f250.type = 'peaking';
      f250.frequency.value = 250;
      f250.Q.value = 1.0;

      const f1k = audioContext.createBiquadFilter();
      f1k.type = 'peaking';
      f1k.frequency.value = 1000;
      f1k.Q.value = 1.0;

      const f4k = audioContext.createBiquadFilter();
      f4k.type = 'peaking';
      f4k.frequency.value = 4000;
      f4k.Q.value = 1.0;

      const f12k = audioContext.createBiquadFilter();
      f12k.type = 'peaking';
      f12k.frequency.value = 12000;
      f12k.Q.value = 1.0;

      const preamp = audioContext.createGain();
      preamp.gain.value = 1.0;

      source.connect(f60);
      f60.connect(f250);
      f250.connect(f1k);
      f1k.connect(f4k);
      f4k.connect(f12k);
      f12k.connect(preamp);
      preamp.connect(audioContext.destination);

      eqNodes = { f60, f250, f1k, f4k, f12k, preamp };

      // Synchronize real playback progress and track completion back to main process
      audioElement.addEventListener('timeupdate', () => {
        ipcRenderer.send('nexus:player-sync', {
          current_pos: audioElement.currentTime,
          duration: audioElement.duration || 0
        });
      });

      audioElement.addEventListener('durationchange', () => {
        if (audioElement.duration && !isNaN(audioElement.duration)) {
          ipcRenderer.send('nexus:player-sync', {
            duration: audioElement.duration
          });
        }
      });

      audioElement.addEventListener('ended', () => {
        ipcRenderer.send('nexus:player-sync', {
          ended: true
        });
      });

      audioElement.addEventListener('error', () => {
        const code = audioElement && audioElement.error && audioElement.error.code;
        if (code === 1) return;
        reportMediaError();
      });

      audioElement.addEventListener('stalled', () => {
        clearTimeout(stallTimer);
        stallTimer = setTimeout(() => {
          if (!audioElement || audioElement.paused) return;
          if (audioElement.readyState >= 3) return;
          reportMediaError();
        }, 12000);
      });

      audioElement.addEventListener('playing', () => clearTimeout(stallTimer));
      audioElement.addEventListener('canplay', () => clearTimeout(stallTimer));
    }
  } catch (err) {
    console.warn("[WebAudio] Init error:", err);
  }
}

// IPC listener for real-time audio sync
ipcRenderer.on('nexus:player-action', (event, { action, data, state }) => {
  initAudioSystem();
  if (!audioElement) return;

  if (audioContext && audioContext.state === 'suspended') {
    audioContext.resume();
  }

  switch (action) {
    case 'play': {
      if (data && data.path) {
        clearTimeout(stallTimer);
        const startAt = (typeof data.startAt === 'number' && data.startAt > 0.3) ? data.startAt : 0;
        if (data.path.startsWith('http://') || data.path.startsWith('https://')) {
          audioElement.src = `remote-media://audio?url=${encodeURIComponent(data.path)}`;
        } else {
          audioElement.src = `local-media://audio?path=${encodeURIComponent(data.path)}`;
        }
        if (data.volume !== undefined) audioElement.volume = data.volume;
        if (data.speed !== undefined) audioElement.playbackRate = data.speed;
        if (startAt) {
          audioElement.addEventListener('loadedmetadata', () => {
            try { audioElement.currentTime = startAt; } catch {}
          }, { once: true });
        }
        if (data.autoplay === false) {
          audioElement.pause();
        } else {
          audioElement.play().catch(e => console.warn("[WebAudio] play() failed:", e.message));
        }
      }
      break;
    }
    case 'pause': {
      audioElement.pause();
      break;
    }
    case 'resume': {
      audioElement.play().catch(() => {});
      break;
    }
    case 'stop': {
      audioElement.pause();
      audioElement.removeAttribute('src');
      audioElement.load();
      break;
    }
    case 'seek': {
      if (typeof data === 'number') {
        audioElement.currentTime = data;
      }
      break;
    }
    case 'set_volume': {
      if (typeof data === 'number') {
        audioElement.volume = Math.max(0, Math.min(1, data));
      }
      break;
    }
    case 'set_speed': {
      if (typeof data === 'number') {
        audioElement.playbackRate = Math.max(0.25, Math.min(3.0, data));
      }
      break;
    }
    case 'set_eq': {
      if (eqNodes && data) {
        if (data.bass !== undefined) eqNodes.f60.gain.value = data.bass;
        if (data.low_mid !== undefined) eqNodes.f250.gain.value = data.low_mid;
        if (data.mid !== undefined) eqNodes.f1k.gain.value = data.mid;
        if (data.high_mid !== undefined) eqNodes.f4k.gain.value = data.high_mid;
        if (data.treble !== undefined) eqNodes.f12k.gain.value = data.treble;
        if (data.preamp !== undefined && eqNodes.preamp) {
          eqNodes.preamp.gain.value = Math.max(0.1, Math.min(2.5, 1.0 + Number(data.preamp) / 10));
        }
      }
      break;
    }
  }
});

// Trigger pywebviewready event when DOM is ready
window.addEventListener('DOMContentLoaded', () => {
  window.dispatchEvent(new Event('pywebviewready'));
});
