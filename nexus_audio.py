"""
NexusTube — Modern Audio Engine & Multi-Platform Resolver
Contains:
- Synchronized Lyrics (LRC) parsing, formatting, matching, and LRCLIB integration
- 5-Band Audio Equalizer & DSP Presets with FFmpeg filtergraph generation
- Spotify, Apple Music, and SoundCloud playlist/track URL detection and metadata resolvers
- Automatic ID3, MP4, and FLAC tagging with embedded high-res cover art and synchronized lyrics
"""

import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    import mutagen
    from mutagen.flac import FLAC, Picture
    from mutagen.id3 import (
        APIC,
        ID3,
        TALB,
        TCON,
        TDRC,
        TIT2,
        TPE1,
        TRCK,
        USLT,
        ID3NoHeaderError,
    )
    from mutagen.mp4 import MP4, MP4Cover
except ImportError:
    mutagen = None

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

# ── Resilient Network Request Engine ──────────────────────────────────────────
def _get_resilient_session():
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

_SHARED_SESSION = _get_resilient_session()

def safe_http_get(url, params=None, headers=None, timeout=8, max_retries=3):
    """
    Executes a network request with automatic retries, backoff, timeout enforcement,
    and standardized User-Agent. Never raises an uncaught network exception.
    """
    if not url:
        return None
    req_headers = {"User-Agent": USER_AGENT}
    if headers:
        req_headers.update(headers)

    for attempt in range(max_retries):
        try:
            resp = _SHARED_SESSION.get(url, params=params, headers=req_headers, timeout=timeout)
            return resp
        except Exception:
            if attempt == max_retries - 1:
                return None
            time.sleep(0.3 * (2 ** attempt))
    return None

def safe_json_response(resp, default=None):
    """Safely extracts JSON from a requests Response object without throwing."""
    if resp is None or getattr(resp, "status_code", None) != 200:
        return default
    try:
        return resp.json()
    except Exception:
        return default

# ── Clean Title & Metadata Sanitization ───────────────────────────────────────
def clean_music_title(raw_title):
    """
    Strips noise from YouTube/music video titles, like '[Official Music Video]',
    '(HD 1080p)', '[MV]', '(Audio)', etc., to yield a clean 'Artist - Title' string.
    """
    if not raw_title:
        return ""
    t = str(raw_title).strip()

    noise_patterns = [
        r'\[\s*(?:official\s+)?(?:music\s+)?(?:video|audio|mv|visualizer|hd|4k|lyric\s+video|official)(?:\s+[\w\d\+]+)*\s*\]',
        r'\(\s*(?:official\s+)?(?:music\s+)?(?:video|audio|mv|visualizer|hd|4k|lyric\s+video|official)(?:\s+[\w\d\+]+)*\s*\)',
        r'\[\s*lyrics?(?:\s*/\s*lyric\s+video)?\s*\]',
        r'\(\s*lyrics?(?:\s*/\s*lyric\s+video)?\s*\)',
        r'\[\s*remaster(?:ed)?(?:\s+\d{4})?\s*\]',
        r'\(\s*remaster(?:ed)?(?:\s+\d{4})?\s*\)',
        r'\[\s*(?:4k|1080p|720p|hd|hq|uhd)(?:\s+\d+fps)?\s*\]',
        r'\(\s*(?:4k|1080p|720p|hd|hq|uhd)(?:\s+\d+fps)?\s*\)',
        r'\|\s*(?:official\s+)?(?:music\s+)?(?:video|audio|mv|visualizer|lyrics?)(?:\s+[\w\d\+]+)*',
    ]
    for pat in noise_patterns:
        t = re.sub(pat, '', t, flags=re.IGNORECASE)

    t = re.sub(r'\s+', ' ', t).strip()
    return t


def parse_music_metadata(raw_title, fallback_artist="", fallback_album="NexusTube Collection", fallback_track=1):
    """
    Intelligently parses track title, artist, album, and track number
    handling cases like '01 - Artist - Title', '01 - Title', 'Artist - Title',
    and YouTube clean title stripping without corrupting artist names.
    """
    cleaned = clean_music_title(raw_title)
    track_num = fallback_track
    artist = fallback_artist or ""
    title = cleaned

    # Check for leading track number prefix e.g. "01 - ", "01. ", "1 - "
    num_match = re.match(r'^(\d{1,3})[\s\.\-_]+(.*)$', cleaned)
    if num_match:
        try:
            track_num = int(num_match.group(1))
        except Exception:
            pass
        cleaned = num_match.group(2).strip()
        title = cleaned

    # Check for "Artist - Title" or "Artist — Title"
    if " - " in cleaned:
        parts = cleaned.split(" - ", 1)
        artist = parts[0].strip() or artist
        title = parts[1].strip() or title
    elif " — " in cleaned:
        parts = cleaned.split(" — ", 1)
        artist = parts[0].strip() or artist
        title = parts[1].strip() or title
    elif not artist and " by " in cleaned.lower():
        idx = cleaned.lower().find(" by ")
        title = cleaned[:idx].strip()
        artist = cleaned[idx+4:].strip()

    if not artist:
        artist = "Unknown Artist"

    return {
        "title": title or "Track",
        "artist": artist,
        "album": fallback_album or "NexusTube Collection",
        "track_num": track_num or 1
    }


# ── Synchronized Lyrics / LRC Engine ──────────────────────────────────────────
def parse_lrc(lrc_text):
    """
    Parses standard .lrc format text into a sorted list of (timestamp_seconds, text_line).
    Handles tags like [hh:mm:ss.xx], [mm:ss.xx], [mm:ss.xxx], [mm:ss], [m:ss], and multi-tag lines.
    Supports extended minute counts (e.g. [120:30.00]).
    """
    lines = []
    if not lrc_text or not isinstance(lrc_text, str):
        return lines

    tag_regex = re.compile(r'\[(?:(\d{1,2}):)?(\d{1,4}):(\d{2})(?:\.(\d{1,3}))?\]')
    try:
        for raw in lrc_text.splitlines():
            raw_str = raw.strip()
            if not raw_str:
                continue
            if re.match(r'^\[[a-zA-Z]+:', raw_str):
                continue

            tags = tag_regex.findall(raw_str)
            if tags:
                lyric_text = tag_regex.sub('', raw_str).strip()
                for h_s, m_s, s_s, ms_s in tags:
                    try:
                        h = int(h_s) if h_s else 0
                        m = int(m_s)
                        s = int(s_s)
                        ms = float(f"0.{ms_s}") if ms_s else 0.0
                        total_sec = round(h * 3600 + m * 60 + s + ms, 2)
                        lines.append((total_sec, lyric_text))
                    except Exception:
                        continue
    except Exception:
        pass

    lines.sort(key=lambda item: item[0])
    return lines


def format_lrc(lyrics_list):
    """Formats a list of (timestamp_seconds, text_line) back into standard .lrc string with precise rollover."""
    out = []
    if not isinstance(lyrics_list, (list, tuple)):
        return ""
    for item in lyrics_list:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        sec, text = item[0], item[1]
        try:
            f_sec = float(sec)
            if not math.isfinite(f_sec):
                f_sec = 0.0
        except Exception:
            f_sec = 0.0
        sec = max(0.0, f_sec)
        csec = int(round(sec * 100))
        ms = csec % 100
        total_s = csec // 100
        s = total_s % 60
        m = total_s // 60
        out.append(f"[{m:02d}:{s:02d}.{ms:02d}] {text}")
    return "\n".join(out)


def get_active_lyric_index(lyrics_list, current_seconds):
    """
    Returns the 0-based index of the currently active lyric line for the given timestamp.
    Returns -1 if current_seconds is before the first timestamp or invalid.
    """
    if not lyrics_list or current_seconds is None:
        return -1
    try:
        cur = float(current_seconds)
        if not math.isfinite(cur) or cur < 0.0:
            return -1
    except Exception:
        return -1

    active_idx = -1
    for i, item in enumerate(lyrics_list):
        if not isinstance(item, (list, tuple)) or len(item) < 1:
            continue
        sec = item[0]
        if cur >= sec:
            active_idx = i
        else:
            break
    return active_idx


def fetch_lyrics(title, artist="", duration=None, file_path=None):
    """
    Fetches synchronized (LRC) and plain lyrics.
    Checks:
    1. Local .lrc file next to audio file (if file_path provided)
    2. Embedded lyrics in ID3/MP4/FLAC metadata
    3. LRCLIB public API (https://lrclib.net)
    Returns dict: {"synced": [...(sec, text)...], "synced_raw": str, "plain": str, "source": str}
    """
    result = {"synced": [], "synced_raw": "", "plain": "", "source": "none"}

    # 1. Check local .lrc file
    if file_path and os.path.exists(file_path):
        base_no_ext = os.path.splitext(file_path)[0]
        for candidate in (f"{base_no_ext}.lrc", f"{file_path}.lrc"):
            if os.path.exists(candidate):
                try:
                    with open(candidate, "r", encoding="utf-8", errors="replace") as f:
                        raw = f.read()
                    parsed = parse_lrc(raw)
                    if parsed:
                        result["synced"] = parsed
                        result["synced_raw"] = raw
                        result["plain"] = "\n".join(t for _, t in parsed if t)
                        result["source"] = "local_lrc"
                        return result
                except Exception:
                    pass

    # 2. Check embedded lyrics
    if file_path and mutagen and os.path.exists(file_path):
        try:
            mf = mutagen.File(file_path)
            if mf and hasattr(mf, "tags") and mf.tags:
                emb_text = ""
                if hasattr(mf.tags, "getall"):
                    for u in mf.tags.getall("USLT"):
                        if u.text:
                            emb_text = str(u.text)
                            break
                if not emb_text:
                    for k in ("\xa9lyr", "LYRICS", "lyrics"):
                        if k in mf.tags:
                            val = mf.tags[k]
                            emb_text = str(val[0] if isinstance(val, list) else val)
                            break
                if emb_text:
                    parsed = parse_lrc(emb_text)
                    result["synced"] = parsed
                    result["synced_raw"] = emb_text if parsed else ""
                    result["plain"] = emb_text if not parsed else "\n".join(t for _, t in parsed if t)
                    result["source"] = "embedded"
                    if parsed:
                        return result
        except Exception:
            pass

    # 3. LRCLIB API Query
    clean_t = clean_music_title(title)
    clean_a = clean_music_title(artist)

    # If artist is not provided, attempt to separate "Artist - Title"
    if not clean_a and " - " in clean_t:
        parts = clean_t.split(" - ", 1)
        clean_a = clean_music_title(parts[0])
        clean_t = clean_music_title(parts[1])

    if not clean_t:
        return result

    # Try exact match if duration and artist are known
    url_base = "https://lrclib.net/api"
    headers = {"User-Agent": f"NexusTube-Downloader/3.0.0 ({USER_AGENT})"}

    try:
        # First attempt: GET /api/get
        params = {"track_name": clean_t}
        if clean_a:
            params["artist_name"] = clean_a
        if duration and duration > 0:
            params["duration"] = int(duration)

        resp = safe_http_get(f"{url_base}/get", params=params, headers=headers, timeout=5)
        data = safe_json_response(resp)
        if data and isinstance(data, dict):
            synced_raw = data.get("syncedLyrics") or ""
            plain = data.get("plainLyrics") or ""
            if synced_raw:
                parsed = parse_lrc(synced_raw)
                if parsed:
                    result["synced"] = parsed
                    result["synced_raw"] = synced_raw
                    result["plain"] = plain or "\n".join(t for _, t in parsed if t)
                    result["source"] = "lrclib_exact"
                    return result
            elif plain:
                result["plain"] = plain
                result["source"] = "lrclib_plain"
                return result

        # Second attempt: GET /api/search
        q = f"{clean_a} {clean_t}".strip() if clean_a else clean_t
        resp_s = safe_http_get(f"{url_base}/search", params={"q": q}, headers=headers, timeout=5)
        items = safe_json_response(resp_s)
        if isinstance(items, list) and items:
            best = next((item for item in items if isinstance(item, dict) and item.get("syncedLyrics")), items[0])
            if isinstance(best, dict):
                synced_raw = best.get("syncedLyrics") or ""
                plain = best.get("plainLyrics") or ""
                if synced_raw:
                    parsed = parse_lrc(synced_raw)
                    result["synced"] = parsed
                    result["synced_raw"] = synced_raw
                    result["plain"] = plain or "\n".join(t for _, t in parsed if t)
                    result["source"] = "lrclib_search"
                    return result
                elif plain:
                    result["plain"] = plain
                    result["source"] = "lrclib_plain"
                    return result
    except Exception:
        pass

    return result


# ── Audio Equalizer & DSP Presets ─────────────────────────────────────────────
EQ_PRESETS = {
    "Flat": {
        "bass": 0, "low_mid": 0, "mid": 0, "high_mid": 0, "treble": 0,
        "name_en": "Flat (Balanced)", "name_th": "ปกติ (เสียงมาตรฐาน)"
    },
    "Bass Boost": {
        "bass": 7, "low_mid": 4, "mid": 0, "high_mid": -1, "treble": 0,
        "name_en": "Bass Boost (+7dB)", "name_th": "เบสหนัก (Bass Boost +7dB)"
    },
    "Treble Boost": {
        "bass": -1, "low_mid": 0, "mid": 1, "high_mid": 4, "treble": 7,
        "name_en": "Treble Boost (Crystal)", "name_th": "เสียงใส (Treble Boost)"
    },
    "Vocal": {
        "bass": -2, "low_mid": 1, "mid": 5, "high_mid": 4, "treble": 1,
        "name_en": "Vocal & Acoustic", "name_th": "เสียงร้องชัด (Vocal Presence)"
    },
    "Club": {
        "bass": 6, "low_mid": 4, "mid": 2, "high_mid": 3.5, "treble": 5,
        "name_en": "Club & Dancehall", "name_th": "คลับ (Club Dancehall)"
    },
    "Rock": {
        "bass": 5, "low_mid": 3, "mid": -1, "high_mid": 3, "treble": 5,
        "name_en": "Rock / Metal", "name_th": "ร็อก (Rock / Punchy)"
    },
    "Acoustic": {
        "bass": 2, "low_mid": 2, "mid": 3, "high_mid": 3, "treble": 4,
        "name_en": "Acoustic / Live", "name_th": "อคูสติก (Acoustic Unplugged)"
    },
    "Electronic": {
        "bass": 7, "low_mid": 4, "mid": 1, "high_mid": 3, "treble": 6,
        "name_en": "Electronic / EDM", "name_th": "อิเล็กทรอนิกส์ (EDM Club)"
    },
    "Pop": {
        "bass": 3.5, "low_mid": 2, "mid": 4, "high_mid": 3, "treble": 4.5,
        "name_en": "Pop & Modern Radio", "name_th": "ป๊อป (Pop Radio)"
    },
    "Jazz": {
        "bass": 3, "low_mid": 2, "mid": 1, "high_mid": 2, "treble": 3,
        "name_en": "Jazz & Warmth", "name_th": "แจ๊ส (Warm & Smooth)"
    },
    "Hip Hop": {
        "bass": 8, "low_mid": 4.5, "mid": 0.5, "high_mid": 1.5, "treble": 3.5,
        "name_en": "Hip Hop & Urban", "name_th": "ฮิปฮอป (Hip Hop Beat)"
    },
    "Dance": {
        "bass": 7, "low_mid": 3.5, "mid": 1, "high_mid": 4.5, "treble": 6,
        "name_en": "Dance & Synth", "name_th": "แดนซ์ (Dance Synth)"
    },
    "Vocal Booster": {
        "bass": -3, "low_mid": 1, "mid": 7, "high_mid": 5, "treble": 2,
        "name_en": "Vocal Booster (Lead)", "name_th": "ขับเสียงร้อง (Vocal Booster)"
    },
    "Deep Bass": {
        "bass": 9.5, "low_mid": 5, "mid": -1, "high_mid": 0, "treble": -2,
        "name_en": "Deep Sub Bass", "name_th": "เบสลึกพิเศษ (Deep Sub Bass)"
    },
    "Nightcore": {
        "bass": 1.5, "low_mid": 1, "mid": 3, "high_mid": 5.5, "treble": 7.5,
        "name_en": "Nightcore & Speed", "name_th": "ไนท์คอร์ (Nightcore Bright)"
    },
    "Slowed Reverb": {
        "bass": 6, "low_mid": 4, "mid": 1, "high_mid": 0, "treble": -3,
        "name_en": "Slowed + Reverb Vibe", "name_th": "สโลว์ด รีเวิร์บ (Slowed + Reverb)"
    },
}

def _safe_float(val, default=0.0, min_val=None, max_val=None):
    try:
        f = float(val)
        if not math.isfinite(f):
            return default
        if min_val is not None:
            f = max(float(min_val), f)
        if max_val is not None:
            f = min(float(max_val), f)
        return f
    except Exception:
        return default

def generate_ffmpeg_eq_filter(bands, preamp=0.0, bass_boost=0.0, surround=False, normalize=False):
    """
    Generates an FFmpeg audio filter string for 5-band Equalizer and optional DSP effects:
    - bass: 60 Hz
    - low_mid: 250 Hz
    - mid: 1000 Hz
    - high_mid: 4000 Hz
    - treble: 12000 Hz
    Optional DSP effects:
    - preamp: Gain adjustment in dB [-12.0, +12.0]
    - bass_boost: Dynamic sub-bass boost percentage [0.0, 100.0]
    - surround: Widens the stereo acoustic stage
    - normalize: Enables EBU R128 dynamic loudness normalization (dynaudnorm)
    """
    if not isinstance(bands, dict):
        return ""
    freq_map = [
        ("bass", 60),
        ("low_mid", 250),
        ("mid", 1000),
        ("high_mid", 4000),
        ("treble", 12000),
    ]
    filters = []

    # Pre-amp gain
    p_val = _safe_float(preamp, 0.0)
    if p_val != 0.0:
        p_clamped = max(-12.0, min(12.0, p_val))
        filters.append(f"volume={p_clamped:.1f}dB")

    for key, freq in freq_map:
        gain = _safe_float(bands.get(key, 0), 0.0)
        if gain != 0.0:
            # Clamp between -15dB and +15dB
            g_clamped = max(-15.0, min(15.0, gain))
            filters.append(f"equalizer=f={freq}:width_type=o:w=1:g={g_clamped:.1f}")

    # Sub-bass exciter (0-100% or 0.0-1.0 ratio)
    bb = _safe_float(bass_boost, 0.0)
    if bb > 0:
        if bb <= 1.0:
            bb = bb * 100.0
        bb_clamped = max(0.0, min(100.0, bb))
        boost_db = (bb_clamped / 100.0) * 8.0  # Up to +8dB boost
        filters.append(f"equalizer=f=50:width_type=o:w=1.5:g={boost_db:.1f}")

    # Stereo Widening / 3D Surround simulation
    if surround:
        filters.append("extrastereo=m=1.6")

    # Dynamic Audio Loudness Normalization (EBU R128 / DynAudNorm)
    if normalize:
        filters.append("dynaudnorm=f=150:g=15:p=0.95:m=10.0")

    return ",".join(filters)


# ── Multi-Platform URL Detection & Resolver ───────────────────────────────────
def detect_platform_url(url):
    """
    Detects platform and link type.
    Returns: (platform, type, identifier)
    platform: 'spotify', 'apple_music', 'soundcloud', 'youtube', 'direct', 'search'
    type: 'track', 'playlist', 'album', 'video', 'search'
    """
    if not url:
        return ("search", "search", "")
    u = str(url).strip()

    # Spotify (URLs & URIs)
    if "open.spotify.com" in u or u.startswith("spotify:"):
        uri_m = re.match(r'spotify:(track|playlist|album):([a-zA-Z0-9]+)', u)
        if uri_m:
            return ("spotify", uri_m.group(1), uri_m.group(2))

        if "/track/" in u:
            m = re.search(r'/track/([a-zA-Z0-9]+)', u)
            return ("spotify", "track", m.group(1) if m else u)
        elif "/playlist/" in u:
            m = re.search(r'/playlist/([a-zA-Z0-9]+)', u)
            return ("spotify", "playlist", m.group(1) if m else u)
        elif "/album/" in u:
            m = re.search(r'/album/([a-zA-Z0-9]+)', u)
            return ("spotify", "album", m.group(1) if m else u)
        return ("spotify", "unknown", u)

    # Apple Music & iTunes
    if "music.apple.com" in u or "itunes.apple.com" in u:
        if "/playlist/" in u:
            return ("apple_music", "playlist", u)
        elif "/album/" in u:
            if "?i=" in u or "&i=" in u:
                return ("apple_music", "track", u)
            return ("apple_music", "album", u)
        elif "/song/" in u:
            return ("apple_music", "track", u)
        return ("apple_music", "unknown", u)

    # SoundCloud
    if "soundcloud.com" in u:
        if "/sets/" in u:
            return ("soundcloud", "playlist", u)
        return ("soundcloud", "track", u)

    # YouTube
    if "youtube.com" in u or "youtu.be" in u:
        if "list=" in u:
            return ("youtube", "playlist", u)
        return ("youtube", "video", u)

    if u.startswith("http://") or u.startswith("https://"):
        return ("direct", "url", u)

    return ("search", "query", u)


def resolve_multiplatform_url(url, ytdlp_bin=None):
    """
    Resolves Spotify, Apple Music, and SoundCloud URLs into structured track listings
    ready for YouTube search and download.
    Returns dict:
    {
      "platform": str,
      "type": "track" | "playlist" | "album",
      "title": str,
      "artist": str,
      "thumbnail": str,
      "tracks": [ {"title": ..., "artist": ..., "album": ..., "duration": ..., "track_num": ..., "search_query": ...}, ... ]
    }
    """
    platform, p_type, ident = detect_platform_url(url)
    res = {
        "platform": platform,
        "type": p_type,
        "title": "Universal Music Stream",
        "artist": "Multi-Platform",
        "thumbnail": "",
        "tracks": [],
    }

    headers = {"User-Agent": USER_AGENT}

    # 1. SPOTIFY RESOLVER
    if platform == "spotify":
        if p_type == "track":
            track_id = ident if ident and ident != url else ""
            if not track_id:
                m = re.search(r'/track/([a-zA-Z0-9]+)', url)
                track_id = m.group(1) if m else ""

            # Scrape embed __NEXT_DATA__ for exact title, artist list, and 640x640 album cover
            if track_id:
                try:
                    embed_url = f"https://open.spotify.com/embed/track/{track_id}"
                    r = safe_http_get(embed_url, headers=headers, timeout=8)
                    if r and r.status_code == 200:
                        m_json = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>', r.text, re.DOTALL)
                        if m_json:
                            d = json.loads(m_json.group(1))
                            entity = d.get("props", {}).get("pageProps", {}).get("state", {}).get("data", {}).get("entity", {})
                            t_title = entity.get("title") or entity.get("name") or "Spotify Track"
                            artists = entity.get("artists")
                            if artists and isinstance(artists, list):
                                t_artist = ", ".join(a.get("name", "") for a in artists if isinstance(a, dict) and a.get("name"))
                            else:
                                t_artist = entity.get("subtitle") or "Spotify Artist"

                            dur = (entity.get("duration") or 0) / 1000.0
                            imgs = entity.get("visualIdentity", {}).get("image", [])
                            thumb = imgs[-1].get("url", "") if (imgs and isinstance(imgs[-1], dict)) else ""

                            res["title"] = t_title
                            res["artist"] = t_artist
                            res["thumbnail"] = thumb
                            res["tracks"].append({
                                "title": t_title,
                                "artist": t_artist,
                                "album": res["title"],
                                "duration": dur,
                                "track_num": 1,
                                "thumbnail": thumb,
                                "search_query": f"{t_artist} - {t_title}".strip(),
                                "url": url,
                            })
                            return res
                except Exception:
                    pass

            # Fallback oEmbed
            try:
                oe_resp = safe_http_get("https://open.spotify.com/oembed", params={"url": url}, headers=headers, timeout=6)
                oe = safe_json_response(oe_resp, {})
                t_title = oe.get("title", "Spotify Track") if isinstance(oe, dict) else "Spotify Track"
                res["title"] = t_title
                res["thumbnail"] = oe.get("thumbnail_url", "") if isinstance(oe, dict) else ""
            except Exception:
                t_title = "Spotify Track"

            try:
                pg_resp = safe_http_get(url, headers=headers, timeout=6)
                if pg_resp and pg_resp.status_code == 200:
                    pg = pg_resp.text
                    m_desc = re.search(r'<meta property="og:description" content="([^"]+)"', pg)
                    if m_desc:
                        parts = m_desc.group(1).split("·")
                        if parts:
                            res["artist"] = parts[0].strip()
            except Exception:
                pass

            sq = f"{res['artist']} - {res['title']}" if res["artist"] != "Multi-Platform" else res["title"]
            res["tracks"].append({
                "title": res["title"],
                "artist": res["artist"],
                "album": res["title"],
                "duration": 0,
                "track_num": 1,
                "thumbnail": res["thumbnail"],
                "search_query": sq,
                "url": url,
            })
            return res

        elif p_type in ("playlist", "album"):
            embed_url = f"https://open.spotify.com/embed/{p_type}/{ident}"
            try:
                r = safe_http_get(embed_url, headers=headers, timeout=8)
                if r and r.status_code == 200:
                    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>', r.text, re.DOTALL)
                    if m:
                        data = json.loads(m.group(1))
                        entity = data.get("props", {}).get("pageProps", {}).get("state", {}).get("data", {}).get("entity", {})
                        res["title"] = entity.get("title") or entity.get("name") or ("Spotify Playlist" if p_type == "playlist" else "Spotify Album")
                        res["artist"] = entity.get("subtitle") or "Spotify"
                        imgs = entity.get("visualIdentity", {}).get("image", [])
                        res["thumbnail"] = imgs[-1].get("url", "") if (imgs and isinstance(imgs[-1], dict)) else ""

                        raw_list = entity.get("trackList", [])
                        for idx, trk in enumerate(raw_list, 1):
                            name = trk.get("title") or f"Track {idx}"
                            art = trk.get("subtitle") or res["artist"]
                            dur = (trk.get("duration") or 0) / 1000.0
                            res["tracks"].append({
                                "title": name,
                                "artist": art,
                                "album": res["title"],
                                "duration": dur,
                                "track_num": idx,
                                "thumbnail": res["thumbnail"],
                                "search_query": f"{art} - {name}".strip(),
                            })
            except Exception:
                pass

            # Fallback if embed failed: use oEmbed for title
            if not res["tracks"]:
                try:
                    oe_resp = safe_http_get("https://open.spotify.com/oembed", params={"url": url}, headers=headers, timeout=6)
                    oe = safe_json_response(oe_resp, {})
                    if isinstance(oe, dict):
                        res["title"] = oe.get("title", "Spotify Playlist")
                        res["thumbnail"] = oe.get("thumbnail_url", "")
                except Exception:
                    pass
            return res

    # 2. APPLE MUSIC RESOLVER (Powered by Official iTunes Lookup API + DOM Lockup Parsing)
    elif platform == "apple_music":
        # Extract track or album ID
        track_id_match = re.search(r'[?&]i=(\d+)', url) or re.search(r'/song/[^/]+/(\d+)', url)
        album_id_match = re.search(r'/album/[^/]+/(\d+)', url)

        # Single Track Resolution via iTunes API
        if track_id_match or p_type == "track":
            track_id = track_id_match.group(1) if track_id_match else None
            if not track_id and album_id_match:
                track_id = album_id_match.group(1)

            if track_id:
                try:
                    itunes_api = f"https://itunes.apple.com/lookup?id={track_id}"
                    r_api = safe_http_get(itunes_api, timeout=6)
                    data = safe_json_response(r_api, {})
                    if isinstance(data, dict):
                        results = data.get("results", [])
                        if results:
                            item = results[0]
                            t_title = item.get("trackName") or item.get("collectionName") or "Apple Music Track"
                            t_artist = item.get("artistName") or "Apple Music Artist"
                            t_album = item.get("collectionName") or "Apple Music"
                            t_dur = (item.get("trackTimeMillis") or 0) / 1000.0
                            art_url = item.get("artworkUrl100", "").replace("100x100bb", "600x600bb")

                            res["title"] = t_title
                            res["artist"] = t_artist
                            res["thumbnail"] = art_url
                            res["tracks"].append({
                                "title": t_title,
                                "artist": t_artist,
                                "album": t_album,
                                "duration": t_dur,
                                "track_num": item.get("trackNumber", 1),
                                "thumbnail": art_url,
                                "search_query": f"{t_artist} - {t_title}".strip(),
                                "url": url,
                            })
                            return res
                except Exception:
                    pass

        # Full Album Resolution via iTunes API
        if album_id_match and p_type == "album":
            album_id = album_id_match.group(1)
            try:
                itunes_api = f"https://itunes.apple.com/lookup?id={album_id}&entity=song"
                r_api = safe_http_get(itunes_api, timeout=8)
                data = safe_json_response(r_api, {})
                if isinstance(data, dict):
                    results = data.get("results", [])
                    if results:
                        collection = results[0]
                        res["title"] = collection.get("collectionName") or "Apple Music Album"
                        res["artist"] = collection.get("artistName") or "Apple Music"
                        res["thumbnail"] = collection.get("artworkUrl100", "").replace("100x100bb", "600x600bb")

                        for idx, item in enumerate(results[1:], 1):
                            if item.get("wrapperType") == "track":
                                t_name = item.get("trackName") or f"Track {idx}"
                                t_art = item.get("artistName") or res["artist"]
                                t_dur = (item.get("trackTimeMillis") or 0) / 1000.0
                                res["tracks"].append({
                                    "title": t_name,
                                    "artist": t_art,
                                    "album": res["title"],
                                    "duration": t_dur,
                                    "track_num": item.get("trackNumber", idx),
                                    "thumbnail": res["thumbnail"],
                                    "search_query": f"{t_art} - {t_name}".strip(),
                                })
                        if res["tracks"]:
                            return res
            except Exception:
                pass

        # Playlist / Web Scrape Fallback with Structured Track Lockups
        try:
            r = safe_http_get(url, headers=headers, timeout=8)
            if r and r.status_code == 200:
                html = r.text
                og_t = re.search(r'<meta property="og:title" content="([^"]+)"', html)
                if og_t:
                    res["title"] = og_t.group(1).replace(" on Apple Music", "")
                og_img = re.search(r'<meta property="og:image" content="([^"]+)"', html)
                if og_img:
                    res["thumbnail"] = og_img.group(1)

                # Parse Apple Music track lockup structure: title, subtitleLinks (artist), duration
                lockup_pat = re.compile(
                    r'"id":"track-lockup[^"]*","title":"([^"]+)".*?"subtitleLinks":\[\{"title":"([^"]+)".*?"duration":(\d+)',
                    re.DOTALL
                )
                for idx, m_trk in enumerate(lockup_pat.finditer(html), 1):
                    t_name = m_trk.group(1)
                    t_art = m_trk.group(2)
                    t_dur = float(m_trk.group(3)) / 1000.0
                    res["tracks"].append({
                        "title": t_name,
                        "artist": t_art,
                        "album": res["title"],
                        "duration": t_dur,
                        "track_num": idx,
                        "thumbnail": res["thumbnail"],
                        "search_query": f"{t_art} - {t_name}".strip(),
                    })

                # Schema fallback if lockups not present
                if not res["tracks"]:
                    schema_tracks = re.findall(r'"@type":"MusicRecording","name":"([^"]+)"', html)
                    clean_album_artist = res["title"]
                    if " by " in res["title"]:
                        parts = res["title"].split(" by ", 1)
                        clean_album_artist = parts[1].strip()
                    for idx, trk_name in enumerate(schema_tracks, 1):
                        res["tracks"].append({
                            "title": trk_name,
                            "artist": clean_album_artist,
                            "album": res["title"],
                            "duration": 0,
                            "track_num": idx,
                            "thumbnail": res["thumbnail"],
                            "search_query": f"{clean_album_artist} - {trk_name}".strip(),
                        })
        except Exception:
            pass
        return res

    # 3. SOUNDCLOUD RESOLVER
    elif platform == "soundcloud":
        if ytdlp_bin and os.path.exists(ytdlp_bin):
            try:
                cmd = [ytdlp_bin, "--flat-playlist", "--dump-json", "--no-warnings", url]
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                )
                items = []
                for line in proc.stdout:
                    try:
                        items.append(json.loads(line.decode("utf-8", errors="replace")))
                    except Exception:
                        pass
                proc.wait()
                if items:
                    res["title"] = items[0].get("playlist_title") or items[0].get("title") or "SoundCloud Playlist"
                    res["artist"] = items[0].get("uploader") or items[0].get("channel") or "SoundCloud"
                    res["thumbnail"] = items[0].get("thumbnail", "")
                    for idx, it in enumerate(items, 1):
                        t = it.get("title") or f"Track {idx}"
                        u = it.get("uploader") or res["artist"]
                        web_url = it.get("url") or it.get("webpage_url") or url
                        res["tracks"].append({
                            "title": t,
                            "artist": u,
                            "album": res["title"],
                            "duration": it.get("duration", 0),
                            "track_num": idx,
                            "thumbnail": res["thumbnail"],
                            "search_query": f"{u} - {t}".strip() if u else t,
                            "url": web_url,
                        })
                    return res
            except Exception:
                pass

        # Fallback oEmbed
        try:
            oe_resp = safe_http_get(f"https://soundcloud.com/oembed?format=json&url={url}", headers=headers, timeout=6)
            oe = safe_json_response(oe_resp, {})
            if isinstance(oe, dict):
                res["title"] = oe.get("title", "SoundCloud Audio")
                res["artist"] = oe.get("author_name", "SoundCloud")
                res["thumbnail"] = oe.get("thumbnail_url", "")
                res["tracks"].append({
                    "title": res["title"],
                    "artist": res["artist"],
                    "album": res["title"],
                    "duration": 0,
                    "track_num": 1,
                    "thumbnail": res["thumbnail"],
                    "search_query": f"{res['artist']} - {res['title']}".strip(),
                    "url": url,
                })
        except Exception:
            pass
        return res

    return res


# ── Automatic ID3 Tagger & Album Art Embedding ────────────────────────────────
def _resolve_image_bytes(cover_data_or_url):
    """Converts image URL, file path, PIL Image, or bytes into raw bytes."""
    if not cover_data_or_url:
        return None
    if isinstance(cover_data_or_url, bytes):
        return cover_data_or_url
    try:
        from PIL import Image
        if isinstance(cover_data_or_url, Image.Image):
            buf = io.BytesIO()
            cover_data_or_url.convert("RGB").save(buf, format="JPEG", quality=90)
            return buf.getvalue()
    except Exception:
        pass
    if isinstance(cover_data_or_url, str):
        if os.path.exists(cover_data_or_url):
            try:
                with open(cover_data_or_url, "rb") as f:
                    return f.read()
            except Exception:
                return None
        if cover_data_or_url.startswith("http://") or cover_data_or_url.startswith("https://"):
            try:
                r = safe_http_get(cover_data_or_url, headers={"User-Agent": USER_AGENT}, timeout=8)
                if r and r.status_code == 200:
                    return r.content
            except Exception:
                return None
    return None


def tag_audio_file(filepath, meta, cover_data_or_url=None, lyrics_text=None):
    """
    Embeds complete ID3 / MP4 / FLAC metadata tags into an audio file:
    - Title, Artist, Album, Genre, Year, Track Number
    - High-Resolution Front Cover Artwork (APIC / covr / Picture)
    - Synchronized or Plain Lyrics (USLT / \xa9lyr / LYRICS)
    Cleanses duplicate frames on re-tagging.
    """
    if not filepath or not os.path.exists(filepath) or not mutagen:
        return False

    meta = meta or {}
    title = meta.get("title") or os.path.basename(filepath).rsplit(".", 1)[0]
    artist = meta.get("artist") or "Unknown Artist"
    album = meta.get("album") or meta.get("playlist_title") or "NexusTube Downloads"
    genre = meta.get("genre") or "Music"
    year = meta.get("year") or time.strftime("%Y")
    track_num = meta.get("track_num") or meta.get("playlist_index") or 1

    img_bytes = _resolve_image_bytes(cover_data_or_url)
    lower_path = filepath.lower()

    # 1. MP3 Tagging (ID3v2.3)
    if lower_path.endswith(".mp3"):
        try:
            try:
                audio = ID3(filepath)
            except ID3NoHeaderError:
                audio = ID3()

            audio.add(TIT2(encoding=3, text=title))
            audio.add(TPE1(encoding=3, text=artist))
            audio.add(TALB(encoding=3, text=album))
            audio.add(TCON(encoding=3, text=genre))
            audio.add(TDRC(encoding=3, text=str(year)))
            audio.add(TRCK(encoding=3, text=str(track_num)))

            if lyrics_text:
                audio.delall("USLT")
                audio.add(USLT(encoding=3, lang="eng", desc="", text=lyrics_text))

            if img_bytes:
                audio.delall("APIC")
                mime = "image/jpeg" if img_bytes.startswith(b"\xff\xd8") else "image/png"
                audio.add(APIC(
                    encoding=3,
                    mime=mime,
                    type=3,  # Front Cover
                    desc="Cover",
                    data=img_bytes
                ))
            audio.save(filepath, v2_version=3)
            return True
        except Exception as e:
            print(f"[tag_audio_file] MP3 error: {e}")
            return False

    # 2. M4A / AAC Tagging (MP4 atom metadata)
    elif lower_path.endswith((".m4a", ".aac", ".mp4")):
        try:
            audio = MP4(filepath)
            audio["\xa9nam"] = [title]
            audio["\xa9ART"] = [artist]
            audio["\xa9alb"] = [album]
            audio["\xa9gen"] = [genre]
            audio["\xa9day"] = [str(year)]
            try:
                audio["trkn"] = [(int(track_num), 0)]
            except Exception:
                pass

            if lyrics_text:
                audio["\xa9lyr"] = [lyrics_text]

            if img_bytes:
                fmt = MP4Cover.FORMAT_JPEG if img_bytes.startswith(b"\xff\xd8") else MP4Cover.FORMAT_PNG
                audio["covr"] = [MP4Cover(img_bytes, imageformat=fmt)]

            audio.save()
            return True
        except Exception as e:
            print(f"[tag_audio_file] M4A error: {e}")
            return False

    # 3. FLAC Tagging (Vorbis Comments)
    elif lower_path.endswith(".flac"):
        try:
            audio = FLAC(filepath)
            audio["TITLE"] = title
            audio["ARTIST"] = artist
            audio["ALBUM"] = album
            audio["GENRE"] = genre
            audio["DATE"] = str(year)
            audio["TRACKNUMBER"] = str(track_num)

            if lyrics_text:
                audio["LYRICS"] = [lyrics_text]

            if img_bytes:
                pic = Picture()
                pic.data = img_bytes
                pic.type = 3
                pic.mime = "image/jpeg" if img_bytes.startswith(b"\xff\xd8") else "image/png"
                pic.desc = "Cover"
                audio.clear_pictures()
                audio.add_picture(pic)

            audio.save()
            return True
        except Exception as e:
            print(f"[tag_audio_file] FLAC error: {e}")
            return False

    return False


# ── Studio Audio Converter & Transcoder ────────────────────────────────────────
def convert_audio_file(input_path, output_format="mp3", bitrate=None, normalize=False, ffmpeg_bin=None, output_path=None):
    """
    Transcodes an audio file into target format: mp3, m4a, flac, wav, ogg, or opus.
    Supports optional bitrate selection (e.g. 320k, 256k, 192k, 128k) and EBU R128 loudnorm filter.
    Preserves and embeds metadata tags from the source audio file.
    """
    if not input_path or not os.path.exists(input_path):
        return {"success": False, "error": "Input file not found."}

    fmt = str(output_format).lower().lstrip(".")
    if fmt not in ("mp3", "m4a", "flac", "wav", "ogg", "opus", "aac"):
        return {"success": False, "error": f"Unsupported format: {output_format}"}

    ffmpeg = ffmpeg_bin
    if not ffmpeg or not os.path.exists(ffmpeg):
        ffmpeg = shutil.which("ffmpeg") or (
            os.path.join(os.getenv("APPDATA") or "", "YTDownloaderPro", "ffmpeg.exe")
            if sys.platform == "win32" else None
        )
    if not ffmpeg or not os.path.exists(ffmpeg):
        return {"success": False, "error": "FFmpeg binary not available for transcoding."}

    if not output_path:
        base, _ = os.path.splitext(input_path)
        ext = "m4a" if fmt == "aac" else fmt
        if f".{ext}" == os.path.splitext(input_path)[1].lower():
            output_path = f"{base}_converted.{ext}"
        else:
            output_path = f"{base}.{ext}"

    cmd = [ffmpeg, "-y", "-i", input_path, "-vn"]

    if normalize:
        cmd += ["-af", "loudnorm=I=-16:LRA=11:TP=-1.5"]

    if fmt == "mp3":
        cmd += ["-c:a", "libmp3lame"]
        br = bitrate if bitrate and str(bitrate).endswith("k") else "320k"
        cmd += ["-b:a", br]
    elif fmt in ("m4a", "aac"):
        cmd += ["-c:a", "aac"]
        br = bitrate if bitrate and str(bitrate).endswith("k") else "256k"
        cmd += ["-b:a", br]
    elif fmt == "flac":
        cmd += ["-c:a", "flac"]
    elif fmt == "wav":
        cmd += ["-c:a", "pcm_s16le", "-ar", "44100"]
    elif fmt == "ogg":
        cmd += ["-c:a", "libvorbis"]
        br = bitrate if bitrate and str(bitrate).endswith("k") else "256k"
        cmd += ["-b:a", br]
    elif fmt == "opus":
        cmd += ["-c:a", "libopus"]
        br = bitrate if bitrate and str(bitrate).endswith("k") else "160k"
        cmd += ["-b:a", br]

    cmd.append(output_path)

    try:
        proc = subprocess.run(
            cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        if not os.path.exists(output_path) or os.path.getsize(output_path) < 100:
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except Exception:
                    pass
            return {"success": False, "error": "Transcoded file was empty or not generated."}

        if mutagen:
            try:
                src_meta = parse_music_metadata(os.path.basename(input_path).rsplit(".", 1)[0])
                src_img = None
                src_lyrics = None
                try:
                    mf = mutagen.File(input_path)
                    if mf and hasattr(mf, "tags") and mf.tags:
                        if hasattr(mf.tags, "getall"):
                            for t in mf.tags.getall("TIT2"):
                                if t.text:
                                    src_meta["title"] = str(t.text[0])
                            for a in mf.tags.getall("TPE1"):
                                if a.text:
                                    src_meta["artist"] = str(a.text[0])
                            for al in mf.tags.getall("TALB"):
                                if al.text:
                                    src_meta["album"] = str(al.text[0])
                            for ap in mf.tags.getall("APIC"):
                                if getattr(ap, "data", None):
                                    src_img = ap.data
                                    break
                            for u in mf.tags.getall("USLT"):
                                if getattr(u, "text", None):
                                    src_lyrics = str(u.text)
                                    break
                        elif hasattr(mf, "pictures") and mf.pictures:
                            src_img = mf.pictures[0].data
                            if "title" in mf:
                                src_meta["title"] = str(mf["title"][0])
                            if "artist" in mf:
                                src_meta["artist"] = str(mf["artist"][0])
                            if "album" in mf:
                                src_meta["album"] = str(mf["album"][0])
                            if "lyrics" in mf:
                                src_lyrics = str(mf["lyrics"][0])
                        elif hasattr(mf, "get"):
                            if mf.get("covr"):
                                src_img = bytes(mf["covr"][0])
                            if "\xa9nam" in mf:
                                src_meta["title"] = str(mf["\xa9nam"][0])
                            if "\xa9ART" in mf:
                                src_meta["artist"] = str(mf["\xa9ART"][0])
                            if "\xa9alb" in mf:
                                src_meta["album"] = str(mf["\xa9alb"][0])
                            if "\xa9lyr" in mf:
                                src_lyrics = str(mf["\xa9lyr"][0])
                except Exception:
                    pass
                tag_audio_file(output_path, src_meta, cover_data_or_url=src_img, lyrics_text=src_lyrics)
            except Exception:
                pass

        return {
            "success": True,
            "output_path": output_path,
            "filename": os.path.basename(output_path),
            "format": fmt,
            "size_bytes": os.path.getsize(output_path),
        }
    except subprocess.CalledProcessError as cpe:
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass
        err_msg = cpe.stderr.decode("utf-8", errors="replace").strip() if cpe.stderr else str(cpe)
        return {"success": False, "error": f"FFmpeg transcoding error: {err_msg[:250]}"}
    except Exception as e:
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass
        return {"success": False, "error": str(e)}


# ── M3U8 Playlist Generator ───────────────────────────────────────────────────
def export_m3u8_playlist(filepaths, playlist_name="NexusTube_Playlist", output_dir=None):
    """
    Exports a list of audio file paths into a standard UTF-8 M3U8 playlist.
    """
    if not filepaths:
        return None
    try:
        if not output_dir or not os.path.exists(output_dir):
            output_dir = os.path.dirname(filepaths[0]) if (filepaths and os.path.exists(filepaths[0])) else tempfile.gettempdir()

        clean_name = re.sub(r'[\\/*?:"<>|]', "", str(playlist_name)).strip() or "NexusTube_Playlist"
        out_file = os.path.join(output_dir, f"{clean_name}.m3u8")

        lines = ["#EXTM3U\n"]
        for p in filepaths:
            if not p or not os.path.exists(p):
                continue
            title = os.path.basename(p).rsplit(".", 1)[0]
            duration = 0
            if mutagen:
                try:
                    mf = mutagen.File(p)
                    if mf and mf.info:
                        duration = int(getattr(mf.info, "length", 0))
                except Exception:
                    pass
            lines.append(f"#EXTINF:{duration},{title}\n{os.path.abspath(p)}\n")

        with open(out_file, "w", encoding="utf-8") as f:
            f.writelines(lines)
        return out_file
    except Exception as e:
        print(f"[export_m3u8_playlist] Error: {e}")
        return None


