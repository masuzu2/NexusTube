# NexusTube — Developer Notes & Maintenance Guide

> Project: NexusTube (Next-Gen YouTube & Multi-Platform Music Suite)
> Architecture: Python 3.11 + pywebview Edge WebView2 + OLED Glassmorphism Design System
> Author: by herlove | Version: 3.3.0

---

## 1. Development Principles & Philosophy

1. **Zero External CDN Dependencies**: All assets (HTML, CSS, JS, Fonts) must be locally self-contained in `web/` to guarantee 100% offline functionality.
2. **Harmonic Design System Integrity**: Follow `DESIGN.md` rules strictly. Use CSS variables for all styling (`var(--accent)`, `var(--bg-card)`, `var(--border-subtle)`). Never hardcode random hex values in component CSS.
3. **Robust Asynchronous Concurrency**: All heavy network requests and subprocess tasks run on `ThreadPoolExecutor` workers. Never block the pywebview main thread.
4. **Hermetic Automated Testing**: Maintain 100% test passing rate across `tests/test_nexus_tube.py` and `tests/test_nexus_bridge.py`.
5. **Mirroring Consistency**: Always maintain identical codebases between `C:\Users\Administrator\NexusTube` (development root) and `C:\Users\Administrator\Downloads\NexusTube` (user distribution mirror).

---

## 2. Key Modules & Responsibility Map

| File | Lines | Primary Responsibility |
| :--- | :--- | :--- |
| `YT_Downloader_V2.py` | ~4,500 | App lifecycle, Tkinter fallback, `NexusBridgeAPI`, download workers, pywebview bootstrap |
| `nexus_audio.py` | ~1,200 | LRC engine, 16-band EQ & DSP suite, platform resolvers, audio transcoder, M3U8 exporter |
| `web/index.html` | ~1,180 | Single-page layout, navigation sidebar, queue dashboard, converter/shortcuts modals, docked player bar |
| `web/styles.css` | ~1,200 | OLED dark theme variables, glassmorphism, responsive utilities, animation keyframes |
| `web/app.js` | ~3,100 | Client state machine, bridge API bindings, 60fps spectrum visualizer, fullscreen karaoke |
| `web/tailwind.js` | ~400k | Offline standalone Tailwind CSS JIT compiler runtime |
| `NexusTube.spec` | ~65 | PyInstaller single-file build specification |

---

## 3. Testing Protocols

Run tests before committing or building executables:

```powershell
# Run full test suite with verbose output
pytest -v tests/

# Run specific test module
pytest -v tests/test_nexus_bridge.py

# Lint check with ruff
ruff check YT_Downloader_V2.py tests/
```

### Coverage Scope (83 Tests):
- `TestNexusBridgeAPI`: Tests volume unmute, cache cleanup, config persistence, file deletion, engine status, EQ bridge, clipboard, initial state, library scanning, sorting, looplist auto-progression, path normalization, playback shuffle/prev, queue lifecycle, URL detection, file reveal, LRC saving, lyrics search, Spotify auto-resolution, trimmer preview, WebUI asset integrity, window controls, queue thumbnail propagation, DSP effects, favorites toggling, batch cancel, audio conversion, M3U8 playlist export, and WebUI v3.3.0 markup completeness.
- `TestNexusTubeLocales`: Tests accent palette and dictionary completeness.
- `TestAudioPlayer`: Tests M4A transcoding, playback controls, repeat, and shuffle.
- `TestAudioEqualizer`: Tests 16 studio presets, 5-band filter generation with preamp, bass boost, and surround.
- `TestMultiPlatformUrlDetection`: Tests Spotify, Apple Music, and SoundCloud URL matching.

---

## 4. PyInstaller Build Recipe

To generate `NexusTube.exe`:

```powershell
# In project root:
pyinstaller --noconfirm NexusTube.spec
```

The resulting executable will be placed in `dist/NexusTube.exe`.

### Packaging Verification Checklist:
- [x] Embedded `icon.ico` and `NexusTube by herlove.ico`.
- [x] Bundled `web/` directory containing `index.html`, `styles.css`, `app.js`, `tailwind.js`.
- [x] Included hidden imports for `webview`, `webview.platforms.edgechromium`, `clr`, `pythonnet`, `bottle`.
- [x] Console window suppressed (`console=False`).
