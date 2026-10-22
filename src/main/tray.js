/**
 * NexusTube — System Tray, Global Hotkeys & Desktop Integration
 * Provides Windows system tray status bar, media keyboard global shortcuts,
 * and background minimize-to-tray handling.
 */

const { Tray, Menu, nativeImage, globalShortcut, app } = require('electron');
const path = require('path');
const fs = require('fs');

class TrayManager {
  constructor(mainWindow, playerManager, configManager, onToggleMini = null) {
    this.win = mainWindow;
    this.player = playerManager;
    this.config = configManager;
    this.onToggleMini = onToggleMini;
    this.tray = null;
    this.iconPath = path.join(__dirname, '..', '..', 'icon.ico');

    this.shortcutsRegistered = false;
  }

  init() {
    if (this.config.get('system_tray', true)) {
      this.createTray();
    }
    if (this.config.get('global_hotkeys', true)) {
      this.registerShortcuts();
    }
  }

  createTray() {
    if (this.tray) return;

    let icon = null;
    try {
      if (fs.existsSync(this.iconPath)) {
        icon = nativeImage.createFromPath(this.iconPath);
      }
    } catch {}

    if (!icon || icon.isEmpty()) {
      icon = nativeImage.createEmpty();
    }

    try {
      this.tray = new Tray(icon);
      this.tray.setToolTip("NexusTube Studio Desktop Player");

      const contextMenu = Menu.buildFromTemplate([
        { label: "NexusTube v3.4.0", enabled: false },
        { type: "separator" },
        {
          label: "▶ Play / Pause",
          click: () => this.player.playerControl("play_pause")
        },
        {
          label: "⏭ Next Track",
          click: () => this.player.playerControl("next")
        },
        {
          label: "⏮ Previous Track",
          click: () => this.player.playerControl("prev")
        },
        { type: "separator" },
        {
          label: "Show NexusTube",
          click: () => {
            if (this.win) {
              this.win.show();
              this.win.focus();
            }
          }
        },
        {
          label: "Quit",
          click: () => {
            if (this.win) {
              this.win.isQuitting = true;
            }
            app.quit();
          }
        }
      ]);

      this.tray.setContextMenu(contextMenu);

      this.tray.on('click', () => {
        if (!this.win) return;
        if (this.win.isVisible()) {
          this.win.focus();
        } else {
          this.win.show();
          this.win.focus();
        }
      });
    } catch (err) {
      console.warn("[TrayManager] Tray creation skipped:", err.message);
    }
  }

  destroyTray() {
    if (this.tray) {
      try {
        this.tray.destroy();
      } catch {}
      this.tray = null;
    }
  }

  registerShortcuts() {
    if (this.shortcutsRegistered) return;
    try {
      globalShortcut.register('MediaPlayPause', () => {
        this.player.playerControl("play_pause");
      });
      globalShortcut.register('MediaNextTrack', () => {
        this.player.playerControl("next");
      });
      globalShortcut.register('MediaPreviousTrack', () => {
        this.player.playerControl("prev");
      });
      globalShortcut.register('CommandOrControl+Alt+M', () => {
        if (typeof this.onToggleMini === 'function') {
          this.onToggleMini();
        }
      });
      this.shortcutsRegistered = true;
    } catch (err) {
      console.warn("[TrayManager] Global shortcuts skipped:", err.message);
    }
  }

  unregisterShortcuts() {
    if (!this.shortcutsRegistered) return;
    try {
      globalShortcut.unregister('MediaPlayPause');
      globalShortcut.unregister('MediaNextTrack');
      globalShortcut.unregister('MediaPreviousTrack');
      globalShortcut.unregister('CommandOrControl+Alt+M');
    } catch {}
    this.shortcutsRegistered = false;
  }

  toggleSystemTray(enabled = null) {
    const next = enabled !== null ? Boolean(enabled) : !this.tray;
    this.config.set('system_tray', next);
    if (next) {
      this.createTray();
    } else {
      this.destroyTray();
    }
    return next;
  }

  toggleGlobalHotkeys(enabled = null) {
    const next = enabled !== null ? Boolean(enabled) : !this.shortcutsRegistered;
    this.config.set('global_hotkeys', next);
    if (next) {
      this.registerShortcuts();
    } else {
      this.unregisterShortcuts();
    }
    return next;
  }

  toggleMinimizeToTray(enabled = null) {
    const next = enabled !== null ? Boolean(enabled) : !this.config.get('minimize_to_tray', false);
    this.config.set('minimize_to_tray', next);
    return next;
  }
}

module.exports = { TrayManager };
