"""v1.1 step 6: re-capture polished screens (AI Tutor enabled for Sunrise only, wizard in progress, full create form...)."""
import asyncio
import requests
from pymongo import MongoClient
from playwright.async_api import async_playwright
from common import BASE, PA, ADMIN, PW, shot, login
from s3_capture import go, click

db = MongoClient("mongodb://localhost:27017")["test_database"]
SUN = db.institutions.find_one({"name": "Sunrise Public School (Demo)"})["id"]
SETUP = ("admin@sunrise-setup.in", "SetupDemo@2026")


async def platform(b):
    page = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()
    await login(page, *PA)

    async def feat(pg):
        await pg.get_by_role("button", name="Features / AI").click()
        await pg.wait_for_timeout(1500)
    await go(page, f"/platform/institutions/{SUN}", "pm_10_ai_before", [("[data-testid=inst-ai-layer-toggle]", "AI Layer switch (this school only)")], before=feat)
    on = await page.locator("[data-testid=inst-ai-layer-toggle]").get_attribute("aria-checked")
    if on != "true":
        await page.click("[data-testid=inst-ai-layer-toggle]")
    await shot(page, "pm_11_ai_enabled", [("[data-testid=inst-ai-layer-toggle]", "Enabled for Sunrise")], wait=1500)
    await go(page, "/platform/plans", "pm_06_plans")
    await go(page, "/platform/issues", "pm_07_issues", wait=2500)
    if not db.institutions.find_one({"name": "Sunrise Demo Setup"}):
        tall = await (await b.new_context(viewport={"width": 1440, "height": 1300})).new_page()
        await login(tall, *PA)
        await tall.goto(f"{BASE}/platform/institutions")
        await tall.click("[data-testid=add-record-btn]")
        await tall.wait_for_selector("[data-testid=form-dialog]")
        for k, v in {"name": "Sunrise Demo Setup", "code": "SDS", "domain": "sunrise-setup.in", "city": "Thrissur", "contact_email": "office@sunrise-setup.in",
                     "phone": "+91 98000 00200", "admin_name": "Joseph Antony", "admin_email": SETUP[0], "admin_password": SETUP[1]}.items():
            loc = tall.locator(f"[data-testid=field-{k}]")
            if await loc.count():
                await loc.fill(v)
        await tall.locator("[data-testid=form-submit-btn]").scroll_into_view_if_needed()
        await shot(tall, "pm_04_create_form", [("[data-testid=form-submit-btn]", "Create")])
        await tall.click("[data-testid=form-submit-btn]")
        await tall.wait_for_timeout(2500)


async def wizard(b):
    db.institutions.update_one({"name": "Sunrise Demo Setup"}, {"$set": {"slug": "sunrise-setup"}})
    page = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()
    await login(page, *SETUP, slug="sunrise-setup")
    await go(page, "/app/setup", "ad_02_setup_wizard", wait=2500)
    s = requests.Session()
    r = s.post("http://localhost:8001/api/auth/login", json={"email": SETUP[0], "password": SETUP[1]})
    s.headers["Authorization"] = f"Bearer {r.cookies.get('access_token')}"
    iid = db.institutions.find_one({"name": "Sunrise Demo Setup"})["id"]
    db.institutions.update_one({"id": iid}, {"$set": {"address": "Round North, Thrissur 680001"}})
    s.post("http://localhost:8001/api/res/academic_years", json={"name": "2026-27", "status": "active", "start_date": "2026-06-01", "end_date": "2027-03-31"})
    s.post("http://localhost:8001/api/res/academic_units", json={"name": "High School", "code": "HS", "status": "active"})
    await go(page, "/app/setup", "ad_02b_setup_progress", wait=2500)


async def admin(b):
    page = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()
    await login(page, *ADMIN, slug="sunrise")
    for path, n in [("/app/support", "op_05_support"), ("/app/communication", "cm_01_comm"), ("/app/homework-monitor", "op_02_homework"),
                    ("/app/assessments", "ex_01_assessments"), ("/app/ai-tutor", "ai_01_admin"), ("/app/dashboard", "ad_03_dashboard")]:
        await go(page, path, n, wait=3000)

    async def att(pg):
        try:
            await pg.get_by_role("tab", name="History").click()
        except Exception:
            await pg.get_by_text("History").first.click()
        await pg.wait_for_timeout(2500)
    await go(page, "/app/attendance", "op_01_attendance", before=att)


async def teacher(b):
    page = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()
    await login(page, "lakshmi@sunrise-demo.in", PW, slug="sunrise")
    for path, n in [("/teacher/marks", "rt_04_marks"), ("/teacher/ai-tutor", "ai_02_teacher"), ("/teacher/homework", "rt_06_homework"), ("/teacher/dashboard", "rt_01_dash")]:
        await go(page, path, n, wait=3000)


async def student(b):
    page = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()
    await login(page, "aarav@sunrise-demo.in", PW, slug="sunrise")
    await page.wait_for_timeout(2000)
    await shot(page, "rs_01_student_home")
    try:
        await click(page, "[data-testid=quick-results]", 2500)
        await shot(page, "rs_03_results")
        rb = page.locator("[data-testid=portal-report-btn]")
        if await rb.count():
            await rb.first.click(); await page.wait_for_timeout(3000)
            await shot(page, "rs_04_report_card")
    except Exception as e:
        print("MISS results", str(e)[:120])
    await login(page, "aarav@sunrise-demo.in", PW, slug="sunrise")
    await click(page, "[data-testid=quick-ai-tutor]", 2500)
    if not await page.locator("[data-testid=ai-input]").count():
        await page.get_by_text("Science").first.click(); await page.wait_for_timeout(2000)
    for q in ["Why does ice float on water? Explain for Class 8.", "Give one everyday example of friction being useful."]:
        try:
            await page.locator("[data-testid=ai-input]").fill(q)
            await page.click("[data-testid=ai-send]")
            n0 = await page.locator("[data-testid=ai-messages] > *").count()
            for _ in range(45):
                await page.wait_for_timeout(1000)
                txt = await page.locator("[data-testid=ai-messages]").inner_text()
                if (await page.locator("[data-testid=ai-messages] > *").count()) > n0 and "thinking" not in txt.lower()[-200:]:
                    break
            await page.wait_for_timeout(2500)
        except Exception as e:
            print("MISS ai", str(e)[:120])
    await shot(page, "ai_03_student")


async def parent(b):
    page = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()
    await login(page, "parent.menon@sunrise-demo.in", PW, slug="sunrise")
    await go(page, "/parents", "rpa_01_parent_home", wait=3500)
    try:
        await click(page, "[data-testid=parent-report-btn]", 3000)
        await shot(page, "rpa_04_report_card")
    except Exception as e:
        print("MISS parent report", str(e)[:120])


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for fn in (platform, wizard, admin, teacher, student, parent):
            try:
                await fn(b)
            except Exception as e:
                print("MISS", fn.__name__, str(e)[:200])
        await b.close()

asyncio.run(main())
