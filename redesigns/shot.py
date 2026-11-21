import sys
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

JOBS = [
    ("A-studio.html",  "A-studio.png"),
    ("B-aurora.html",  "B-aurora.png"),
    ("C-console.html", "C-console.png"),
]
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 1280, "height": 800})
    for f, out in JOBS:
        pg.goto(f"file:///E:/projects_backup/NexusTube - js/redesigns/{f}")
        pg.wait_for_timeout(1200)
        pg.screenshot(path=f"E:/projects_backup/NexusTube - js/redesigns/{out}")
        print("shot", out)
    b.close()
