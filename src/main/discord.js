/**
 * NexusTube — Discord Rich Presence (RPC) Integration
 * Zero-dependency Node.js Discord IPC client using native Windows named pipes
 * and Unix domain sockets.
 */

const net = require('net');
const path = require('path');
const os = require('os');
const fs = require('fs');

const DEFAULT_CLIENT_ID = "1251829037289013318";

const OP_HANDSHAKE = 0;
const OP_FRAME = 1;
const OP_CLOSE = 2;
const OP_PING = 3;
const OP_PONG = 4;

class DiscordRPC {
  constructor(clientId = DEFAULT_CLIENT_ID, enabled = true) {
    this.clientId = String(clientId);
    this.enabled = Boolean(enabled);
    this.socket = null;
    this.connected = false;
    this.connecting = false;
    this.lastConnectAttempt = 0;
    this.lastActivity = null;
    this.isWin = process.platform === 'win32';
  }

  setEnabled(enabled) {
    this.enabled = Boolean(enabled);
    if (!this.enabled) {
      this.disconnect();
    } else {
      this.connect();
    }
    return this.enabled;
  }

  getSocketPath(i) {
    if (this.isWin) {
      return `\\\\.\\pipe\\discord-ipc-${i}`;
    }
    const envDirs = [process.env.XDG_RUNTIME_DIR, process.env.TMPDIR, process.env.TMP, process.env.TEMP, '/tmp'];
    for (const d of envDirs) {
      if (d) {
        const candidate = path.join(d, `discord-ipc-${i}`);
        if (fs.existsSync(candidate)) return candidate;
      }
    }
    return `/tmp/discord-ipc-${i}`;
  }

  connect() {
    if (!this.enabled || this.connected || this.connecting) {
      return Promise.resolve(this.connected);
    }

    const now = Date.now();
    if (now - this.lastConnectAttempt < 3000) {
      return Promise.resolve(false);
    }
    this.lastConnectAttempt = now;
    this.connecting = true;

    return new Promise((resolve) => {
      let index = 0;

      const tryNextPipe = () => {
        if (index >= 10 || !this.enabled) {
          this.connecting = false;
          this.connected = false;
          return resolve(false);
        }

        const pipePath = this.getSocketPath(index);
        index++;

        const sock = net.createConnection(pipePath);

        const cleanup = () => {
          sock.removeAllListeners();
          try { sock.destroy(); } catch {}
        };

        const timeoutId = setTimeout(() => {
          cleanup();
          tryNextPipe();
        }, 800);

        sock.once('error', () => {
          clearTimeout(timeoutId);
          cleanup();
          tryNextPipe();
        });

        sock.once('connect', () => {
          clearTimeout(timeoutId);
          this.socket = sock;

          // Send Handshake
          try {
            this.sendPacket(OP_HANDSHAKE, { v: 1, client_id: this.clientId });
          } catch {
            cleanup();
            return tryNextPipe();
          }

          sock.once('data', (data) => {
            if (data.length >= 8) {
              const op = data.readUInt32LE(0);
              if (op === OP_FRAME) {
                this.connected = true;
                this.connecting = false;

                sock.on('error', () => this.disconnect());
                sock.on('close', () => this.disconnect());

                if (this.lastActivity) {
                  this.setActivity(this.lastActivity);
                }
                return resolve(true);
              }
            }
            cleanup();
            tryNextPipe();
          });
        });
      };

      tryNextPipe();
    });
  }

  sendPacket(opcode, payload) {
    if (!this.socket || !this.socket.writable) return false;
    const jsonStr = JSON.stringify(payload);
    const jsonBuf = Buffer.from(jsonStr, 'utf8');
    const headerBuf = Buffer.alloc(8);
    headerBuf.writeUInt32LE(opcode, 0);
    headerBuf.writeUInt32LE(jsonBuf.length, 4);

    try {
      this.socket.write(Buffer.concat([headerBuf, jsonBuf]));
      return true;
    } catch {
      this.disconnect();
      return false;
    }
  }

  setActivity(activity = null) {
    if (!this.enabled) return false;

    this.lastActivity = activity;

    if (!this.connected) {
      this.connect();
      return false;
    }

    const nonce = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const packet = {
      cmd: 'SET_ACTIVITY',
      args: {
        pid: process.pid,
        activity: activity || null
      },
      nonce
    };

    return this.sendPacket(OP_FRAME, packet);
  }

  clearActivity() {
    this.lastActivity = null;
    return this.setActivity(null);
  }

  updatePlayback(playerState) {
    if (!this.enabled) return false;
    if (!playerState || (!playerState.is_playing && !playerState.is_paused)) {
      return this.clearActivity();
    }

    const info = playerState.info || {};
    const titleStr = (String(info.title || path.basename(playerState.current_path || '') || 'NexusTube Track').trim()).slice(0, 128);
    const artistStr = (String(info.artist || 'NexusTube Artist').trim()).slice(0, 128);
    const albumStr = (String(info.album || 'NexusTube Music').trim()).slice(0, 128);

    const isPlaying = playerState.is_playing && !playerState.is_paused;

    const activity = {
      details: titleStr,
      state: `by ${artistStr}`,
      assets: {
        large_image: "nexustube_logo",
        large_text: albumStr,
        small_image: isPlaying ? "play" : "pause",
        small_text: isPlaying ? "Playing" : "Paused"
      },
      instance: true
    };

    if (isPlaying) {
      const now = Math.floor(Date.now() / 1000);
      const curPos = Math.max(0, Math.floor(playerState.current_pos || 0));
      const startTs = Math.max(0, now - curPos);
      const timestamps = { start: startTs };

      if (playerState.duration && playerState.duration > curPos) {
        timestamps.end = Math.max(startTs, now - curPos + Math.floor(playerState.duration));
      }
      activity.timestamps = timestamps;
    }

    return this.setActivity(activity);
  }

  disconnect() {
    this.connected = false;
    this.connecting = false;
    if (this.socket) {
      try {
        this.socket.removeAllListeners();
        this.socket.destroy();
      } catch {}
      this.socket = null;
    }
  }
}

module.exports = { DiscordRPC };
