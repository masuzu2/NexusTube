/**
 * NexusTube — Modern Studio Desktop Music Suite (Electron Edition)
 * Main Process Orchestrator
 * Pure JavaScript & Node.js architecture with zero Python dependencies.
 */

const { app, BrowserWindow, ipcMain, protocol, net, session } = require('electron');
const path = require('path');
const { pathToFileURL } = require('url');
const fs = require('fs');
const { getStreamHeaders } = require('./src/main/youtube');

function noteCrash(kind, err) {
  try {
    const dir = process.env.APPDATA ? path.join(process.env.APPDATA, 'NexusTube') : path.join(process.cwd(), 'tmp');
    fs.mkdirSync(dir, { recursive: true });
    const text = String(err && err.stack || err).slice(0, 500);
    fs.appendFileSync(path.join(dir, 'app.log'), `${new Date().toISOString()} ${kind} ${text}\n`);
  } catch {}
}
process.on('uncaughtException', (err) => noteCrash('uncaught', err));
process.on('unhandledRejection', (err) => noteCrash('rejection', err));

const { ConfigManager } = require('./src/main/config');
const { EngineManager } = require('./src/main/engine');
const { DownloadManager } = require('./src/main/downloader');
const { PlayerManager } = require('./src/main/player');
const { TrayManager } = require('./src/main/tray');
const { NexusBridgeAPI } = require('./src/main/bridge');

// Register custom privileged scheme for streaming audio files
protocol.registerSchemesAsPrivileged([
  {
    scheme: 'local-media',
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      corsEnabled: true,
      stream: true,
      bypassCSP: true
    }
  },
  {
    scheme: 'remote-media',
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      corsEnabled: true,
      stream: true,
      bypassCSP: true
    }
  }
]);

// Single Instance Lock
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
  process.exit(0);
}

let mainWindow = null;
let bridge = null;
let configManager = null;
let engineManager = null;
let playerManager = null;
let downloadManager = null;
let trayManager = null;

function createWindow() {
  configManager = new ConfigManager();
  engineManager = new EngineManager(configManager.appdataDir);

  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 960,
    minHeight: 600,
    frame: false,
    backgroundColor: '#030307',
    show: false,
    autoHideMenuBar: true,
    icon: path.join(__dirname, 'icon.ico'),
    webPreferences: {
      preload: path.join(__dirname, 'src', 'preload', 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: false,
      webSecurity: false // Enables loading local sidecar assets
    }
  });

  playerManager = new PlayerManager(configManager, (channel, data) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send(channel, data);
    }
  });

  downloadManager = new DownloadManager(engineManager, configManager);
  downloadManager.restoreQueue();

  trayManager = new TrayManager(
    mainWindow,
    playerManager,
    configManager,
    () => bridge.toggle_mini_player()
  );

  bridge = new NexusBridgeAPI({
    mainWindow,
    configManager,
    engineManager,
    downloadManager,
    playerManager,
    trayManager
  });

  trayManager.init();

  engineManager.ensureEngines()
    .then(() => engineManager.ensureFreshYtdlp())
    .catch((err) => console.warn('[Engine] background refresh failed:', err && err.message || err));

  // Load the WebUI
  const indexPath = path.join(__dirname, 'web', 'index.html');
  mainWindow.loadFile(indexPath);

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  mainWindow.on('close', (event) => {
    const stay = configManager.get('minimize_to_tray', false) && configManager.get('system_tray', false);
    if (stay && !mainWindow.isQuitting) {
      event.preventDefault();
      mainWindow.hide();
      return;
    }
    mainWindow.isQuitting = true;
    releaseRuntime();
    app.exit(0);
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// IPC Dispatcher
ipcMain.handle('nexus:api', async (event, method, ...args) => {
  if (!bridge || typeof bridge[method] !== 'function') {
    console.warn(`[IPC] Method not found on bridge: ${method}`);
    return null;
  }
  try {
    const result = await bridge[method](...args);
    return result;
  } catch (err) {
    console.error(`[IPC] Error invoking ${method}:`, err);
    return { error: String(err.message || err) };
  }
});

// IPC Listener for Renderer Player Feedback (real-time audio position & track ended)
ipcMain.on('nexus:player-sync', (event, syncData) => {
  if (playerManager && typeof playerManager.syncFromRenderer === 'function') {
    playerManager.syncFromRenderer(syncData);
  }
});

// App Lifecycle
app.whenReady().then(() => {
  const streamFilter = { urls: ['*://*.googlevideo.com/*', '*://*.youtube.com/*'] };
  session.defaultSession.webRequest.onBeforeSendHeaders(streamFilter, (details, callback) => {
    const headers = details.requestHeaders || {};
    const extra = getStreamHeaders();
    for (const [key, value] of Object.entries(extra)) {
      if (typeof value === 'string' && value) headers[key] = value;
    }
    callback({ requestHeaders: headers });
  });

  // Protocol handler for streaming local audio files
  protocol.handle('local-media', (request) => {
    try {
      let rawPath = null;
      try {
        const parsed = new URL(request.url);
        rawPath = parsed.searchParams.get('path');
      } catch {}
      if (!rawPath) {
        const rawUrl = request.url.replace(/^local-media:\/\//, '');
        rawPath = decodeURIComponent(rawUrl);
      }
      if (rawPath && fs.existsSync(rawPath)) {
        return net.fetch(pathToFileURL(rawPath).toString());
      }
    } catch (e) {
      console.warn("[Protocol] Error serving local media:", e);
    }
    return new Response('Not Found', { status: 404 });
  });

  protocol.handle('remote-media', async (request) => {
    try {
      const target = new URL(request.url).searchParams.get('url');
      if (!target || !/^https?:\/\//i.test(target)) {
        return new Response('Bad Request', { status: 400 });
      }
      const headers = { ...getStreamHeaders() };
      delete headers.Host;
      delete headers.host;
      const range = request.headers.get('range') || request.headers.get('Range');
      if (range) headers.Range = range;
      return await net.fetch(target, { headers });
    } catch (e) {
      console.warn('[Protocol] Error proxying remote media:', e);
      return new Response('Bad Gateway', { status: 502 });
    }
  });

  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    } else if (mainWindow) {
      mainWindow.show();
      mainWindow.focus();
    }
  });
});

app.on('second-instance', () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.show();
    mainWindow.focus();
  }
});

function releaseRuntime() {
  if (releaseRuntime.done) return;
  releaseRuntime.done = true;
  try { if (downloadManager) downloadManager.release(); } catch {}
  try { if (playerManager) playerManager.release(); } catch {}
  try { if (bridge && bridge.discord) bridge.discord.disconnect(); } catch {}
  try {
    if (trayManager) {
      trayManager.destroyTray();
      trayManager.unregisterShortcuts();
    }
  } catch {}
  try {
    fs.rmSync(path.join(require('os').tmpdir(), 'nexustube_cache'), { recursive: true, force: true });
  } catch {}
}

app.on('before-quit', () => {
  if (mainWindow) mainWindow.isQuitting = true;
  releaseRuntime();
});

app.on('will-quit', () => {
  releaseRuntime();
  setTimeout(() => process.exit(0), 300);
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
