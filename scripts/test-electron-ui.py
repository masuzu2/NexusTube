"""Electron UI test (CDP): เปิดแอปแพ็กจริง ตรวจ tab หลักทั้ง 6 + bridge."""
import subprocess, time
from playwright.sync_api import sync_playwright

import sys
APP = sys.argv[1] if len(sys.argv) > 1 else "dist_electron/win-unpacked/NexusTube.exe"
TABS = ["search", "queue", "library", "equalizer", "lyrics", "settings"]

proc = subprocess.Popen([APP, "--remote-debugging-port=9333"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(12)

try:
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9333", timeout=30000)
        # หา page ของหน้าต่างหลัก (web/index.html)
        ctx = browser.contexts[0]
        page = None
        for pg in ctx.pages:
            if "index.html" in pg.url and "download.html" not in pg.url:
                page = pg
                break
        assert page, f"main UI page not found: {[pg.url for pg in ctx.pages]}"
        page.wait_for_load_state("networkidle", timeout=30000)
        page.wait_for_timeout(5000)
        print("UI url:", page.url[:80])

        # 1) bridge
        api_ready = page.evaluate("!!window.pywebview && !!window.pywebview.api")
        print("bridge ready:", api_ready)
        assert api_ready, "pywebview bridge missing"

        # 2) ทุก tab
        for tab in TABS:
            page.click(f'button.nav-item[data-tab="{tab}"]')
            page.wait_for_timeout(700)
            active = page.evaluate("""() => {
              const active = document.querySelector('.nav-item.active');
              return active ? active.dataset.tab : '';
            }""")
            print(f"  tab {tab}: active={active}")
            assert active == tab, f"tab {tab} did not activate (got {active})"

        # 3) ค้นหาในแอป → ผลข้ามแพลตฟอร์ม
        page.click('button.nav-item[data-tab="search"]')
        page.wait_for_timeout(500)
        inp = page.locator("#query").first
        if inp.count() > 0:
            inp.fill("bodyslam")
            go = page.locator("#search-btn, button[type='submit']").first
            if go.count() > 0:
                go.click()
                page.wait_for_timeout(15000)
                badges = page.locator(".src-badge").count()
                print("in-app search badges:", badges)

        page.screenshot(path="C:/Users/Administrator/Desktop/electron-ui.png")
        print("ELECTRON UI TEST OK")
finally:
    proc.terminate()
