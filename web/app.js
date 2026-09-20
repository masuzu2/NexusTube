/**
 * NexusTube — Modern OLED Web Desktop Client (ui-ux-pro-max-skill)
 * Connected via native Python-JS pywebview Bridge.
 */

// Global State
const state = {
  apiReady: false,
  config: {
    accent: "#22C55E",
    lang: "th",
    format: "mp3_320",
    embed_thumb: true,
    embed_meta: true,
    embed_lyrics: false,
    sponsorblock: true,
    normalize: false,
    outdir: "",
    discord_rpc: true,
    global_hotkeys: true,
    system_tray: true,
    minimize_to_tray: false,
  },
  locales: {},
  accentPalette: {},
  activeTab: "search",
  currentFormat: "mp3_320",
  isSeeking: false,
  librarySort: "date",
  libraryViewMode: "grid",
  favoritesOnly: false,
  playbackSpeed: 1.0,
  dsp: { preamp: 0.0, bass_boost: 0.0, surround: false },
  sleepTimer: { active: false, minutes: 0, endsAt: null, intervalId: null, endOfTrack: false, fading: false },
  lyricsFontSize: 16,
  recentSearches: [],
  discordRpc: { enabled: true, connected: false },
  miniPlayer: false,
  miniPlayerToggling: false,
  normalizeAudio: false,
  visualizerMode: "neon_bars",
  player: {
    isPlaying: false,
    isPaused: false,
    currentPos: 0,
    duration: 0,
    volume: 0.85,
    isMuted: false,
    repeatMode: "off",
    isShuffle: false,
    currentPath: null,
    info: {},
    lyrics: { synced: [], plain: "", source: "none" },
  },
  eqPresets: {},
  eqBands: { bass: 0, low_mid: 0, mid: 0, high_mid: 0, treble: 0 },
  library: [],
  queue: [],
  activeResolvedUrl: null,
  activePlaylistTracks: [],
  activeTrimTarget: null,
  activeConvertTarget: null,
  activeDeleteTarget: null,
  lastLyricIndex: -1,
  pollTimer: null,
  eqDebounceTimer: null,
};

// ============================================================================
// Initialization & Bridge Connection
// ============================================================================
function initApp() {
  setupNavigation();
  setupFormatSelector();
  setupOptionToggles();
  setupPlayerControls();
  setupEqualizerControls();
  setupWindowControls();
  setupSearchHandlers();
  setupLyricsControls();
  setupModals();
  setupModernFeatures();
  createVisualizerBars();
  startVisualizerLoop();
  setupSpotlightEffect();
  renderAccentPicker();
  renderEqPresets();

  const enginePill = document.getElementById("engine-status-pill");
  if (enginePill) {
    enginePill.onclick = () => {
      switchTab("settings");
      const target = document.getElementById("engine-cards-group");
      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "center" });
        target.classList.add("ring-2", "ring-[var(--accent)]");
        setTimeout(() => target.classList.remove("ring-2", "ring-[var(--accent)]"), 1500);
      }
    };
  }

  if (window.pywebview && window.pywebview.api) {
    onBridgeReady();
  } else {
    window.addEventListener("pywebviewready", onBridgeReady);
  }
}

function setupOptionToggles() {
  const optionsMap = [
    { id: "opt-embed-thumb", key: "embed_thumb" },
    { id: "opt-embed-meta", key: "embed_meta" },
    { id: "opt-embed-lyrics", key: "embed_lyrics" },
    { id: "opt-sponsorblock", key: "sponsorblock" },
    { id: "opt-loudnorm", key: "normalize" },
  ];
  optionsMap.forEach(({ id, key }) => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener("change", () => {
        saveConfig({ [key]: el.checked });
      });
    }
  });
}

async function onBridgeReady() {
  state.apiReady = true;
  console.log("[NexusTube] Bridge API connected successfully.");
  try {
    const initData = await window.pywebview.api.get_initial_state();
    if (initData) {
      if (initData.version) {
        const badge = document.getElementById("app-version-badge");
        if (badge) badge.textContent = `v${initData.version}`;
      }
      if (initData.config) state.config = { ...state.config, ...initData.config };
      if (initData.locales) state.locales = initData.locales;
      if (initData.accents) state.accentPalette = initData.accents;
      if (initData.eq_presets) state.eqPresets = initData.eq_presets;
      if (initData.eq_bands) state.eqBands = initData.eq_bands;

      applyThemeAccent(state.config.accent);
      applyLanguage(state.config.lang || "th");
      renderAccentPicker();
      renderEqPresets();
      updateEngineStatus(initData.engine_status);

      // Sync checkboxes with persisted config
      const optThumb = document.getElementById("opt-embed-thumb");
      if (optThumb && state.config.embed_thumb !== undefined) optThumb.checked = !!state.config.embed_thumb;
      const optMeta = document.getElementById("opt-embed-meta");
      if (optMeta && state.config.embed_meta !== undefined) optMeta.checked = !!state.config.embed_meta;
      const optLyr = document.getElementById("opt-embed-lyrics");
      if (optLyr && state.config.embed_lyrics !== undefined) optLyr.checked = !!state.config.embed_lyrics;
      const optSb = document.getElementById("opt-sponsorblock");
      if (optSb && state.config.sponsorblock !== undefined) optSb.checked = !!state.config.sponsorblock;
      const optNorm = document.getElementById("opt-loudnorm");
      if (optNorm && state.config.normalize !== undefined) optNorm.checked = !!state.config.normalize;

      // Sync Discord RPC
      if (initData.discord_rpc) {
        state.discordRpc = initData.discord_rpc;
        const optDiscord = document.getElementById("setting-discord-rpc");
        if (optDiscord) optDiscord.checked = !!initData.discord_rpc.enabled;
        updateDiscordRpcPill(initData.discord_rpc);
      }

      // Sync Global Hotkeys & System Tray
      const optHotkeys = document.getElementById("setting-global-hotkeys");
      if (optHotkeys && state.config.global_hotkeys !== undefined) optHotkeys.checked = !!state.config.global_hotkeys;
      const optTray = document.getElementById("setting-system-tray");
      if (optTray && state.config.system_tray !== undefined) optTray.checked = !!state.config.system_tray;
      const optMinTray = document.getElementById("setting-minimize-to-tray");
      if (optMinTray && state.config.minimize_to_tray !== undefined) optMinTray.checked = !!state.config.minimize_to_tray;

      // Sync Audio Normalization
      const isNorm = !!(initData.normalize || state.config.normalize);
      syncNormalizationUI(isNorm);

      // Sync Mini-Player state
      if (initData.mini_player) {
        syncMiniPlayerUI(true);
      }

      // Sync yt-dlp version in settings
      const ytdlpVer = (initData.engine_status && initData.engine_status.ytdlp_version) || "Ready";
      const curVerEl = document.getElementById("setting-ytdlp-current-ver");
      if (curVerEl) curVerEl.textContent = ytdlpVer;

      // Sync Sleep Timer state
      if (initData.sleep_timer && initData.sleep_timer.active) {
        state.sleepTimer = {
          active: true,
          minutes: Math.ceil((initData.sleep_timer.remaining_seconds || 0) / 60),
          endsAt: Date.now() + (initData.sleep_timer.remaining_seconds || 0) * 1000,
          endOfTrack: initData.sleep_timer.mode === "end_of_track",
          fading: !!initData.sleep_timer.fading,
        };
        updateSleepTimerUI();
      }

      // Sync EQ sliders & preset label
      const presetLabel = document.getElementById("current-eq-preset-label");
      if (presetLabel && state.config.eq_preset) presetLabel.textContent = state.config.eq_preset;
      if (state.eqBands) {
        Object.entries(state.eqBands).forEach(([bKey, val]) => {
          const sld = document.querySelector(`.eq-slider[data-band="${bKey}"]`);
          if (sld) sld.value = val;
          const lbl = document.getElementById(`eq-val-${bKey}`);
          if (lbl) lbl.textContent = `${val >= 0 ? "+" : ""}${Number(val).toFixed(1)} dB`;
        });
        drawEqCurve();
      }

      if (state.config.format) {
        selectFormat(state.config.format);
      }
      if (state.config.outdir) {
        document.getElementById("quick-folder-path").textContent = state.config.outdir;
        document.getElementById("setting-outdir").value = state.config.outdir;
      }
    }

    // Start background polling loop for queue and player status
    startPollingLoop();
    refreshLibrary();
    refreshQueue();
  } catch (err) {
    console.error("[NexusTube] Initial state load error:", err);
    showToast("Failed to initialize app state from backend engine.", "error");
  }
}

// ============================================================================
// Dynamic Theme Accent & Styling
// ============================================================================
function hexToRgb(hex) {
  const clean = hex.replace("#", "");
  const num = parseInt(clean, 16);
  return {
    r: (num >> 16) & 255,
    g: (num >> 8) & 255,
    b: num & 255,
  };
}

function applyThemeAccent(hexColor) {
  state.config.accent = hexColor;
  const rgb = hexToRgb(hexColor);
  const rgbStr = `${rgb.r}, ${rgb.g}, ${rgb.b}`;

  document.documentElement.style.setProperty("--accent", hexColor);
  document.documentElement.style.setProperty("--accent-rgb", rgbStr);
  document.documentElement.style.setProperty("--accent-glow", `rgba(${rgbStr}, 0.35)`);
  document.documentElement.style.setProperty("--accent-glow-subtle", `rgba(${rgbStr}, 0.15)`);
  document.documentElement.style.setProperty("--accent-glow-high", `rgba(${rgbStr}, 0.55)`);

  // Update canvas curve if on EQ page
  drawEqCurve();
}

function renderAccentPicker() {
  const container = document.getElementById("accent-colors-container");
  if (!container) return;
  container.innerHTML = "";

  const defaultPal = {
    Green: { color: "#22C55E" },
    Indigo: { color: "#6366F1" },
    Pink: { color: "#EC4899" },
    Cyan: { color: "#06B6D4" },
    Amber: { color: "#F59E0B" },
    Purple: { color: "#A855F7" },
  };
  const palette = Object.keys(state.accentPalette).length > 0 ? state.accentPalette : defaultPal;

  Object.entries(palette).forEach(([name, meta]) => {
    const btn = document.createElement("button");
    const color = meta.color;
    btn.className = "w-9 h-9 rounded-full transition-transform hover:scale-110 cursor-pointer relative flex items-center justify-center";
    btn.style.backgroundColor = color;
    btn.title = name;

    if (color.toLowerCase() === state.config.accent.toLowerCase()) {
      btn.classList.add("ring-4", "ring-white/40", "scale-110");
      btn.innerHTML = '<span class="w-2.5 h-2.5 rounded-full bg-white"></span>';
    }

    btn.onclick = () => {
      applyThemeAccent(color);
      renderAccentPicker();
      saveConfig({ accent: color });
      showToast(`Theme accent changed to ${name}`);
    };
    container.appendChild(btn);
  });
}

// ============================================================================
// Bilingual Localization Engine (EN / TH)
// ============================================================================
function t(key) {
  const lang = state.config.lang || "th";
  if (state.locales && state.locales[key] && state.locales[key][lang]) {
    return state.locales[key][lang];
  }
  return key;
}

function applyLanguage(lang) {
  state.config.lang = lang;
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (key) {
      el.textContent = t(key);
    }
  });

  // Update active state on language buttons
  document.querySelectorAll(".lang-btn").forEach((btn) => {
    if (btn.getAttribute("data-lang") === lang) {
      btn.classList.add("border-[var(--accent)]", "bg-white/[0.12]");
      btn.classList.remove("border-transparent");
    } else {
      btn.classList.remove("border-[var(--accent)]", "bg-white/[0.12]");
      btn.classList.add("border-transparent");
    }
  });
}

// ============================================================================
// Navigation Tabs
// ============================================================================
function setupNavigation() {
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.getAttribute("data-tab");
      if (tab) switchTab(tab);
    });
  });
}

function switchTab(tabId) {
  state.activeTab = tabId;
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.classList.toggle("active", btn.getAttribute("data-tab") === tabId);
  });

  document.querySelectorAll(".page-view").forEach((p) => {
    p.classList.add("hidden");
  });

  const targetPage = document.getElementById(`page-${tabId}`);
  if (targetPage) {
    targetPage.classList.remove("hidden");
    targetPage.classList.add("animate-fadeIn");
  }

  if (tabId === "library") refreshLibrary();
  if (tabId === "queue") refreshQueue();
  if (tabId === "equalizer") requestAnimationFrame(() => drawEqCurve());
  if (tabId === "lyrics") renderLyricsView();

  const quickLyrics = document.getElementById("btn-quick-lyrics");
  if (quickLyrics) {
    quickLyrics.classList.toggle("text-[var(--accent)]", tabId === "lyrics");
    quickLyrics.classList.toggle("text-slate-400", tabId !== "lyrics");
  }
  const quickEq = document.getElementById("btn-quick-eq");
  if (quickEq) {
    quickEq.classList.toggle("text-[var(--accent)]", tabId === "equalizer");
    quickEq.classList.toggle("text-slate-400", tabId !== "equalizer");
  }
}

// ============================================================================
// Format Selector
// ============================================================================
function setupFormatSelector() {
  document.querySelectorAll(".fmt-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const fmt = btn.getAttribute("data-fmt");
      if (fmt) {
        selectFormat(fmt);
        saveConfig({ format: fmt });
      }
    });
  });
}

function selectFormat(fmtKey) {
  state.currentFormat = fmtKey;
  document.querySelectorAll(".fmt-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.getAttribute("data-fmt") === fmtKey);
  });
  const map = {
    mp3_320: "MP3 320kbps Extreme CBR",
    m4a_best: "M4A / AAC Source Quality",
    flac: "FLAC Lossless Studio Audio",
    mp4_best: "MP4 4K / Best Video",
    mp4_1080: "MP4 1080p Full HD",
    mp4_720: "MP4 720p HD",
  };
  const tagEl = document.getElementById("format-tag-preview");
  if (tagEl) tagEl.textContent = map[fmtKey] || fmtKey;
}

// ============================================================================
// Search & URL Auto-Detection
// ============================================================================
function setupSearchHandlers() {
  const input = document.getElementById("search-input");
  const pasteBtn = document.getElementById("btn-paste-search");
  const searchBtn = document.getElementById("btn-execute-search");

  let debounceTimer = null;
  input.addEventListener("input", () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      handleSearchInputChange(input.value.trim());
    }, 350);
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      executeSearch();
    }
  });

  pasteBtn.addEventListener("click", async () => {
    let text = "";
    try {
      text = await navigator.clipboard.readText();
    } catch (e) {
      if (state.apiReady && window.pywebview.api && window.pywebview.api.get_clipboard) {
        text = await window.pywebview.api.get_clipboard();
      }
    }
    if (!text && state.apiReady && window.pywebview.api && window.pywebview.api.get_clipboard) {
      text = await window.pywebview.api.get_clipboard();
    }
    if (text) {
      input.value = text.trim();
      handleSearchInputChange(input.value);
    }
  });

  searchBtn.addEventListener("click", executeSearch);

  // Resolved card buttons
  const previewBtn = document.getElementById("btn-preview-resolved");
  if (previewBtn) {
    previewBtn.addEventListener("click", () => {
      if (state.activeResolvedUrl) {
        streamTrack(state.activeResolvedUrl.url || state.activeResolvedUrl.webpage_url);
      }
    });
  }

  document.getElementById("btn-download-resolved").addEventListener("click", () => {
    if (state.activeResolvedUrl) {
      downloadResolvedItem(state.activeResolvedUrl);
    }
  });

  document.getElementById("btn-trim-resolved").addEventListener("click", () => {
    if (state.activeResolvedUrl) {
      openTrimmerModal(state.activeResolvedUrl.title, state.activeResolvedUrl.url, state.activeResolvedUrl.duration || 0);
    }
  });
}

async function handleSearchInputChange(val) {
  const indicator = document.getElementById("platform-detection-indicator");
  const dot = document.getElementById("platform-dot");
  const text = document.getElementById("platform-text");

  if (!val) {
    indicator.classList.add("hidden");
    document.getElementById("url-resolved-card").classList.add("hidden");
    return;
  }

  if (val.startsWith("http://") || val.startsWith("https://")) {
    indicator.classList.remove("hidden");
    if (val.includes("spotify.com")) {
      dot.className = "w-2 h-2 rounded-full bg-green-500";
      text.textContent = "Spotify Link Detected (Direct Metadata Scraper)";
    } else if (val.includes("apple.com")) {
      dot.className = "w-2 h-2 rounded-full bg-pink-500";
      text.textContent = "Apple Music Link Detected (iTunes Lookup API)";
    } else if (val.includes("soundcloud.com")) {
      dot.className = "w-2 h-2 rounded-full bg-orange-500";
      text.textContent = "SoundCloud Link Detected";
    } else {
      dot.className = "w-2 h-2 rounded-full bg-red-500";
      text.textContent = "YouTube Video / Playlist Link Detected";
    }

    // Auto-resolve single URL or Playlist / Album
    if (state.apiReady) {
      try {
        const res = await window.pywebview.api.resolve_url(val);
        if (res && res.error) {
          showToast(res.error, "warning");
        } else if (res && (res.type === "playlist" || res.type === "album" || res.type === "set" || (res.tracks && res.tracks.length > 1))) {
          openPlaylistModal(res);
        } else if (res && res.title) {
          state.activeResolvedUrl = res;
          showResolvedCard(res);
        }
      } catch (err) {
        console.warn("Resolve URL failed:", err);
      }
    }
  } else {
    indicator.classList.add("hidden");
    document.getElementById("url-resolved-card").classList.add("hidden");
  }
}

function showResolvedCard(res) {
  const card = document.getElementById("url-resolved-card");
  card.classList.remove("hidden");
  document.getElementById("res-card-title").textContent = res.title || "Track Title";
  document.getElementById("res-card-artist").textContent = res.artist || res.uploader || "Artist";
  document.getElementById("res-card-duration").textContent = formatDuration(res.duration || 0);

  const thumbEl = document.getElementById("res-card-thumb");
  if (res.thumbnail) {
    thumbEl.src = res.thumbnail;
  } else {
    thumbEl.src = "";
  }

  const platEl = document.getElementById("res-card-platform");
  platEl.textContent = (res.platform || "Media").toUpperCase();
}

async function executeSearch() {
  const input = document.getElementById("search-input");
  const query = input.value.trim();
  if (!query) return;

  if (query.startsWith("http://") || query.startsWith("https://")) {
    handleSearchInputChange(query);
    return;
  }

  addRecentSearch(query);

  const spinner = document.getElementById("search-spinner");
  spinner.classList.remove("hidden");

  try {
    if (state.apiReady) {
      const results = await window.pywebview.api.search_youtube(query);
      renderSearchResults(results || []);
    }
  } catch (err) {
    console.error("Search error:", err);
    showToast("Search failed: " + err, "error");
  } finally {
    spinner.classList.add("hidden");
  }
}

function renderSearchResults(items) {
  const grid = document.getElementById("results-grid");
  const countBadge = document.getElementById("results-count");
  grid.innerHTML = "";
  countBadge.textContent = items.length;

  if (items.length === 0) {
    grid.innerHTML = '<div class="col-span-full py-10 text-center text-slate-500">No results found.</div>';
    return;
  }

  items.forEach((item) => {
    const card = document.createElement("div");
    card.className = "p-4 rounded-2xl bg-card border border-white/[0.08] hover:border-[var(--accent)] space-y-3 transition-all group card-glass spotlight-card";

    const dur = formatDuration(item.duration || 0);
    const fmtBadge = state.currentFormat.startsWith("mp4")
      ? "badge-red"
      : (state.currentFormat === "flac"
          ? "badge-purple"
          : (state.currentFormat.startsWith("m4a") ? "badge-cyan" : "badge-gold"));
    const fmtText = state.currentFormat.toUpperCase().replace("_", " ");

    card.innerHTML = `
      <div class="relative w-full aspect-video rounded-xl overflow-hidden bg-black/50 group/thumb">
        <img src="${item.thumbnail || ''}" alt="" class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200">
        <div class="absolute inset-0 bg-black/40 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
          <button class="btn-preview-item w-10 h-10 rounded-full bg-[var(--accent)] text-black flex items-center justify-center shadow-lg hover:scale-110 active:scale-95 transition-transform cursor-pointer" title="Preview Stream">
            <svg class="w-5 h-5 fill-current translate-x-0.5" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
          </button>
        </div>
        <div class="absolute top-2 left-2 flex items-center space-x-1">
          <span class="badge-audio ${fmtBadge} text-[9px]">${fmtText}</span>
        </div>
        <span class="absolute bottom-2 right-2 px-2 py-0.5 rounded text-[10px] font-mono bg-black/80 text-white font-semibold">${dur}</span>
      </div>
      <div class="space-y-1">
        <h4 class="text-sm font-bold text-white line-clamp-2 leading-snug" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</h4>
        <p class="text-xs text-slate-400 truncate">${escapeHtml(item.channel || item.uploader || '')}</p>
      </div>
      <div class="flex items-center space-x-2 pt-1">
        <button class="btn-dl-item flex-1 py-2.5 rounded-xl bg-[var(--accent)] text-black font-extrabold text-xs hover:brightness-110 active:scale-95 transition-all flex items-center justify-center space-x-1.5 cursor-pointer shadow-[0_0_12px_var(--accent-glow-subtle)]">
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
          <span>Download</span>
        </button>
      </div>
    `;

    const prevBtn = card.querySelector(".btn-preview-item");
    if (prevBtn) {
      prevBtn.onclick = (e) => {
        e.stopPropagation();
        streamTrack(item.url || item.webpage_url);
      };
    }

    card.querySelector(".btn-dl-item").addEventListener("click", () => {
      addDownloadTask(item.url || item.webpage_url, item.title, {
        artist: item.channel || item.uploader || "",
        thumbnail: item.thumbnail || "",
      });
    });

    grid.appendChild(card);
  });
}

function downloadResolvedItem(res) {
  addDownloadTask(res.url, res.title, {
    artist: res.artist || res.uploader || "",
    album: res.album || "NexusTube Collection",
    track_num: res.track_num || 1,
    thumbnail: res.thumbnail || "",
  });
}

// ============================================================================
// Download Queue Management
// ============================================================================
async function addDownloadTask(url, title, metadata = {}) {
  if (!state.apiReady) return;

  const options = {
    embed_thumb: document.getElementById("opt-embed-thumb").checked,
    embed_meta: document.getElementById("opt-embed-meta").checked,
    embed_lyrics: document.getElementById("opt-embed-lyrics").checked,
    sponsorblock: document.getElementById("opt-sponsorblock").checked,
    normalize: document.getElementById("opt-loudnorm").checked,
  };

  try {
    const res = await window.pywebview.api.add_to_queue(url, title, state.currentFormat, options, metadata);
    showToast(`Added to queue: ${title || url}`, "success");
    switchTab("queue");
    refreshQueue();
  } catch (err) {
    console.error("Queue add error:", err);
    showToast("Failed to queue download: " + err, "error");
  }
}

async function refreshQueue() {
  if (!state.apiReady) return;
  try {
    const queue = await window.pywebview.api.get_queue_state();
    state.queue = queue || [];
    renderQueueList(state.queue);
  } catch (err) {
    console.warn("Queue fetch error:", err);
  }
}

function renderQueueList(tasks) {
  const listEl = document.getElementById("queue-tasks-list");
  const placeholder = document.getElementById("queue-empty-placeholder");
  const badge = document.getElementById("queue-badge");
  const statsBar = document.getElementById("queue-stats-bar");
  const statTotal = document.getElementById("queue-stat-total");
  const statActive = document.getElementById("queue-stat-active");
  const statCompleted = document.getElementById("queue-stat-completed");

  const completedCount = tasks.filter((t) => t.status === "completed").length;
  const activeCount = tasks.filter((t) => t.status === "downloading" || t.status === "waiting" || t.status === "processing").length;

  if (activeCount > 0) {
    badge.classList.remove("hidden");
    badge.textContent = activeCount;
  } else {
    badge.classList.add("hidden");
  }

  if (statsBar) {
    if (tasks && tasks.length > 0) {
      statsBar.classList.remove("hidden");
      if (statTotal) statTotal.textContent = tasks.length;
      if (statActive) statActive.textContent = activeCount;
      if (statCompleted) statCompleted.textContent = completedCount;
    } else {
      statsBar.classList.add("hidden");
    }
  }

  if (!tasks || tasks.length === 0) {
    listEl.innerHTML = "";
    placeholder.classList.remove("hidden");
    return;
  }

  placeholder.classList.add("hidden");
  listEl.innerHTML = "";

  tasks.forEach((task) => {
    const card = document.createElement("div");
    card.className = "p-4 rounded-2xl bg-card border border-white/[0.06] space-y-3 card-glass";

    let statusPill = "";
    let progColor = "bg-[var(--accent)]";
    if (task.status === "completed") {
      statusPill = `<span class="px-2.5 py-0.5 rounded-md text-[10px] font-bold bg-green-500/20 text-green-400 border border-green-500/30">${t("Complete ✓")}</span>`;
    } else if (task.status === "downloading") {
      const pctVal = ((task.percent || 0) * 100).toFixed(0);
      statusPill = `<span class="px-2.5 py-0.5 rounded-md text-[10px] font-bold bg-[var(--accent)]/20 text-[var(--accent)] border border-[var(--accent)]/30 animate-pulse">${t("Downloading")} · ${pctVal}%</span>`;
    } else if (task.status === "processing") {
      statusPill = `<span class="px-2.5 py-0.5 rounded-md text-[10px] font-bold bg-purple-500/20 text-purple-400 border border-purple-500/30">${t("Processing Tags…")}</span>`;
    } else if (task.status === "cancelled") {
      statusPill = `<span class="px-2.5 py-0.5 rounded-md text-[10px] font-bold bg-white/[0.08] text-slate-400 border border-white/[0.08]">${t("Cancelled")}</span>`;
      progColor = "bg-slate-600";
    } else if (task.status === "failed") {
      statusPill = `<span class="px-2.5 py-0.5 rounded-md text-[10px] font-bold bg-red-500/20 text-red-400 border border-red-500/30">${t("Failed ✗")}</span>`;
      progColor = "bg-red-500";
    } else {
      statusPill = `<span class="px-2.5 py-0.5 rounded-md text-[10px] font-bold bg-amber-500/20 text-amber-400 border border-amber-500/30">${t("Waiting…")}</span>`;
    }

    const pct = Math.max(0, Math.min(100, (task.percent || 0) * 100));

    // Cover art / thumbnail preview
    let thumbHtml = "";
    if (task.thumbnail) {
      thumbHtml = `
        <div class="w-14 h-14 rounded-xl overflow-hidden bg-white/[0.04] border border-white/[0.08] flex items-center justify-center text-slate-400 flex-shrink-0 relative shadow-md">
          <img src="${escapeHtml(task.thumbnail)}" class="w-full h-full object-cover" onerror="this.style.display='none'; if(this.nextElementSibling) this.nextElementSibling.style.display='flex';">
          <div class="w-full h-full items-center justify-center text-slate-500" style="display: none;">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
          </div>
        </div>
      `;
    } else {
      thumbHtml = `
        <div class="w-14 h-14 rounded-xl bg-white/[0.04] border border-white/[0.08] flex items-center justify-center text-slate-400 flex-shrink-0 shadow-md">
          <svg class="w-6 h-6" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
        </div>
      `;
    }

    const speedLbl = t("Speed");
    const etaLbl = t("ETA");
    const speedPart = task.speed ? `${speedLbl}: ${task.speed}` : "";
    const etaPart = task.eta ? `${etaLbl}: ${task.eta}` : "";
    const metricsStr = [speedPart, etaPart].filter(Boolean).join(" · ");

    let errorDetailHtml = "";
    if (task.status === "failed" && task.error) {
      errorDetailHtml = `
        <div class="px-3 py-2 rounded-xl bg-red-950/40 border border-red-500/25 text-red-300 text-[11px] flex items-start space-x-2 font-mono">
          <span class="text-red-400 flex-shrink-0">⚠️</span>
          <span class="flex-1 overflow-hidden text-ellipsis line-clamp-2">${escapeHtml(task.error)}</span>
        </div>
      `;
    } else if (task.warning) {
      errorDetailHtml = `
        <div class="px-3 py-2 rounded-xl bg-amber-950/40 border border-amber-500/25 text-amber-300 text-[11px] flex items-start space-x-2 font-mono">
          <span class="text-amber-400 flex-shrink-0">ℹ️</span>
          <span class="flex-1 overflow-hidden text-ellipsis line-clamp-2">${escapeHtml(task.warning)}</span>
        </div>
      `;
    }

    card.innerHTML = `
      <div class="flex items-center justify-between">
        <div class="flex items-center space-x-3.5 min-w-0">
          ${thumbHtml}
          <div class="min-w-0">
            <div class="text-sm font-bold text-white truncate">${escapeHtml(task.title || task.url)}</div>
            <div class="text-[11px] text-slate-400 font-mono mt-0.5">${escapeHtml(task.format || '')}</div>
          </div>
        </div>
        <div>${statusPill}</div>
      </div>

      <!-- Progress Bar -->
      <div class="w-full h-1.5 bg-white/[0.06] rounded-full overflow-hidden">
        <div class="h-full ${progColor} transition-[width] duration-150 rounded-full" style="width: ${pct}%"></div>
      </div>

      ${errorDetailHtml}

      <!-- Metrics and Actions -->
      <div class="flex items-center justify-between text-xs text-slate-400 pt-1 font-mono">
        <div class="text-[11px] text-slate-400">${metricsStr}</div>
        <div class="flex items-center space-x-2">
          ${task.status === "downloading" || task.status === "waiting"
            ? `<button class="btn-cancel-task px-3 py-1.5 rounded-xl bg-white/[0.06] hover:bg-red-500/20 hover:text-red-400 text-slate-300 font-bold text-xs transition-colors cursor-pointer border border-white/[0.06]" data-id="${task.id}">${t("Cancel")}</button>`
            : ""}
          ${task.status === "completed" && task.out_file
            ? `<button class="btn-play-task px-3.5 py-1.5 rounded-xl bg-[var(--accent)] text-black font-extrabold text-xs shadow-[0_0_12px_var(--accent-glow)] hover:brightness-110 transition-all cursor-pointer active:scale-95 flex items-center space-x-1.5" data-path="${escapeHtml(task.out_file)}">
                <svg class="w-3.5 h-3.5 fill-current" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                <span>${t("Play")}</span>
              </button>
              <button class="btn-reveal-task px-3.5 py-1.5 rounded-xl bg-white/[0.06] hover:bg-white/[0.12] text-slate-300 font-bold text-xs transition-colors cursor-pointer border border-white/[0.06] flex items-center space-x-1.5" data-path="${escapeHtml(task.out_file)}" title="Open Folder">
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
                <span>${t("Folder")}</span>
              </button>`
            : ""}
          ${task.status === "failed" || task.status === "cancelled"
            ? `<button class="btn-retry-task px-3.5 py-1.5 rounded-xl bg-white/[0.06] hover:bg-white/[0.12] text-white font-bold text-xs transition-colors cursor-pointer border border-white/[0.06]" data-id="${task.id}">${t("Retry")}</button>`
            : ""}
        </div>
      </div>
    `;

    const cancelBtn = card.querySelector(".btn-cancel-task");
    if (cancelBtn) {
      cancelBtn.onclick = async () => {
        await window.pywebview.api.cancel_task(task.id);
        refreshQueue();
      };
    }
    const playBtn = card.querySelector(".btn-play-task");
    if (playBtn) {
      playBtn.onclick = () => {
        playTrack(task.out_file);
      };
    }
    const revealBtn = card.querySelector(".btn-reveal-task");
    if (revealBtn) {
      revealBtn.onclick = () => {
        if (state.apiReady) window.pywebview.api.reveal_file(task.out_file);
      };
    }
    const retryBtn = card.querySelector(".btn-retry-task");
    if (retryBtn) {
      retryBtn.onclick = async () => {
        await window.pywebview.api.retry_task(task.id);
        refreshQueue();
      };
    }

    listEl.appendChild(card);
  });
}

// Clear finished queue tasks
document.getElementById("btn-clear-finished-queue").addEventListener("click", async () => {
  if (state.apiReady) {
    await window.pywebview.api.clear_finished();
    refreshQueue();
  }
});
document.getElementById("btn-open-queue-folder").addEventListener("click", async () => {
  if (state.apiReady) {
    await window.pywebview.api.open_folder(state.config.outdir);
  }
});

// ============================================================================
// Music Library
// ============================================================================
async function refreshLibrary() {
  if (!state.apiReady) return;
  const filterInput = document.getElementById("lib-search-input");
  const query = filterInput ? filterInput.value.trim() : "";
  const sortSelect = document.getElementById("lib-sort-select");
  const sortBy = sortSelect ? sortSelect.value : (state.librarySort || "date");

  try {
    const items = await window.pywebview.api.get_library(query, sortBy);
    state.library = items || [];
    renderLibrary(state.library);
  } catch (err) {
    console.warn("Library refresh error:", err);
  }
}

function renderLibrary(rawItems) {
  const gridContainer = document.getElementById("library-items-container");
  const tableContainer = document.getElementById("library-table-container");
  const tableBody = document.getElementById("library-table-body");
  const placeholder = document.getElementById("library-empty-placeholder");
  const countEl = document.getElementById("lib-total-songs");
  const sizeEl = document.getElementById("lib-total-size");
  const badge = document.getElementById("library-count-badge");

  let items = rawItems || [];
  if (state.favoritesOnly) {
    items = items.filter((item) => !!item.is_favorite);
  }

  if (badge) badge.textContent = rawItems ? rawItems.length : 0;
  if (countEl) {
    countEl.textContent = state.favoritesOnly
      ? `${items.length} favorites (${rawItems.length} total)`
      : `${items.length} tracks`;
  }

  const totalBytes = items.reduce((sum, item) => sum + (item.size_bytes || 0), 0);
  if (sizeEl) sizeEl.textContent = formatBytes(totalBytes);

  if (!items || items.length === 0) {
    if (gridContainer) gridContainer.innerHTML = "";
    if (tableBody) tableBody.innerHTML = "";
    if (gridContainer) gridContainer.classList.add("hidden");
    if (tableContainer) tableContainer.classList.add("hidden");
    if (placeholder) placeholder.classList.remove("hidden");
    return;
  }

  if (placeholder) placeholder.classList.add("hidden");

  const isTable = state.libraryViewMode === "table";
  if (isTable) {
    if (gridContainer) gridContainer.classList.add("hidden");
    if (tableContainer) tableContainer.classList.remove("hidden");
    renderLibraryTable(items, tableBody);
  } else {
    if (tableContainer) tableContainer.classList.add("hidden");
    if (gridContainer) gridContainer.classList.remove("hidden");
    renderLibraryGrid(items, gridContainer);
  }
}

function renderLibraryGrid(items, container) {
  container.innerHTML = "";

  items.forEach((item) => {
    const card = document.createElement("div");
    card.dataset.path = item.path || "";
    card.className = "p-4 rounded-2xl bg-card border border-white/[0.08] hover:border-[var(--accent)] space-y-3 transition-all group card-glass spotlight-card";

    const dur = formatDuration(item.duration || 0);
    const size = formatBytes(item.size_bytes || 0);
    const fmt = (item.format || "MP3").toUpperCase();
    let badgeClass = "badge-gold";
    if (fmt.includes("FLAC")) badgeClass = "badge-purple";
    else if (fmt.includes("M4A") || fmt.includes("AAC")) badgeClass = "badge-cyan";
    else if (fmt.includes("MP4")) badgeClass = "badge-red";

    const isFav = !!item.is_favorite;

    card.innerHTML = `
      <div class="relative w-full aspect-square rounded-xl overflow-hidden bg-white/[0.03] group/thumb">
        ${item.cover_base64
          ? `<img src="${item.cover_base64}" class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200" alt="">`
          : `<div class="w-full h-full flex items-center justify-center bg-white/[0.03] text-slate-500 group-hover:text-[var(--accent)] transition-colors"><svg class="w-12 h-12" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path d="M9 18V5l12-2v13"></path><circle cx="6" cy="18" r="3"></circle><circle cx="18" cy="16" r="3"></circle></svg></div>`}
        <div class="absolute inset-0 bg-black/40 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
          <button class="btn-play-card w-12 h-12 rounded-full bg-[var(--accent)] text-black flex items-center justify-center shadow-[0_0_20px_var(--accent-glow)] hover:scale-110 active:scale-95 transition-transform cursor-pointer">
            <svg class="w-6 h-6 fill-current translate-x-0.5" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
          </button>
        </div>
        <div class="absolute top-2 left-2 flex items-center space-x-1">
          <span class="badge-audio ${badgeClass} text-[9px]">${escapeHtml(fmt)}</span>
        </div>
        <button class="favorite-btn ${isFav ? 'is-favorite' : ''} absolute top-2 right-2 p-1.5 rounded-lg bg-black/60 hover:bg-black/80 text-white transition-all cursor-pointer z-10" title="Favorite">
          <svg class="w-4 h-4 ${isFav ? 'fill-red-500 text-red-500' : 'text-white'}" fill="${isFav ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>
        </button>
        <span class="absolute bottom-2 right-2 px-2 py-0.5 rounded text-[10px] font-mono bg-black/80 text-white font-semibold">${dur}</span>
      </div>
      <div class="space-y-0.5 min-w-0">
        <h4 class="text-sm font-bold text-white truncate" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</h4>
        <p class="text-xs text-slate-400 truncate">${escapeHtml(item.artist || 'Local Audio')}</p>
      </div>
      <div class="flex items-center justify-between pt-1.5 border-t border-white/[0.04]">
        <span class="text-[10px] font-mono text-slate-400 uppercase">${size}</span>
        <div class="flex items-center space-x-1">
          <button class="btn-reveal-card p-1.5 rounded-lg hover:bg-white/[0.08] text-slate-400 hover:text-white cursor-pointer" title="Reveal in Explorer">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
          </button>
          <button class="btn-convert-card p-1.5 rounded-lg hover:bg-white/[0.08] text-slate-400 hover:text-white cursor-pointer" title="Convert Audio">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
          </button>
          <button class="btn-trim-card p-1.5 rounded-lg hover:bg-white/[0.08] text-slate-400 hover:text-white cursor-pointer" title="Trim Slice">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="6" cy="6" r="3"></circle><circle cx="6" cy="18" r="3"></circle><line x1="20" y1="4" x2="8.12" y2="15.88"></line><line x1="14.47" y1="14.48" x2="20" y2="20"></line><line x1="8.12" y1="8.12" x2="12" y2="12"></line></svg>
          </button>
          <button class="btn-delete-card p-1.5 rounded-lg hover:bg-red-500/20 text-slate-400 hover:text-red-400 cursor-pointer" title="Delete Track">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
          </button>
        </div>
      </div>
    `;

    card.querySelector(".btn-play-card").onclick = () => playTrack(item.path);
    card.querySelector(".favorite-btn").onclick = async (e) => {
      e.stopPropagation();
      await toggleTrackFavorite(item.path);
    };
    card.querySelector(".btn-reveal-card").onclick = () => {
      if (state.apiReady) window.pywebview.api.reveal_file(item.path);
    };
    card.querySelector(".btn-convert-card").onclick = () => openConverterModal(item.title, item.path);
    card.querySelector(".btn-trim-card").onclick = () => openTrimmerModal(item.title, item.path, item.duration || 0);
    card.querySelector(".btn-delete-card").onclick = () => openDeleteModal(item.path, item.title);

    container.appendChild(card);
  });
}

function renderLibraryTable(items, tbody) {
  tbody.innerHTML = "";

  items.forEach((item, idx) => {
    const row = document.createElement("tr");
    row.dataset.path = item.path || "";
    row.className = "library-table-row border-b border-white/[0.04] hover:bg-white/[0.03] transition-colors group";

    const dur = formatDuration(item.duration || 0);
    const size = formatBytes(item.size_bytes || 0);
    const fmt = (item.format || "MP3").toUpperCase();
    const isFav = !!item.is_favorite;

    row.innerHTML = `
      <td class="py-3 px-4 text-center font-mono text-slate-500 text-xs">${idx + 1}</td>
      <td class="py-3 px-3">
        <div class="flex items-center space-x-3 min-w-0">
          <div class="w-10 h-10 rounded-lg overflow-hidden bg-white/[0.03] flex-shrink-0 relative">
            ${item.cover_base64
              ? `<img src="${item.cover_base64}" class="w-full h-full object-cover" alt="">`
              : `<div class="w-full h-full flex items-center justify-center text-slate-500"><svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path d="M9 18V5l12-2v13"></path><circle cx="6" cy="18" r="3"></circle><circle cx="18" cy="16" r="3"></circle></svg></div>`}
            <button class="btn-play-row absolute inset-0 bg-black/60 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer">
              <svg class="w-4 h-4 fill-white translate-x-0.5" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
            </button>
          </div>
          <div class="min-w-0">
            <div class="font-bold text-white truncate max-w-xs md:max-w-md cursor-pointer hover:text-[var(--accent)]" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</div>
            <div class="text-[11px] text-slate-400 truncate">${escapeHtml(item.artist || 'Local Audio')}</div>
          </div>
        </div>
      </td>
      <td class="py-3 px-3 text-center">
        <span class="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-white/[0.06] text-slate-300 border border-white/[0.06]">${escapeHtml(fmt)}</span>
      </td>
      <td class="py-3 px-3 text-right font-mono text-slate-300">${dur}</td>
      <td class="py-3 px-3 text-right font-mono text-slate-400 text-[11px]">${size}</td>
      <td class="py-3 px-4 text-center">
        <div class="flex items-center justify-center space-x-1">
          <button class="favorite-btn ${isFav ? 'is-favorite' : ''} p-1.5 rounded-lg hover:bg-white/[0.08] text-slate-400 hover:text-red-400 transition-colors cursor-pointer" title="Favorite">
            <svg class="w-3.5 h-3.5 ${isFav ? 'fill-red-500 text-red-500' : ''}" fill="${isFav ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>
          </button>
          <button class="btn-reveal-row p-1.5 rounded-lg hover:bg-white/[0.08] text-slate-400 hover:text-white cursor-pointer" title="Reveal in Explorer">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
          </button>
          <button class="btn-convert-row p-1.5 rounded-lg hover:bg-white/[0.08] text-slate-400 hover:text-white cursor-pointer" title="Convert Audio">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
          </button>
          <button class="btn-trim-row p-1.5 rounded-lg hover:bg-white/[0.08] text-slate-400 hover:text-white cursor-pointer" title="Trim Slice">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="6" cy="6" r="3"></circle><circle cx="6" cy="18" r="3"></circle><line x1="20" y1="4" x2="8.12" y2="15.88"></line><line x1="14.47" y1="14.48" x2="20" y2="20"></line><line x1="8.12" y1="8.12" x2="12" y2="12"></line></svg>
          </button>
          <button class="btn-delete-row p-1.5 rounded-lg hover:bg-red-500/20 text-slate-400 hover:text-red-400 cursor-pointer" title="Delete Track">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
          </button>
        </div>
      </td>
    `;

    row.querySelector(".btn-play-row").onclick = () => playTrack(item.path);
    row.ondblclick = () => playTrack(item.path);
    row.querySelector(".favorite-btn").onclick = async (e) => {
      e.stopPropagation();
      await toggleTrackFavorite(item.path);
    };
    row.querySelector(".btn-reveal-row").onclick = () => {
      if (state.apiReady) window.pywebview.api.reveal_file(item.path);
    };
    row.querySelector(".btn-convert-row").onclick = () => openConverterModal(item.title, item.path);
    row.querySelector(".btn-trim-row").onclick = () => openTrimmerModal(item.title, item.path, item.duration || 0);
    row.querySelector(".btn-delete-row").onclick = () => openDeleteModal(item.path, item.title);

    tbody.appendChild(row);
  });
}

async function toggleTrackFavorite(filepath) {
  if (!state.apiReady || !filepath) return;
  try {
    const isFav = await window.pywebview.api.toggle_favorite(filepath);
    showToast(isFav ? "Added to Favorites ❤️" : "Removed from Favorites");
    refreshLibrary();
  } catch (err) {
    console.warn("Favorite toggle error:", err);
  }
}

document.getElementById("btn-refresh-library").addEventListener("click", refreshLibrary);
document.getElementById("lib-search-input").addEventListener("input", () => {
  refreshLibrary();
});
const sortSelectEl = document.getElementById("lib-sort-select");
if (sortSelectEl) {
  sortSelectEl.addEventListener("change", () => {
    state.librarySort = sortSelectEl.value;
    refreshLibrary();
  });
}

// ============================================================================
// Docked Audio Player Controller
// ============================================================================
function setupPlayerControls() {
  const playPauseBtn = document.getElementById("btn-play-pause");
  const stopBtn = document.getElementById("btn-stop");
  const prevBtn = document.getElementById("btn-prev");
  const nextBtn = document.getElementById("btn-next");
  const shuffleBtn = document.getElementById("btn-shuffle");
  const repeatBtn = document.getElementById("btn-repeat");
  const seekRange = document.getElementById("seek-range");
  const volumeRange = document.getElementById("volume-range");
  const muteBtn = document.getElementById("btn-volume-mute");

  playPauseBtn.onclick = async () => {
    if (state.apiReady) {
      await window.pywebview.api.player_control("play_pause", null);
      updatePlayerUI();
    }
  };

  if (stopBtn) {
    stopBtn.onclick = async () => {
      if (state.apiReady) {
        await window.pywebview.api.player_control("stop", null);
        state.player.isPlaying = false;
        state.player.isPaused = false;
        state.player.currentPos = 0;
        seekRange.value = 0;
        document.getElementById("seek-bar-fill").style.width = "0%";
        document.getElementById("time-current").textContent = "00:00";
        updatePlayerUI();
      }
    };
  }

  prevBtn.onclick = async () => {
    if (state.apiReady) {
      await window.pywebview.api.player_control("prev", null);
      updatePlayerUI();
    }
  };

  nextBtn.onclick = async () => {
    if (state.apiReady) {
      await window.pywebview.api.player_control("next", null);
      updatePlayerUI();
    }
  };

  shuffleBtn.onclick = async () => {
    if (state.apiReady) {
      const isShuffle = await window.pywebview.api.player_control("toggle_shuffle", null);
      state.player.isShuffle = isShuffle;
      updatePlayerUI();
      showToast(isShuffle ? "Shuffle: Enabled" : "Shuffle: Disabled");
    }
  };

  repeatBtn.onclick = async () => {
    if (state.apiReady) {
      const mode = await window.pywebview.api.player_control("toggle_repeat", null);
      state.player.repeatMode = mode;
      updatePlayerUI();
      const label = mode === "all" ? "Repeat: All (Loop List)" : (mode === "one" ? "Repeat: Current Track" : "Repeat: Off");
      showToast(label);
    }
  };

  // Anti-jitter seek controls with global mouseup/touchend release
  const onSeekEnd = async () => {
    if (!state.isSeeking) return;
    state.isSeeking = false;
    const targetSec = parseFloat(seekRange.value);
    if (state.apiReady) {
      await window.pywebview.api.player_control("seek", targetSec);
    }
  };
  const onSeekStart = () => {
    state.isSeeking = true;
    const onWindowRelease = async () => {
      window.removeEventListener("mouseup", onWindowRelease);
      window.removeEventListener("touchend", onWindowRelease);
      await onSeekEnd();
    };
    window.addEventListener("mouseup", onWindowRelease);
    window.addEventListener("touchend", onWindowRelease, { passive: true });
  };

  seekRange.addEventListener("mousedown", onSeekStart);
  seekRange.addEventListener("touchstart", onSeekStart, { passive: true });
  seekRange.addEventListener("mouseup", onSeekEnd);
  seekRange.addEventListener("touchend", onSeekEnd, { passive: true });
  seekRange.addEventListener("change", onSeekEnd);
  seekRange.addEventListener("input", () => {
    const targetSec = parseFloat(seekRange.value);
    document.getElementById("time-current").textContent = formatDuration(targetSec);
    const dur = state.player.duration || 100;
    const pct = dur > 0 ? (targetSec / dur) * 100 : 0;
    document.getElementById("seek-bar-fill").style.width = `${pct}%`;
  });

  volumeRange.oninput = async () => {
    const vol = parseFloat(volumeRange.value);
    state.player.volume = vol;
    if (vol > 0 && state.player.isMuted) {
      state.player.isMuted = false;
    }
    document.getElementById("icon-vol-high").classList.toggle("hidden", !!state.player.isMuted);
    document.getElementById("icon-vol-mute").classList.toggle("hidden", !state.player.isMuted);
    if (state.apiReady) {
      await window.pywebview.api.player_control("set_volume", vol);
    }
  };

  const quickLyricsBtn = document.getElementById("btn-quick-lyrics");
  if (quickLyricsBtn) {
    quickLyricsBtn.onclick = () => switchTab("lyrics");
  }
  const quickEqBtn = document.getElementById("btn-quick-eq");
  if (quickEqBtn) {
    quickEqBtn.onclick = () => switchTab("equalizer");
  }

  const loudnormBtn = document.getElementById("btn-player-loudnorm");
  if (loudnormBtn) {
    loudnormBtn.onclick = () => toggleNormalization();
  }

  const playerMiniBtn = document.getElementById("btn-player-mini");
  if (playerMiniBtn) {
    playerMiniBtn.onclick = () => toggleMiniPlayer();
  }

  const visualizerBtn = document.getElementById("btn-open-visualizer");
  if (visualizerBtn) {
    visualizerBtn.onclick = () => openFullscreenVisualizer();
  }

  muteBtn.onclick = async () => {
    if (state.apiReady) {
      const muted = await window.pywebview.api.player_control("toggle_mute", null);
      state.player.isMuted = muted;
      document.getElementById("icon-vol-high").classList.toggle("hidden", muted);
      document.getElementById("icon-vol-mute").classList.toggle("hidden", !muted);
    }
  };
}

async function playTrack(filepath) {
  if (!state.apiReady || !filepath) return;
  try {
    const res = await window.pywebview.api.play_track(filepath);
    if (res) {
      showToast(`Playing: ${res.title || 'Track'}`);
      updatePlayerUI();
      refreshLyrics(res.title, res.artist, res.duration, filepath);
    } else {
      showToast("Playback failed: Audio file not found or unsupported format.", "error");
    }
  } catch (err) {
    console.error("Play error:", err);
    showToast("Playback failed: " + err, "error");
  }
}

async function updatePlayerUI() {
  if (!state.apiReady) return;
  try {
    const p = await window.pywebview.api.get_player_state();
    if (!p) return;
    
    // Normalize both snake_case and camelCase on state.player
    state.player.isPlaying = !!p.is_playing;
    state.player.isPaused = !!p.is_paused;
    state.player.is_playing = state.player.isPlaying;
    state.player.is_paused = state.player.isPaused;
    state.player.currentPos = p.current_pos || 0;
    state.player.current_pos = state.player.currentPos;
    state.player.duration = p.duration || 0;
    if (p.volume !== undefined) state.player.volume = p.volume;
    state.player.isMuted = !!p.is_muted;
    if (p.repeat_mode) state.player.repeatMode = p.repeat_mode;
    if (p.is_shuffle !== undefined) state.player.isShuffle = !!p.is_shuffle;
    if (p.info) state.player.info = p.info;

    // Detect automatic track changes (e.g. Loop list progression or next/prev)
    const prevPath = state.player.currentPath;
    if (p.current_path) {
      state.player.currentPath = p.current_path;
      if (prevPath && prevPath !== p.current_path && state.player.isPlaying) {
        if (p.info && p.info.title) {
          refreshLyrics(p.info.title, p.info.artist, p.info.duration, p.current_path);
        }
      }
    }

    // Check end-of-track sleep timer trigger
    if (state.sleepTimer && state.sleepTimer.active && state.sleepTimer.endOfTrack) {
      if ((prevPath && p.current_path && prevPath !== p.current_path) || (!state.player.isPlaying && prevPath)) {
        state.sleepTimer.active = false;
        state.sleepTimer.endOfTrack = false;
        if (state.apiReady) {
          window.pywebview.api.player_control("pause", null);
        }
        updateSleepTimerUI();
        showToast("Sleep timer completed: Track ended, music paused. 🌙");
      }
    }

    // Synchronize Repeat Button & Badge
    const repeatBtn = document.getElementById("btn-repeat");
    const repeatBadge = document.getElementById("repeat-mode-badge");
    if (repeatBtn && repeatBadge) {
      const mode = state.player.repeatMode || "off";
      if (mode === "one") {
        repeatBadge.classList.remove("hidden");
        repeatBadge.textContent = "1";
        repeatBtn.classList.add("text-[var(--accent)]");
        repeatBtn.classList.remove("text-slate-400");
        repeatBtn.title = "Repeat: One Track";
      } else if (mode === "all") {
        repeatBadge.classList.remove("hidden");
        repeatBadge.textContent = "ALL";
        repeatBtn.classList.add("text-[var(--accent)]");
        repeatBtn.classList.remove("text-slate-400");
        repeatBtn.title = "Repeat: All (Loop List)";
      } else {
        repeatBadge.classList.add("hidden");
        repeatBtn.classList.remove("text-[var(--accent)]");
        repeatBtn.classList.add("text-slate-400");
        repeatBtn.title = "Repeat: Off (Click to Loop List)";
      }
    }

    // Synchronize Shuffle Button & Indicator
    const shuffleBtn = document.getElementById("btn-shuffle");
    const shuffleDot = document.getElementById("shuffle-dot");
    if (shuffleBtn && shuffleDot) {
      shuffleDot.classList.toggle("hidden", !state.player.isShuffle);
      shuffleBtn.classList.toggle("text-[var(--accent)]", state.player.isShuffle);
      shuffleBtn.classList.toggle("text-slate-400", !state.player.isShuffle);
      shuffleBtn.title = state.player.isShuffle ? "Shuffle: On" : "Shuffle: Off";
    }

    const playIcon = document.getElementById("icon-play");
    const pauseIcon = document.getElementById("icon-pause");

    if (state.player.isPlaying && !state.player.isPaused) {
      playIcon.classList.add("hidden");
      pauseIcon.classList.remove("hidden");
    } else {
      playIcon.classList.remove("hidden");
      pauseIcon.classList.add("hidden");
    }

    const thumbEl = document.getElementById("player-thumb");
    const fallbackEl = document.getElementById("player-thumb-fallback");

    if (p.info && p.info.title) {
      document.getElementById("player-title").textContent = p.info.title;
      document.getElementById("player-artist").textContent = p.info.artist || "NexusTube";
      if (p.info.cover_base64) {
        if (thumbEl) {
          thumbEl.src = p.info.cover_base64;
          thumbEl.classList.remove("hidden");
        }
        if (fallbackEl) fallbackEl.classList.add("hidden");
      } else {
        if (thumbEl) {
          thumbEl.src = "";
          thumbEl.classList.add("hidden");
        }
        if (fallbackEl) fallbackEl.classList.remove("hidden");
      }
    }

    const cur = p.current_pos || 0;
    const dur = p.duration || 0;

    const seekRange = document.getElementById("seek-range");
    const fill = document.getElementById("seek-bar-fill");

    if (!state.isSeeking) {
      seekRange.max = dur > 0 ? dur : 100;
      seekRange.value = cur;
      const pct = dur > 0 ? (cur / dur) * 100 : 0;
      fill.style.width = `${pct}%`;
      document.getElementById("time-current").textContent = formatDuration(cur);
    }
    document.getElementById("time-total").textContent = formatDuration(dur);

    // Sync volume slider & mute icon when not user focused
    const volumeRange = document.getElementById("volume-range");
    if (document.activeElement !== volumeRange && p.volume !== undefined) {
      volumeRange.value = p.volume;
    }
    const isMuted = !!p.is_muted;
    document.getElementById("icon-vol-high").classList.toggle("hidden", isMuted);
    document.getElementById("icon-vol-mute").classList.toggle("hidden", !isMuted);

    // Sync Karaoke lyrics scrolling
    syncLyricsWithPlayback(cur);

    // Dynamic Active Track Highlighting in Library (Grid Cards and Table Rows)
    const activePath = (p.current_path || "").replace(/\\/g, "/").toLowerCase();
    const libCards = document.querySelectorAll("#library-items-container [data-path]");
    if (libCards.length > 0) {
      libCards.forEach((c) => {
        const cardPath = (c.dataset.path || "").replace(/\\/g, "/").toLowerCase();
        const isCurrent = (cardPath === activePath && state.player.isPlaying);
        c.classList.toggle("card-playing", isCurrent);
      });
    }
    const libRows = document.querySelectorAll("#library-table-body [data-path]");
    if (libRows.length > 0) {
      libRows.forEach((r) => {
        const rowPath = (r.dataset.path || "").replace(/\\/g, "/").toLowerCase();
        const isCurrent = (rowPath === activePath && state.player.isPlaying);
        r.classList.toggle("table-row-playing", isCurrent);
      });
    }

    // Sync Fullscreen Karaoke UI if open
    syncFullscreenKaraokeUI(cur, dur, p);

    // Sync Mini-Player HUD & active synchronized lyric line
    if (!state.miniPlayerToggling && p.mini_player !== undefined && p.mini_player !== state.miniPlayer) {
      state.miniPlayer = !!p.mini_player;
      syncMiniPlayerUI(state.miniPlayer);
    }
    syncMiniPlayerUIProgress(cur, dur, p);

    // Sync Fullscreen Ambient Visualizer HUD
    syncFullscreenVisualizerHUD(cur, dur, p);

    // Sync Dynamic Audio Normalization
    if (p.normalize !== undefined && p.normalize !== state.normalizeAudio) {
      syncNormalizationUI(p.normalize);
    }

    // Sync Sleep Timer Countdown & Fading State
    syncSleepTimerState(p);
  } catch (err) {
    console.warn("Player state poll error:", err);
  }
}

// ============================================================================
// Dynamic 16-Bar Spectrum Audio Visualizer (60 FPS Smooth Dynamic)
// ============================================================================
let cachedVisualizerBars = [];

function createVisualizerBars() {
  const container = document.getElementById("visualizer-bars-container");
  if (!container) return;
  container.innerHTML = "";
  cachedVisualizerBars = [];
  for (let i = 0; i < 16; i++) {
    const bar = document.createElement("div");
    bar.className = "vis-bar";
    bar.style.height = "3px";
    container.appendChild(bar);
    cachedVisualizerBars.push(bar);
  }
}

let visAnimFrame = null;
const currentBarHeights = new Array(16).fill(2);

function startVisualizerLoop() {
  function frame() {
    const bars = cachedVisualizerBars.length === 16 ? cachedVisualizerBars : document.querySelectorAll(".vis-bar");
    if (bars && bars.length > 0) {
      const isPlaying = (state.player.isPlaying || state.player.is_playing) && !(state.player.isPaused || state.player.is_paused);
      const vol = (state.player.isMuted || state.player.is_muted) ? 0 : (state.player.volume ?? 0.85);
      const bass = Math.max(-0.5, (state.eqBands.bass || 0) / 12);
      const mid = Math.max(-0.5, (state.eqBands.mid || 0) / 12);
      const treble = Math.max(-0.5, (state.eqBands.treble || 0) / 12);
      const t = performance.now() * 0.007;

      bars.forEach((bar, i) => {
        let targetH = 2;
        if (isPlaying && vol > 0.01) {
          // Band distribution: 0-4 (bass), 5-10 (mids), 11-15 (treble/air)
          let bandGain = 1.0;
          if (i < 5) bandGain = 1.25 * (1 + bass * 0.75);
          else if (i < 11) bandGain = 1.0 * (1 + mid * 0.6);
          else bandGain = 0.85 * (1 + treble * 0.8);

          // Harmonic wave motion + acoustic jitter
          const harmonic = (Math.sin(t * 1.6 + i * 0.45) * 0.4 + 0.6) * (Math.cos(t * 0.9 - i * 0.35) * 0.3 + 0.7);
          const jitter = Math.random() * 0.4 + 0.6;
          const amplitude = harmonic * jitter * bandGain * vol;
          targetH = Math.min(22, Math.max(2, amplitude * 18));
        }
        currentBarHeights[i] += (targetH - currentBarHeights[i]) * 0.32;
        bar.style.height = `${currentBarHeights[i].toFixed(1)}px`;
        if (isPlaying && vol > 0.05) {
          bar.style.boxShadow = `0 -2px 8px var(--accent-glow)`;
        } else {
          bar.style.boxShadow = "none";
        }
      });
    }
    visAnimFrame = requestAnimationFrame(frame);
  }
  if (!visAnimFrame) {
    visAnimFrame = requestAnimationFrame(frame);
  }
}

// ============================================================================
// Studio Equalizer DSP
// ============================================================================
function setupEqualizerControls() {
  document.querySelectorAll(".eq-slider").forEach((sld) => {
    sld.addEventListener("input", (e) => {
      const band = sld.getAttribute("data-band");
      const val = parseFloat(sld.value);
      state.eqBands[band] = val;

      const lbl = document.getElementById(`eq-val-${band}`);
      if (lbl) lbl.textContent = `${val >= 0 ? "+" : ""}${val.toFixed(1)} dB`;

      drawEqCurve();

      // Debounced live FFmpeg filtergraph update
      clearTimeout(state.eqDebounceTimer);
      state.eqDebounceTimer = setTimeout(async () => {
        if (state.apiReady) {
          await window.pywebview.api.set_eq_bands(state.eqBands);
          const presetLbl = document.getElementById("current-eq-preset-label");
          if (presetLbl) presetLbl.textContent = "Custom";
        }
      }, 220);
    });
  });

  document.getElementById("btn-reset-eq").onclick = () => {
    applyEqPreset("Flat");
  };

  // Interactive EQ Canvas Dragging & Touch Support
  const canvas = document.getElementById("eq-curve-canvas");
  if (canvas) {
    let isDragging = false;
    let activeBandIdx = -1;
    const bandKeys = ["bass", "low_mid", "mid", "high_mid", "treble"];

    const handlePointer = (e) => {
      const rect = canvas.getBoundingClientRect();
      const clientX = e.clientX ?? (e.touches && e.touches[0] ? e.touches[0].clientX : 0);
      const clientY = e.clientY ?? (e.touches && e.touches[0] ? e.touches[0].clientY : 0);
      const x = clientX - rect.left;
      const y = clientY - rect.top;
      const w = rect.width || 600;
      const h = rect.height || 120;
      const midY = h / 2;

      if (!isDragging) {
        let closestIdx = 0;
        let minDist = Infinity;
        for (let i = 0; i < bandKeys.length; i++) {
          const ptX = (w / (bandKeys.length - 1)) * i;
          const dist = Math.abs(x - ptX);
          if (dist < minDist) {
            minDist = dist;
            closestIdx = i;
          }
        }
        activeBandIdx = closestIdx;
      }

      const bandKey = bandKeys[activeBandIdx];
      const normalizedY = (y - midY) / (midY - 14);
      const dB = Math.max(-12, Math.min(12, -normalizedY * 14));

      state.eqBands[bandKey] = Math.round(dB * 10) / 10;

      const slider = document.querySelector(`.eq-slider[data-band="${bandKey}"]`);
      if (slider) slider.value = state.eqBands[bandKey];
      const lbl = document.getElementById(`eq-val-${bandKey}`);
      if (lbl) lbl.textContent = `${state.eqBands[bandKey] >= 0 ? "+" : ""}${state.eqBands[bandKey].toFixed(1)} dB`;

      drawEqCurve();

      clearTimeout(state.eqDebounceTimer);
      state.eqDebounceTimer = setTimeout(async () => {
        if (state.apiReady) {
          await window.pywebview.api.set_eq_bands(state.eqBands);
          const presetLbl = document.getElementById("current-eq-preset-label");
          if (presetLbl) presetLbl.textContent = "Custom";
        }
      }, 150);
    };

    canvas.addEventListener("pointerdown", (e) => {
      isDragging = true;
      try { canvas.setPointerCapture(e.pointerId); } catch (_) {}
      handlePointer(e);
    });

    canvas.addEventListener("pointermove", (e) => {
      if (isDragging) {
        handlePointer(e);
      }
    });

    const stopDragging = (e) => {
      if (isDragging) {
        isDragging = false;
        try { canvas.releasePointerCapture(e.pointerId); } catch (_) {}
      }
    };

    canvas.addEventListener("pointerup", stopDragging);
    canvas.addEventListener("pointercancel", stopDragging);

    if (window.ResizeObserver && canvas.parentElement) {
      const ro = new ResizeObserver(() => {
        if (state.activeTab === "equalizer") {
          requestAnimationFrame(drawEqCurve);
        }
      });
      ro.observe(canvas.parentElement);
    }
  }
}

function updateEqPresetButtons(activePreset) {
  document.querySelectorAll("#eq-presets-group button").forEach((b) => {
    const isActive = b.textContent.trim() === activePreset.trim();
    b.classList.toggle("bg-[var(--accent)]", isActive);
    b.classList.toggle("text-black", isActive);
    b.classList.toggle("border-[var(--accent)]", isActive);
    b.classList.toggle("font-bold", isActive);
    b.classList.toggle("bg-white/[0.04]", !isActive);
    b.classList.toggle("text-slate-200", !isActive);
  });
}

function renderEqPresets() {
  const group = document.getElementById("eq-presets-group");
  if (!group) return;
  group.innerHTML = "";

  const presets = Object.keys(state.eqPresets).length > 0 ? state.eqPresets : {
    Flat: { bass: 0, low_mid: 0, mid: 0, high_mid: 0, treble: 0 },
    "Bass Boost": { bass: 7, low_mid: 3, mid: 0, high_mid: -1, treble: 1 },
    "Treble Boost": { bass: -2, low_mid: 0, mid: 1, high_mid: 4, treble: 7 },
    Vocal: { bass: -2, low_mid: 1, mid: 5, high_mid: 4, treble: 1 },
    Club: { bass: 6, low_mid: 2, mid: 0, high_mid: 2, treble: 4 },
    Rock: { bass: 5, low_mid: 3, mid: -1, high_mid: 3, treble: 5 },
  };

  const currentPreset = state.config.eq_preset || "Flat";
  Object.keys(presets).forEach((pName) => {
    const btn = document.createElement("button");
    const isActive = pName === currentPreset;
    btn.className = `px-3 py-1.5 rounded-xl text-xs transition-all cursor-pointer border ${
      isActive
        ? "bg-[var(--accent)] text-black border-[var(--accent)] font-bold shadow-[0_0_12px_var(--accent-glow)]"
        : "bg-white/[0.04] hover:bg-white/[0.1] text-slate-200 border-white/[0.06] hover:border-[var(--accent)] font-semibold"
    }`;
    btn.textContent = pName;
    btn.onclick = () => applyEqPreset(pName);
    group.appendChild(btn);
  });
}

async function applyEqPreset(presetName) {
  if (state.apiReady) {
    const bands = await window.pywebview.api.set_eq_preset(presetName);
    if (bands) {
      state.eqBands = bands;
      state.config.eq_preset = presetName;
      Object.entries(bands).forEach(([bKey, val]) => {
        const sld = document.querySelector(`.eq-slider[data-band="${bKey}"]`);
        if (sld) sld.value = val;
        const lbl = document.getElementById(`eq-val-${bKey}`);
        if (lbl) lbl.textContent = `${val >= 0 ? "+" : ""}${val.toFixed(1)} dB`;
      });
      document.getElementById("current-eq-preset-label").textContent = presetName;
      updateEqPresetButtons(presetName);
      drawEqCurve();
      showToast(`EQ Preset applied: ${presetName}`);
    }
  }
}

function drawEqCurve() {
  const canvas = document.getElementById("eq-curve-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const parent = canvas.parentElement;
  const w = parent.clientWidth || 600;
  const h = parent.clientHeight || 120;

  // High-DPI crisp rendering
  const dpr = window.devicePixelRatio || 1;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  canvas.style.width = `${w}px`;
  canvas.style.height = `${h}px`;
  ctx.scale(dpr, dpr);

  ctx.clearRect(0, 0, w, h);

  const bands = [
    { name: "60Hz", gain: state.eqBands.bass || 0 },
    { name: "250Hz", gain: state.eqBands.low_mid || 0 },
    { name: "1kHz", gain: state.eqBands.mid || 0 },
    { name: "4kHz", gain: state.eqBands.high_mid || 0 },
    { name: "12kHz", gain: state.eqBands.treble || 0 },
  ];
  const midY = h / 2;
  const points = bands.map((b, i) => {
    const x = (w / (bands.length - 1)) * i;
    // Map -12dB..+12dB to height with margin
    const y = midY - (b.gain / 14) * (midY - 14);
    return { x, y, gain: b.gain, name: b.name };
  });

  // 1. Draw subtle vertical grid markers & zero line
  ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
  ctx.lineWidth = 1;
  ctx.setLineDash([4, 4]);

  // Zero reference line
  ctx.beginPath();
  ctx.moveTo(0, midY);
  ctx.lineTo(w, midY);
  ctx.stroke();

  // Vertical frequency lines
  points.forEach((pt) => {
    ctx.beginPath();
    ctx.moveTo(pt.x, 8);
    ctx.lineTo(pt.x, h - 8);
    ctx.stroke();
  });
  ctx.setLineDash([]);

  // 2. Area fill underneath the curve with glowing gradient
  const accent = state.config.accent || "#22C55E";
  const rgb = hexToRgb(accent);
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, 0.35)`);
  grad.addColorStop(0.5, `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, 0.12)`);
  grad.addColorStop(1, `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, 0.0)`);

  ctx.beginPath();
  ctx.moveTo(0, midY);
  ctx.lineTo(0, points[0].y);
  for (let i = 0; i < points.length - 1; i++) {
    const xc = (points[i].x + points[i + 1].x) / 2;
    const yc = (points[i].y + points[i + 1].y) / 2;
    ctx.quadraticCurveTo(points[i].x, points[i].y, xc, yc);
  }
  ctx.lineTo(points[points.length - 1].x, points[points.length - 1].y);
  ctx.lineTo(w, midY);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();

  // 3. Draw curved equalizer line with glow
  ctx.beginPath();
  ctx.moveTo(0, points[0].y);
  for (let i = 0; i < points.length - 1; i++) {
    const xc = (points[i].x + points[i + 1].x) / 2;
    const yc = (points[i].y + points[i + 1].y) / 2;
    ctx.quadraticCurveTo(points[i].x, points[i].y, xc, yc);
  }
  ctx.lineTo(points[points.length - 1].x, points[points.length - 1].y);

  ctx.strokeStyle = accent;
  ctx.lineWidth = 3;
  ctx.shadowColor = accent;
  ctx.shadowBlur = 12;
  ctx.stroke();
  ctx.shadowBlur = 0;

  // 4. Draw interactive node points
  points.forEach((pt) => {
    // Outer halo
    ctx.beginPath();
    ctx.arc(pt.x, pt.y, 7, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, 0.3)`;
    ctx.fill();

    // Inner core
    ctx.beginPath();
    ctx.arc(pt.x, pt.y, 4, 0, Math.PI * 2);
    ctx.fillStyle = "#FFFFFF";
    ctx.fill();
    ctx.strokeStyle = accent;
    ctx.lineWidth = 2;
    ctx.stroke();
  });
}

// ============================================================================
// Synchronized Karaoke Lyrics (LRC Engine)
// ============================================================================
async function refreshLyrics(title, artist, duration, filepath) {
  if (!state.apiReady) return;
  try {
    const res = await window.pywebview.api.fetch_lyrics_data(title, artist, duration, filepath);
    if (res) {
      state.player.lyrics = res;
      renderLyricsView();
    }
  } catch (err) {
    console.warn("Lyrics fetch error:", err);
  }
}

function renderLyricsView() {
  const container = document.getElementById("lyrics-scroll-box");
  const thumbEl = document.getElementById("lyrics-track-thumb");
  const titleEl = document.getElementById("lyrics-track-title");
  const artistEl = document.getElementById("lyrics-track-artist");
  const srcBadge = document.getElementById("lyrics-source-badge");

  if (!container) return;

  const info = state.player.info || {};
  titleEl.textContent = info.title || "No track playing";
  artistEl.textContent = info.artist || "NexusTube Karaoke Engine";
  const thumbFallback = document.getElementById("lyrics-thumb-fallback") || document.getElementById("lyrics-track-thumb-fallback");
  if (info.cover_base64) {
    if (thumbEl) {
      thumbEl.src = info.cover_base64;
      thumbEl.classList.remove("hidden");
    }
    if (thumbFallback) thumbFallback.classList.add("hidden");
  } else {
    if (thumbEl) {
      thumbEl.src = "";
      thumbEl.classList.add("hidden");
    }
    if (thumbFallback) thumbFallback.classList.remove("hidden");
  }

  const lyr = state.player.lyrics || { synced: [] };
  const synced = lyr.synced || [];

  srcBadge.textContent = lyr.source ? `Source: ${lyr.source.toUpperCase()}` : "No lyrics found";
  container.innerHTML = "";
  state.lastLyricIndex = -1;

  if (synced.length === 0) {
    const plain = lyr.plain || "";
    if (plain) {
      container.innerHTML = `<div class="text-slate-300 text-base font-medium whitespace-pre-line leading-loose max-w-xl mx-auto py-12">${escapeHtml(plain)}</div>`;
    } else {
      container.innerHTML = '<div class="py-24 text-slate-500 text-sm font-medium">No synchronized lyrics available for this song.</div>';
    }
    return;
  }

  synced.forEach(([sec, text], idx) => {
    const line = document.createElement("div");
    line.className = "lyric-line";
    line.setAttribute("data-sec", sec);
    line.setAttribute("data-idx", idx);
    line.title = `Jump to ${formatDuration(sec)}`;

    const timePill = document.createElement("span");
    timePill.className = "lyric-time-pill";
    timePill.textContent = formatDuration(sec);
    line.appendChild(timePill);

    const textSpan = document.createElement("span");
    textSpan.className = "lyric-text";
    textSpan.textContent = text || "♪ ♪ ♪";
    line.appendChild(textSpan);

    line.onclick = async () => {
      if (state.apiReady) {
        await window.pywebview.api.player_control("seek", sec);
      }
    };

    container.appendChild(line);
  });
}

function syncLyricsWithPlayback(currentTime) {
  const lyr = state.player.lyrics || {};
  const synced = lyr.synced || [];
  if (synced.length === 0) return;

  // Find active line index
  let activeIdx = -1;
  for (let i = 0; i < synced.length; i++) {
    if (currentTime >= synced[i][0]) {
      activeIdx = i;
    } else {
      break;
    }
  }

  if (activeIdx === state.lastLyricIndex) return;
  state.lastLyricIndex = activeIdx;

  const lines = document.querySelectorAll(".lyric-line");
  lines.forEach((l, idx) => {
    if (idx === activeIdx) {
      l.classList.add("active");
      l.style.opacity = "1";
      l.style.filter = "none";
      l.scrollIntoView({ behavior: "smooth", block: "center" });
    } else {
      l.classList.remove("active");
      const dist = Math.abs(idx - activeIdx);
      if (dist === 1) {
        l.style.opacity = "0.7";
        l.style.filter = "none";
      } else if (dist === 2) {
        l.style.opacity = "0.45";
        l.style.filter = "none";
      } else {
        l.style.opacity = "0.28";
        l.style.filter = "none";
      }
    }
  });
}

// ============================================================================
// Lyrics Controls & Studio Editor
// ============================================================================
let lyricsEditMode = false;

function setupLyricsControls() {
  const toggleBtn = document.getElementById("btn-toggle-edit-lrc");
  const scrollBox = document.getElementById("lyrics-scroll-box");
  const editBox = document.getElementById("lyrics-edit-box");
  const textarea = document.getElementById("lyrics-editor-textarea");
  const saveBtn = document.getElementById("btn-save-lrc");
  const fetchBtn = document.getElementById("btn-fetch-lyrics");
  const searchInput = document.getElementById("lyrics-search-input");

  if (toggleBtn) {
    toggleBtn.onclick = () => {
      lyricsEditMode = !lyricsEditMode;
      if (lyricsEditMode) {
        scrollBox.classList.add("hidden");
        editBox.classList.remove("hidden");
        toggleBtn.textContent = t("View Synced") || "View Synced";
        toggleBtn.classList.add("bg-[var(--accent)]", "text-black", "font-bold");
        toggleBtn.classList.remove("bg-white/[0.06]", "text-slate-300");
        const raw = state.player.lyrics ? (state.player.lyrics.synced_raw || state.player.lyrics.plain || "") : "";
        textarea.value = raw;
      } else {
        editBox.classList.add("hidden");
        scrollBox.classList.remove("hidden");
        toggleBtn.textContent = t("Edit LRC") || "Edit LRC";
        toggleBtn.classList.remove("bg-[var(--accent)]", "text-black", "font-bold");
        toggleBtn.classList.add("bg-white/[0.06]", "text-slate-300");
      }
    };
  }

  const doFetchLyrics = async () => {
    const q = searchInput ? searchInput.value.trim() : "";
    let title = state.player.info ? (state.player.info.title || "") : "";
    let artist = state.player.info ? (state.player.info.artist || "") : "";
    if (q) {
      if (q.includes(" - ")) {
        const parts = q.split(" - ");
        artist = parts[0].trim();
        title = parts[1].trim();
      } else {
        title = q;
      }
    }
    if (!title) {
      showToast("Please enter song title or play a track first.");
      return;
    }
    showToast(`Searching lyrics for: ${title}…`);
    try {
      if (state.apiReady) {
        const res = await window.pywebview.api.search_lyrics(title, artist);
        if (res) {
          state.player.lyrics = res;
          renderLyricsView();
          if (textarea) textarea.value = res.synced_raw || res.plain || "";
          showToast(`Lyrics loaded (${res.source.toUpperCase()})`);
        } else {
          showToast("No lyrics found for this song.");
        }
      }
    } catch (err) {
      console.warn("Manual lyrics search error:", err);
      showToast("Lyrics search failed.");
    }
  };

  if (fetchBtn) fetchBtn.onclick = doFetchLyrics;
  if (searchInput) {
    searchInput.onkeydown = (e) => {
      if (e.key === "Enter") doFetchLyrics();
    };
  }

  if (saveBtn) {
    saveBtn.onclick = async () => {
      if (!state.apiReady) return;
      let raw = "";
      if (lyricsEditMode && textarea) {
        raw = textarea.value.trim();
      } else {
        raw = state.player.lyrics && state.player.lyrics.synced_raw;
      }
      if (!raw) {
        showToast("No synchronized lyrics content to save.");
        return;
      }
      const curFile = state.player.current_path;
      const res = await window.pywebview.api.save_lrc(curFile, raw);
      if (res) {
        refreshLyrics(state.player.info.title, state.player.info.artist, state.player.duration, curFile);
        showToast("LRC lyrics file saved successfully!");
      } else {
        showToast("Could not save LRC (play a local track first or check permissions).");
      }
    };
  }
}

async function streamTrack(url) {
  if (!state.apiReady || !url) return;
  showToast("Streaming audio preview… please wait.");
  try {
    const res = await window.pywebview.api.stream_track(url);
    if (res) {
      showToast(`Playing stream: ${res.title || 'Online Stream'}`);
      updatePlayerUI();
      refreshLyrics(res.title, res.artist, res.duration, null);
    } else {
      showToast("Could not preview online stream.", "warning");
    }
  } catch (err) {
    console.error("Stream track error:", err);
    showToast("Stream preview error: " + err, "error");
  }
}

// ============================================================================
// Modals (Playlist Selector, Audio Trimmer, Delete Confirmation)
// ============================================================================
function setupModals() {
  // Trimmer actions
  const trimPreviewBtn = document.getElementById("btn-trim-preview");
  const trimStopBtn = document.getElementById("btn-trim-stop-preview");

  if (trimPreviewBtn) {
    trimPreviewBtn.onclick = async () => {
      const start = document.getElementById("trim-start").value;
      const end = document.getElementById("trim-end").value;
      if (state.apiReady && state.activeTrimTarget) {
        trimPreviewBtn.classList.add("bg-[var(--accent)]", "text-black");
        trimPreviewBtn.classList.remove("bg-white/[0.08]", "text-white");
        const span = trimPreviewBtn.querySelector("span");
        if (span) span.textContent = "Playing Preview...";
        const ok = await window.pywebview.api.preview_trim(state.activeTrimTarget.path, start, end);
        if (!ok) {
          trimPreviewBtn.classList.remove("bg-[var(--accent)]", "text-black");
          trimPreviewBtn.classList.add("bg-white/[0.08]", "text-white");
          if (span) span.textContent = t("Preview Slice") || "Preview Slice";
        }
      }
    };
  }

  if (trimStopBtn) {
    trimStopBtn.onclick = async () => {
      if (state.apiReady) {
        await window.pywebview.api.stop_trim_preview();
      }
      if (trimPreviewBtn) {
        trimPreviewBtn.classList.remove("bg-[var(--accent)]", "text-black");
        trimPreviewBtn.classList.add("bg-white/[0.08]", "text-white");
        const span = trimPreviewBtn.querySelector("span");
        if (span) span.textContent = t("Preview Slice") || "Preview Slice";
      }
    };
  }

  const trimExecBtn = document.getElementById("btn-trim-execute");
  if (trimExecBtn) {
    trimExecBtn.onclick = async () => {
      const start = document.getElementById("trim-start").value;
      const end = document.getElementById("trim-end").value;
      if (state.apiReady && state.activeTrimTarget) {
        showToast("Trimming audio… please wait.");
        const ok = await window.pywebview.api.trim_audio_file(state.activeTrimTarget.path, start, end, "mp3");
        if (ok) {
          showToast("Audio slice trimmed and saved!", "success");
          closeModal("modal-trimmer");
          refreshLibrary();
        } else {
          showToast("Trimming failed.", "error");
        }
      }
    };
  }

  // Delete modal
  const confirmDeleteBtn = document.getElementById("btn-confirm-delete");
  if (confirmDeleteBtn) {
    confirmDeleteBtn.onclick = async () => {
      if (state.apiReady && state.activeDeleteTarget) {
        const ok = await window.pywebview.api.delete_file(state.activeDeleteTarget.path);
        if (ok) {
          showToast("File deleted permanently.", "success");
          closeModal("modal-delete");
          refreshLibrary();
        } else {
          showToast("Failed to delete file.", "error");
        }
      }
    };
  }

  // Dismiss modals on backdrop click
  ["modal-playlist", "modal-trimmer", "modal-delete"].forEach((mId) => {
    const modalEl = document.getElementById(mId);
    if (modalEl) {
      modalEl.addEventListener("click", (e) => {
        if (e.target === modalEl) {
          closeModal(mId);
        }
      });
    }
  });

  // Global Keyboard Shortcuts
  window.addEventListener("keydown", (e) => {
    // 1. Escape key: dismiss any open modal
    if (e.key === "Escape") {
      ["modal-playlist", "modal-trimmer", "modal-delete"].forEach((mId) => {
        const modalEl = document.getElementById(mId);
        if (modalEl && !modalEl.classList.contains("hidden")) {
          closeModal(mId);
        }
      });
      return;
    }

    // Check if user is currently typing in an input / textarea
    const activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : "";
    const isTyping = activeTag === "input" || activeTag === "textarea" || (document.activeElement && document.activeElement.isContentEditable);

    // Ctrl+K or '/' (when not typing): Focus search bar
    if ((e.ctrlKey && e.key.toLowerCase() === "k") || (!isTyping && e.key === "/")) {
      e.preventDefault();
      switchTab("search");
      const searchInput = document.getElementById("search-input");
      if (searchInput) {
        searchInput.focus();
        searchInput.select();
      }
      return;
    }

    if (isTyping) return;

    // Space: Play/Pause toggle
    if (e.code === "Space") {
      e.preventDefault();
      const playBtn = document.getElementById("btn-play-pause");
      if (playBtn) playBtn.click();
      return;
    }

    // Ctrl + Right Arrow: Next Track
    if (e.ctrlKey && e.key === "ArrowRight") {
      e.preventDefault();
      const nextBtn = document.getElementById("btn-next");
      if (nextBtn) nextBtn.click();
      return;
    }

    // Ctrl + Left Arrow: Previous Track
    if (e.ctrlKey && e.key === "ArrowLeft") {
      e.preventDefault();
      const prevBtn = document.getElementById("btn-prev");
      if (prevBtn) prevBtn.click();
      return;
    }

    // Ctrl + Up Arrow: Volume +5%
    if (e.ctrlKey && e.key === "ArrowUp") {
      e.preventDefault();
      const volRange = document.getElementById("volume-range");
      if (volRange) {
        const cur = parseFloat(volRange.value || "0.85");
        const next = Math.min(1.0, cur + 0.05);
        volRange.value = next;
        volRange.dispatchEvent(new Event("input"));
      }
      return;
    }

    // Ctrl + Down Arrow: Volume -5%
    if (e.ctrlKey && e.key === "ArrowDown") {
      e.preventDefault();
      const volRange = document.getElementById("volume-range");
      if (volRange) {
        const cur = parseFloat(volRange.value || "0.85");
        const next = Math.max(0.0, cur - 0.05);
        volRange.value = next;
        volRange.dispatchEvent(new Event("input"));
      }
      return;
    }

    // Ctrl + M: Toggle Mute
    if (e.ctrlKey && e.key.toLowerCase() === "m") {
      e.preventDefault();
      const muteBtn = document.getElementById("btn-volume-mute");
      if (muteBtn) muteBtn.click();
      return;
    }

    // Alt + 1..6: Quick Switch Tabs
    if (e.altKey) {
      if (e.key === "1") switchTab("search");
      else if (e.key === "2") switchTab("queue");
      else if (e.key === "3") switchTab("library");
      else if (e.key === "4") switchTab("equalizer");
      else if (e.key === "5") switchTab("lyrics");
      else if (e.key === "6") switchTab("settings");
    }
  });

  // Browse folder in Settings
  const browseFolderBtn = document.getElementById("btn-browse-folder");
  if (browseFolderBtn) {
    browseFolderBtn.onclick = async () => {
      if (state.apiReady) {
        const folder = await window.pywebview.api.select_folder();
        if (folder) {
          state.config.outdir = folder;
          document.getElementById("setting-outdir").value = folder;
          document.getElementById("quick-folder-path").textContent = folder;
          saveConfig({ outdir: folder });
        }
      }
    };
  }

  const quickOpenBtn = document.getElementById("btn-quick-open-folder");
  if (quickOpenBtn) {
    quickOpenBtn.onclick = async () => {
      if (state.apiReady) {
        await window.pywebview.api.open_folder(state.config.outdir);
      }
    };
  }

  const updateEnginesBtn = document.getElementById("btn-update-engines");
  if (updateEnginesBtn) {
    updateEnginesBtn.onclick = async () => {
      if (state.apiReady) {
        showToast("Checking and updating download engines…");
        const st = await window.pywebview.api.update_engines();
        updateEngineStatus(st);
        showToast("Engines verified and updated!");
      }
    };
  }

  // Language buttons
  document.querySelectorAll(".lang-btn").forEach((btn) => {
    btn.onclick = () => {
      const l = btn.getAttribute("data-lang");
      applyLanguage(l);
      saveConfig({ lang: l });
    };
  });
}

function openPlaylistModal(playlistData) {
  const modal = document.getElementById("modal-playlist");
  modal.classList.remove("hidden");

  document.getElementById("playlist-modal-title").textContent = playlistData.title || "Playlist";
  document.getElementById("playlist-tracks-count").textContent = playlistData.tracks ? playlistData.tracks.length : 0;
  if (playlistData.cover) {
    document.getElementById("playlist-cover-img").src = playlistData.cover;
  }

  state.activePlaylistTracks = (playlistData.tracks || []).map((t) => ({ ...t, selected: true }));
  renderPlaylistTracks(state.activePlaylistTracks);

  const filterInput = document.getElementById("playlist-filter-input");
  if (filterInput) {
    filterInput.value = "";
    filterInput.oninput = () => {
      const q = filterInput.value.trim().toLowerCase();
      if (!q) {
        renderPlaylistTracks(state.activePlaylistTracks);
        return;
      }
      const filtered = state.activePlaylistTracks.filter(
        (t) => (t.title && t.title.toLowerCase().includes(q)) || (t.artist && t.artist.toLowerCase().includes(q))
      );
      renderPlaylistTracks(filtered);
    };
  }

  document.getElementById("btn-playlist-select-all").onclick = () => {
    state.activePlaylistTracks.forEach((t) => (t.selected = true));
    document.querySelectorAll(".playlist-chk").forEach((c) => (c.checked = true));
    updatePlaylistCount();
  };

  document.getElementById("btn-playlist-deselect-all").onclick = () => {
    state.activePlaylistTracks.forEach((t) => (t.selected = false));
    document.querySelectorAll(".playlist-chk").forEach((c) => (c.checked = false));
    updatePlaylistCount();
  };

  document.getElementById("btn-playlist-download-selected").onclick = async () => {
    const selected = state.activePlaylistTracks.filter((t) => t.selected !== false);

    if (selected.length > 0) {
      closeModal("modal-playlist");
      showToast(`Adding ${selected.length} tracks to queue…`);
      for (const item of selected) {
        const targetUrl = item.search_query ? `ytsearch1:${item.search_query}` : (item.url || item.title);
        await addDownloadTask(targetUrl, item.title, {
          artist: item.artist || "",
          album: playlistData.title || "NexusTube Collection",
          track_num: item.track_num || 1,
          is_playlist: true,
          thumbnail: item.thumbnail || playlistData.cover || "",
        });
      }
    } else {
      showToast("No tracks selected to download.");
    }
  };
}

function renderPlaylistTracks(tracks) {
  const list = document.getElementById("playlist-tracks-list");
  list.innerHTML = "";
  tracks.forEach((track) => {
    const origIdx = state.activePlaylistTracks.indexOf(track);
    const idx = origIdx >= 0 ? origIdx : 0;
    const isChecked = track.selected !== false;
    const row = document.createElement("label");
    row.className = "flex items-center space-x-3 p-2.5 rounded-xl hover:bg-white/[0.04] cursor-pointer border border-transparent hover:border-white/[0.06]";
    row.innerHTML = `
      <input type="checkbox" ${isChecked ? "checked" : ""} class="playlist-chk accent-[var(--accent)] w-4 h-4 rounded cursor-pointer" data-idx="${idx}">
      <span class="text-xs font-mono text-slate-500 w-6">${idx + 1}</span>
      <div class="flex-1 min-w-0">
        <div class="text-sm font-bold text-white truncate">${escapeHtml(track.title)}</div>
        <div class="text-xs text-slate-400 truncate">${escapeHtml(track.artist || '')}</div>
      </div>
      <span class="text-xs font-mono text-slate-400">${formatDuration(track.duration || 0)}</span>
    `;
    const chk = row.querySelector(".playlist-chk");
    chk.onchange = () => {
      track.selected = chk.checked;
      updatePlaylistCount();
    };
    list.appendChild(row);
  });
  updatePlaylistCount();
}

function updatePlaylistCount() {
  const sel = state.activePlaylistTracks.filter((t) => t.selected !== false).length;
  document.getElementById("playlist-selected-count").textContent = `${sel} tracks selected`;
}

function openTrimmerModal(title, filepath, duration = 0) {
  state.activeTrimTarget = { title, path: filepath, duration };
  document.getElementById("trimmer-file-title").textContent = title || "Track";
  document.getElementById("trimmer-file-path").textContent = filepath || "";
  document.getElementById("trim-start").value = "00:00:00";
  const defaultEnd = duration > 0 ? formatDuration(duration) : "00:00:30";
  document.getElementById("trim-end").value = defaultEnd;

  // Wire preset buttons
  document.querySelectorAll(".btn-trim-preset").forEach((btn) => {
    btn.onclick = () => {
      if (btn.id === "btn-trim-preset-full") {
        document.getElementById("trim-start").value = "00:00:00";
        document.getElementById("trim-end").value = duration > 0 ? formatDuration(duration) : "00:03:00";
      } else {
        const s = btn.getAttribute("data-start");
        const e = btn.getAttribute("data-end");
        if (s) document.getElementById("trim-start").value = s;
        if (e) document.getElementById("trim-end").value = e;
      }
    };
  });

  const modal = document.getElementById("modal-trimmer");
  modal.classList.remove("hidden");
}

function openDeleteModal(filepath, title) {
  state.activeDeleteTarget = { path: filepath, title };
  document.getElementById("delete-modal-filename").textContent = title || filepath;
  document.getElementById("modal-delete").classList.remove("hidden");
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) modal.classList.add("hidden");
  if (modalId === "modal-trimmer") {
    if (state.apiReady) window.pywebview.api.stop_trim_preview();
    const trimPreviewBtn = document.getElementById("btn-trim-preview");
    if (trimPreviewBtn) {
      trimPreviewBtn.classList.remove("bg-[var(--accent)]", "text-black");
      trimPreviewBtn.classList.add("bg-white/[0.08]", "text-white");
      const span = trimPreviewBtn.querySelector("span");
      if (span) span.textContent = t("Preview Slice") || "Preview Slice";
    }
  }
}

// ============================================================================
// Engine Status Health Check
// ============================================================================
function updateEngineStatus(st) {
  if (!st) return;
  const dot = document.getElementById("engine-status-dot");
  const text = document.getElementById("engine-status-text");

  const allReady = st.ytdlp_ready && st.ffmpeg_ready;
  if (allReady) {
    dot.className = "w-2 h-2 rounded-full bg-emerald-400";
    text.textContent = "Engines: Ready";
  } else {
    dot.className = "w-2 h-2 rounded-full bg-amber-400 animate-pulse";
    text.textContent = "Engines: Missing/Updating";
  }

  const container = document.getElementById("engine-cards-group");
  if (!container) return;
  container.innerHTML = "";

  const engines = [
    { name: "yt-dlp", ready: st.ytdlp_ready, ver: st.ytdlp_version || "OK" },
    { name: "FFmpeg", ready: st.ffmpeg_ready, ver: "Universal" },
    { name: "FFprobe", ready: st.ffprobe_ready, ver: "Stream Inspector" },
    { name: "FFplay", ready: st.ffplay_ready, ver: "Stream Preview" },
  ];

  engines.forEach((e) => {
    const card = document.createElement("div");
    card.className = "p-3 rounded-xl bg-white/[0.03] border border-white/[0.06] space-y-1";
    card.innerHTML = `
      <div class="flex items-center justify-between">
        <span class="text-xs font-bold text-white">${e.name}</span>
        <span class="w-2 h-2 rounded-full ${e.ready ? 'bg-emerald-400' : 'bg-red-400'}"></span>
      </div>
      <div class="text-[10px] text-slate-400 truncate">${e.ver}</div>
    `;
    container.appendChild(card);
  });
}

// ============================================================================
// Window Controls (Frameless Titlebar)
// ============================================================================
function setupWindowControls() {
  const minBtn = document.getElementById("btn-win-min");
  const maxBtn = document.getElementById("btn-win-max");
  const closeBtn = document.getElementById("btn-win-close");

  minBtn.onclick = () => {
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.window_control("minimize");
    }
  };
  maxBtn.onclick = () => {
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.window_control("maximize");
    }
  };
  closeBtn.onclick = () => {
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.window_control("close");
    }
  };

  // Double click drag header to toggle maximize
  const dragHeader = document.querySelector(".pywebview-drag-region");
  if (dragHeader) {
    dragHeader.addEventListener("dblclick", (e) => {
      if (e.target.closest("button") || e.target.closest("input") || e.target.closest("a")) return;
      if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.window_control("maximize");
      }
    });
  }
}

// ============================================================================
// State Polling Loop & Helpers
// ============================================================================
function startPollingLoop() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = setInterval(() => {
    updatePlayerUI();
    if (state.activeTab === "queue") {
      refreshQueue();
    }
  }, 300);
}

async function saveConfig(updates) {
  if (!state.apiReady) return;
  state.config = { ...state.config, ...updates };
  await window.pywebview.api.save_config(state.config);
}

function showToast(msg, type = "info", duration = null) {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const t = document.createElement("div");
  const normalizedType = ["error", "warning", "success", "info"].includes(type) ? type : "info";
  t.className = `toast-msg toast-${normalizedType}`;

  let icon = "ℹ️";
  if (normalizedType === "error") icon = "❌";
  else if (normalizedType === "warning") icon = "⚠️";
  else if (normalizedType === "success") icon = "✅";

  const closeBtn = document.createElement("button");
  closeBtn.className = "toast-close";
  closeBtn.setAttribute("aria-label", "Dismiss");
  closeBtn.innerHTML = "&times;";

  t.innerHTML = `<span class="toast-icon">${icon}</span><span class="toast-body">${escapeHtml(msg)}</span>`;
  t.appendChild(closeBtn);

  let dismissTimeout = null;
  const removeToast = () => {
    if (dismissTimeout) clearTimeout(dismissTimeout);
    t.style.opacity = "0";
    t.style.transform = "translateY(10px)";
    t.style.transition = "all 0.3s ease";
    setTimeout(() => {
      if (t.parentNode) t.remove();
    }, 300);
  };

  closeBtn.onclick = (e) => {
    e.stopPropagation();
    removeToast();
  };

  container.appendChild(t);
  const ttl = duration || (normalizedType === "error" ? 5500 : normalizedType === "warning" ? 4500 : 3000);
  dismissTimeout = setTimeout(removeToast, ttl);
}

// Global runtime error listeners
window.addEventListener("error", (event) => {
  console.error("[NexusTube Frontend Error]:", event.error || event.message);
  showToast(event.message || "An unexpected UI error occurred.", "error", 6000);
});

window.addEventListener("unhandledrejection", (event) => {
  console.error("[NexusTube Unhandled Rejection]:", event.reason);
  const reasonText = event.reason?.message || event.reason || "Background task error.";
  showToast(String(reasonText), "warning", 5000);
});

function formatDuration(sec) {
  const isec = Math.max(0, parseInt(sec || 0));
  const m = Math.floor(isec / 60);
  const s = isec % 60;
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return "0 MB";
  const mb = bytes / (1024 * 1024);
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  return `${(mb / 1024).toFixed(2)} GB`;
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// ============================================================================
// Spotlight Mouse-Tracking Engine (60 FPS rAF Throttled)
// ============================================================================
function setupSpotlightEffect() {
  let rAF = null;
  let lastEvent = null;

  document.addEventListener(
    "pointermove",
    (e) => {
      lastEvent = e;
      if (!rAF) {
        rAF = requestAnimationFrame(() => {
          rAF = null;
          if (!lastEvent) return;
          const target = lastEvent.target.closest(".spotlight-card, .card-glass, .fmt-btn");
          if (target) {
            const rect = target.getBoundingClientRect();
            const x = lastEvent.clientX - rect.left;
            const y = lastEvent.clientY - rect.top;
            target.style.setProperty("--mx", `${x}px`);
            target.style.setProperty("--my", `${y}px`);
          }
        });
      }
    },
    { passive: true }
  );
}

// ============================================================================
// Modern Features (v3.3.0 Pro Suite): Converter, Shortcuts, Fullscreen Karaoke, DSP, Vibes
// ============================================================================
function openConverterModal(title, filepath) {
  state.activeConvertTarget = { title, path: filepath };
  const titleEl = document.getElementById("converter-file-title");
  const pathEl = document.getElementById("converter-file-path");
  if (titleEl) titleEl.textContent = title || "Track";
  if (pathEl) pathEl.textContent = filepath || "";
  const modal = document.getElementById("modal-converter");
  if (modal) modal.classList.remove("hidden");
}

function syncFullscreenKaraokeUI(cur, dur, p) {
  const modal = document.getElementById("fullscreen-karaoke-modal");
  if (!modal || modal.classList.contains("hidden")) return;

  const titleEl = document.getElementById("fs-lyrics-title");
  const artistEl = document.getElementById("fs-lyrics-artist");
  const thumbEl = document.getElementById("fs-lyrics-thumb");
  const playIcon = document.getElementById("fs-icon-play");
  const pauseIcon = document.getElementById("fs-icon-pause");
  const timeCur = document.getElementById("fs-time-current");
  const timeTot = document.getElementById("fs-time-total");
  const fill = document.getElementById("fs-seek-bar-fill");
  const range = document.getElementById("fs-seek-range");

  if (p.info && p.info.title) {
    if (titleEl) titleEl.textContent = p.info.title;
    if (artistEl) artistEl.textContent = p.info.artist || "NexusTube";
    if (thumbEl) {
      if (p.info.cover_base64) {
        thumbEl.src = p.info.cover_base64;
        thumbEl.classList.remove("hidden");
      } else {
        thumbEl.classList.add("hidden");
      }
    }
  }

  if (playIcon && pauseIcon) {
    const isPlaying = state.player.isPlaying && !state.player.isPaused;
    playIcon.classList.toggle("hidden", isPlaying);
    pauseIcon.classList.toggle("hidden", !isPlaying);
  }

  if (timeCur) timeCur.textContent = formatDuration(cur);
  if (timeTot) timeTot.textContent = formatDuration(dur);
  if (range && !state.isSeeking) {
    range.max = dur > 0 ? dur : 100;
    range.value = cur;
    const pct = dur > 0 ? (cur / dur) * 100 : 0;
    if (fill) fill.style.width = `${pct}%`;
  }

  // Render or sync fullscreen lyrics lines
  const fsScrollBox = document.getElementById("fs-lyrics-scroll-box");
  if (!fsScrollBox) return;

  const lyr = state.player.lyrics || {};
  const synced = lyr.synced || [];
  const trackKey = (p.current_path || "") + "::" + (p.info ? p.info.title || "" : "");

  if (synced.length === 0) {
    const plain = lyr.plain || "";
    if (fsScrollBox.dataset.trackKey !== trackKey || fsScrollBox.dataset.mode !== "plain") {
      fsScrollBox.dataset.trackKey = trackKey;
      fsScrollBox.dataset.mode = "plain";
      fsScrollBox.innerHTML = plain
        ? `<div class="text-slate-300 text-2xl font-bold whitespace-pre-line leading-loose max-w-2xl mx-auto">${escapeHtml(plain)}</div>`
        : '<div class="text-slate-500 text-xl font-medium">No lyrics available for this song</div>';
    }
    return;
  }

  if (fsScrollBox.dataset.trackKey !== trackKey || fsScrollBox.dataset.mode !== "synced" || fsScrollBox.children.length !== synced.length) {
    fsScrollBox.dataset.trackKey = trackKey;
    fsScrollBox.dataset.mode = "synced";
    fsScrollBox.innerHTML = "";
    synced.forEach(([sec, text], idx) => {
      const line = document.createElement("div");
      line.className = "fs-lyric-line";
      line.setAttribute("data-sec", sec);
      line.setAttribute("data-idx", idx);
      line.textContent = text || "♪ ♪ ♪";
      line.onclick = async () => {
        if (state.apiReady) {
          await window.pywebview.api.player_control("seek", sec);
        }
      };
      fsScrollBox.appendChild(line);
    });
  }

  // Active line highlight in fullscreen
  let activeIdx = -1;
  for (let i = 0; i < synced.length; i++) {
    if (cur >= synced[i][0]) {
      activeIdx = i;
    } else {
      break;
    }
  }

  const lines = fsScrollBox.querySelectorAll(".fs-lyric-line");
  lines.forEach((l, idx) => {
    if (idx === activeIdx) {
      if (!l.classList.contains("fs-lyric-active")) {
        l.classList.add("fs-lyric-active");
        l.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    } else {
      l.classList.remove("fs-lyric-active");
    }
  });
}

function setupModernFeatures() {
  // 1. Trending Vibes Discovery Chips
  document.querySelectorAll(".vibe-tag").forEach((chip) => {
    chip.addEventListener("click", () => {
      const query = chip.getAttribute("data-vibe") || chip.textContent.trim();
      const searchInput = document.getElementById("search-input");
      if (searchInput) {
        searchInput.value = query;
        switchTab("search");
        const submitBtn = document.getElementById("btn-execute-search") || document.getElementById("btn-search-submit");
        if (submitBtn) submitBtn.click();
      }
    });
  });

  // 2. Recent Searches Management
  initRecentSearches();

  // 3. Batch Cancel All Downloads
  const cancelAllBtn = document.getElementById("btn-cancel-all-queue") || document.getElementById("btn-cancel-all-downloads");
  if (cancelAllBtn) {
    cancelAllBtn.addEventListener("click", async () => {
      if (!state.apiReady) return;
      try {
        const count = await window.pywebview.api.batch_cancel_all();
        showToast(count > 0 ? `Cancelled ${count} active downloads` : "No active downloads to cancel");
        refreshQueue();
      } catch (err) {
        console.warn("Cancel all error:", err);
      }
    });
  }

  // 4. Music Library Table vs Grid View Toggle
  const btnGrid = document.getElementById("btn-view-grid");
  const btnTable = document.getElementById("btn-view-table");

  if (btnGrid && btnTable) {
    btnGrid.onclick = () => {
      state.libraryViewMode = "grid";
      btnGrid.className = "p-2 rounded-lg bg-white/[0.12] text-white transition-colors cursor-pointer";
      btnTable.className = "p-2 rounded-lg text-slate-400 hover:text-white transition-colors cursor-pointer";
      renderLibrary(state.library);
    };

    btnTable.onclick = () => {
      state.libraryViewMode = "table";
      btnTable.className = "p-2 rounded-lg bg-white/[0.12] text-white transition-colors cursor-pointer";
      btnGrid.className = "p-2 rounded-lg text-slate-400 hover:text-white transition-colors cursor-pointer";
      renderLibrary(state.library);
    };
  }

  // 5. Library Favorites Filter Toggle
  const btnFavFilter = document.getElementById("btn-filter-favorites");
  if (btnFavFilter) {
    btnFavFilter.onclick = () => {
      state.favoritesOnly = !state.favoritesOnly;
      const heartIcon = document.getElementById("filter-heart-icon");
      if (state.favoritesOnly) {
        btnFavFilter.classList.add("bg-red-500/20", "border-red-500/30", "text-white");
        btnFavFilter.classList.remove("bg-white/[0.06]", "text-slate-300");
        if (heartIcon) heartIcon.classList.add("fill-red-500");
      } else {
        btnFavFilter.classList.remove("bg-red-500/20", "border-red-500/30", "text-white");
        btnFavFilter.classList.add("bg-white/[0.06]", "text-slate-300");
        if (heartIcon) heartIcon.classList.remove("fill-red-500");
      }
      renderLibrary(state.library);
    };
  }

  // 6. Play All & Shuffle All Library Actions
  const btnPlayAll = document.getElementById("btn-play-all-lib");
  if (btnPlayAll) {
    btnPlayAll.onclick = () => {
      const items = state.favoritesOnly ? state.library.filter((i) => i.is_favorite) : state.library;
      if (items && items.length > 0) {
        playTrack(items[0].path);
      } else {
        showToast("No tracks in current library view to play.");
      }
    };
  }

  const btnShuffleAll = document.getElementById("btn-shuffle-all-lib");
  if (btnShuffleAll) {
    btnShuffleAll.onclick = async () => {
      const items = state.favoritesOnly ? state.library.filter((i) => i.is_favorite) : state.library;
      if (items && items.length > 0) {
        if (state.apiReady) {
          await window.pywebview.api.player_control("toggle_shuffle", true);
          state.player.isShuffle = true;
          updatePlayerUI();
        }
        const randIdx = Math.floor(Math.random() * items.length);
        playTrack(items[randIdx].path);
      } else {
        showToast("No tracks in current library view to shuffle.");
      }
    };
  }

  // 7. Export M3U8 Playlist
  const btnExportM3U8 = document.getElementById("btn-export-m3u8");
  if (btnExportM3U8) {
    btnExportM3U8.onclick = async () => {
      if (!state.apiReady) return;
      try {
        const res = await window.pywebview.api.export_library_playlist("NexusTube_Library");
        if (res && res.success) {
          showToast(`Playlist exported: ${res.playlist_name}.m3u8`);
        } else {
          showToast("Export failed or library is empty.");
        }
      } catch (err) {
        console.warn("Export M3U8 error:", err);
      }
    };
  }

  // 8. DSP Mastering Suite (Pre-amp, Sub-Bass Exciter, 3D Spatial Surround)
  const preampSlider = document.getElementById("dsp-preamp-slider");
  const preampVal = document.getElementById("dsp-preamp-val");
  const bassSlider = document.getElementById("dsp-bass-slider");
  const bassVal = document.getElementById("dsp-bass-val");
  const surroundToggle = document.getElementById("dsp-surround-toggle");

  let dspDebounce = null;
  const dispatchDspUpdate = () => {
    clearTimeout(dspDebounce);
    dspDebounce = setTimeout(async () => {
      if (state.apiReady) {
        await window.pywebview.api.set_dsp_effects(
          state.dsp.preamp,
          state.dsp.bass_boost,
          state.dsp.surround
        );
      }
    }, 180);
  };

  if (preampSlider) {
    preampSlider.addEventListener("input", () => {
      const val = parseFloat(preampSlider.value);
      state.dsp.preamp = val;
      if (preampVal) preampVal.textContent = `${val >= 0 ? "+" : ""}${val.toFixed(1)} dB`;
      dispatchDspUpdate();
    });
  }

  if (bassSlider) {
    bassSlider.addEventListener("input", () => {
      const val = parseFloat(bassSlider.value);
      state.dsp.bass_boost = val / 100.0;
      if (bassVal) bassVal.textContent = `${Math.round(val)}%`;
      dispatchDspUpdate();
    });
  }

  if (surroundToggle) {
    surroundToggle.addEventListener("change", () => {
      state.dsp.surround = surroundToggle.checked;
      dispatchDspUpdate();
      showToast(state.dsp.surround ? "3D Spatial Surround: Enabled" : "3D Spatial Surround: Disabled");
    });
  }

  // 9. Karaoke Lyrics: Copy, Font Zoom, Fullscreen Karaoke
  const btnCopyLyrics = document.getElementById("btn-copy-lyrics");
  if (btnCopyLyrics) {
    btnCopyLyrics.onclick = async () => {
      const lyr = state.player.lyrics || {};
      const textToCopy = lyr.plain || lyr.synced_raw || (lyr.synced ? lyr.synced.map((l) => l[1]).join("\n") : "");
      if (!textToCopy) {
        showToast("No lyrics available to copy.");
        return;
      }
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(textToCopy);
        } else {
          const ta = document.createElement("textarea");
          ta.value = textToCopy;
          document.body.appendChild(ta);
          ta.select();
          document.execCommand("copy");
          ta.remove();
        }
        showToast("Lyrics copied to clipboard! 📋");
      } catch (err) {
        showToast("Could not copy lyrics: " + err);
      }
    };
  }

  const btnZoomIn = document.getElementById("btn-lyrics-zoom-in");
  const btnZoomOut = document.getElementById("btn-lyrics-zoom-out");
  if (btnZoomIn && btnZoomOut) {
    btnZoomIn.onclick = () => {
      state.lyricsFontSize = Math.min(28, state.lyricsFontSize + 2);
      applyLyricsFontSize();
    };
    btnZoomOut.onclick = () => {
      state.lyricsFontSize = Math.max(12, state.lyricsFontSize - 2);
      applyLyricsFontSize();
    };
  }

  function applyLyricsFontSize() {
    const lines = document.querySelectorAll(".lyric-line, .lyric-text");
    lines.forEach((l) => {
      l.style.fontSize = `${state.lyricsFontSize}px`;
    });
  }

  // Fullscreen Karaoke Modal
  const btnFsLyrics = document.getElementById("btn-fullscreen-lyrics");
  const btnExitFs = document.getElementById("btn-exit-fullscreen-lyrics");
  const fsModal = document.getElementById("fullscreen-karaoke-modal");

  if (btnFsLyrics && fsModal) {
    btnFsLyrics.onclick = () => {
      fsModal.classList.remove("hidden");
      syncFullscreenKaraokeUI(state.player.currentPos, state.player.duration, { info: state.player.info });
    };
  }
  if (btnExitFs && fsModal) {
    btnExitFs.onclick = () => fsModal.classList.add("hidden");
  }

  // Fullscreen Mini-Player Bar Controls
  const fsPlayPause = document.getElementById("fs-btn-play-pause");
  const fsPrev = document.getElementById("fs-btn-prev");
  const fsNext = document.getElementById("fs-btn-next");
  const fsSeek = document.getElementById("fs-seek-range");

  if (fsPlayPause) {
    fsPlayPause.onclick = () => {
      const playBtn = document.getElementById("btn-play-pause");
      if (playBtn) playBtn.click();
    };
  }
  if (fsPrev) {
    fsPrev.onclick = () => {
      const prevBtn = document.getElementById("btn-prev");
      if (prevBtn) prevBtn.click();
    };
  }
  if (fsNext) {
    fsNext.onclick = () => {
      const nextBtn = document.getElementById("btn-next");
      if (nextBtn) nextBtn.click();
    };
  }
  if (fsSeek) {
    fsSeek.addEventListener("input", () => {
      const targetSec = parseFloat(fsSeek.value);
      const fsTimeCur = document.getElementById("fs-time-current");
      if (fsTimeCur) fsTimeCur.textContent = formatDuration(targetSec);
      const dur = state.player.duration || 100;
      const pct = dur > 0 ? (targetSec / dur) * 100 : 0;
      const fsFill = document.getElementById("fs-seek-bar-fill");
      if (fsFill) fsFill.style.width = `${pct}%`;
    });
    fsSeek.addEventListener("change", async () => {
      const targetSec = parseFloat(fsSeek.value);
      if (state.apiReady) {
        await window.pywebview.api.player_control("seek", targetSec);
      }
    });
  }

  // 10. Docked Player Seek Hover Tooltip
  const seekBarTrack = document.getElementById("seek-bar-track");
  const seekTooltip = document.getElementById("seek-hover-tooltip");
  if (seekBarTrack && seekTooltip) {
    seekBarTrack.addEventListener("mouseenter", () => {
      seekTooltip.classList.remove("hidden");
    });
    seekBarTrack.addEventListener("mouseleave", () => {
      seekTooltip.classList.add("hidden");
    });
    seekBarTrack.addEventListener("mousemove", (e) => {
      const rect = seekBarTrack.getBoundingClientRect();
      const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
      const pct = rect.width > 0 ? x / rect.width : 0;
      const dur = state.player.duration || 0;
      const hoverSec = pct * dur;
      seekTooltip.textContent = formatDuration(hoverSec);
      seekTooltip.style.left = `${x}px`;
    });
  }

  // 11. Playback Speed Button
  const speedBtn = document.getElementById("btn-playback-speed");
  const speeds = [1.0, 1.25, 1.5, 1.75, 2.0, 0.75];
  let speedIdx = 0;
  if (speedBtn) {
    speedBtn.onclick = async () => {
      speedIdx = (speedIdx + 1) % speeds.length;
      state.playbackSpeed = speeds[speedIdx];
      speedBtn.textContent = `${state.playbackSpeed.toFixed(state.playbackSpeed === 1 ? 1 : 2)}x`;
      if (state.apiReady) {
        await window.pywebview.api.player_control("set_speed", state.playbackSpeed);
      }
      showToast(`Playback Speed: ${state.playbackSpeed}x`);
    };
  }

  // 12. Sleep Timer Modal & Backend Integration with Gradual Fade-out
  const btnSleepTimer = document.getElementById("btn-sleep-timer") || document.getElementById("btn-sleep-timer-trigger");
  const sleepModal = document.getElementById("modal-sleep-timer");

  if (btnSleepTimer && sleepModal) {
    btnSleepTimer.onclick = () => sleepModal.classList.remove("hidden");
  }

  document.querySelectorAll(".sleep-option-btn").forEach((btn) => {
    btn.onclick = async () => {
      const minsVal = btn.getAttribute("data-minutes");
      document.querySelectorAll(".sleep-option-btn").forEach((b) => b.classList.remove("active-timer"));
      btn.classList.add("active-timer");

      if (state.sleepTimer.intervalId) clearInterval(state.sleepTimer.intervalId);

      if (state.apiReady) {
        try {
          await window.pywebview.api.set_sleep_timer(minsVal);
        } catch (e) {
          console.warn("set_sleep_timer bridge error:", e);
        }
      }

      if (minsVal === "end_of_track") {
        state.sleepTimer = { active: true, minutes: 0, endsAt: null, endOfTrack: true, intervalId: null, fading: false };
        showToast("Sleep timer set: Stop after current song (30s audio fade-out)");
      } else {
        const mins = parseInt(minsVal, 10);
        const endsAt = Date.now() + mins * 60 * 1000;
        state.sleepTimer = { active: true, minutes: mins, endsAt, endOfTrack: false, fading: false };

        state.sleepTimer.intervalId = setInterval(() => {
          const remaining = state.sleepTimer.endsAt - Date.now();
          if (remaining <= 0) {
            clearInterval(state.sleepTimer.intervalId);
            state.sleepTimer.active = false;
            state.sleepTimer.intervalId = null;
            updateSleepTimerUI();
            if (state.apiReady) window.pywebview.api.player_control("pause", null);
            showToast("Sleep timer completed: Music gently faded out and paused. 🌙");
          }
        }, 1000);

        showToast(`Sleep timer set for ${mins} minutes (with gentle fade-out)`);
      }

      updateSleepTimerUI();
      closeModal("modal-sleep-timer");
    };
  });

  const btnCancelSleep = document.getElementById("btn-cancel-sleep-timer");
  if (btnCancelSleep) {
    btnCancelSleep.onclick = async () => {
      if (state.sleepTimer.intervalId) clearInterval(state.sleepTimer.intervalId);
      state.sleepTimer = { active: false, minutes: 0, endsAt: null, intervalId: null, endOfTrack: false, fading: false };
      if (state.apiReady) {
        try {
          await window.pywebview.api.cancel_sleep_timer();
        } catch (e) {
          console.warn("cancel_sleep_timer bridge error:", e);
        }
      }
      document.querySelectorAll(".sleep-option-btn").forEach((b) => b.classList.remove("active-timer"));
      updateSleepTimerUI();
      showToast("Sleep timer disabled.");
      closeModal("modal-sleep-timer");
    };
  }

  // 13. Keyboard Shortcuts Modal & Quick Button
  const btnShortcuts = document.getElementById("btn-keyboard-shortcuts") || document.getElementById("btn-shortcuts-help");
  if (btnShortcuts) {
    btnShortcuts.onclick = () => {
      const modal = document.getElementById("modal-shortcuts");
      if (modal) modal.classList.remove("hidden");
    };
  }

  // 14. Audio Transcoder Modal Execute Button
  const btnExecuteConvert = document.getElementById("btn-execute-convert");
  if (btnExecuteConvert) {
    btnExecuteConvert.onclick = async () => {
      if (!state.apiReady || !state.activeConvertTarget) return;
      const targetFmt = document.getElementById("converter-target-format").value;
      const targetBitrate = document.getElementById("converter-target-bitrate").value;
      const loudnorm = document.getElementById("converter-loudnorm").checked;

      showToast(`Transcoding audio to ${targetFmt.toUpperCase()}… please wait`);
      btnExecuteConvert.disabled = true;
      btnExecuteConvert.textContent = "Transcoding...";

      try {
        const res = await window.pywebview.api.convert_track(
          state.activeConvertTarget.path,
          targetFmt,
          targetBitrate,
          loudnorm
        );
        btnExecuteConvert.disabled = false;
        btnExecuteConvert.textContent = "Convert & Save";
        closeModal("modal-converter");
        if (res && res.success) {
          showToast(`Conversion complete! Saved: ${res.output_path}`);
          refreshLibrary();
        } else {
          showToast(`Transcoding failed: ${(res && res.error) || 'Unknown error'}`);
        }
      } catch (err) {
        btnExecuteConvert.disabled = false;
        btnExecuteConvert.textContent = "Convert & Save";
        showToast("Conversion error: " + err);
      }
    };
  }

  // 15. Discord Rich Presence Settings Switch
  const settingDiscord = document.getElementById("setting-discord-rpc");
  if (settingDiscord) {
    settingDiscord.onchange = async () => {
      if (state.apiReady) {
        try {
          const en = await window.pywebview.api.toggle_discord_rpc(settingDiscord.checked);
          updateDiscordRpcPill({ enabled: en, connected: en });
          showToast(en ? "Discord Rich Presence Enabled" : "Discord Rich Presence Disabled");
        } catch (err) {
          console.error("toggle_discord_rpc error:", err);
        }
      }
    };
  }

  // 16. Global Hotkeys & System Tray Settings Toggles
  const settingHotkeys = document.getElementById("setting-global-hotkeys");
  if (settingHotkeys) {
    settingHotkeys.onchange = async () => {
      if (state.apiReady) {
        try {
          const en = await window.pywebview.api.toggle_global_hotkeys(settingHotkeys.checked);
          showToast(en ? "Global Media Hotkeys Active (Media Keys & Ctrl+Alt+Space/Arrows)" : "Global Hotkeys Disabled");
        } catch (err) {
          console.error("toggle_global_hotkeys error:", err);
        }
      }
    };
  }

  const settingTray = document.getElementById("setting-system-tray");
  if (settingTray) {
    settingTray.onchange = async () => {
      if (state.apiReady) {
        try {
          const en = await window.pywebview.api.toggle_system_tray(settingTray.checked);
          showToast(en ? "Windows System Tray Icon Active" : "System Tray Disabled");
        } catch (err) {
          console.error("toggle_system_tray error:", err);
        }
      }
    };
  }

  const settingMinTray = document.getElementById("setting-minimize-to-tray");
  if (settingMinTray) {
    settingMinTray.onchange = async () => {
      if (state.apiReady) {
        try {
          const en = await window.pywebview.api.toggle_minimize_to_tray(settingMinTray.checked);
          showToast(en ? "Minimize to Tray on Close Active" : "Standard Window Close Active");
        } catch (err) {
          console.error("toggle_minimize_to_tray error:", err);
        }
      }
    };
  }

  // 17. Audio Normalization Toggles (DSP & Settings)
  const dspNormToggle = document.getElementById("dsp-normalize-toggle");
  if (dspNormToggle) {
    dspNormToggle.onchange = () => toggleNormalization(dspNormToggle.checked);
  }
  const settingDefNorm = document.getElementById("setting-default-normalize");
  if (settingDefNorm) {
    settingDefNorm.onchange = () => toggleNormalization(settingDefNorm.checked);
  }

  // 18. Mini-Player PiP Mode Buttons & Controls
  const btnHeaderMini = document.getElementById("btn-header-mini-player");
  if (btnHeaderMini) btnHeaderMini.onclick = () => toggleMiniPlayer();

  const miniBtnRestore = document.getElementById("mini-btn-restore");
  if (miniBtnRestore) {
    const doRestore = (e) => {
      if (e) {
        e.preventDefault();
        e.stopPropagation();
      }
      toggleMiniPlayer(false);
    };
    miniBtnRestore.onclick = doRestore;
    miniBtnRestore.onpointerdown = (e) => e.stopPropagation();
    miniBtnRestore.onmousedown = (e) => e.stopPropagation();
    miniBtnRestore.onmouseup = (e) => e.stopPropagation();
  }

  const miniPlayerArtBox = document.getElementById("mini-player-art-box");
  if (miniPlayerArtBox) {
    const doArtRestore = (e) => {
      e.preventDefault();
      e.stopPropagation();
      toggleMiniPlayer(false);
    };
    miniPlayerArtBox.onclick = doArtRestore;
    miniPlayerArtBox.onpointerdown = (e) => e.stopPropagation();
    miniPlayerArtBox.onmousedown = (e) => e.stopPropagation();
    miniPlayerArtBox.onmouseup = (e) => e.stopPropagation();
  }

  const miniBtnClose = document.getElementById("mini-btn-close");
  if (miniBtnClose) {
    miniBtnClose.onpointerdown = (e) => e.stopPropagation();
    miniBtnClose.onmousedown = (e) => e.stopPropagation();
    miniBtnClose.onmouseup = (e) => e.stopPropagation();
    miniBtnClose.onclick = (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (state.apiReady) window.pywebview.api.window_control("close");
    };
  }

  // Double-click on mini title bar, drag handle, or background to restore full window
  const miniTitleBar = document.getElementById("mini-title-bar");
  if (miniTitleBar) {
    miniTitleBar.ondblclick = (e) => {
      e.preventDefault();
      e.stopPropagation();
      toggleMiniPlayer(false);
    };
  }

  const miniDragHandle = document.getElementById("mini-drag-handle");
  if (miniDragHandle) {
    miniDragHandle.ondblclick = (e) => {
      e.preventDefault();
      e.stopPropagation();
      toggleMiniPlayer(false);
    };
  }

  const miniOverlay = document.getElementById("mini-player-overlay");
  if (miniOverlay) {
    miniOverlay.ondblclick = (e) => {
      const tag = (e.target.tagName || "").toLowerCase();
      if (tag !== "button" && tag !== "input" && !e.target.closest("button") && !e.target.closest("input")) {
        e.preventDefault();
        e.stopPropagation();
        toggleMiniPlayer(false);
      }
    };
  }

  const miniPlayPause = document.getElementById("mini-btn-play-pause");
  if (miniPlayPause) {
    miniPlayPause.onclick = (e) => {
      if (e) e.stopPropagation();
      if (state.apiReady) window.pywebview.api.player_control("play_pause");
    };
  }

  const miniPrev = document.getElementById("mini-btn-prev");
  if (miniPrev) {
    miniPrev.onclick = (e) => {
      if (e) e.stopPropagation();
      if (state.apiReady) window.pywebview.api.player_control("prev");
    };
  }

  const miniNext = document.getElementById("mini-btn-next");
  if (miniNext) {
    miniNext.onclick = (e) => {
      if (e) e.stopPropagation();
      if (state.apiReady) window.pywebview.api.player_control("next");
    };
  }

  const miniShuffle = document.getElementById("mini-btn-shuffle");
  if (miniShuffle) {
    miniShuffle.onclick = (e) => {
      if (e) e.stopPropagation();
      if (state.apiReady) window.pywebview.api.player_control("toggle_shuffle");
    };
  }

  const miniRepeat = document.getElementById("mini-btn-repeat");
  if (miniRepeat) {
    miniRepeat.onclick = (e) => {
      if (e) e.stopPropagation();
      if (state.apiReady) window.pywebview.api.player_control("toggle_repeat");
    };
  }

  const miniMute = document.getElementById("mini-btn-mute");
  if (miniMute) {
    miniMute.onclick = (e) => {
      if (e) e.stopPropagation();
      if (state.apiReady) window.pywebview.api.player_control("toggle_mute");
    };
  }

  const miniSeek = document.getElementById("mini-seek-range");
  if (miniSeek) {
    miniSeek.oninput = (e) => {
      if (e) e.stopPropagation();
      const pct = parseFloat(miniSeek.value) / 100.0;
      const sec = pct * (state.player.duration || 0);
      if (state.apiReady) window.pywebview.api.player_control("seek", sec);
    };
  }

  // Prevent drag interception on all interactive mini-player controls
  [miniPlayPause, miniPrev, miniNext, miniShuffle, miniRepeat, miniMute, miniSeek].forEach((el) => {
    if (el) {
      el.onmousedown = (e) => e.stopPropagation();
      el.onpointerdown = (e) => e.stopPropagation();
    }
  });

  // 19. Fullscreen Ambient Visualizer Controls
  const btnExitVis = document.getElementById("btn-exit-visualizer");
  if (btnExitVis) btnExitVis.onclick = () => closeFullscreenVisualizer();

  const btnCycleVis = document.getElementById("btn-vis-mode-cycle");
  if (btnCycleVis) btnCycleVis.onclick = () => cycleVisualizerMode();

  const visPlayPause = document.getElementById("vis-btn-play-pause");
  if (visPlayPause) {
    visPlayPause.onclick = () => {
      if (state.apiReady) window.pywebview.api.player_control("play_pause");
    };
  }

  const visPrev = document.getElementById("vis-btn-prev");
  if (visPrev) {
    visPrev.onclick = () => {
      if (state.apiReady) window.pywebview.api.player_control("prev");
    };
  }

  const visNext = document.getElementById("vis-btn-next");
  if (visNext) {
    visNext.onclick = () => {
      if (state.apiReady) window.pywebview.api.player_control("next");
    };
  }

  const visSeek = document.getElementById("vis-seek-range");
  if (visSeek) {
    visSeek.oninput = () => {
      const pct = parseFloat(visSeek.value) / 100.0;
      const sec = pct * (state.player.duration || 0);
      if (state.apiReady) window.pywebview.api.player_control("seek", sec);
    };
  }

  // 20. In-App yt-dlp One-Click Updater
  const btnCheckYtdlp = document.getElementById("btn-check-ytdlp-update");
  if (btnCheckYtdlp) btnCheckYtdlp.onclick = checkYtdlpUpdate;

  const btnUpdateYtdlp = document.getElementById("btn-update-ytdlp");
  if (btnUpdateYtdlp) btnUpdateYtdlp.onclick = updateYtdlp;

  // Dismiss new modals on backdrop click
  ["modal-converter", "modal-shortcuts", "modal-sleep-timer"].forEach((mId) => {
    const modalEl = document.getElementById(mId);
    if (modalEl) {
      modalEl.addEventListener("click", (e) => {
        if (e.target === modalEl) closeModal(mId);
      });
    }
  });

  // Additional keyboard listeners
  window.addEventListener("keydown", (e) => {
    // Top-priority: Escape key always exits visualizer or mini-player even if an input was focused
    if (e.key === "Escape") {
      if (document.activeElement && typeof document.activeElement.blur === "function") {
        document.activeElement.blur();
      }
      if (state.miniPlayer) {
        e.preventDefault();
        toggleMiniPlayer(false);
        return;
      }
      if (ambientVisActive) {
        e.preventDefault();
        closeFullscreenVisualizer();
        return;
      }
    }

    const activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : "";
    const activeType = document.activeElement ? (document.activeElement.type || "").toLowerCase() : "";
    const isTyping = activeTag === "textarea" || (activeTag === "input" && !["range", "checkbox", "radio", "button"].includes(activeType)) || (document.activeElement && document.activeElement.isContentEditable);
    if (isTyping) return;

    if (e.key.toLowerCase() === "f") {
      e.preventDefault();
      const fs = document.getElementById("fullscreen-karaoke-modal");
      if (fs) {
        if (fs.classList.contains("hidden")) {
          fs.classList.remove("hidden");
          syncFullscreenKaraokeUI(state.player.currentPos, state.player.duration, { info: state.player.info });
        } else {
          fs.classList.add("hidden");
        }
      }
    } else if (e.key.toLowerCase() === "v") {
      e.preventDefault();
      if (ambientVisActive) closeFullscreenVisualizer();
      else openFullscreenVisualizer();
    } else if ((e.ctrlKey && e.altKey && e.key.toLowerCase() === "m") || (!e.ctrlKey && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "m" && !state.isSeeking)) {
      // Toggle Mini-Player on Ctrl+Alt+M or 'm'
      e.preventDefault();
      toggleMiniPlayer();
    } else if (e.key === "?") {
      e.preventDefault();
      const sc = document.getElementById("modal-shortcuts");
      if (sc) sc.classList.toggle("hidden");
    }
  });
}

// ============================================================================
// v3.4.0 Extended Systems Helper Functions
// ============================================================================
let ambientVisActive = false;
let ambientVisAnimFrame = null;

function getActiveLyricText() {
  const lyr = state.player.lyrics || {};
  const synced = lyr.synced || [];
  const cur = state.player.currentPos || 0;
  if (synced && synced.length > 0) {
    let activeText = "";
    for (let i = 0; i < synced.length; i++) {
      if (cur >= synced[i][0]) {
        activeText = synced[i][1];
      } else {
        break;
      }
    }
    if (activeText && activeText.trim()) return activeText.trim();
  }
  if (lyr.plain && lyr.plain.trim()) {
    const lines = lyr.plain.split("\n").map((l) => l.trim()).filter(Boolean);
    if (lines.length > 0) return lines[0];
  }
  return "♪ NexusTube Studio Audio";
}

async function toggleNormalization(enabled) {
  if (enabled === undefined) {
    enabled = !state.normalizeAudio;
  }
  state.normalizeAudio = !!enabled;
  syncNormalizationUI(state.normalizeAudio);
  if (state.apiReady) {
    try {
      const res = await window.pywebview.api.toggle_normalization(state.normalizeAudio);
      state.normalizeAudio = !!res;
      syncNormalizationUI(state.normalizeAudio);
      showToast(state.normalizeAudio ? "EBU R128 Dynamic Loudness Normalization Active" : "Audio Normalization Disabled");
    } catch (err) {
      console.error("toggle_normalization error:", err);
    }
  }
}

function syncNormalizationUI(enabled) {
  state.normalizeAudio = !!enabled;
  const dspToggle = document.getElementById("dsp-normalize-toggle");
  if (dspToggle && dspToggle.checked !== state.normalizeAudio) dspToggle.checked = state.normalizeAudio;
  const defToggle = document.getElementById("setting-default-normalize");
  if (defToggle && defToggle.checked !== state.normalizeAudio) defToggle.checked = state.normalizeAudio;
  const playerBtn = document.getElementById("btn-player-loudnorm");
  if (playerBtn) {
    playerBtn.classList.toggle("text-[var(--accent)]", state.normalizeAudio);
    playerBtn.classList.toggle("text-slate-400", !state.normalizeAudio);
    playerBtn.title = state.normalizeAudio ? "EBU R128 Normalization: ON (-14 LUFS)" : "Loudness Normalization: OFF";
  }
}

function updateDiscordRpcPill(status) {
  const pill = document.getElementById("discord-rpc-pill");
  const text = document.getElementById("discord-rpc-pill-text");
  if (!pill || !text) return;
  const isConn = !!(status && status.connected);
  const isEn = !!(status && status.enabled);
  if (!isEn) {
    pill.className = "status-pill-discord disabled";
    text.textContent = "Disabled";
  } else if (isConn) {
    pill.className = "status-pill-discord connected";
    text.textContent = "Connected";
  } else {
    pill.className = "status-pill-discord connecting";
    text.textContent = "Connecting…";
  }
}

window.syncMiniPlayerFromBackend = function(active) {
  if (state.miniPlayerToggling) return;
  state.miniPlayer = !!active;
  syncMiniPlayerUI(state.miniPlayer);
};

async function toggleMiniPlayer(enable) {
  if (state.miniPlayerToggling) return;
  state.miniPlayerToggling = true;

  if (enable === undefined) {
    enable = !state.miniPlayer;
  }
  const nextState = !!enable;

  if (nextState) {
    if (ambientVisActive) closeFullscreenVisualizer();
    const fsModal = document.getElementById("fullscreen-karaoke-modal");
    if (fsModal && !fsModal.classList.contains("hidden")) fsModal.classList.add("hidden");
  }

  state.miniPlayer = nextState;
  syncMiniPlayerUI(nextState);

  if (state.apiReady && window.pywebview && window.pywebview.api) {
    try {
      const curW = window.outerWidth || window.innerWidth || 1280;
      const curH = window.outerHeight || window.innerHeight || 840;
      const curX = (window.screenX !== undefined) ? window.screenX : ((window.screenLeft !== undefined) ? window.screenLeft : 0);
      const curY = (window.screenY !== undefined) ? window.screenY : ((window.screenTop !== undefined) ? window.screenTop : 0);
      const isMax = !!(
        window.screenX <= 0 &&
        window.screenY <= 0 &&
        ((window.outerWidth >= (window.screen.availWidth - 25)) || (window.innerWidth >= (window.screen.availWidth - 25))) &&
        ((window.outerHeight >= (window.screen.availHeight - 25)) || (window.innerHeight >= (window.screen.availHeight - 25)))
      );
      const res = await window.pywebview.api.toggle_mini_player(nextState, curW, curH, curX, curY, isMax);
      if (res && res.mini_player !== undefined) {
        state.miniPlayer = !!res.mini_player;
        syncMiniPlayerUI(state.miniPlayer);
      }
    } catch (err) {
      console.error("toggle_mini_player error:", err);
    }
  }

  setTimeout(() => {
    state.miniPlayerToggling = false;
  }, 400);
}

function syncMiniPlayerUI(active) {
  state.miniPlayer = !!active;
  const overlay = document.getElementById("mini-player-overlay");
  const appContainer = document.getElementById("app-root") || document.getElementById("app-container");
  const body = document.body;
  if (overlay) overlay.classList.toggle("hidden", !active);
  if (body) body.classList.toggle("mini-player-mode", active);
  if (appContainer) appContainer.classList.toggle("mini-player-active", active);

  const headerBtn = document.getElementById("btn-header-mini-player");
  if (headerBtn) {
    headerBtn.classList.toggle("text-[var(--accent)]", active);
  }
  const playerBarBtn = document.getElementById("btn-player-mini");
  if (playerBarBtn) {
    playerBarBtn.classList.toggle("text-[var(--accent)]", active);
  }
}

function syncMiniPlayerUIProgress(cur, dur, p) {
  if (!state.miniPlayer) return;
  const titleEl = document.getElementById("mini-player-title");
  const artistEl = document.getElementById("mini-player-artist");
  const lyricEl = document.getElementById("mini-player-lyric");
  const thumbEl = document.getElementById("mini-player-thumb");
  const fallbackEl = document.getElementById("mini-player-thumb-fallback");
  const fillEl = document.getElementById("mini-seek-bar-fill");
  const rangeEl = document.getElementById("mini-seek-range");
  const curTimeEl = document.getElementById("mini-time-current");
  const totTimeEl = document.getElementById("mini-time-total");
  const playIcon = document.getElementById("mini-icon-play");
  const pauseIcon = document.getElementById("mini-icon-pause");

  if (p && p.info && p.info.title) {
    if (titleEl) titleEl.textContent = p.info.title;
    if (artistEl) artistEl.textContent = p.info.artist || "NexusTube";
    if (thumbEl && fallbackEl) {
      if (p.info.cover_base64) {
        thumbEl.src = p.info.cover_base64;
        thumbEl.classList.remove("hidden");
        fallbackEl.classList.add("hidden");
      } else {
        thumbEl.src = "";
        thumbEl.classList.add("hidden");
        fallbackEl.classList.remove("hidden");
      }
    }
  }

  if (lyricEl) {
    lyricEl.textContent = getActiveLyricText();
  }

  const pct = dur > 0 ? (cur / dur) * 100 : 0;
  if (fillEl) fillEl.style.width = `${pct}%`;
  if (rangeEl && document.activeElement !== rangeEl) rangeEl.value = pct;
  if (curTimeEl) curTimeEl.textContent = formatDuration(cur);
  if (totTimeEl) totTimeEl.textContent = formatDuration(dur);

  const isPlaying = state.player.isPlaying && !state.player.isPaused;
  if (playIcon && pauseIcon) {
    playIcon.classList.toggle("hidden", isPlaying);
    pauseIcon.classList.toggle("hidden", !isPlaying);
  }

  const shuffleBtn = document.getElementById("mini-btn-shuffle");
  if (shuffleBtn) shuffleBtn.classList.toggle("text-[var(--accent)]", !!state.player.isShuffle);

  const repeatBtn = document.getElementById("mini-btn-repeat");
  if (repeatBtn) repeatBtn.classList.toggle("text-[var(--accent)]", state.player.repeatMode !== "off");

  const muteBtn = document.getElementById("mini-btn-mute");
  if (muteBtn) muteBtn.classList.toggle("text-red-400", !!state.player.isMuted);
}

function openFullscreenVisualizer() {
  const modal = document.getElementById("fullscreen-visualizer-modal");
  if (!modal) return;
  modal.classList.remove("hidden");
  ambientVisActive = true;
  startAmbientVisualizerCanvas();
  const btnPlayerVis = document.getElementById("btn-open-visualizer");
  if (btnPlayerVis) btnPlayerVis.classList.add("text-[var(--accent)]");
}

function closeFullscreenVisualizer() {
  const modal = document.getElementById("fullscreen-visualizer-modal");
  if (!modal) return;
  modal.classList.add("hidden");
  ambientVisActive = false;
  if (ambientVisAnimFrame) {
    cancelAnimationFrame(ambientVisAnimFrame);
    ambientVisAnimFrame = null;
  }
  const btnPlayerVis = document.getElementById("btn-open-visualizer");
  if (btnPlayerVis) btnPlayerVis.classList.remove("text-[var(--accent)]");
}

function cycleVisualizerMode() {
  const modes = ["neon_bars", "radial_pulse", "cyber_wave"];
  const curIdx = modes.indexOf(state.visualizerMode || "neon_bars");
  const nextIdx = (curIdx + 1) % modes.length;
  state.visualizerMode = modes[nextIdx];
  const labelEl = document.getElementById("vis-mode-label");
  if (labelEl) {
    const titles = {
      neon_bars: "Mode: Neon Bars",
      radial_pulse: "Mode: Radial Pulse",
      cyber_wave: "Mode: Cyber Wave",
    };
    labelEl.textContent = titles[state.visualizerMode] || "Mode: Neon Bars";
  }
  showToast(`Visualizer: ${state.visualizerMode.replace("_", " ").toUpperCase()}`);
}

function syncFullscreenVisualizerHUD(cur, dur, p) {
  if (!ambientVisActive) return;
  const titleEl = document.getElementById("vis-hud-title");
  const artistEl = document.getElementById("vis-hud-artist");
  const thumbEl = document.getElementById("vis-hud-thumb");
  const fillEl = document.getElementById("vis-seek-bar-fill");
  const rangeEl = document.getElementById("vis-seek-range");
  const curTimeEl = document.getElementById("vis-time-current");
  const totTimeEl = document.getElementById("vis-time-total");
  const playIcon = document.getElementById("vis-icon-play");
  const pauseIcon = document.getElementById("vis-icon-pause");

  if (p && p.info && p.info.title) {
    if (titleEl) titleEl.textContent = p.info.title;
    if (artistEl) artistEl.textContent = p.info.artist || "NexusTube";
    if (thumbEl && p.info.cover_base64) {
      thumbEl.src = p.info.cover_base64;
    }
  }

  const pct = dur > 0 ? (cur / dur) * 100 : 0;
  if (fillEl) fillEl.style.width = `${pct}%`;
  if (rangeEl && document.activeElement !== rangeEl) rangeEl.value = pct;
  if (curTimeEl) curTimeEl.textContent = formatDuration(cur);
  if (totTimeEl) totTimeEl.textContent = formatDuration(dur);

  const isPlaying = state.player.isPlaying && !state.player.isPaused;
  if (playIcon && pauseIcon) {
    playIcon.classList.toggle("hidden", isPlaying);
    pauseIcon.classList.toggle("hidden", !isPlaying);
  }
}

function startAmbientVisualizerCanvas() {
  const canvas = document.getElementById("ambient-visualizer-canvas");
  const glow = document.getElementById("vis-ambient-glow");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  function resizeCanvas() {
    if (canvas.clientWidth && canvas.clientHeight) {
      canvas.width = canvas.clientWidth * window.devicePixelRatio;
      canvas.height = canvas.clientHeight * window.devicePixelRatio;
    }
  }
  resizeCanvas();

  let phase = 0;
  const numBars = 64;
  const barHeights = new Float32Array(numBars).fill(0);

  function renderLoop() {
    if (!ambientVisActive) return;
    resizeCanvas();
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    const isPlaying = state.player.isPlaying && !state.player.isPaused;
    const vol = state.player.volume || 0.85;
    phase += 0.04;

    const accent = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#22C55E";
    let avgAmp = 0;

    if (state.visualizerMode === "radial_pulse") {
      const cx = w / 2;
      const cy = h / 2;
      const baseR = Math.min(w, h) * 0.22;
      const maxExt = Math.min(w, h) * 0.22;

      ctx.save();
      for (let i = 0; i < numBars; i++) {
        const angle = (i / numBars) * Math.PI * 2 + phase * 0.2;
        let target = 0;
        if (isPlaying) {
          const harmonic = Math.sin(phase * 1.5 + i * 0.3) * 0.5 + 0.5;
          const bass = Math.sin(phase * 3.0) * 0.4 + 0.6;
          target = (harmonic * 0.7 + bass * 0.3) * vol * maxExt;
        }
        barHeights[i] += (target - barHeights[i]) * 0.25;
        avgAmp += barHeights[i];

        const r1 = baseR;
        const r2 = baseR + barHeights[i];
        const x1 = cx + Math.cos(angle) * r1;
        const y1 = cy + Math.sin(angle) * r1;
        const x2 = cx + Math.cos(angle) * r2;
        const y2 = cy + Math.sin(angle) * r2;

        ctx.strokeStyle = accent;
        ctx.lineWidth = Math.max(2, (w / numBars) * 0.6);
        ctx.lineCap = "round";
        ctx.shadowColor = accent;
        ctx.shadowBlur = 12;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
      }
      ctx.restore();
    } else if (state.visualizerMode === "cyber_wave") {
      ctx.save();
      ctx.beginPath();
      ctx.strokeStyle = accent;
      ctx.lineWidth = 3.5;
      ctx.shadowColor = accent;
      ctx.shadowBlur = 16;
      const midY = h / 2;
      for (let x = 0; x < w; x += 4) {
        let yOffset = 0;
        if (isPlaying) {
          const w1 = Math.sin(x * 0.015 + phase * 2.0);
          const w2 = Math.cos(x * 0.035 - phase * 1.2);
          yOffset = (w1 * 0.7 + w2 * 0.3) * 60 * vol;
        }
        avgAmp += Math.abs(yOffset);
        const y = midY + yOffset;
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
      ctx.restore();
    } else {
      const barW = (w / numBars) * 0.75;
      const gap = (w / numBars) * 0.25;
      ctx.save();
      for (let i = 0; i < numBars; i++) {
        let target = 2;
        if (isPlaying) {
          const freq = Math.sin(phase * 1.8 + i * 0.22) * 0.5 + 0.5;
          const noise = Math.sin(phase * 4.0 + i * 0.8) * 0.2 + 0.8;
          target = Math.max(4, freq * noise * (h * 0.7) * vol);
        }
        barHeights[i] += (target - barHeights[i]) * 0.3;
        avgAmp += barHeights[i];

        const x = i * (barW + gap) + gap / 2;
        const y = h - barHeights[i];

        const grad = ctx.createLinearGradient(0, y, 0, h);
        grad.addColorStop(0, accent);
        grad.addColorStop(1, "rgba(255, 255, 255, 0.05)");

        ctx.fillStyle = grad;
        ctx.shadowColor = accent;
        ctx.shadowBlur = 10;
        ctx.fillRect(x, y, barW, barHeights[i]);
      }
      ctx.restore();
    }

    if (glow) {
      const normAmp = Math.min(1.0, (avgAmp / numBars) / 50.0);
      glow.style.opacity = (0.25 + normAmp * 0.55).toFixed(2);
      glow.style.transform = `scale(${(1.0 + normAmp * 0.12).toFixed(3)})`;
    }

    ambientVisAnimFrame = requestAnimationFrame(renderLoop);
  }

  if (ambientVisAnimFrame) cancelAnimationFrame(ambientVisAnimFrame);
  ambientVisAnimFrame = requestAnimationFrame(renderLoop);
}

async function checkYtdlpUpdate() {
  if (!state.apiReady) return;
  const statusEl = document.getElementById("setting-ytdlp-status-text");
  const curVerEl = document.getElementById("setting-ytdlp-current-ver");
  const latestInfo = document.getElementById("setting-ytdlp-latest-info");
  const latestVerEl = document.getElementById("setting-ytdlp-latest-ver");
  const badge = document.getElementById("setting-ytdlp-update-badge");

  if (statusEl) statusEl.textContent = "Checking GitHub…";
  try {
    const res = await window.pywebview.api.check_ytdlp_update();
    if (res) {
      if (curVerEl && res.current_version) curVerEl.textContent = res.current_version;
      if (res.has_update) {
        if (badge) badge.classList.remove("hidden");
        if (latestInfo && latestVerEl) {
          latestInfo.classList.remove("hidden");
          latestVerEl.textContent = res.latest_version;
        }
        if (statusEl) statusEl.textContent = `New release available: v${res.latest_version}`;
        showToast(`yt-dlp update found: v${res.latest_version}`, "info");
      } else {
        if (badge) badge.classList.add("hidden");
        if (statusEl) statusEl.textContent = "yt-dlp is up to date!";
        showToast("yt-dlp is up to date!");
      }
    }
  } catch (err) {
    if (statusEl) statusEl.textContent = "Check failed: " + err;
  }
}

async function updateYtdlp() {
  if (!state.apiReady) return;
  const btn = document.getElementById("btn-update-ytdlp");
  const spinner = document.getElementById("ytdlp-update-spinner");
  const btnText = document.getElementById("btn-update-ytdlp-text");
  const statusEl = document.getElementById("setting-ytdlp-status-text");
  const curVerEl = document.getElementById("setting-ytdlp-current-ver");
  const badge = document.getElementById("setting-ytdlp-update-badge");

  if (btn) btn.disabled = true;
  if (spinner) spinner.classList.remove("hidden");
  if (btnText) btnText.textContent = "Updating…";
  if (statusEl) statusEl.textContent = "Downloading latest binary from GitHub…";

  try {
    const res = await window.pywebview.api.update_ytdlp();
    if (res && res.success) {
      if (curVerEl) curVerEl.textContent = res.new_version || "Updated";
      if (badge) badge.classList.add("hidden");
      if (statusEl) statusEl.textContent = "Successfully updated to " + (res.new_version || "latest");
      showToast("yt-dlp engine updated successfully!", "success");
    } else {
      if (statusEl) statusEl.textContent = "Update failed: " + (res.error || "Unknown");
      showToast("Failed to update yt-dlp: " + (res.error || ""), "error");
    }
  } catch (err) {
    if (statusEl) statusEl.textContent = "Update error: " + err;
    showToast("Update error: " + err, "error");
  } finally {
    if (btn) btn.disabled = false;
    if (spinner) spinner.classList.add("hidden");
    if (btnText) btnText.textContent = "Update yt-dlp Now";
  }
}

function syncSleepTimerState(p) {
  if (!state.sleepTimer || !state.sleepTimer.active) return;
  if (state.sleepTimer.endOfTrack) {
    return;
  }
  const now = Date.now();
  if (state.sleepTimer.endsAt && now >= state.sleepTimer.endsAt) {
    state.sleepTimer.active = false;
    updateSleepTimerUI();
    showToast("Sleep timer elapsed: Playback stopped. 🌙");
  }
}

function updateSleepTimerUI() {
  const badge = document.getElementById("sleep-timer-badge");
  const dot = document.getElementById("sleep-timer-active-dot");
  const isActive = !!(state.sleepTimer && state.sleepTimer.active);
  if (badge) {
    if (isActive) {
      badge.classList.remove("hidden");
      badge.textContent = state.sleepTimer.endOfTrack ? "End 🌙" : `${state.sleepTimer.minutes}m 🌙`;
    } else {
      badge.classList.add("hidden");
    }
  }
  if (dot) dot.classList.toggle("hidden", !isActive);
}

function initRecentSearches() {
  const container = document.getElementById("recent-searches-tags") || document.getElementById("recent-searches-list");
  if (!container) return;

  try {
    const saved = localStorage.getItem("nexustube_recent_searches");
    state.recentSearches = saved ? JSON.parse(saved) : ["Taylor Swift", "Ed Sheeran", "Lofi Hip Hop", "Anime OST"];
  } catch (_) {
    state.recentSearches = ["Taylor Swift", "Ed Sheeran", "Lofi Hip Hop"];
  }

  const clearBtn = document.getElementById("btn-clear-recent");
  if (clearBtn) {
    clearBtn.onclick = () => {
      state.recentSearches = [];
      try {
        localStorage.removeItem("nexustube_recent_searches");
      } catch (_) {}
      renderRecentSearches();
    };
  }

  renderRecentSearches();
}

function renderRecentSearches() {
  const container = document.getElementById("recent-searches-tags") || document.getElementById("recent-searches-list");
  const parentRow = document.getElementById("recent-searches-container");
  if (!container) return;
  container.innerHTML = "";

  const items = (state.recentSearches || []).slice(0, 8);
  if (items.length === 0) {
    if (parentRow) parentRow.classList.add("hidden");
    return;
  }
  if (parentRow) parentRow.classList.remove("hidden");

  items.forEach((term) => {
    const chip = document.createElement("button");
    chip.className = "recent-search-chip";
    chip.innerHTML = `
      <svg class="w-3 h-3 text-slate-500" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
      <span>${escapeHtml(term)}</span>
    `;
    chip.onclick = () => {
      const searchInput = document.getElementById("search-input");
      if (searchInput) {
        searchInput.value = term;
        const submitBtn = document.getElementById("btn-execute-search") || document.getElementById("btn-search-submit");
        if (submitBtn) submitBtn.click();
      }
    };
    container.appendChild(chip);
  });
}

function addRecentSearch(term) {
  if (!term || typeof term !== "string") return;
  const clean = term.trim();
  if (!clean || clean.startsWith("http")) return;
  state.recentSearches = [clean, ...state.recentSearches.filter((t) => t.toLowerCase() !== clean.toLowerCase())].slice(0, 10);
  try {
    localStorage.setItem("nexustube_recent_searches", JSON.stringify(state.recentSearches));
  } catch (_) {}
  renderRecentSearches();
}

// Global functions exposed to window for inline onclicks
window.switchTab = switchTab;
window.closeModal = closeModal;
window.openConverterModal = openConverterModal;
window.addEventListener("resize", () => {
  if (state.activeTab === "equalizer") {
    requestAnimationFrame(drawEqCurve);
  }
});

// Global bootstrap on DOM ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initApp);
} else {
  initApp();
}
