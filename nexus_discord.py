"""
NexusTube — Discord Rich Presence (RPC) Integration
Lightweight, zero-dependency Discord IPC client using native Windows named pipes
and Unix domain sockets.
"""

import json
import os
import socket
import struct
import sys
import threading
import time
import uuid

# Default Client ID for NexusTube Discord Application
DEFAULT_CLIENT_ID = "1251829037289013318"

OP_HANDSHAKE = 0
OP_FRAME = 1
OP_CLOSE = 2
OP_PING = 3
OP_PONG = 4


class DiscordRPC:
    """
    Asynchronous, non-blocking Discord Rich Presence client.
    Safely connects to the local Discord client via IPC without blocking main audio threads.
    """

    def __init__(self, client_id=DEFAULT_CLIENT_ID, enabled=True):
        self.client_id = str(client_id)
        self.enabled = bool(enabled)
        self._pipe = None
        self._connected = False
        self._lock = threading.Lock()
        self._last_connect_attempt = 0
        self._last_activity = None
        self._is_win = sys.platform == "win32"

    @property
    def connected(self):
        return self._connected

    def connect(self):
        """Attempts to establish an IPC pipe connection to the local Discord client."""
        if not self.enabled:
            return False
        if self._connected and self._pipe:
            return True

        now = time.time()
        if now - self._last_connect_attempt < 3.0:
            return False
        self._last_connect_attempt = now

        with self._lock:
            self._close_pipe()
            for i in range(10):
                try:
                    if self._is_win:
                        pipe_path = f"\\\\.\\pipe\\discord-ipc-{i}"
                        self._pipe = open(pipe_path, "r+b", buffering=0)
                    else:
                        path = ""
                        for env_var in ("XDG_RUNTIME_DIR", "TMPDIR", "TMP", "TEMP"):
                            val = os.getenv(env_var)
                            if val and os.path.exists(os.path.join(val, f"discord-ipc-{i}")):
                                path = os.path.join(val, f"discord-ipc-{i}")
                                break
                        if not path and os.path.exists(f"/tmp/discord-ipc-{i}"):
                            path = f"/tmp/discord-ipc-{i}"
                        if not path:
                            continue
                        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                        s.connect(path)
                        self._pipe = s.makefile("rwb", buffering=0)

                    # Send handshake
                    handshake_payload = {"v": 1, "client_id": self.client_id}
                    self._send(OP_HANDSHAKE, handshake_payload)
                    opcode, _resp = self._read(timeout=0.6)
                    if opcode == OP_FRAME:
                        self._connected = True
                        return True
                    else:
                        self._close_pipe()
                except Exception:
                    self._close_pipe()
                    continue

        self._connected = False
        return False

    def _close_pipe(self):
        """Safely closes the underlying pipe handle."""
        if self._pipe:
            try:
                self._pipe.close()
            except Exception:
                pass
            self._pipe = None
        self._connected = False

    def _send(self, opcode, data):
        """Encodes and sends an IPC frame packet."""
        if not self._pipe:
            raise OSError("IPC pipe is not open")
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        header = struct.pack("<II", opcode, len(payload))
        self._pipe.write(header + payload)
        self._pipe.flush()

    def _read_bytes(self, n, timeout=0.8):
        """Reads exactly n bytes with strict non-blocking timeout protection."""
        if not self._pipe:
            return None
        has_fileno = False
        try:
            has_fileno = hasattr(self._pipe, "fileno") and callable(self._pipe.fileno)
            if has_fileno:
                self._pipe.fileno()
        except Exception:
            has_fileno = False

        if not has_fileno:
            try:
                data = self._pipe.read(n)
                return data if len(data) == n else None
            except Exception:
                return None

        if self._is_win:
            try:
                import msvcrt
                import ctypes
                from ctypes import wintypes
                handle = msvcrt.get_osfhandle(self._pipe.fileno())
                avail = wintypes.DWORD()
                start = time.time()
                buf = bytearray()
                while len(buf) < n:
                    if time.time() - start > timeout:
                        return None
                    ok = ctypes.windll.kernel32.PeekNamedPipe(
                        handle, None, 0, None, ctypes.byref(avail), None
                    )
                    if not ok:
                        return None
                    if avail.value > 0:
                        needed = n - len(buf)
                        to_read = min(needed, avail.value)
                        chunk = self._pipe.read(to_read)
                        if not chunk:
                            return None
                        buf.extend(chunk)
                    else:
                        time.sleep(0.02)
                return bytes(buf)
            except Exception:
                return None
        else:
            try:
                import select
                fd = self._pipe.fileno()
                start = time.time()
                buf = bytearray()
                while len(buf) < n:
                    rem = max(0.01, timeout - (time.time() - start))
                    r, _, _ = select.select([fd], [], [], rem)
                    if not r:
                        return None
                    chunk = self._pipe.read(n - len(buf))
                    if not chunk:
                        return None
                    buf.extend(chunk)
                return bytes(buf)
            except Exception:
                return None

    def _read(self, timeout=0.8):
        """Reads an incoming IPC frame packet with timeout guard."""
        header = self._read_bytes(8, timeout=timeout)
        if not header or len(header) < 8:
            return None, None
        opcode, length = struct.unpack("<II", header)
        if length > 65536:
            return None, None
        payload = self._read_bytes(length, timeout=timeout)
        if not payload or len(payload) < length:
            return None, None
        try:
            return opcode, json.loads(payload.decode("utf-8", errors="replace"))
        except Exception:
            return opcode, {}

    def set_activity(self, activity=None):
        """Sets the Discord Rich Presence status."""
        if not self.enabled:
            return False

        if activity is None and not self._connected:
            return True

        if not self._connected:
            if not self.connect():
                return False

        with self._lock:
            try:
                packet = {
                    "cmd": "SET_ACTIVITY",
                    "args": {
                        "pid": os.getpid(),
                        "activity": activity,
                    },
                    "nonce": str(uuid.uuid4()),
                }
                self._send(OP_FRAME, packet)
                self._last_activity = activity
                return True
            except Exception:
                self._close_pipe()
                return False

    def clear_activity(self):
        """Clears the active Discord presence."""
        if not self._connected:
            return True
        return self.set_activity(None)

    def update_playback(
        self,
        title="Unknown Title",
        artist="NexusTube",
        duration=0,
        current_pos=0.0,
        is_playing=True,
        is_paused=False,
        album="NexusTube Music",
        cover_url="",
    ):
        """
        High-level helper to update rich presence based on current audio playback state.
        """
        if not self.enabled:
            return False

        if not is_playing and not is_paused:
            return self.clear_activity()

        title_str = (str(title).strip() or "Unknown Title")[:128]
        artist_str = (str(artist).strip() or "NexusTube")[:128]
        album_str = (str(album).strip() or "NexusTube Music")[:128]

        # Construct Discord activity dictionary
        activity = {
            "details": title_str,
            "state": f"by {artist_str}",
            "assets": {
                "large_image": cover_url if (cover_url and cover_url.startswith("http")) else "nexustube_logo",
                "large_text": album_str,
                "small_image": "play" if (is_playing and not is_paused) else "pause",
                "small_text": "Playing" if (is_playing and not is_paused) else "Paused",
            },
            "instance": True,
        }

        # Timestamps for dynamic Discord progress bar
        if is_playing and not is_paused:
            now = time.time()
            start_ts = max(0, int(now - current_pos))
            timestamps = {"start": start_ts}
            if duration and duration > current_pos:
                timestamps["end"] = max(start_ts, int(now - current_pos + duration))
            activity["timestamps"] = timestamps

        return self.set_activity(activity)

    def close(self):
        """Gracefully tears down connection."""
        with self._lock:
            if self._connected and self._pipe:
                try:
                    self._send(OP_CLOSE, {})
                except Exception:
                    pass
            self._close_pipe()
