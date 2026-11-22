"""ทดสอบครบทุก feature ใหม่บนเว็บโหลดจริง: ค้นหาข้ามแพลตฟอร์ม, settings, concurrency, i18n."""
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8787"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(BASE, timeout=30000)
    page.wait_for_load_state("networkidle", timeout=15000)
    page.wait_for_timeout(2500)

    # ── ข้อ 7: i18n ──
    assert page.locator("#lang").count() == 1, "no language selector"
    assert "คิวโหลด" in page.locator("h1").text_content(), "TH title missing"
    page.select_option("#lang", "en")
    page.wait_for_timeout(400)
    assert "Download Queue" in page.locator("h1").text_content(), "EN title missing"
    assert "Set folder" in page.locator("#save-folder").text_content(), "EN folder btn missing"
    assert "Settings" in page.locator(".settings-title").text_content(), "EN settings missing"
    print("PASS i18n: TH -> EN toggle")
    page.select_option("#lang", "th")
    page.wait_for_timeout(400)

    # ── ข้อ 4+5: settings checkboxes + concurrency ──
    assert page.locator("#set-sponsor").count() == 1, "no sponsor checkbox"
    page.evaluate("document.getElementById('set-sponsor').checked = false")  # กัน state ค้างจากรอบก่อน — check บนของที่ checked อยู่ = no-op
    page.check("#set-sponsor")
    for _ in range(15):
        page.wait_for_timeout(200)
        if page.locator("#settings-note").text_content().strip():
            break
    assert "บันทึกแล้ว" in page.locator("#settings-note").text_content(), f"settings not saved: {page.locator('#settings-note').text_content()!r}"
    page.select_option("#set-conc", "5")
    for _ in range(15):
        page.wait_for_timeout(200)
        if page.locator("#settings-note").text_content().strip():
            break
    # ยืนยันผ่าน API ตรง ๆ ว่า config ถูกเขียนจริง
    import urllib.request, json
    page.evaluate("""() => fetch('/api', {method:'POST', headers:{'Content-Type':'application/json','X-Nexus-Token': token}, body: JSON.stringify({op:'state'})}).then(r=>r.json()).then(s => window.__state = s)""")
    state = page.evaluate("window.__state")
    assert state["settings"]["sponsorblock"] is True, "sponsorblock not persisted"
    assert state["settings"]["max_concurrent"] == 5, f"concurrency not persisted: {state['settings']}"
    print("PASS settings: checkbox + concurrency persisted via API")
    # คืนค่าเดิม
    page.evaluate("document.getElementById('set-sponsor').checked = false")
    page.evaluate("document.getElementById('set-sponsor').dispatchEvent(new Event('change', {bubbles:true}))")
    page.select_option("#set-conc", "3")
    page.wait_for_timeout(1000)

    # ── ข้อ 2: ค้นหาข้ามแพลตฟอร์ม + badge ──
    page.fill("#query", "bodyslam")
    page.click("#go")
    page.wait_for_timeout(12000)
    badges = page.locator(".src-badge")
    n_badges = badges.count()
    texts = [badges.nth(i).text_content() for i in range(min(n_badges, 15))]
    has_yt = any("YouTube" in t for t in texts)
    has_apple = any("Apple" in t for t in texts)
    print(f"results badges: {n_badges} | YouTube: {has_yt} | Apple: {has_apple}")
    assert has_yt and has_apple, f"cross-platform badges missing (yt={has_yt}, apple={has_apple})"
    print("PASS cross-platform search with badges")

    page.screenshot(path="C:/Users/Administrator/Desktop/final-features.png", full_page=False)
    browser.close()
print("ALL FEATURE TESTS OK")
