/**
 * NexusTube — Configuration & Localization Manager
 * Handles persistent configuration, themes, accents, and bilingual dictionaries.
 */

const fs = require('fs');
const path = require('path');
const os = require('os');

const VERSION = "3.4.0";

const DEFAULT_CONFIG = {
  accent: "#22C55E",
  lang: "th",
  format: "mp3_320",
  embed_thumb: true,
  embed_meta: true,
  embed_lyrics: false,
  sponsorblock: "sponsor",
  normalize: false,
  eq_preset: "Flat",
  eq_bands: { bass: 0.0, low_mid: 0.0, mid: 0.0, high_mid: 0.0, treble: 0.0 },
  dsp_effects: { preamp: 0.0, bass_boost: 0.0, surround: false },
  favorites: [],
  library_view: "grid",
  recent_searches: [],
  outdir: path.join(os.homedir(), "Downloads", "NexusTube"),
  discord_rpc: true,
  global_hotkeys: true,
  system_tray: false,
  minimize_to_tray: false,
  cookie_source: null,
  cookie_file: null,
  telemetry: false,
};

const ACCENT_PALETTE = {
  Green:  { color: "#22C55E", hover: "#16A34A" },
  Indigo: { color: "#6366F1", hover: "#4F46E5" },
  Pink:   { color: "#EC4899", hover: "#DB2777" },
  Cyan:   { color: "#06B6D4", hover: "#0891B2" },
  Amber:  { color: "#F59E0B", hover: "#D97706" },
  Purple: { color: "#A855F7", hover: "#9333EA" },
};

const EQ_PRESETS = {
  "Flat": {
    bass: 0, low_mid: 0, mid: 0, high_mid: 0, treble: 0,
    name_en: "Flat (Balanced)", name_th: "ปกติ (เสียงมาตรฐาน)"
  },
  "Bass Boost": {
    bass: 7, low_mid: 4, mid: 0, high_mid: -1, treble: 0,
    name_en: "Bass Boost (+7dB)", name_th: "เบสหนัก (Bass Boost +7dB)"
  },
  "Treble Boost": {
    bass: -1, low_mid: 0, mid: 1, high_mid: 4, treble: 7,
    name_en: "Treble Boost (Crystal)", name_th: "เสียงใส (Treble Boost)"
  },
  "Vocal": {
    bass: -2, low_mid: 1, mid: 5, high_mid: 4, treble: 1,
    name_en: "Vocal & Acoustic", name_th: "เสียงร้องชัด (Vocal Presence)"
  },
  "Club": {
    bass: 6, low_mid: 4, mid: 2, high_mid: 3.5, treble: 5,
    name_en: "Club & Dancehall", name_th: "คลับ (Club Dancehall)"
  },
  "Rock": {
    bass: 5, low_mid: 3, mid: -1, high_mid: 3, treble: 5,
    name_en: "Rock / Metal", name_th: "ร็อก (Rock / Punchy)"
  },
  "Acoustic": {
    bass: 2, low_mid: 2, mid: 3, high_mid: 3, treble: 4,
    name_en: "Acoustic / Live", name_th: "อคูสติก (Acoustic Unplugged)"
  },
  "Electronic": {
    bass: 7, low_mid: 4, mid: 1, high_mid: 3, treble: 6,
    name_en: "Electronic / EDM", name_th: "อิเล็กทรอนิกส์ (EDM Club)"
  },
  "Pop": {
    bass: 3.5, low_mid: 2, mid: 4, high_mid: 3, treble: 4.5,
    name_en: "Pop & Modern Radio", name_th: "ป๊อป (Pop Radio)"
  },
  "Jazz": {
    bass: 3, low_mid: 2, mid: 1, high_mid: 2, treble: 3,
    name_en: "Jazz & Warmth", name_th: "แจ๊ส (Warm & Smooth)"
  },
  "Hip Hop": {
    bass: 8, low_mid: 4.5, mid: 0.5, high_mid: 1.5, treble: 3.5,
    name_en: "Hip Hop & Urban", name_th: "ฮิปฮอป (Hip Hop Beat)"
  },
  "Dance": {
    bass: 7, low_mid: 3.5, mid: 1, high_mid: 4.5, treble: 6,
    name_en: "Dance & Synth", name_th: "แดนซ์ (Dance Synth)"
  },
  "Vocal Booster": {
    bass: -3, low_mid: 1, mid: 7, high_mid: 5, treble: 2,
    name_en: "Vocal Booster (Lead)", name_th: "ขับเสียงร้อง (Vocal Booster)"
  },
  "Deep Bass": {
    bass: 9.5, low_mid: 5, mid: -1, high_mid: 0, treble: -2,
    name_en: "Deep Sub Bass", name_th: "เบสลึกพิเศษ (Deep Sub Bass)"
  },
  "Nightcore": {
    bass: 1.5, low_mid: 1, mid: 3, high_mid: 5.5, treble: 7.5,
    name_en: "Nightcore & Speed", name_th: "ไนท์คอร์ (Nightcore Bright)"
  },
  "Slowed Reverb": {
    bass: 4, low_mid: 2, mid: -1, high_mid: 1, treble: 3,
    name_en: "Slowed & Reverb Vibe", name_th: "สโลว์ + รีเวิร์บ (Slowed Chill)"
  }
};

const LOCALES = {
  "Search": { en: "Search", th: "ค้นหา" },
  "Queue": { en: "Queue", th: "คิวโหลด" },
  "Library": { en: "Library", th: "คลังเพลง" },
  "Settings": { en: "Settings", th: "ตั้งค่า" },
  "Search & Download": { en: "Search & Download", th: "ค้นหาและดาวน์โหลด" },
  "Search_Sub": { en: "A file under 8 KB does not count as finished. The queue is saved if you close the app.", th: "ไฟล์ที่เล็กกว่า 8 KB ไม่นับว่าเสร็จ คิวถูกบันทึกไว้ถ้าปิดแอป" },
  "Paste": { en: "📋 Paste", th: "📋 วางลิงก์" },
  "SearchBtn": { en: "🔍 Search", th: "🔍 ค้นหา" },
  "+ Add URL": { en: "+ Add URL", th: "+ เพิ่ม URL" },
  "Import TXT": { en: "📄 Import TXT", th: "📄 นำเข้า TXT" },
  "Results": { en: "Results", th: "ผลการค้นหา" },
  "No results found.": { en: "No results found.", th: "ไม่พบผลลัพธ์" },
  "Searching...": { en: "Searching YouTube...", th: "กำลังค้นหาจาก YouTube..." },
  "Resolving URL...": { en: "Resolving video details...", th: "กำลังดึงข้อมูลวิดีโอ..." },
  "Download": { en: "Download", th: "ดาวน์โหลด" },
  "Download Queue": { en: "Download Queue", th: "คิวการดาวน์โหลด" },
  "Queue_Sub": { en: "2 downloads at once. A silent 90 seconds switches method.", th: "พร้อมกัน 2 งาน ถ้าเงียบ 90 วินาทีจะเปลี่ยนวิธี" },
  "Clear Finished": { en: "🗑️ Clear Finished", th: "🗑️ ล้างที่เสร็จแล้ว" },
  "Open Downloads Folder": { en: "📂 Open Folder", th: "📂 เปิดโฟลเดอร์" },
  "No active downloads": { en: "No active downloads in queue.", th: "ยังไม่มีรายการในคิวโหลด" },
  "Refresh": { en: "🔄 Refresh", th: "🔄 รีเฟรช" },
  "Search Library...": { en: "🔍 Filter library songs or artists...", th: "🔍 ค้นหาเพลงหรือศิลปินในคลัง..." },
  "No files downloaded yet.": { en: "No files downloaded yet.", th: "ยังไม่มีไฟล์ที่ดาวน์โหลด" },
  "Trim": { en: "✂️ Trim", th: "✂️ ตัดเสียง" },
  "Play": { en: "▶ Play", th: "▶ เล่น" },
  "Play in App": { en: "▶ Play", th: "▶ เล่นในแอป" },
  "Show in Folder": { en: "📂 Folder", th: "📂 ที่เก็บไฟล์" },
  "Delete": { en: "🗑️ Delete", th: "🗑️ ลบ" },
  "DeleteConfirm": { en: "Are you sure you want to permanently delete:\n", th: "คุณแน่ใจหรือไม่ว่าต้องการลบไฟล์นี้ถาวร:\n" },
  "Settings_Title": { en: "Settings & Preferences", th: "ตั้งค่าและปรับแต่ง" },
  "Settings_Sub": { en: "Configure download formats, engine behavior, and UI", th: "ตั้งค่ารูปแบบการดาวน์โหลด ระบบ และหน้าตาแอป" },
  "Default Format": { en: "Default Download Format", th: "รูปแบบการดาวน์โหลดเริ่มต้น" },
  "Download Options": { en: "Download Options", th: "ตัวเลือกการดาวน์โหลดเพิ่มเติม" },
  "Theme Accent Color": { en: "Theme Accent Color", th: "สีธีมหลัก (Accent Color)" },
  "Language": { en: "Language", th: "ภาษา (Language)" },
  "Output Folder": { en: "Output Folder", th: "โฟลเดอร์บันทึกไฟล์" },
  "Browse": { en: "Browse", th: "เลือกโฟลเดอร์" },
  "Engines Status": { en: "Self-Healing Engine Status", th: "สถานะระบบเครื่องมือและตัวช่วยดาวน์โหลด" },
  "Update Engines Now": { en: "🔄 Update Engines Now", th: "🔄 ตรวจสอบและอัปเดตเครื่องมือ" },
  "Audio  —  MP3 320kbps (Extreme)": { en: "Audio  —  MP3 320kbps (Extreme CBR)", th: "เสียง  —  MP3 320kbps (ชัดสูงสุด CBR)" },
  "Audio  —  M4A / AAC (Source Quality)": { en: "Audio  —  M4A / AAC (Source Quality, No Loss)", th: "เสียง  —  M4A / AAC (คุณภาพแท้จากต้นฉบับ ไม่ลดทอน)" },
  "Audio  —  FLAC (Lossless)": { en: "Audio  —  FLAC (Lossless Audio)", th: "เสียง  —  FLAC (Lossless คุณภาพสูงสุด)" },
  "Video  —  MP4 (Best Available / 4K)": { en: "Video  —  MP4 (Best Available / up to 4K)", th: "วิดีโอ  —  MP4 (ชัดที่สุด / สูงสุด 4K)" },
  "Video  —  MP4 (1080p Full HD)": { en: "Video  —  MP4 (1080p Full HD)", th: "วิดีโอ  —  MP4 (1080p Full HD คมชัดสูง)" },
  "Video  —  MP4 (720p HD)": { en: "Video  —  MP4 (720p HD)", th: "วิดีโอ  —  MP4 (720p HD มาตรฐาน)" },
  "Embed thumbnail / album art": { en: "Embed thumbnail & album cover art", th: "ฝังรูปภาพหน้าปกและอัลบั้มอาร์ต" },
  "Embed metadata & artist info": { en: "Embed ID3 tags & artist metadata", th: "ฝังแท็กข้อมูลเพลง ศิลปิน อัลบั้ม" },
  "Embed lyrics / subtitles": { en: "Embed lyrics / subtitles (English/Thai)", th: "ฝังเนื้อเพลงและคำบรรยาย (English/Thai)" },
  "SponsorBlock": { en: "SponsorBlock (Auto-skip sponsors)", th: "SponsorBlock (ตัดท่อนโฆษณา/สปอนเซอร์อัตโนมัติ)" },
  "Volume Normalization": { en: "Audio Volume Normalization", th: "ปรับระดับความดังเสียงให้เท่ากันอัตโนมัติ" },
  "Smart Playlist": { en: "Smart Playlist Selector", th: "เลือกดาวน์โหลดจากเพลย์ลิสต์" },
  "Select All": { en: "✓ Select All", th: "✓ เลือกทั้งหมด" },
  "Deselect All": { en: "✗ Deselect All", th: "✗ ยกเลิกทั้งหมด" },
  "Download Selected": { en: "Download Selected", th: "ดาวน์โหลดที่เลือก" },
  "Cancel": { en: "🛑 Cancel", th: "🛑 ยกเลิก" },
  "Retry": { en: "🔄 Retry", th: "🔄 ลองใหม่" },
  "Waiting…": { en: "Waiting in queue…", th: "กำลังรอคิว…" },
  "Starting…": { en: "Starting engine…", th: "กำลังเริ่มดาวน์โหลด…" },
  "Processing…": { en: "Processing audio / tags…", th: "กำลังประมวลผลไฟล์และแท็ก…" },
  "Complete ✓": { en: "Complete ✓", th: "ดาวน์โหลดเสร็จสมบูรณ์ ✓" },
  "Cancelled": { en: "Cancelled 🛑", th: "ยกเลิกแล้ว 🛑" },
  "Failed ✗": { en: "Failed ✗", th: "ดาวน์โหลดไม่สำเร็จ ✗" },
  "Trimmer_Title": { en: "✂️ Audio Trimmer & Ringtone Maker", th: "✂️ เครื่องมือตัดเสียงและทำเสียงเรียกเข้า" },
  "Start Time": { en: "Start Time (HH:MM:SS or SS)", th: "เวลาเริ่มต้น (HH:MM:SS หรือ วินาที)" },
  "End Time": { en: "End Time (HH:MM:SS or SS)", th: "เวลาสิ้นสุด (HH:MM:SS หรือ วินาที)" },
  "Preview Slice": { en: "🔊 Preview Slice", th: "🔊 ฟังตัวอย่าง" },
  "Stop Preview": { en: "⏹ Stop", th: "⏹ หยุด" },
  "Trim Now": { en: "✂️ Trim & Save", th: "✂️ ตัดและบันทึก" },
  "Repeat": { en: "Repeat", th: "เล่นซ้ำ" },
  "Shuffle": { en: "Shuffle", th: "สุ่มเพลง" },
  "Lyrics": { en: "🎤 Lyrics", th: "🎤 เนื้อเพลง" },
  "Synchronized Lyrics": { en: "🎤 Synchronized Lyrics & Karaoke", th: "🎤 คาราโอเกะและเนื้อเพลงสด" },
  "Equalizer": { en: "🎛️ Equalizer", th: "🎛️ อีควอไลเซอร์" },
  "Audio Equalizer & Presets": { en: "🎛️ Audio Equalizer & DSP Presets", th: "🎛️ ปรับแต่งเสียง & พรีเซ็ต EQ" },
  "EQ Preset": { en: "Preset:", th: "พรีเซ็ตเสียง:" },
  "Reset EQ": { en: "Reset to Flat", th: "รีเซ็ตค่าเดิม" },
  "Bass (60Hz)": { en: "Sub Bass (60 Hz)", th: "เสียงเบสลึก (60 Hz)" },
  "Low-Mid (250Hz)": { en: "Low Mid (250 Hz)", th: "เสียงกลางต่ำ (250 Hz)" },
  "Mid (1kHz)": { en: "Midrange (1 kHz)", th: "เสียงกลาง/ร้อง (1 kHz)" },
  "High-Mid (4kHz)": { en: "High Mid (4 kHz)", th: "เสียงกลางสูง (4 kHz)" },
  "Treble (12kHz)": { en: "Treble (12 kHz)", th: "เสียงแหลม (12 kHz)" },
  "Save .LRC": { en: "💾 Save .LRC", th: "💾 บันทึก .LRC" },
  "LRC Saved": { en: "LRC lyrics saved successfully!", th: "บันทึกไฟล์เนื้อเพลง .LRC เรียบร้อยแล้ว!" },
  "No Lyrics Found": { en: "No synchronized lyrics found for this song.", th: "ไม่พบเนื้อเพลงสำหรับเพลงนี้" },
  "Searching Lyrics...": { en: "Searching lyrics...", th: "กำลังค้นหาเนื้อเพลง..." },
  "Search Lyrics": { en: "🔍 Search", th: "🔍 ค้นหา" },
  "Import to Queue": { en: "📥 Import to Queue", th: "📥 เพิ่มเข้าคิวโหลด" },
  "Universal Playlist": { en: "Universal Multi-Platform Playlist", th: "เพลย์ลิสต์เพลงหลายแพลตฟอร์ม" },
  "Visualizer": { en: "Audio Visualizer", th: "แถบคลื่นเสียง" },
  "Speed": { en: "Speed", th: "ความเร็ว" },
  "ETA": { en: "ETA", th: "เวลาที่เหลือ" },
  "Downloading": { en: "Downloading", th: "กำลังดาวน์โหลด" },
  "Processing Tags…": { en: "Processing Tags…", th: "กำลังประมวลผลแท็ก…" },
  "Folder": { en: "Folder", th: "เปิดโฟลเดอร์" },
  "MENU": { en: "Navigation", th: "เมนูหลัก" },
  "STUDIO_TOOLS": { en: "Studio Tools", th: "เครื่องมือสตูดิโอ" },
  "Open": { en: "Open", th: "เปิด" },
  "Total Downloads": { en: "Total Downloads", th: "งานทั้งหมด" },
  "Active": { en: "Active", th: "กำลังทำงาน" },
  "Completed": { en: "Completed", th: "เสร็จสมบูรณ์" },
  "Search_Hero": { en: "Paste a link. The queue tries up to 7 ways.", th: "วางลิงก์ แล้วคิวลองได้สูงสุด 7 วิธี" },
  "Reveal in Explorer": { en: "Reveal in Explorer", th: "เปิดในโฟลเดอร์" },
  "Edit LRC": { en: "Edit LRC", th: "แก้ไข .LRC" },
  "View Synced": { en: "View Synced", th: "ดูเนื้อเพลงสด" },
  "Auto-Fetch": { en: "Auto-Fetch", th: "ค้นหาอัตโนมัติ" },
  "Sort: Recent": { en: "Sort: Recent", th: "เรียง: ล่าสุด" },
  "Sort: Title": { en: "Sort: Title", th: "เรียง: ชื่อเพลง" },
  "Sort: Artist": { en: "Sort: Artist", th: "เรียง: ศิลปิน" },
  "Sort: Duration": { en: "Sort: Duration", th: "เรียง: ความยาว" },
  "Sort: File Size": { en: "Sort: File Size", th: "เรียง: ขนาดไฟล์" },
  "Delete File?": { en: "Delete File?", th: "ลบไฟล์นี้?" },
  "Delete Permanently": { en: "Delete Permanently", th: "ลบไฟล์ถาวร" },
  "Tracks Selected": { en: "tracks selected", th: "เพลงที่เลือก" },
  "Tracks Found": { en: "tracks found", th: "เพลงที่พบ" },
  "Engines: Ready": { en: "Engines: Ready", th: "เครื่องมือ: พร้อมใช้งาน" },
  "Engines: Missing/Updating": { en: "Engines: Missing/Updating", th: "เครื่องมือ: กำลังอัปเดต..." },
  "Table View": { en: "Table View", th: "มุมมองตาราง" },
  "Grid View": { en: "Grid View", th: "มุมมองการ์ด" },
  "Favorites": { en: "Favorites", th: "เพลงโปรด" },
  "Favorites Only": { en: "❤️ Favorites Only", th: "❤️ เฉพาะเพลงโปรด" },
  "Play All": { en: "▶ Play All", th: "▶ เล่นทั้งหมด" },
  "Shuffle All": { en: "🔀 Shuffle All", th: "🔀 สุ่มทั้งหมด" },
  "Sleep Timer": { en: "🌙 Sleep Timer", th: "🌙 ตั้งเวลาปิดเพลง" },
  "Sleep Timer Off": { en: "Timer Off", th: "ปิดตัวตั้งเวลา" },
  "Keyboard Shortcuts": { en: "Keyboard Shortcuts", th: "คีย์ลัดแป้นพิมพ์" },
  "Convert Audio": { en: "Studio Audio Converter", th: "แปลงไฟล์เสียงสตูดิโอ" },
  "Convert Now": { en: "Convert Now", th: "เริ่มแปลงไฟล์" },
  "Pre-Amp": { en: "Pre-Amp Gain", th: "ระดับขยาย Pre-Amp" },
  "Bass Boost Knob": { en: "Sub-Bass Exciter", th: "เพิ่มพลังเสียงเบสลึก" },
  "3D Surround": { en: "3D Spatial Surround", th: "มิติเสียงโอบล้อม 3D" },
  "Trending Vibes": { en: "Trending Vibes & Discovery", th: "แนวเพลงยอดนิยม & ค้นหาด่วน" },
  "Recent Searches": { en: "Recent Searches", th: "การค้นหาล่าสุด" },
  "Fullscreen Karaoke": { en: "Fullscreen Karaoke", th: "คาราโอเกะเต็มจอ" },
  "Copy Lyrics": { en: "📋 Copy Lyrics", th: "📋 คัดลอกเนื้อเพลง" },
  "Lyrics Copied": { en: "Lyrics copied to clipboard!", th: "คัดลอกเนื้อเพลงแล้ว!" },
  "Export M3U8": { en: "Export Playlist (.M3U8)", th: "ส่งออกเพลย์ลิสต์ (.M3U8)" },
  "Playlist Exported": { en: "Playlist exported successfully!", th: "ส่งออกเพลย์ลิสต์สำเร็จแล้ว!" },
  "Cancel All": { en: "🛑 Cancel All", th: "🛑 ยกเลิกทั้งหมด" },
  "Playback Speed": { en: "Playback Speed", th: "ความเร็วการเล่น" },
  "Target Format": { en: "Target Format", th: "รูปแบบปลายทาง" },
  "Target Bitrate": { en: "Bitrate", th: "บิตเรต" },
  "Normalize Audio": { en: "Normalize Audio (EBU R128)", th: "ปรับระดับเสียงให้เท่ากัน (EBU R128)" }
};

class ConfigManager {
  constructor() {
    const appdataBase = process.env.APPDATA || (process.platform === 'darwin' ? path.join(os.homedir(), 'Library', 'Preferences') : os.homedir());
    this.appdataDir = path.join(appdataBase, 'NexusTube');
    this.legacyDir = path.join(appdataBase, 'YTDownloaderPro');
    
    try {
      if (!fs.existsSync(this.appdataDir)) {
        fs.mkdirSync(this.appdataDir, { recursive: true });
      }
    } catch {
      this.appdataDir = path.join(os.tmpdir(), 'NexusTube');
      try { fs.mkdirSync(this.appdataDir, { recursive: true }); } catch {}
    }

    this.configPath = path.join(this.appdataDir, 'config.json');
    this.config = { ...DEFAULT_CONFIG };
    this.loadConfig();
  }

  loadConfig() {
    // Check main path or legacy path
    let loaded = false;
    for (const p of [this.configPath, path.join(this.legacyDir, 'config.json')]) {
      if (fs.existsSync(p)) {
        try {
          const raw = fs.readFileSync(p, 'utf8');
          const data = JSON.parse(raw);
          this.config = { ...this.config, ...data };
          loaded = true;
          break;
        } catch {}
      }
    }
    // Ensure outdir exists or can be created
    if (this.config.outdir) {
      try { fs.mkdirSync(this.config.outdir, { recursive: true }); } catch {}
    }
  }

  saveConfig(updates = {}) {
    this.config = { ...this.config, ...updates };
    try {
      fs.writeFileSync(this.configPath, JSON.stringify(this.config, null, 2), 'utf8');
      return true;
    } catch (e) {
      console.error("[ConfigManager] Failed to save config:", e);
      return false;
    }
  }

  get(key, defaultValue = null) {
    return this.config[key] !== undefined ? this.config[key] : defaultValue;
  }

  set(key, value) {
    this.config[key] = value;
    return this.saveConfig();
  }
}

module.exports = {
  VERSION,
  DEFAULT_CONFIG,
  ACCENT_PALETTE,
  EQ_PRESETS,
  LOCALES,
  ConfigManager
};
