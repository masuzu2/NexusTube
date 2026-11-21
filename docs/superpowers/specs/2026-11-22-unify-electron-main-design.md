# NexusTube — Unify to Single Main, Clean Up, Best NSIS Installer, Working Download Site

Date: 2026-11-22
Status: Draft for approval
Repo: `masuzu2/NexusTube` — work happens in `E:\projects_backup\NexusTube - js` (branch `electron-js`)

## Intent

The project has two diverged lines: `main` (the "Mixed Redesign" Electron line with a
local web download site, public gh-pages page wired to a **dead** Cloudflare tunnel)
and `electron-js` (this machine's Electron app: player UI, lyrics, Discord RPC, tray,
updater — already built into installers and published as release v3.9.0). The user
wants ONE clean `main`, the junk gone, the best possible NSIS installer on the
release, and a download website that actually works.

## User decisions (already made)

1. **Web approach: Local-first.** The local site (`127.0.0.1:8787`, ships with the
   app) is the real download UI. The public GitHub Pages page becomes a portal:
   intro, download-the-app button, and instructions — no tunnel dependency.
2. **Branches: unify into one `main`.** Our `electron-js` line is the base; valuable
   pieces of old `main` (the web download server + its client) are ported onto it.
   Old `main` gets a safety tag (`mixed-redesign-final`) before replacement so
   nothing is lost.
3. **Cleanup: delete all junk** (Python-era files, mp3s, logs, old binaries,
   mockups, test shots) locally and from the repo.

## Goals

- One `main` containing: Electron app (`index.js`, `src/main`, `src/preload`, `web/`
  player UI) **plus** the ported local download site (`web-download.js`,
  `download-plan.js`, `web/download.html`, `web/download.js`, `START_WEB.bat`).
- A polished NSIS installer: assisted mode, language picker (Thai/English),
  license page, install-directory choice, desktop + start-menu shortcuts,
  run-after-finish; published to the v3.9.0 release (assets replaced, version
  numbers consistent).
- Repo contains only files the app and docs actually need.

## Non-goals / anti-goals

- No hosted/public download backend (cost + YouTube ban risk) — decided.
- No Python app revival; all Python-era tooling goes.
- No redesign mockup implementation (`redesigns/` is deleted, not built).

## Approach (and why)

Two ways were considered for unification:

- **A. electron-js as base, port the web-download stack in (CHOSEN).** Our line is
  the app the user builds and releases; the web server is a small, self-contained
  subsystem (351-line server, 209-line client, one pure-logic helper). Port risk is
  low: both lines have same-named modules with near-identical constructor shapes
  (`ConfigManager` with `.appdataDir`, `EngineManager(engine/config)`,
  `DownloadManager(engine, config)`, `searchYoutube(query, engineManager)`).
- B. main as base, port the player/lyrics/discord stack in. Rejected: much more
  surface to move, and the user's released artifacts come from the electron-js line.

## Design

### Part 1 — Cleanup

Delete (local + git): `YT_Downloader_V2.py`, `nexus_audio.py`, `nexus_discord.py`,
`nexus_doctor.py`, `nexus_hotkeys_tray.py`, `setup.py`, `smoke_test.py`,
`ui-test.py`, `requirements.txt`, `NexusTube.spec`, `build_installer.py`,
`BUILD_INSTALLER.bat`, `SETUP.bat`, `__pycache__/`, `.pytest_cache/`,
`.ruff_cache/`, `build/`, `dist/`, `install_*.log`, `*.mp3`, `NexusTube.exe`,
`*.msi`, `redesigns/`, `ui-shots/`, `update-package/`,
`NexusTube by herlove.ico` (duplicate of `icon.ico`).

Keep: `index.js`, `src/`, `web/`, `tests/`, `package.json`, `package-lock.json`,
`icon.ico`, `icon.png`, `README.md`, `CHANGELOG.md`, `LICENSE`, `.gitignore`,
`START_ELECTRON.bat`, `docs/`.

### Part 2 — Port the download site (Local-first)

Port from `origin/main` (tagged `mixed-redesign-final` first):
`src/main/web-download.js`, `src/main/download-plan.js`, `web/download.html`,
`web/download.js`, `START_WEB.bat`.

Adaptation points (verified against our modules):
- `engine.ensureFreshYtdlp()` — guard with `typeof` check or add a no-op wrapper
  calling our `ensureEngines` path (builder's call, keep behavior safe).
- `downloads.restoreQueue()` — already guarded on `main`; keep the guard.
- Queue state shape: map `web/download.js` client expectations onto our
  `getQueueState()` if field names differ (builder verifies at test time).
- `searchYoutube(query, engineManager)` — signatures match; wire directly.

Web behavior (Local-first):
- `web/download.js`: when served from the local server, same-origin API calls
  (existing behavior minus tunnel branch). Remove the hard-coded
  `trycloudflare.com` fallback entirely.
- gh-pages `index.html`: rewritten as a portal — hero, "ดาวน์โหลด NexusTube"
  button linking to the v3.9.0 release assets, short how-to, and a status line
  that checks `http://127.0.0.1:8787/health` and offers to open the local site
  when it's running. No API calls to remote tunnels.

### Part 3 — Best NSIS installer

`package.json → build.nsis`:
- `oneClick: false`, `allowToChangeInstallationDirectory: true`
- `perMachine: false`, `allowElevation: true` (no forced admin; user can elevate)
- `multiLanguageInstaller` with Thai + English UI strings
- `license` page from `LICENSE`
- `createDesktopShortcut: "always"`, `createStartMenuShortcut: true`,
  `shortcutName: "NexusTube"`, `runAfterFinish: true`
- `deleteAppDataOnUninstall: false` (keep user music/settings; stated as our call)
- `artifactName: "NexusTube-Setup-${version}.${ext}"`; portable target keeps
  `NexusTube-${version}-Portable.${ext}`
- `asar: false` stays (our downloader/engines write beside the app today; flipping
  it is a risk we don't take in this change — noted as our call)

Version: bump `package.json` to `3.9.0` so installer filenames, `latest.yml`, and
the release all agree.

### Part 4 — Publish

1. Build: `npm run dist`.
2. Test: `node --test tests/`, electron smoke launch, Playwright pass on
   `127.0.0.1:8787` (search → queue → engine status), silent install check
   (`Setup.exe /S`) where practical.
3. Replace v3.9.0 release assets with the new installers; update release notes.
4. Push unified `main`; rewrite gh-pages with the portal page.

## What's left to the builder

- Exact diffs for the adaptation points above (guard vs implement
  `ensureFreshYtdlp`; queue-state field mapping).
- Tag name finalization (`mixed-redesign-final`).
- gh-pages portal page copy/design (dark, Thai-first, matches app branding).

## Verification checklist

- [ ] `npm run dist` produces Setup + Portable without warnings blocking
- [ ] Installer: assisted flow, Thai language, license, dir choice, shortcuts
- [ ] `node --test tests/*.test.js` green
- [ ] Local site: search returns results, queue accepts a job, `/health` OK
- [ ] gh-pages portal loads, no tunnel URLs anywhere in the repo
- [ ] Release v3.9.0 assets are the new build; `latest.yml` version = 3.9.0
