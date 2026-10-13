"""v1.2 step 8: Smart Timetable, Substitutions and Class Hub captures (Sunrise demo only)."""
import asyncio
import os
import re
from pymongo import MongoClient
from playwright.async_api import async_playwright
from common import ADMIN, BASE, PW, shot, login
from s3_capture import go

db = MongoClient("mongodb://localhost:27017")["test_database"]
IID = db.institutions.find_one({"name": "Sunrise Public School (Demo)"})["id"]
Q = {"institution_id": IID}
CLS = {c["name"]: c["id"] for c in db.classes.find(Q)}
SEC8A = db.sections.find_one({**Q, "class_name": "Grade 8", "name": "A"})["id"]
TODAY = "2026-10-13"


def conflict_move():
    pub = list(db.timetable_entries.find({**Q, "status": "active", "publish_state": "published"}))
    busy = {(e["teacher_id"], e["day"], e["period_no"]) for e in pub if e.get("teacher_id")}
    for e in pub:
        if (e["class_name"], e["section"]) != ("Grade 8", "A") or not e.get("teacher_id"):
            continue
        for (t, d, p) in busy:
            if t == e["teacher_id"] and not any(x["class_name"] == "Grade 8" and x["section"] == "A" and x["day"] == d and x["period_no"] == p and x["teacher_id"] == t for x in pub):
                return e["day"], e["period_no"], d, p
    return None


async def pick(page, trigger, text):
    await page.click(f"[data-testid={trigger}]")
    await page.wait_for_timeout(500)
    await page.get_by_role("option", name=re.compile("^" + re.escape(text))).first.click()
    await page.wait_for_timeout(1800)


page_ref = []
ONLY = os.environ.get("ONLY", "tt,subs,hub").split(",")


async def safe(name, coro):
    if name in ("tt", "subs", "hub", "teachers") and name not in ONLY:
        coro.close()
        return
    try:
        await coro
    except Exception as e:
        print("MISS", name, str(e)[:160])
        try:
            await page_ref[0].keyboard.press("Escape")
        except Exception:
            pass


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()
        page_ref.append(page)
        await login(page, *ADMIN, slug="sunrise")

        async def tab(key):
            await page.click(f"[data-testid=tt-tab-{key}]")
            await page.wait_for_timeout(2200)

        async def tt():
            await page.goto(BASE + "/app/timetable")
            await page.wait_for_timeout(2500)
            await tab("setup"); await shot(page, "tt_10_setup")
            await tab("requirements")
            await safe("req", pick(page, "req-class-select", "Grade 8")); await shot(page, "tt_11_requirements")
            await tab("teacher"); await safe("tsel", pick(page, "tt-teacher-select", "Lakshmi Menon")); await shot(page, "tt_15_by_teacher")
            await tab("subject"); await safe("ssel", pick(page, "subject-select", "Mathematics")); await shot(page, "tt_17_by_subject")
            await tab("day"); await shot(page, "tt_16_by_day")
            await tab("grade"); await safe("g8", pick(page, "grade-class-select", "Grade 8"))
            mv = conflict_move()
            print("move", mv)
            if mv:
                d0, p0, d1, p1 = mv
                await page.drag_and_drop(f"[data-testid=grade-cell-{d0}-{p0}]", f"[data-testid=grade-cell-{d1}-{p1}]")
                await page.wait_for_timeout(2000)
                await shot(page, "tt_14_conflict")
                await page.keyboard.press("Escape"); await page.wait_for_timeout(800)
            await safe("g9", pick(page, "grade-class-select", "Grade 9"))
            await page.fill("[data-testid=grade-date-picker]", TODAY); await page.wait_for_timeout(2500)
            await shot(page, "tt_18_date_overlay")
            await page.click("[data-testid=grade-clear-date]"); await page.wait_for_timeout(1500)
            if not await page.locator("[data-testid=tt-autobalance-checkbox]").is_checked():
                await page.click("[data-testid=tt-autobalance-checkbox]")
            await page.click("[data-testid=tt-generate-btn]"); await page.wait_for_timeout(1500)
            btn = page.get_by_role("button", name="Regenerate draft")
            if await btn.count() > 1:
                await btn.last.click()
            await page.wait_for_timeout(4000)
            await shot(page, "tt_13_generate_report", full=True)
        await safe("tt", tt())

        async def subs():
            await page.goto(BASE + "/app/substitutions")
            await page.wait_for_timeout(2500)
            await page.fill("[data-testid=sub-date]", TODAY); await page.wait_for_timeout(2000)
            await page.locator("[data-testid^=absence-toggle-]").first.click(); await page.wait_for_timeout(2000)
            await shot(page, "sub_01_dashboard", full=True)
            await page.click("[data-testid=mark-absent-btn]"); await page.wait_for_timeout(800)
            await shot(page, "sub_00_mark_absent")
            await page.keyboard.press("Escape"); await page.wait_for_timeout(600)
            await page.locator("button:has-text('Find cover')").last.click(); await page.wait_for_timeout(2500)
            await shot(page, "sub_02_suggestions")
            meera = db.users.find_one({**Q, "email": "meera@sunrise-demo.in"})["id"]
            if await page.locator(f"[data-testid=assign-{meera}]").count():
                await page.click(f"[data-testid=assign-{meera}]")
            else:
                await page.keyboard.press("Escape")
            await page.wait_for_timeout(2500)
            await page.fill("[data-testid=sub-date]", "2026-10-12"); await page.wait_for_timeout(2000)
            await page.locator("[data-testid^=absence-toggle-]").first.click(); await page.wait_for_timeout(2000)
            await shot(page, "sub_05_history")
        await safe("subs", subs())

        async def hub():
            base = BASE
            await page.goto(base + "/app/class-hub"); await page.wait_for_timeout(2500)
            await shot(page, "ch_01_classes")
            await page.click("[data-testid='class-chip-Grade 8']"); await page.wait_for_timeout(1500)
            for k, n in [("sections", "ch_02_sections"), ("enrollments", "ch_03_enrollments"), ("teachers", "ch_04_teacher_assign"), ("offerings", "ch_05_offerings")]:
                await page.click(f"[data-testid=hub-tab-{k}]"); await page.wait_for_timeout(1800)
                await shot(page, n, full=True)
            for k, n in [("overview", "ch_06_class_overview"), ("staff", "ch_07_class_staff"), ("subjects", "ch_08_class_subjects"),
                         ("students", "ch_09_class_students"), ("timetable", "ch_10_class_timetable")]:
                await page.goto(f"{base}/app/class-hub/{CLS['Grade 8']}?tab={k}"); await page.wait_for_timeout(3000)
                await shot(page, n, full=k in ("staff", "students"))
            await page.goto(f"{base}/app/class-hub/{CLS['Grade 8']}/section/{SEC8A}"); await page.wait_for_timeout(3000)
            await shot(page, "ch_11_section_page")
        await safe("hub", hub())

        async def teachers():
            await login(page, "lakshmi@sunrise-demo.in", PW, slug="sunrise")
            await go(page, "/teacher/substitutions", "sub_03_teacher_requests")
            await login(page, "meera@sunrise-demo.in", PW, slug="sunrise")
            await page.goto(BASE + "/teacher/timetable"); await page.wait_for_timeout(2500)
            await page.fill("[data-testid=teacher-tt-date]", TODAY); await page.wait_for_timeout(2500)
            await shot(page, "sub_04_teacher_cover_view")
            await go(page, "/teacher/substitutions", "sub_06_teacher_assigned")
            await login(page, "aarav@sunrise-demo.in", PW, slug="sunrise")
            await page.click("[data-testid=portal-nav-timetable]"); await page.wait_for_timeout(2500)
            await shot(page, "tt_19_student_portal")
        await safe("teachers", teachers())
        await b.close()

asyncio.run(main())
