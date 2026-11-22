"""Interaction sweep: กดทุกปุ่มในทุก tab ของแอปจริง จับ error รายปุ่ม — กันบั๊กแบบเดียวกับ engine cards ซ่อนอีก."""
import subprocess, sys, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright

import sys
APP = sys.argv[1] if len(sys.argv) > 1 else "dist_electron/win-unpacked/NexusTube.exe"
TABS = ["search", "queue", "library", "equalizer", "lyrics", "settings"]
# ปุ่มที่ข้าม — เปิด native dialog / ปิดแอป / รีสตาร์ท (ผลข้างเคียงนอกเหนือจากการตรวจ JS)
SKIP_IDS = {"btn-win-min", "btn-win-max", "btn-win-close", "btn-browse-folder", "btn-update-engines"}

proc = subprocess.Popen([APP, "--remote-debugging-port=9333"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(12)

results = []
try:
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9333", timeout=30000)
        page = next(pg for pg in browser.contexts[0].pages if "index.html" in pg.url and "download.html" not in pg.url)
        page.wait_for_load_state("networkidle", timeout=30000)
        page.wait_for_timeout(5000)

        # ติดตั้ง error collector
        page.evaluate("""() => {
          window.__errors = [];
          window.addEventListener('pageerror', e => window.__errors.push('pageerror: ' + String(e).slice(0,150)));
          const origErr = console.error;
          console.error = (...a) => { window.__errors.push('console.error: ' + a.map(x => String(x).slice(0,100)).join(' ').slice(0,150)); origErr(...a); };
        }""")

        for tab in TABS:
            page.click(f'button.nav-item[data-tab="{tab}"]')
            page.wait_for_timeout(600)
            btns = page.evaluate("""() => Array.from(document.querySelectorAll('button[id]'))
              .filter(b => b.offsetParent !== null)
              .map(b => ({ id: b.id, text: (b.textContent || '').trim().slice(0, 30) }))
              .filter(b => b.id && !b.id.startsWith('btn-win'))""")
            for b in btns:
                if b["id"] in SKIP_IDS:
                    continue
                page.evaluate("() => { window.__errors = []; }")
                try:
                    page.click(f"#{b['id']}", timeout=3000)
                except Exception as e:
                    results.append((tab, b["id"], b["text"], f"CLICK FAIL: {str(e)[:80]}"))
                    continue
                page.wait_for_timeout(900)
                errs = page.evaluate("() => window.__errors.splice(0)")
                # ปิด modal/overlay ที่อาจเปิดขึ้น ด้วยการกด Escape
                page.keyboard.press("Escape")
                # ปิด modal/overlay ใด ๆ ที่ปุ่มเพิ่งเปิด กันมันบังปุ่มถัดไป
                page.evaluate("() => document.querySelectorAll('.fixed.inset-0').forEach(m => { m.style.display = 'none'; })")
                page.wait_for_timeout(150)
                for err in errs:
                    results.append((tab, b["id"], b["text"], err))
        browser.close()
finally:
    proc.terminate()

print(f"buttons swept, issues found: {len(results)}")
for tab, bid, text, err in results:
    print(f"  [{tab}] #{bid} '{text}' -> {err}")
if not results:
    print("NO INTERACTION ERRORS FOUND")
