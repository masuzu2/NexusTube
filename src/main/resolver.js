/**
 * NexusTube — Multi-Platform Resolver & Metadata Engine
 * Intelligently resolves YouTube, Spotify, Apple Music, and SoundCloud links into
 * structured metadata and track listings.
 */

const https = require('https');
const http = require('http');
const { spawn } = require('child_process');

const USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36";

function fetchHttp(url, headers = {}, timeout = 8000) {
  return new Promise((resolve) => {
    try {
      const u = new URL(url);
      const client = u.protocol === 'https:' ? https : http;
      const req = client.get(url, {
        headers: { 'User-Agent': USER_AGENT, ...headers },
        timeout
      }, (res) => {
        if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          return resolve(fetchHttp(res.headers.location, headers, timeout));
        }
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => resolve({ status: res.statusCode, text: data }));
      });
      req.on('error', () => resolve(null));
      req.on('timeout', () => { req.destroy(); resolve(null); });
    } catch {
      resolve(null);
    }
  });
}

function cleanMusicTitle(rawTitle) {
  if (!rawTitle) return "";
  let t = String(rawTitle).trim();

  const noisePatterns = [
    /\[\s*(?:official\s+)?(?:music\s+)?(?:video|audio|mv|visualizer|hd|4k|lyric\s+video|official)(?:\s+[\w\d\+]+)*\s*\]/gi,
    /\(\s*(?:official\s+)?(?:music\s+)?(?:video|audio|mv|visualizer|hd|4k|lyric\s+video|official)(?:\s+[\w\d\+]+)*\s*\)/gi,
    /\[\s*lyrics?(?:\s*\/\s*lyric\s+video)?\s*\]/gi,
    /\(\s*lyrics?(?:\s*\/\s*lyric\s+video)?\s*\)/gi,
    /\[\s*remaster(?:ed)?(?:\s+\d{4})?\s*\]/gi,
    /\(\s*remaster(?:ed)?(?:\s+\d{4})?\s*\)/gi,
    /\[\s*(?:4k|1080p|720p|hd|hq|uhd)(?:\s+\d+fps)?\s*\]/gi,
    /\(\s*(?:4k|1080p|720p|hd|hq|uhd)(?:\s+\d+fps)?\s*\)/gi,
    /\|\s*(?:official\s+)?(?:music\s+)?(?:video|audio|mv|visualizer|lyrics?)(?:\s+[\w\d\+]+)*/gi,
  ];

  for (const pat of noisePatterns) {
    t = t.replace(pat, '');
  }

  return t.replace(/\s+/g, ' ').trim();
}

function parseMusicMetadata(rawTitle, fallbackArtist = "", fallbackAlbum = "NexusTube Collection", fallbackTrack = 1) {
  let cleaned = cleanMusicTitle(rawTitle);
  let trackNum = fallbackTrack || 1;
  let artist = fallbackArtist || "";
  let title = cleaned;

  const numMatch = cleaned.match(/^(\d{1,3})[\s\.\-_]+(.*)$/);
  if (numMatch) {
    trackNum = parseInt(numMatch[1], 10) || 1;
    cleaned = numMatch[2].trim();
    title = cleaned;
  }

  if (cleaned.includes(" - ")) {
    const parts = cleaned.split(" - ");
    artist = parts[0].trim() || artist;
    title = parts.slice(1).join(" - ").trim() || title;
  } else if (cleaned.includes(" — ")) {
    const parts = cleaned.split(" — ");
    artist = parts[0].trim() || artist;
    title = parts.slice(1).join(" — ").trim() || title;
  } else if (!artist && cleaned.toLowerCase().includes(" by ")) {
    const idx = cleaned.toLowerCase().indexOf(" by ");
    title = cleaned.slice(0, idx).trim();
    artist = cleaned.slice(idx + 4).trim();
  }

  return {
    title: title || "Track",
    artist: artist || "Unknown Artist",
    album: fallbackAlbum || "NexusTube Collection",
    track_num: trackNum
  };
}

function detectPlatformUrl(url) {
  if (!url) return ["search", "search", ""];
  const u = String(url).trim();

  // Spotify
  if (u.includes("open.spotify.com") || u.startsWith("spotify:")) {
    const uriM = u.match(/spotify:(track|playlist|album):([a-zA-Z0-9]+)/);
    if (uriM) return ["spotify", uriM[1], uriM[2]];

    if (u.includes("/track/")) {
      const m = u.match(/\/track\/([a-zA-Z0-9]+)/);
      return ["spotify", "track", m ? m[1] : u];
    } else if (u.includes("/playlist/")) {
      const m = u.match(/\/playlist\/([a-zA-Z0-9]+)/);
      return ["spotify", "playlist", m ? m[1] : u];
    } else if (u.includes("/album/")) {
      const m = u.match(/\/album\/([a-zA-Z0-9]+)/);
      return ["spotify", "album", m ? m[1] : u];
    }
    return ["spotify", "unknown", u];
  }

  // Apple Music
  if (u.includes("music.apple.com") || u.includes("itunes.apple.com")) {
    if (u.includes("/playlist/")) return ["apple_music", "playlist", u];
    if (u.includes("/album/")) {
      if (u.includes("?i=") || u.includes("&i=")) return ["apple_music", "track", u];
      return ["apple_music", "album", u];
    }
    if (u.includes("/song/")) return ["apple_music", "track", u];
    return ["apple_music", "unknown", u];
  }

  // SoundCloud
  if (u.includes("soundcloud.com")) {
    if (u.includes("/sets/")) return ["soundcloud", "playlist", u];
    return ["soundcloud", "track", u];
  }

  // YouTube
  if (u.includes("youtube.com") || u.includes("youtu.be")) {
    if (u.includes("list=")) return ["youtube", "playlist", u];
    return ["youtube", "video", u];
  }

  if (u.startsWith("http://") || u.startsWith("https://")) {
    return ["direct", "url", u];
  }

  return ["search", "query", u];
}

async function searchYoutube(query, engineManager) {
  if (!query) return [];
  const ytdlpBin = engineManager.getYtdlpBin();
  if (!engineManager.isValidBinary(ytdlpBin)) return [];

  return new Promise((resolve) => {
    const cmd = [
      ytdlpBin,
      '--dump-json',
      '--flat-playlist',
      '--no-warnings',
      `ytsearch12:${query}`
    ];

    const proc = spawn(cmd[0], cmd.slice(1), { windowsHide: true });
    let stdout = '';
    proc.stdout.on('data', d => stdout += d.toString('utf8'));
    proc.on('close', () => {
      const items = [];
      const lines = stdout.split('\n');
      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const data = JSON.parse(line);
          const thumbs = data.thumbnails || [];
          const tUrl = thumbs.length > 0 ? thumbs[thumbs.length - 1].url : (data.thumbnail || '');
          items.push({
            id: data.id,
            title: data.title || "Unknown Title",
            channel: data.uploader || data.channel || "",
            duration: data.duration || 0,
            thumbnail: tUrl,
            url: data.url || data.webpage_url || `https://www.youtube.com/watch?v=${data.id}`
          });
        } catch {}
      }
      resolve(items);
    });
    proc.on('error', () => resolve([]));
  });
}

async function resolveUrl(url, engineManager) {
  const [plat, pType, ident] = detectPlatformUrl(url);

  // 1. Spotify Resolver
  if (plat === 'spotify') {
    const res = {
      platform: "spotify",
      type: pType,
      title: "Spotify Track",
      artist: "Spotify Artist",
      thumbnail: "",
      tracks: []
    };

    if (pType === 'track') {
      let trackId = ident;
      if (!trackId || trackId === url) {
        const m = url.match(/\/track\/([a-zA-Z0-9]+)/);
        trackId = m ? m[1] : "";
      }

      if (trackId) {
        const embedRes = await fetchHttp(`https://open.spotify.com/embed/track/${trackId}`);
        if (embedRes && embedRes.status === 200) {
          const jsonM = embedRes.text.match(/<script id="__NEXT_DATA__" type="application\/json">(.+?)<\/script>/);
          if (jsonM) {
            try {
              const d = JSON.parse(jsonM[1]);
              const entity = d.props?.pageProps?.state?.data?.entity || {};
              const tTitle = entity.title || entity.name || "Spotify Track";
              let tArtist = "Spotify Artist";
              if (Array.isArray(entity.artists)) {
                tArtist = entity.artists.map(a => a.name).filter(Boolean).join(", ");
              } else if (entity.subtitle) {
                tArtist = entity.subtitle;
              }
              const dur = (entity.duration || 0) / 1000.0;
              const imgs = entity.visualIdentity?.image || [];
              const thumb = imgs.length > 0 ? imgs[imgs.length - 1].url : "";

              res.title = tTitle;
              res.artist = tArtist;
              res.thumbnail = thumb;
              res.tracks.push({
                title: tTitle,
                artist: tArtist,
                album: res.title,
                duration: dur,
                track_num: 1,
                thumbnail: thumb,
                search_query: `${tArtist} - ${tTitle}`.trim(),
                url
              });
              res.search_query = `${tArtist} - ${tTitle}`.trim();
              return res;
            } catch {}
          }
        }
      }

      // Fallback oEmbed
      const oeRes = await fetchHttp(`https://open.spotify.com/oembed?url=${encodeURIComponent(url)}`);
      if (oeRes && oeRes.status === 200) {
        try {
          const oe = JSON.parse(oeRes.text);
          res.title = oe.title || "Spotify Track";
          res.thumbnail = oe.thumbnail_url || "";
        } catch {}
      }
      res.tracks.push({
        title: res.title,
        artist: res.artist,
        album: res.title,
        duration: 0,
        track_num: 1,
        thumbnail: res.thumbnail,
        search_query: res.title,
        url
      });
      return res;
    } else if (pType === 'playlist' || pType === 'album') {
      const embedUrl = `https://open.spotify.com/embed/${pType}/${ident}`;
      const embedRes = await fetchHttp(embedUrl);
      if (embedRes && embedRes.status === 200) {
        const jsonM = embedRes.text.match(/<script id="__NEXT_DATA__" type="application\/json">(.+?)<\/script>/);
        if (jsonM) {
          try {
            const data = JSON.parse(jsonM[1]);
            const entity = data.props?.pageProps?.state?.data?.entity || {};
            res.title = entity.title || entity.name || (pType === 'playlist' ? "Spotify Playlist" : "Spotify Album");
            res.artist = entity.subtitle || "Spotify";
            const imgs = entity.visualIdentity?.image || [];
            res.thumbnail = imgs.length > 0 ? imgs[imgs.length - 1].url : "";
            res.cover = res.thumbnail;

            const rawList = entity.trackList || [];
            rawList.forEach((trk, idx) => {
              const name = trk.title || `Track ${idx + 1}`;
              const art = trk.subtitle || res.artist;
              const dur = (trk.duration || 0) / 1000.0;
              res.tracks.push({
                title: name,
                artist: art,
                album: res.title,
                duration: dur,
                track_num: idx + 1,
                thumbnail: res.thumbnail,
                search_query: `${art} - ${name}`.trim()
              });
            });
          } catch {}
        }
      }
      return res;
    }
  }

  // 2. Apple Music Resolver
  if (plat === 'apple_music') {
    const res = {
      platform: "apple_music",
      type: pType,
      title: "Apple Music Track",
      artist: "Apple Music Artist",
      thumbnail: "",
      tracks: []
    };

    const trackIdM = url.match(/[?&]i=(\d+)/) || url.match(/\/song\/[^/]+\/(\d+)/);
    const albumIdM = url.match(/\/album\/[^/]+\/(\d+)/);

    if (trackIdM || pType === 'track') {
      const trackId = trackIdM ? trackIdM[1] : (albumIdM ? albumIdM[1] : null);
      if (trackId) {
        const itunesRes = await fetchHttp(`https://itunes.apple.com/lookup?id=${trackId}`);
        if (itunesRes && itunesRes.status === 200) {
          try {
            const data = JSON.parse(itunesRes.text);
            const results = data.results || [];
            if (results.length > 0) {
              const item = results[0];
              const tTitle = item.trackName || item.collectionName || "Apple Music Track";
              const tArtist = item.artistName || "Apple Music Artist";
              const tAlbum = item.collectionName || "Apple Music";
              const tDur = (item.trackTimeMillis || 0) / 1000.0;
              const artUrl = (item.artworkUrl100 || "").replace("100x100bb", "600x600bb");

              res.title = tTitle;
              res.artist = tArtist;
              res.thumbnail = artUrl;
              res.tracks.push({
                title: tTitle,
                artist: tArtist,
                album: tAlbum,
                duration: tDur,
                track_num: item.trackNumber || 1,
                thumbnail: artUrl,
                search_query: `${tArtist} - ${tTitle}`.trim(),
                url
              });
              res.search_query = `${tArtist} - ${tTitle}`.trim();
              return res;
            }
          } catch {}
        }
      }
    }

    if (albumIdM && pType === 'album') {
      const albumId = albumIdM[1];
      const itunesRes = await fetchHttp(`https://itunes.apple.com/lookup?id=${albumId}&entity=song`);
      if (itunesRes && itunesRes.status === 200) {
        try {
          const data = JSON.parse(itunesRes.text);
          const results = data.results || [];
          if (results.length > 0) {
            const collection = results[0];
            res.title = collection.collectionName || "Apple Music Album";
            res.artist = collection.artistName || "Apple Music";
            res.thumbnail = (collection.artworkUrl100 || "").replace("100x100bb", "600x600bb");
            res.cover = res.thumbnail;

            results.slice(1).forEach((item, idx) => {
              if (item.wrapperType === 'track') {
                const tName = item.trackName || `Track ${idx + 1}`;
                const tArt = item.artistName || res.artist;
                const tDur = (item.trackTimeMillis || 0) / 1000.0;
                res.tracks.push({
                  title: tName,
                  artist: tArt,
                  album: res.title,
                  duration: tDur,
                  track_num: item.trackNumber || (idx + 1),
                  thumbnail: res.thumbnail,
                  search_query: `${tArt} - ${tName}`.trim()
                });
              }
            });
            return res;
          }
        } catch {}
      }
    }
  }

  // 3. YouTube Resolver
  if (plat === 'youtube') {
    const ytdlpBin = engineManager.getYtdlpBin();
    if (engineManager.isValidBinary(ytdlpBin)) {
      return new Promise((resolve) => {
        const cmd = [ytdlpBin, '--dump-json', '--flat-playlist', '--no-warnings', url];
        const proc = spawn(cmd[0], cmd.slice(1), { windowsHide: true });
        let stdout = '';
        proc.stdout.on('data', d => stdout += d.toString('utf8'));
        proc.on('close', () => {
          const lines = stdout.split('\n').filter(l => l.trim());
          if (lines.length > 1 || pType === 'playlist') {
            const tracks = [];
            lines.forEach((line, idx) => {
              try {
                const d = JSON.parse(line);
                tracks.push({
                  track_num: idx + 1,
                  title: d.title || `Track ${idx + 1}`,
                  artist: d.uploader || d.channel || "",
                  duration: d.duration || 0,
                  url: d.url || d.webpage_url || `https://www.youtube.com/watch?v=${d.id}`,
                  thumbnail: d.thumbnail || ""
                });
              } catch {}
            });
            return resolve({
              platform: "youtube",
              type: "playlist",
              title: `YouTube Playlist (${tracks.length} tracks)`,
              cover: tracks.length > 0 ? tracks[0].thumbnail : "",
              tracks
            });
          } else if (lines.length > 0) {
            try {
              const d = JSON.parse(lines[0]);
              const thumbs = d.thumbnails || [];
              const tUrl = thumbs.length > 0 ? thumbs[thumbs.length - 1].url : (d.thumbnail || "");
              return resolve({
                platform: "youtube",
                type: "video",
                title: d.title || "YouTube Video",
                artist: d.uploader || d.channel || "",
                duration: d.duration || 0,
                thumbnail: tUrl,
                url: d.url || d.webpage_url || url,
                tracks: [{
                  title: d.title || "YouTube Video",
                  artist: d.uploader || d.channel || "",
                  album: "YouTube",
                  duration: d.duration || 0,
                  thumbnail: tUrl,
                  search_query: d.title || "",
                  url: d.url || d.webpage_url || url
                }]
              });
            } catch {}
          }
          resolve({ platform: plat, type: pType, url, title: url });
        });
        proc.on('error', () => resolve({ platform: plat, type: pType, url, title: url }));
      });
    }
  }

  // 4. SoundCloud Resolver
  if (plat === 'soundcloud') {
    const oeRes = await fetchHttp(`https://soundcloud.com/oembed?format=json&url=${encodeURIComponent(url)}`);
    if (oeRes && oeRes.status === 200) {
      try {
        const oe = JSON.parse(oeRes.text);
        return {
          platform: "soundcloud",
          type: pType,
          title: oe.title || "SoundCloud Track",
          artist: oe.author_name || "SoundCloud",
          thumbnail: oe.thumbnail_url || "",
          tracks: [{
            title: oe.title || "SoundCloud Track",
            artist: oe.author_name || "SoundCloud",
            album: oe.title || "SoundCloud",
            duration: 0,
            track_num: 1,
            thumbnail: oe.thumbnail_url || "",
            search_query: `${oe.author_name || ''} - ${oe.title || ''}`.trim(),
            url
          }]
        };
      } catch {}
    }
  }

  return { platform: plat, type: pType, url, title: url };
}

module.exports = {
  cleanMusicTitle,
  parseMusicMetadata,
  detectPlatformUrl,
  searchYoutube,
  resolveUrl
};
