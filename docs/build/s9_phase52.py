"""Phase 52 screenshots on the Sunrise demo: cancel dialog, cancelled history, portal substitute notice."""
import asyncio
import requests
from pymongo import MongoClient
from playwright.async_api import async_playwright
from common import ADMIN, BASE, PW, shot, login

API = "http://localhost:8001/api"
db = MongoClient("mongodb://localhost:27017")["test_database"]
IID = db.institutions.find_one({"name": "Sunrise Public School (Demo)"})["id"]
Q = {"institution_id": IID}
TODAY, TMRW = "2026-10-13", "2026-10-14"


def sess(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw})
    r.raise_for_status()
    s.headers["Authorization"] = f"Bearer {r.cookies.get('access_token')}"
    return s


a = sess(*ADMIN)
arjun = db.absences.find_one({**Q, "teacher_name": "Arjun Pillai", "date": TODAY})
rahul = db.absences.find_one({**Q, "teacher_name": "Rahul Nair", "date": TMRW})
p7 = db.substitutions.find_one({**Q, "absence_id": arjun["id"], "class_name": "Grade 8", "section": "A"})


async def portal(page, tag, mobile):
    await login(page, "aarav@sunrise-demo.in", PW, slug="sunrise")
    await page.wait_for_timeout(2500)
    await shot(page, f"p52_student_today_{tag}{'_m' if mobile else ''}", full=mobile)
    if not mobile:
        await page.click("[data-testid=portal-nav-timetable]")
        await page.wait_for_timeout(2500)
        await shot(page, f"p52_student_tt_{tag}")
    await login(page, "parent.menon@sunrise-demo.in", PW, slug="sunrise")
    await page.wait_for_timeout(3000)
    await page.locator("[data-testid=parent-today-tt]").scroll_into_view_if_needed()
    await page.wait_for_timeout(800)
    await shot(page, f"p52_parent_today_{tag}{'_m' if mobile else ''}")


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        desk = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()
        mob = await (await b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True)).new_page()
        await portal(desk, "open", False)
        await portal(mob, "open", True)
        if p7["status"] != "assigned":
            sug = a.get(f"{API}/substitutions/{p7['id']}/suggestions").json()["suggestions"]
            print("assign P7", a.post(f"{API}/substitutions/{p7['id']}/assign", json={"teacher_id": sug[0]["teacher_id"]}).status_code, sug[0]["name"])
        await portal(desk, "covered", False)
        await portal(mob, "covered", True)

        if rahul["status"] == "requested":
            print("approve rahul", a.post(f"{API}/absences/{rahul['id']}/approve").status_code)
            subs = sorted(a.get(f"{API}/absences/{rahul['id']}").json()["substitutions"], key=lambda s: s["period_no"])
            print("rahul subs", [(s["period_no"], s["class_name"], s["section"]) for s in subs])
            if subs:
                sug = a.get(f"{API}/substitutions/{subs[0]['id']}/suggestions").json()["suggestions"]
                a.post(f"{API}/substitutions/{subs[0]['id']}/assign", json={"teacher_id": sug[0]["teacher_id"]})
            if len(subs) > 1:
                sug = a.get(f"{API}/substitutions/{subs[1]['id']}/suggestions").json()["suggestions"]
                a.post(f"{API}/substitutions/{subs[1]['id']}/request", json={"teacher_ids": [s["teacher_id"] for s in sug[:2]]})
        pg = desk
        await login(pg, *ADMIN, slug="sunrise")
        await pg.goto(BASE + "/app/substitutions"); await pg.wait_for_timeout(2500)
        await pg.fill("[data-testid=sub-date]", TODAY); await pg.wait_for_timeout(2000)
        await pg.click(f"[data-testid=cancel-absence-{arjun['id']}]"); await pg.wait_for_timeout(2000)
        await shot(pg, "p52_cancel_dialog_today_kept")
        await pg.keyboard.press("Escape"); await pg.wait_for_timeout(800)
        await pg.fill("[data-testid=sub-date]", TMRW); await pg.wait_for_timeout(2000)
        await pg.click(f"[data-testid=absence-toggle-{rahul['id']}]"); await pg.wait_for_timeout(1500)
        await shot(pg, "p52_tomorrow_before")
        await pg.click(f"[data-testid=cancel-absence-{rahul['id']}]"); await pg.wait_for_timeout(2000)
        await pg.fill("[data-testid=cancel-reason-input]", "Appointment moved to Saturday — Rahul will be in school")
        await pg.wait_for_timeout(500)
        await shot(pg, "p52_cancel_dialog")
        await pg.click("[data-testid=cancel-absence-confirm]"); await pg.wait_for_timeout(3000)
        await shot(pg, "p52_history_cancelled")
        await b.close()

asyncio.run(main())
