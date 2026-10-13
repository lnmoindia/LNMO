"""Step 3: capture every module/role (1440x900 desktop + 390x844 mobile)."""
import asyncio
import re
from playwright.async_api import async_playwright
from common import BASE, PA, ADMIN, PW, shot, login

MOB = {"width": 390, "height": 844}


async def go(page, path, name, marks=(), wait=2200, full=False, before=None):
    try:
        await page.goto(f"{BASE}{path}")
        await page.wait_for_timeout(wait)
        if before:
            await before(page)
        await shot(page, name, marks, full=full)
    except Exception as e:
        print("MISS", name, str(e)[:160])


async def click(page, sel, wait=1500):
    await page.locator(sel).first.click(timeout=8000)
    await page.wait_for_timeout(wait)


async def platform(page):
    await login(page, *PA)
    await go(page, "/platform/dashboard", "pm_02_dashboard", wait=3000)
    await go(page, "/platform/institutions", "pm_03_institutions", [("[data-testid=add-record-btn]", "Add a new school")])
    await go(page, "/platform/institutions", "pm_05_created", before=lambda p: p.get_by_text("Sunrise Public School (Demo)").first.click())
    await go(page, "/platform/plans", "pm_06_plans")
    await go(page, "/platform/issues", "pm_07_issues")
    await go(page, "/platform/communication", "pm_08_comm")
    await go(page, "/platform/library", "pm_09_library")


async def admin(page):
    await login(page, *ADMIN, slug="sunrise")
    await go(page, "/app/dashboard", "ad_03_dashboard", wait=3500)
    await go(page, "/app/setup", "ad_04_setup_done")
    await go(page, "/app/settings", "ad_05_settings")
    await go(page, "/app/settings", "ad_06_upi_settings", [("[data-testid=settings-upi-card]", "UPI payments")],
             before=lambda p: p.locator("[data-testid=settings-upi-card]").scroll_into_view_if_needed())
    for path, n in [("/app/academic-years", "ad_07_years"), ("/app/academic-units", "ad_08_units"), ("/app/class-hub", "ad_09_classhub"),
                    ("/app/subjects", "ad_10_subjects"), ("/app/teachers", "ad_11_teachers"), ("/app/users", "ad_12_users"),
                    ("/app/students", "ad_13_students"), ("/app/timetable", "tt_01_timetable"), ("/app/substitutions", "tt_02_substitutions"),
                    ("/app/attendance", "op_01_attendance"), ("/app/assessments", "ex_01_assessments"), ("/app/exams", "ex_02_exams"),
                    ("/app/homework-monitor", "op_02_homework"), ("/app/ai-tutor", "ai_01_admin"), ("/app/notices", "op_03_notices"),
                    ("/app/communication", "cm_01_comm"), ("/app/audit", "op_04_audit"), ("/app/support", "op_05_support")]:
        await go(page, path, n, wait=2600)

    async def open_student(p):
        await p.get_by_text("Aarav", exact=False).first.click()
        await p.wait_for_timeout(2500)
    await go(page, "/app/students", "pf_01_student_profile", before=open_student)

    async def open_exam(p):
        await p.get_by_text("Term 1 Examination 2026").first.click()
        await p.wait_for_timeout(2500)
    await go(page, "/app/exams", "ex_03_exam_detail", before=open_exam)
    # fees
    for tab, n in [("structures", "fe_01_structures"), ("accounts", "fe_02_accounts"), ("receipts", "fe_05_receipts"), ("daybook", "fe_06_daybook"),
                   ("defaulters", "fe_07_defaulters"), ("monthly", "fe_09_monthly"), ("proofs", "fe_11_proofs")]:
        await go(page, f"/app/fees?tab={tab}", n, wait=2800)

    async def ledger(p):
        await click(p, "[data-testid^=fee-ledger-]", 2500)
    await go(page, "/app/fees?tab=accounts", "fe_03_ledger", [("[data-testid=fee-ledger-statement]", "Statement PDF")], before=ledger)

    async def collect(p):
        await ledger(p)
        await click(p, "[data-testid^=fee-collect-]", 1500)
        await p.locator("[data-testid=fee-collect-date]").fill("2026-10-10")
    await go(page, "/app/fees?tab=accounts", "fe_04_collect", [("[data-testid=fee-collect-date]", "Payment date (backdating allowed)")], before=collect)

    async def daybook(p):
        inp = p.locator("input[type=date]").first
        await inp.fill("2026-10-12")
        await p.wait_for_timeout(2000)
    await go(page, "/app/fees?tab=daybook", "fe_06_daybook", before=daybook)

    async def monthly(p):
        await p.locator("[data-testid=monthly-month]").fill("2026-07")
        await p.wait_for_timeout(2500)
    await go(page, "/app/fees?tab=monthly", "fe_09_monthly", [("[data-testid=monthly-print]", "Printable report")], before=monthly)
    await go(page, "/app/fees?tab=defaulters", "fe_07_defaulters", [("[data-testid^=defaulter-remind-]", "One-tap reminder")])

    async def issues(p):
        await click(p, "[data-testid=proofs-kind-issues]", 2000)
    await go(page, "/app/fees?tab=proofs", "fe_12_issues", before=issues)
    await go(page, "/app/fees?tab=proofs", "fe_11_proofs", [("[data-testid^=proof-approve-]", "Approve → receipt")], wait=3500)

    async def promo(p):
        try:
            await click(p, "[data-testid=promo-from-year]", 800)
            await p.get_by_role("option", name="2026-27").click()
            to = p.locator("[data-testid=promo-to-year]")
            if await to.evaluate("e => e.tagName") == "INPUT":
                await to.fill("2027-28")
            else:
                await to.click(); await p.get_by_role("option").filter(has_text=re.compile("2027")).first.click()
        except Exception as e:
            print("promo select", str(e)[:120])
        await click(p, "[data-testid=promo-preview-btn]", 3500)
    await go(page, "/app/promotion", "pr_01_promotion", [("[data-testid=promo-dues-summary]", "Dues warning (promotion not blocked)")], before=promo)
    await go(page, "/app/students", "po_01_invites", [("text=Invite", "Parent invites")], wait=2500)


async def principal(page):
    await login(page, "thomas@sunrise-demo.in", PW, slug="sunrise")
    await go(page, "/app/dashboard", "rp_01_principal_dash", wait=3500)
    await go(page, "/app/fees?tab=defaulters", "rp_02_principal_defaulters", wait=2800)


async def teacher(page):
    await login(page, "lakshmi@sunrise-demo.in", PW, slug="sunrise")
    for path, n in [("/teacher/dashboard", "rt_01_dash"), ("/teacher/my-class", "rt_02_myclass"), ("/teacher/timetable", "rt_03_timetable"),
                    ("/teacher/marks", "rt_04_marks"), ("/teacher/attendance", "rt_05_attendance"), ("/teacher/homework", "rt_06_homework"),
                    ("/teacher/fee-defaulters", "rt_07_feedefaulters"), ("/teacher/profile", "rt_08_profile"), ("/teacher/ai-tutor", "ai_02_teacher")]:
        await go(page, path, n, wait=2600)


async def parent(page, mobile=False):
    await login(page, "parent.menon@sunrise-demo.in", PW, slug="sunrise")
    if mobile:
        async def scroll_qr(p):
            await p.locator("[data-testid^=upi-qr-]").first.scroll_into_view_if_needed()
        await go(page, "/parents", "rpa_03_mobile_home", wait=3500)
        await go(page, "/parents", "fe_10_parent_qr_mobile", [("[data-testid^=upi-open-app-]", "Open UPI app")], wait=3500, before=scroll_qr)
        return
    await go(page, "/parents", "rpa_01_parent_home", wait=3500)

    async def fees(p):
        await p.locator("[data-testid=parent-fees]").scroll_into_view_if_needed()
    await go(page, "/parents", "rpa_02_parent_fees", [("[data-testid^=proof-status-]", "Verification pending")], wait=3500, before=fees)


async def student(page, mobile=False):
    await login(page, "aarav@sunrise-demo.in", PW, slug="sunrise")
    await page.wait_for_timeout(2000)
    await shot(page, "rs_02_student_mobile" if mobile else "rs_01_student_home")
    if not mobile:
        try:
            await click(page, "[data-testid=quick-ai-tutor]", 2500)
            await shot(page, "ai_03_student")
        except Exception as e:
            print("MISS ai student", str(e)[:100])


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for fn, vp in [(platform, None), (admin, None), (principal, None), (teacher, None), (parent, None), (student, None)]:
            ctx = await b.new_context(viewport={"width": 1440, "height": 900})
            await fn(await ctx.new_page())
            await ctx.close()
        for fn in (parent, student):
            ctx = await b.new_context(viewport=MOB, device_scale_factor=2, is_mobile=True, has_touch=True)
            await fn(await ctx.new_page(), mobile=True)
            await ctx.close()
        await b.close()

if __name__ == "__main__":
    asyncio.run(main())
