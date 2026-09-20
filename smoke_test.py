# -*- coding: utf-8 -*-
"""
NexusTube — Automated & Manual Smoke Test Script (smoke_test.py)
===============================================================
Performs comprehensive sanity checks across all core systems:
1. Environment & Pre-flight verification (yt-dlp, ffmpeg, WebView2, writable dir)
2. External tool execution & logging via run_external_tool
3. Headless URL resolution (extract title, uploader, thumbnail)
4. Headless micro-download slice test (audio extraction & transcode)
5. Real process lifecycle, Pygame SDL mixer release, DLL lock audit & orphan process verification
6. Interactive checklist guide for manual GUI sign-off
"""

import sys
import os
import time
import json
import tempfile
import subprocess
import shutil
import wave
import struct

# Ensure workspace root is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

TEST_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Permanent public video (Rick Astley)

def print_header(title):
    print("\n" + "=" * 65)
    print(f" [SMOKE TEST] {title}")
    print("=" * 65)

def print_pass(msg):
    print(f"  [PASS] {msg}")

def print_fail(msg):
    print(f"  [FAIL] {msg}")

def get_running_multimedia_processes():
    """Queries Windows tasklist to check for running multimedia binaries."""
    if sys.platform != "win32":
        return []
    try:
        res = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True)
        found = []
        targets = {"ffmpeg.exe", "yt-dlp.exe", "ffprobe.exe", "ffplay.exe"}
        for line in res.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = [p.strip('"') for p in line.split('","')]
            if parts and parts[0].lower() in targets:
                found.append((parts[0], parts[1]))
        return found
    except Exception:
        return []

def run_all_tests():
    total_tests = 5
    passed_tests = 0

    print_header("NexusTube Reliability & Sanity Smoke Test")
    print(f"Python: {sys.version.split()[0]} on {sys.platform}")
    print(f"Workspace: {SCRIPT_DIR}")

    # Record multimedia processes before tests
    initial_processes = get_running_multimedia_processes()

    # ── Test 1: Pre-flight Startup Checks ────────────────────────────────────
    print_header("Test 1/5: Startup Dependency & Doctor Pre-flight")
    try:
        import YT_Downloader_V2 as yt
        preflight = yt.preflight_startup_checks()
        print(f"  Diagnostics: {preflight}")

        if preflight.get("ytdlp") and preflight.get("ffmpeg") and preflight.get("output_writable"):
            print_pass("yt-dlp, FFmpeg, and output directory are functional.")
            passed_tests += 1
        else:
            print_fail(f"Pre-flight reported missing components: {preflight.get('errors') or preflight.get('warnings')}")
    except Exception as e:
        print_fail(f"Pre-flight exception: {e}")

    # ── Test 2: run_external_tool Logging and Execution ──────────────────────
    print_header("Test 2/5: run_external_tool Centralized Runner")
    try:
        import YT_Downloader_V2 as yt
        from nexus_doctor import find_binary

        ytdlp_bin = find_binary("yt-dlp") or shutil.which("yt-dlp")
        ffmpeg_bin = find_binary("ffmpeg") or shutil.which("ffmpeg")

        res_yt = yt.run_external_tool([ytdlp_bin, "--version"], label="Smoke Test yt-dlp", check=True)
        res_ff = yt.run_external_tool([ffmpeg_bin, "-version"], label="Smoke Test ffmpeg", check=True)

        yt_ver = res_yt.stdout.strip().splitlines()[0]
        ff_ver = res_ff.stdout.strip().splitlines()[0]

        print_pass(f"yt-dlp verified via run_external_tool: {yt_ver}")
        print_pass(f"ffmpeg verified via run_external_tool: {ff_ver[:50]}...")
        passed_tests += 1
    except Exception as e:
        print_fail(f"run_external_tool failed: {e}")

    # ── Test 3: Headless URL Resolution ──────────────────────────────────────
    print_header("Test 3/5: Headless YouTube URL Resolution")
    try:
        import YT_Downloader_V2 as yt
        from nexus_doctor import find_binary

        ytdlp_bin = find_binary("yt-dlp") or shutil.which("yt-dlp")
        cmd = [ytdlp_bin, "--dump-json", "--no-playlist", "--no-warnings", TEST_URL]
        res = yt.run_external_tool(cmd, label="Smoke Test Resolve", timeout=30, check=True)

        data = json.loads(res.stdout.strip().splitlines()[0])
        title = data.get("title", "Unknown")
        uploader = data.get("uploader", "Unknown")
        duration = data.get("duration", 0)

        print_pass(f"Resolved Title: {title}")
        print_pass(f"Uploader: {uploader} | Duration: {duration}s")
        passed_tests += 1
    except Exception as e:
        print_fail(f"URL Resolution failed: {e}")

    # ── Test 4: Headless Micro-Download Slice Test ────────────────────────────
    print_header("Test 4/5: Headless Micro-Download & Audio Processing Slice")
    test_out = None
    try:
        import YT_Downloader_V2 as yt
        from nexus_doctor import find_binary

        ytdlp_bin = find_binary("yt-dlp") or shutil.which("yt-dlp")
        ffmpeg_bin = find_binary("ffmpeg") or shutil.which("ffmpeg")

        temp_dir = tempfile.gettempdir()
        test_out = os.path.join(temp_dir, f"nexus_smoke_test_{int(time.time())}.mp3")

        cmd = [
            ytdlp_bin, "--no-warnings",
            "--download-sections", "*0-3",
            "-x", "--audio-format", "mp3",
            "-o", test_out,
            TEST_URL
        ]
        if ffmpeg_bin and os.path.exists(ffmpeg_bin):
            cmd += ["--ffmpeg-location", os.path.dirname(ffmpeg_bin)]

        print(f"  Downloading 3-second audio slice to: {test_out}")
        res = yt.run_external_tool(cmd, label="Smoke Test Download Slice", timeout=60, check=True)

        if os.path.exists(test_out) and os.path.getsize(test_out) > 1000:
            print_pass(f"Downloaded and converted audio slice ({os.path.getsize(test_out)} bytes).")
            passed_tests += 1
        else:
            print_fail("Audio slice was not produced or is too small.")
    except Exception as e:
        print_fail(f"Audio download slice failed: {e}")
    finally:
        if test_out and os.path.exists(test_out):
            try:
                os.remove(test_out)
            except Exception:
                pass

    # ── Test 5: Real Lifecycle, PyGame Lock Release & Orphan Process Audit ────
    print_header("Test 5/5: Real Process Lifecycle, Pygame Lock Release & Orphan Audit")
    test_5_ok = True

    # 5.1: Pygame Audio Lock & Temp Directory Cleanup Verification
    print("  [Step 5.1] Testing PyGame Mixer Release & Temporary Directory Lock...")
    lock_temp_dir = None
    try:
        import YT_Downloader_V2 as yt
        lock_temp_dir = tempfile.mkdtemp(prefix="nexus_lock_audit_")
        dummy_wav = os.path.join(lock_temp_dir, "test_audio.wav")

        # Generate a valid 1-second silent WAV file in the temporary directory
        with wave.open(dummy_wav, "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(44100)
            wf.writeframes(b"\x00\x00" * 44100)

        player = yt.AudioPlayer()
        player.load_and_play(dummy_wav)

        if yt.PYGAME_AVAILABLE:
            if yt.pygame.mixer.get_init():
                print("    - Pygame mixer active and playing audio from temp directory.")
            else:
                print("    - Note: Pygame mixer not active on this device.")

        # Trigger cleanup
        player.cleanup()

        # Check mixer state
        if yt.PYGAME_AVAILABLE:
            mixer_status = yt.pygame.mixer.get_init()
            if mixer_status is not None:
                print_fail("Pygame mixer was NOT released by player.cleanup() (still active)!")
                test_5_ok = False
            else:
                print_pass("Pygame mixer subsystem released cleanly (pygame.mixer.quit() executed).")

        # Crucial Verification: Delete the temporary directory where audio was played.
        # If any native DLL or SDL handle is still holding the file, Windows will throw
        # PermissionError [WinError 32] (which causes 'Failed to remove temporary directory' on exit).
        try:
            shutil.rmtree(lock_temp_dir)
            print_pass("Temporary directory removed cleanly without WinError 32 file lock!")
            lock_temp_dir = None
        except PermissionError as pe:
            print_fail(f"FILE LOCK DETECTED! Unable to remove temporary directory: {pe}")
            test_5_ok = False
    except Exception as e:
        print_fail(f"Audio lock audit exception: {e}")
        test_5_ok = False
    finally:
        if lock_temp_dir and os.path.exists(lock_temp_dir):
            try:
                shutil.rmtree(lock_temp_dir, ignore_errors=True)
            except Exception:
                pass

    # 5.2: Process Launch & Clean Exit Verification
    print("  [Step 5.2] Testing Process Launch & Exit Code...")
    try:
        test_code = (
            "import YT_Downloader_V2 as yt\n"
            "import sys\n"
            "sys.stdout.write('Runtime stream ok\\n')\n"
            "sys.exit(0)\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", test_code],
            capture_output=True,
            text=True,
            timeout=15
        )
        if proc.returncode == 0:
            print_pass("Process initialized bulletproof runtime and exited with code 0.")
        else:
            print_fail(f"Process exited with non-zero code {proc.returncode}: {proc.stderr}")
            test_5_ok = False
    except Exception as e:
        print_fail(f"Process launch test failed: {e}")
        test_5_ok = False

    # 5.3: Orphan Process Audit
    print("  [Step 5.3] Auditing for Dangling Orphan Processes...")
    final_processes = get_running_multimedia_processes()
    new_orphans = [p for p in final_processes if p not in initial_processes]
    if new_orphans:
        print_fail(f"Orphan process(es) detected: {new_orphans}")
        test_5_ok = False
    else:
        print_pass("No dangling orphan processes (ffmpeg, yt-dlp) remain in the system.")

    if test_5_ok:
        passed_tests += 1

    # ── Summary ──────────────────────────────────────────────────────────────
    print_header("Smoke Test Results Summary")
    print(f"  Passed: {passed_tests}/{total_tests} tests ({(passed_tests/total_tests)*100:.0f}%)")

    if passed_tests == total_tests:
        print("\n [OK] ALL AUTOMATED SANITY CHECKS PASSED SUCCESSFULLY!\n")
    else:
        print(f"\n [WARN] {total_tests - passed_tests} test(s) failed or requires attention.\n")

    # ── Manual GUI Checklist ─────────────────────────────────────────────────
    print_header("Manual GUI Verification Checklist (Perform on built executable)")
    print("""
  Please perform the following quick manual steps on the GUI app:
  [ ] 1. Launch dist\\NexusTube\\NexusTube.exe (or installed app).
         -> Verify modern Studio Dark glass UI opens with no error dialogs.
  [ ] 2. Paste a YouTube URL into the search bar:
         -> Verify title and cover thumbnail appear immediately.
  [ ] 3. Click 'Download' (MP3 320kbps):
         -> Verify progress bar animates and status shows 'Downloading' then 'Processing'.
         -> Verify completed card displays with file size and 'Open File' button.
  [ ] 4. Close the application window:
         -> Verify app closes smoothly and no process remains in Task Manager.
    """)

    return passed_tests == total_tests

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
