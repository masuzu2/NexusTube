# NexusBridgeAPI — Technical API Reference

> NexusTube v3.2.0 Python-JavaScript Native Inter-Process Communication Bridge Specification
> Bridge Instance: `window.pywebview.api`

---

## 1. Overview

The `NexusBridgeAPI` class in `YT_Downloader_V2.py` exposes native Python capabilities to the Chromium/Edge WebView2 runtime. All methods are asynchronous and return standard JSON-serializable Python data structures (dicts, lists, strings, numbers, booleans).

---

## 2. API Endpoints

### 2.1 Application State & Configuration

#### `get_initial_state()`
Retrieves application bootstrap configuration, locale dictionaries, accent colors, and engine readiness.
- **Returns**: `dict`
  ```json
  {
    "version": "3.2.0",
    "config": {
      "accent": "#22C55E",
      "lang": "th",
      "format": "mp3_320",
      "embed_thumb": true,
      "embed_meta": true,
      "embed_lyrics": false,
      "sponsorblock": true,
      "normalize": false,
      "outdir": "C:\\Downloads\\NexusTube"
    },
    "locales": { ... },
    "accents": { ... },
    "eq_presets": { ... },
    "eq_bands": { "bass": 0, "low_mid": 0, "mid": 0, "high_mid": 0, "treble": 0 },
    "engine_status": {
      "ytdlp_ready": true,
      "ytdlp_version": "2025.02.19",
      "ffmpeg_ready": true,
      "ffprobe_ready": true,
      "ffplay_ready": true
    }
  }
  ```

#### `save_config(config_updates: dict)`
Persists user configuration updates to `%APPDATA%\YTDownloaderPro\config.json`.
- **Parameters**: `config_updates` (`dict`): Key-value pairs to update.
- **Returns**: `bool`: `true` if saved successfully.

#### `get_engine_status()`
Returns real-time readiness and versions for external binary tools.
- **Returns**: `dict` containing `ytdlp_ready`, `ffmpeg_ready`, `ffprobe_ready`, `ffplay_ready`.

#### `update_engines_now()`
Triggers asynchronous self-healing update check for `yt-dlp` and `ffmpeg`.
- **Returns**: `dict`: `{"success": true, "message": "Engine update completed."}`.

---

### 2.2 Search & URL Resolvers

#### `search_youtube(query: str)`
Executes `yt-dlp --dump-json --flat-playlist` to search for top YouTube results.
- **Parameters**: `query` (`str`): Search keywords.
- **Returns**: `list[dict]` containing `id`, `title`, `uploader`, `duration`, `thumbnail`, `url`.

#### `resolve_url(url: str)`
Automatically parses and extracts metadata from YouTube, Spotify, Apple Music, or SoundCloud links.
- **Parameters**: `url` (`str`): Media or playlist URL.
- **Returns**: `dict` containing:
  - `platform`: `"youtube" | "spotify" | "apple_music" | "soundcloud"`
  - `type`: `"video" | "track" | "playlist" | "album" | "set"`
  - `title`: `str`
  - `artist`: `str`
  - `duration`: `int` (seconds)
  - `thumbnail`: `str` (URL)
  - `tracks`: `list[dict]` (if playlist/album)

---

### 2.3 Download Queue Operations

#### `add_to_queue(url: str, title: str = "", fmt_choice: str = "mp3_320", options: dict = None, metadata: dict = None)`
Enqueues a media download task and spawns a background worker thread.
- **Parameters**:
  - `url` (`str`): Stream URL or search specifier.
  - `title` (`str`): Target track title.
  - `fmt_choice` (`str`): `"mp3_320" | "m4a_best" | "flac" | "mp4_best" | "mp4_1080" | "mp4_720"`
  - `options` (`dict`): Download options flags (`embed_thumb`, `embed_meta`, `embed_lyrics`, `sponsorblock`, `normalize`).
  - `metadata` (`dict`): Resolved metadata overrides (`artist`, `album`, `track_num`, `thumbnail`).
- **Returns**: `dict`: `{"task_id": "task_1725619200000_0"}`.

#### `get_queue_state()`
Returns active download tasks with real-time speed, ETA, percent, status, and thumbnails.
- **Returns**: `list[dict]`
  ```json
  [
    {
      "id": "task_1725619200000_0",
      "url": "https://www.youtube.com/watch?v=...",
      "title": "Song Title",
      "format": "mp3_320",
      "status": "downloading",
      "percent": 0.45,
      "speed": "12.5MiB/s",
      "eta": "00:08",
      "thumbnail": "https://i.ytimg.com/vi/.../mqdefault.jpg",
      "out_file": null
    }
  ]
  ```

#### `cancel_task(task_id: str)`
Terminates the active download subprocess and marks task as cancelled.
- **Returns**: `bool`.

#### `retry_task(task_id: str)`
Resets a failed or cancelled task to waiting state and restarts the download worker.
- **Returns**: `bool`.

#### `clear_finished()`
Purges completed, cancelled, and failed tasks from the in-memory queue.
- **Returns**: `bool`.

---

### 2.4 Audio Player & Equalizer Controls

#### `play_track(file_path: str)`
Loads and begins playback of an audio file. If format is non-native (e.g. M4A, Opus, FLAC), transcodes on-demand into temporary cache first.
- **Returns**: `bool`.

#### `player_control(action: str, value: any = None)`
Controls playback state.
- **Supported actions**:
  - `"play_pause"`: Toggles play/pause state.
  - `"stop"`: Stops playback and resets scrubber to 0.
  - `"prev"`: If position > 3.0s, seeks to start; otherwise plays previous track in library.
  - `"next"`: Plays next track in library (respecting shuffle state).
  - `"seek"`: Seeks to timestamp `value` (in seconds).
  - `"set_volume"`: Adjusts mixer volume `value` (`0.0` to `1.0`). Auto-unmutes.
  - `"toggle_mute"`: Toggles audio mute state.
  - `"toggle_shuffle"`: Toggles shuffle flag.
  - `"toggle_repeat"`: Cycles repeat mode: `"off"` -> `"all"` -> `"one"` -> `"off"`.
- **Returns**: Result value or boolean state.

#### `get_player_state()`
Polls current playback position, duration, and track status.
- **Returns**: `dict` containing `is_playing`, `is_paused`, `current_pos`, `duration`, `volume`, `is_muted`, `repeat_mode`, `is_shuffle`, `current_path`.

#### `set_equalizer(bands: dict)`
Applies 5-band gain parameters `{ "bass": float, "low_mid": float, "mid": float, "high_mid": float, "treble": float }` in dB.
- **Returns**: `bool`.

#### `set_eq_preset(preset_name: str)`
Applies preset gains by name (`"Flat"`, `"Bass Boost"`, `"Treble Boost"`, `"Vocal"`, `"Club"`, `"Rock"`, `"Acoustic"`, `"Electronic"`).
- **Returns**: `dict` of updated bands.

---

### 2.5 Lyrics & Sidecar Files

#### `get_lyrics(title: str, artist: str, file_path: str)`
Queries lyrics across 3 tiers: local `.lrc` sidecar file, embedded audio metadata tag, and LRCLIB public API.
- **Returns**: `dict` containing `synced` (`list[{"time": float, "text": str}]`), `plain` (`str`), and `source` (`"lrc_file" | "embedded" | "lrclib" | "none"`).

#### `save_lrc(file_path: str, lrc_content: str)`
Saves plain LRC text into a `.lrc` sidecar file next to the audio file.
- **Returns**: `bool`.

---

### 2.6 File Management & System Dialogs

#### `scan_library(filter_text: str = "", sort_by: str = "date")`
Scans the download directory for downloaded media files and extracts metadata and embedded cover art.
- **Returns**: `list[dict]` containing `path`, `title`, `artist`, `duration`, `size_bytes`, `format`, `cover_base64`.

#### `delete_file(file_path: str)`
Permanently deletes audio file and any matching `.lrc` and cover art image sidecars.
- **Returns**: `bool`.

#### `reveal_file(file_path: str)`
Opens Windows Explorer with the target file highlighted.
- **Returns**: `bool`.

#### `open_folder(folder_path: str)`
Opens Windows Explorer at the target directory.
- **Returns**: `bool`.

#### `browse_folder()`
Displays native Windows folder selection dialog.
- **Returns**: `str` selected directory path.

#### `window_control(action: str)`
Controls frameless desktop window (`"minimize" | "maximize" | "close"`).
- **Returns**: `bool`.
