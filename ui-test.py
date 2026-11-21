# NexusTube UI test (webapp-testing: real browser, http:// not file://)
# Stubs window.pywebview.api with full-shape mock, clicks through all views,
# collects console errors / page errors / layout overflow, screenshots each view.
import json, sys
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

PAGE = "http://127.0.0.1:8140/index.html"
OUT = r"E:\projects_backup\NexusTube - js\ui-shots"

results = {"console_errors": [], "console_warns": [], "page_errors": [], "overflow": [], "steps": []}

def check_overflow(page, label):
    bad = page.evaluate("""() => {
      const doc = document.documentElement;
      const out = [];
      if (doc.scrollWidth > doc.clientWidth + 2) out.push('page hscroll ' + doc.scrollWidth + '>' + doc.clientWidth);
      for (const el of document.querySelectorAll('*')) {
        const r = el.getBoundingClientRect();
        if (r.width > 0 && (r.right > doc.clientWidth + 4 || r.left < -4)) {
          const cs = getComputedStyle(el);
          if (cs.position === 'fixed') continue;
          out.push(el.tagName.toLowerCase() + ' right=' + Math.round(r.right));
          if (out.length > 8) break;
        }
      }
      return out;
    }""")
    if bad:
        results["overflow"].append(f"{label}: {bad[:8]}")

STUB = """
const engine_status = { ytdlp_ready: true, ytdlp_version: '2026.10.26', ffmpeg_ready: true, ffprobe_ready: true, ffplay_ready: true };
const handlers = {
  get_initial_state: async () => ({
    version: '3.4.1',
    config: { accent: '#8B5CF6', lang: 'th', format: 'mp3_320', outdir: 'C:/Users/Administrator/Downloads/NexusTube',
              embed_thumb: true, embed_meta: true, embed_lyrics: false, sponsorblock: 'sponsor', normalize: false,
              eq_preset: 'Flat', eq_bands: { bass: 0, low_mid: 0, mid: 0, high_mid: 0, treble: 0 },
              dsp_effects: { preamp: 0, bass_boost: 0, surround: false }, favorites: [], library_view: 'table',
              recent_searches: [], discord_rpc: true, global_hotkeys: true, system_tray: true, minimize_to_tray: false },
    locales: {
      MENU: { en: 'MENU', th: 'เมนูหลัก' },
      STUDIO_TOOLS: { en: 'STUDIO TOOLS', th: 'เครื่องมือสตูดิโอ' },
      Queue_Sub: { en: 'Track active downloads', th: 'ติดตามสถานะการดาวน์โหลดแบบเรียลไทม์' },
      Search: { en: 'Search', th: 'ค้นหา' },
      Queue: { en: 'Queue', th: 'ดาวน์โหลด' },
      Library: { en: 'Library', th: 'คลังเพลง' },
      Equalizer: { en: 'Equalizer', th: 'อีควอไลเซอร์' },
      Lyrics: { en: 'Lyrics', th: 'เนื้อเพลง' },
      Settings: { en: 'Settings', th: 'ตั้งค่า' },
      SearchBtn: { en: 'Search', th: 'ค้นหา' },
      Downloading: { en: 'Downloading', th: 'กำลังดาวน์โหลด' },
    }, accents: [], eq_presets: { Flat: { bass: 0, low_mid: 0, mid: 0, high_mid: 0, treble: 0, name_en: 'Flat', name_th: 'ปกติ' } },
    eq_bands: { bass: 0, low_mid: 0, mid: 0, high_mid: 0, treble: 0 },
    engine_status,
    sleep_timer: { active: false }, mini_player: false, normalize: false,
    discord_rpc: { enabled: true, connected: false },
  }),
  get_engine_status: async () => engine_status,
  check_ytdlp_update: async () => ({ has_update: false, current_version: '2026.10.26', latest_version: '2026.10.26' }),
  get_clipboard: async () => '',
  get_queue_state: async () => ([
    { id: 't1', title: 'Lofi Study Mix', url: 'https://youtube.com/watch?v=1', format: 'MP3 320K', status: 'completed', percent: 1.0, speed: '2.5 MiB/s', eta: '00:00', thumbnail: '', out_file: 'C:/music/Lofi Study Mix.mp3', error: null },
    { id: 't2', title: 'Cyber Indie Track', url: 'https://youtube.com/watch?v=2', format: 'MP4 1080P', status: 'downloading', percent: 0.45, speed: '4.1 MiB/s', eta: '00:32', thumbnail: '', out_file: null, error: null },
  ]),
  get_library: async () => ([
    { path: 'C:/music/Sunset Drive.mp3', title: 'Sunset Drive', artist: 'Neon Wave', album: 'Retrowave', duration: 214, size_bytes: 8355840, is_favorite: true, format: 'MP3' },
    { path: 'C:/music/Midnight Coffee.mp3', title: 'Midnight Coffee', artist: 'Lofi Cat', album: 'Chill Beats', duration: 187, size_bytes: 7168000, is_favorite: false, format: 'MP3' },
    { path: 'C:/music/Rainy Window.flac', title: 'Rainy Window', artist: 'Ambient Owl', album: 'Soft Focus', duration: 256, size_bytes: 28311552, is_favorite: false, format: 'FLAC' },
  ]),
  get_favorites: async () => ([]),
  get_player_state: async () => ({ is_playing: false, is_paused: false, current_pos: 0, duration: 0, volume: 0.8,
                                   is_muted: false, repeat_mode: 'off', is_shuffle: false, playback_speed: 1,
                                   info: { title: '', artist: '', album: '', duration: 0 } }),
  play_track: async () => ({ title: 'Sunset Drive', artist: 'Neon Wave', duration: 214 }),
  stream_track: async () => ({ url: 'http://127.0.0.1:1/silent.mp3', title: 'Preview' }),
  get_sleep_timer_state: async () => ({ active: false }),
  get_mini_player_state: async () => ({ active: false }),
  get_cookie_config: async () => ({ cookie_source: null, cookie_file: null }),
  save_config: async () => ({}),
  search_youtube: async () => ([
    { id: 'a1', title: 'Neon Skyline (Official MV)', channel: 'SynthRider', duration: 231, thumbnail: '', url: 'https://youtube.com/watch?v=a1' },
    { id: 'a2', title: 'Glass City - Lofi Remix', channel: 'ChillWave', duration: 198, thumbnail: '', url: 'https://youtube.com/watch?v=a2' },
  ]),
  resolve_url: async () => ({ url: 'https://youtube.com/watch?v=a1', title: 'Neon Skyline', artist: 'SynthRider', tracks: [] }),
};
window.pywebview = { api: new Proxy(handlers, { get: (t, k) => t[k] || (async () => ({})) }) };
window.electronAPI = window.pywebview;
document.addEventListener('DOMContentLoaded', () => window.dispatchEvent(new Event('pywebviewready')));
"""

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.on("console", lambda m: (results["console_errors"].append(m.text) if m.type == "error" else
                                   (results["console_warns"].append(m.text[:120]) if m.type == "warning" else None)))
    page.on("pageerror", lambda e: results["page_errors"].append(getattr(e, "stack", None) or str(e)))

    page.add_init_script(STUB)
    page.goto(PAGE)
    page.wait_for_load_state("load")
    page.wait_for_timeout(2000)
    page.screenshot(path=OUT + r"\t1-home.png")
    check_overflow(page, "home")
    results["steps"].append("home: title=" + page.title())

    # ผลค้นหา (พิมพ์ค้น + กดปุ่มกระจก)
    try:
        page.fill("#search-input", "neon")
        page.click("#btn-execute-search")
        page.wait_for_timeout(1200)
        page.screenshot(path=OUT + r"\t2-search.png")
        check_overflow(page, "search")
        results["steps"].append("search ok")
    except Exception as e:
        results["steps"].append(f"search failed: {str(e)[:150]}")

    # ทุกแท็บหลักผ่าน data-tab
    for tab, name in [("queue", "queue"), ("library", "library"), ("equalizer", "equalizer"), ("lyrics", "lyrics"), ("settings", "settings")]:
        try:
            page.click(f'.nav-item[data-tab="{tab}"]')
            page.wait_for_timeout(1100)
            page.screenshot(path=OUT + rf"\t3-{name}.png")
            check_overflow(page, name)
            results["steps"].append(f"{name} ok")
        except Exception as e:
            results["steps"].append(f"{name} nav failed: {str(e)[:120]}")

    # หาตัว overflow div บน home ว่าคืออะไร
    try:
        page.click('.nav-item[data-tab="search"]')
        page.wait_for_timeout(800)
        culprit = page.evaluate("""() => {
          const doc = document.documentElement;
          const out = [];
          for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            if (r.width > 0 && r.right > doc.clientWidth + 4) {
              out.push({ tag: el.tagName.toLowerCase(), cls: String(el.className).slice(0, 90),
                         right: Math.round(r.right), id: el.id || null });
              if (out.length > 5) break;
            }
          }
          return out;
        }""")
        results["overflow_detail"] = culprit
    except Exception as e:
        results["overflow_detail"] = str(e)

    browser.close()

print(json.dumps(results, ensure_ascii=False, indent=1))
