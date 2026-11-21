/**
 * NexusTube — Modern Studio Desktop Music Suite (Electron Edition)
 * Main Process Orchestrator
 * Pure JavaScript & Node.js architecture with zero Python dependencies.
 */

const { app, BrowserWindow, ipcMain, protocol, net } = require('electron');
const path = require('path');
const { pathToFileURL } = require('url');
const fs = require('fs');

const { ConfigManager } = require('./src/main/config');
const { EngineManager } = require('./src/main/engine');
const { DownloadManager } = require('./src/main/downloader');
const { PlayerManager } = require('./src/main/player');
const { TrayManager } = require('./src/main/tray');
const { NexusBridgeAPI } = require('./src/main/bridge');
const { Logger } = require('./src/main/logger');
const { AppUpdater } = require('./src/main/updater');
const { startWebServer } = require('./src/main/web-download');

// ── โหมดเซิร์ฟเวอร์โหลดเพลง: `NexusTube.exe --web-server` เปิดหน้าเว็บโหลดอย่างเดียว ไม่เปิดหน้าต่างแอป
if (process.argv.includes('--web-server')) {
  const { PORT, HOST } = require('./src/main/web-download');
  const server = startWebServer();
  server.on('error', (err) => {
    if (err && err.code === 'EADDRINUSE') {
      console.log(`เว็บโหลดเปิดอยู่แล้วที่ http://${HOST}:${PORT}`);
      process.exit(0);
    }
    console.error(err);
    process.exit(1);
  });
  server.listen(PORT, HOST, () => console.log(`เว็บโหลดเพลง: http://${HOST}:${PORT}`));
  return;
}

// ── Crash-proofing: log ทุก error ลงไฟล์ ไม่ปล่อยแอปตายเงียบ ๆ
const logger = new Logger();
process.on('uncaughtException', (err) => {
  logger.error(`uncaughtException: ${err.stack || err.message}`);
});
process.on('unhandledRejection', (reason) => {
  logger.error(`unhandledRejection: ${String(reason && reason.stack || reason)}`);
});

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
let webServer = null;
const { PORT: WEB_PORT, HOST: WEB_HOST } = require('./src/main/web-download');
const webToken = require('crypto').randomBytes(16).toString('hex');

function createWindow() {
  configManager = new ConfigManager();
  engineManager = new EngineManager(configManager.appdataDir);

  // Rollback safety: ถ้าอัปเดตครั้งก่อนโดนขัดจังหวะกลางทาง คืนไฟล์เดิมก่อนโหลด UI
  try {
    const restored = AppUpdater.startupIntegrityCheck();
    if (restored) logger.warn('Update integrity check: restored previous version from backup');
  } catch {}

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
      backgroundThrottling: false,
      webSecurity: false // Enables loading local sidecar assets
    }
  });

  // Renderer พัง (crash/OOM) → โหลดหน้าใหม่อัตโนมัติ ไม่ปล่อยจอดำ
  mainWindow.webContents.on('render-process-gone', (event, details) => {
    logger.error(`renderer-process-gone: ${JSON.stringify(details)}`);
    if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.reload();
  });

  playerManager = new PlayerManager(configManager, (channel, data) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send(channel, data);
    }
  });

  downloadManager = new DownloadManager(engineManager, configManager);

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

  // ── App Self-Update (แบบ FLUX Launcher): เช็คตอนเปิด + ทุก 5 นาที → อัปเองเงียบ ๆ → รีสตาร์ทเอง
  if (app.isPackaged) {
    const sendUpdateProgress = (payload) => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('nexus:app-update-progress', payload);
      }
    };
    const checkForAppUpdate = async () => {
      try {
        if (bridge.updater.busy) return;
        const r = await bridge.updater.check();
        if (r.hasUpdate) {
          sendUpdateProgress({ phase: 'found', latest: r.latest });
          const res = await bridge.updater.apply((phase, done, total) => {
            sendUpdateProgress({ phase, done, total });
          });
          if (res && res.success) {
            sendUpdateProgress({ phase: 'restarting' });
            app.relaunch();
            app.exit(0);
          } else {
            sendUpdateProgress({ phase: 'error', message: res ? res.error : 'unknown' });
          }
        }
      } catch {}
    };
    setTimeout(checkForAppUpdate, 6000);
    setInterval(checkForAppUpdate, 5 * 60 * 1000);
  }

  // Zero Setup: ถ้ายังไม่มี yt-dlp / ffmpeg ให้โหลดอัตโนมัติตอนเปิดแอปครั้งแรก
  const engineStatus0 = engineManager.getStatus();
  if (!engineStatus0.ytdlp_ready || !engineStatus0.ffmpeg_ready) {
    const sendEngineProgress = (payload) => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('nexus:engine-progress', payload);
      }
    };
    sendEngineProgress({ phase: 'start' });
    engineManager.ensureEngines((done, total) => {
      sendEngineProgress({ phase: 'downloading', done, total });
    }).then((finalStatus) => {
      sendEngineProgress({ phase: 'done', status: finalStatus });
      logger.info(`Engine auto-setup complete: ${JSON.stringify(finalStatus)}`);
    }).catch((err) => {
      sendEngineProgress({ phase: 'error', message: String(err.message || err) });
      logger.error(`Engine auto-setup failed: ${err.message}`);
    });
  } else {
    // Self-Healing: เช็ค yt-dlp ใหม่วันละครั้ง (เงียบ ๆ ไม่รบกวน)
    const lastCheck = configManager.get('ytdlp_last_check', 0);
    if (Date.now() - lastCheck > 20 * 60 * 60 * 1000) {
      engineManager.checkYtdlpUpdate().then(async (upd) => {
        configManager.set('ytdlp_last_check', Date.now());
        if (upd && upd.has_update) {
          logger.info(`yt-dlp update available ${upd.current_version} -> ${upd.latest_version}, updating silently`);
          const res = await engineManager.updateYtdlp();
          logger.info(`yt-dlp silent update: ${JSON.stringify(res)}`);
        }
      }).catch(() => {});
    }
  }

  // Load the WebUI
  const indexPath = path.join(__dirname, 'web', 'index.html');
  mainWindow.loadFile(indexPath);

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  // Minimize to tray handling
  mainWindow.on('close', (event) => {
    if (configManager.get('minimize_to_tray', false) && !mainWindow.isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
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

  createWindow();

  // ── เว็บโหลดเพลงแบบ Local-first: ใช้ config/engine/download ตัวเดียวกับแอป จึงไม่ตีกันเอง
  try {
    webServer = startWebServer({
      config: configManager,
      engine: engineManager,
      downloads: downloadManager,
      token: webToken
    });
    webServer.on('error', (err) => {
      if (err && err.code === 'EADDRINUSE') console.warn('[web] พอร์ต 8787 ถูกใช้อยู่ ข้ามการเปิดเว็บโหลด');
      else console.error('[web]', err);
    });
    webServer.listen(WEB_PORT, WEB_HOST, () => console.log(`เว็บโหลดเพลง: http://${WEB_HOST}:${WEB_PORT}`));
  } catch (e) {
    logger.error(`web-download start failed: ${e.stack || e.message}`);
  }

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

app.on('before-quit', () => {
  if (mainWindow) {
    mainWindow.isQuitting = true;
  }
  try { if (webServer) webServer.close(); } catch {}
  if (trayManager) {
    trayManager.destroyTray();
    trayManager.unregisterShortcuts();
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
