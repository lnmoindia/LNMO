"""Phase 56 screenshots: platform dashboard, institutions list, detail tabs, admin dialogs, reset page (1440 + 1024 + 390)."""
import asyncio
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from playwright.async_api import async_playwright
from pymongo import MongoClient
from common import BASE


def _env(k):
    for line in open("/app/backend/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


db = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]
SUN = "e8f49f14-df1b-41e1-ac30-499cdc81522c"
OUT = "/app/docs/shots/p56_"
ERR = []


async def shot(p, name, wait=1500):
    await p.wait_for_timeout(wait)
    await p.screenshot(path=f"{OUT}{name}.png")


async def main():
    tw = db.institutions.find_one({"name": {"$regex": "^P56 Throwaway"}}, sort=[("created_at", -1)])
    adm = db.users.find_one({"institution_id": tw["id"], "role": "institution_admin"})
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        c = await b.new_context(viewport={"width": 1440, "height": 900})
        p = await c.new_page()
        p.on("console", lambda m: ERR.append(m.text) if m.type == "error" else None)
        await p.goto(f"{BASE}/lnmoplatformlogin")
        await p.locator("input").nth(0).fill("lnmopvt@gmail.com")
        await p.locator("input[type=password]").fill("Lnmo@2026!")
        await p.locator("button[type=submit]").click()
        await p.wait_for_url("**/platform/**", timeout=20000)
        await shot(p, "dashboard", 2500)
        await p.goto(f"{BASE}/platform/institutions")
        await p.get_by_test_id("institutions-table").wait_for()
        await shot(p, "institutions")
        await p.get_by_test_id(f"inst-row-{SUN}").click()
        await p.get_by_test_id("inst-overview-tab").wait_for()
        await shot(p, "detail_overview")
        for t in ("analytics", "plan", "admins", "activity", "domain", "features"):
            await p.goto(f"{BASE}/platform/institutions/{SUN}?tab={t}")
            await shot(p, f"detail_{t}", 2200)
        await p.goto(f"{BASE}/platform/institutions/{SUN}?tab=plan")
        await p.get_by_test_id("edit-plan-btn").click()
        await shot(p, "plan_edit_dialog", 800)
        await p.keyboard.press("Escape")
        await p.goto(f"{BASE}/platform/institutions/{tw['id']}?tab=admins")
        await p.get_by_test_id(f"admin-reset-{adm['id']}").click()
        await p.get_by_test_id("reset-send-btn").click()
        await p.get_by_test_id("reset-result").wait_for(timeout=20000)
        print("reset result:", await p.get_by_test_id("reset-result").inner_text())
        await shot(p, "admin_reset_sent", 600)
        await p.keyboard.press("Escape")
        await p.get_by_test_id(f"admin-email-btn-{adm['id']}").click()
        await p.get_by_test_id("new-email-input").fill("admin@sunrise-demo.in")
        await p.get_by_test_id("email-save-btn").click()
        await p.get_by_test_id("email-error").wait_for()
        print("dup email:", await p.get_by_test_id("email-error").inner_text())
        await shot(p, "admin_email_conflict", 400)
        await p.set_viewport_size({"width": 1024, "height": 800})
        await p.goto(f"{BASE}/platform/institutions/{SUN}?tab=analytics")
        await shot(p, "detail_analytics_1024", 2200)
        await p.goto(f"{BASE}/platform/institutions")
        await shot(p, "institutions_1024", 1800)
        await c.close()

        tok = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        db.password_resets.update_many({"user_id": adm["id"], "used_at": None, "invalidated_at": None}, {"$set": {"invalidated_at": now.isoformat()}})
        db.password_resets.insert_one({"id": str(uuid.uuid4()), "user_id": adm["id"], "institution_id": tw["id"], "token_hash": hashlib.sha256(tok.encode()).hexdigest(),
                                       "created_at": now.isoformat(), "expires_at": (now + timedelta(hours=24)).isoformat(), "created_by": "screenshot",
                                       "used_at": None, "invalidated_at": None})
        for mobile in (False, True):
            c = await b.new_context(viewport={"width": 390, "height": 844} if mobile else {"width": 1440, "height": 900}, is_mobile=mobile, device_scale_factor=2 if mobile else 1)
            p = await c.new_page()
            await p.goto(f"{BASE}/reset-password/{tok}")
            await p.get_by_test_id("reset-password-input").wait_for()
            await p.get_by_test_id("reset-password-input").fill("NewPass@2026")
            await p.get_by_test_id("reset-confirm-input").fill("NewPass@2026")
            await p.get_by_test_id("reset-password-input-toggle").click()
            await shot(p, "reset_page" + ("_m" if mobile else ""), 500)
            if mobile:
                await p.get_by_test_id("reset-submit-btn").click()
                await p.get_by_test_id("reset-success").wait_for()
                await shot(p, "reset_success_m", 400)
                await p.reload()
                await p.get_by_test_id("reset-invalid").wait_for()
                print("reuse:", await p.get_by_test_id("reset-invalid").inner_text())
                await shot(p, "reset_used_m", 300)
            await c.close()
        await b.close()
    print("console errors:", len(ERR), ERR[:6])

asyncio.run(main())
