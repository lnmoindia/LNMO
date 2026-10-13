"""Phase 55 screenshots: eye toggle, admission login, generic guidance, locked badge + unlock toast (Sunrise)."""
import asyncio
import requests
from playwright.async_api import async_playwright
from common import BASE

PW = "Sunrise@2026"
API = BASE + "/api"


def lock_aarav():
    for i in range(5):
        requests.post(f"{API}/auth/login", json={"identifier": "aarav@sunrise-demo.in" if i % 2 else "SPS-001",
                                                 "password": "wrong-pass", "slug": "sunrise"})


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        for mobile in (False, True):
            c = await b.new_context(viewport={"width": 390, "height": 844} if mobile else {"width": 1440, "height": 900},
                                    is_mobile=mobile, device_scale_factor=2 if mobile else 1)
            p = await c.new_page()
            await p.goto(f"{BASE}/login/sunrise")
            await p.get_by_test_id("login-email-input").fill("SPS-001")
            await p.get_by_test_id("login-password-input").fill(PW)
            t = p.get_by_test_id("login-password-input-toggle")
            await t.focus()
            await p.keyboard.press("Enter")
            typ = await p.get_by_test_id("login-password-input").get_attribute("type")
            print("mobile" if mobile else "desktop", "after toggle type=", typ, "aria=", await t.get_attribute("aria-label"),
                  "| still on", p.url, "| value kept:", await p.get_by_test_id("login-password-input").input_value() == PW)
            await p.wait_for_timeout(1500)
            await p.screenshot(path=f"/app/docs/shots/p55_login_eye{'_m' if mobile else ''}.png")
            await p.get_by_test_id("login-submit-btn").click()
            await p.wait_for_url("**/portal/**", timeout=15000)
            print("   admission login ->", p.url)
            await c.close()
        c = await b.new_context(viewport={"width": 1440, "height": 900})
        p = await c.new_page()
        await p.goto(f"{BASE}/login")
        await p.get_by_test_id("login-email-input").fill("SPS-001")
        await p.get_by_test_id("login-password-input").fill(PW)
        await p.get_by_test_id("login-password-input-toggle").click()
        await p.get_by_test_id("login-submit-btn").click()
        await p.get_by_test_id("login-error").wait_for()
        print("generic:", await p.get_by_test_id("login-error").inner_text(), "| type after fail:",
              await p.get_by_test_id("login-password-input").get_attribute("type"))
        await p.screenshot(path="/app/docs/shots/p55_generic_guidance.png")
        await c.close()

        lock_aarav()
        c = await b.new_context(viewport={"width": 1440, "height": 900})
        p = await c.new_page()
        await p.goto(f"{BASE}/login/sunrise")
        await p.get_by_test_id("login-email-input").fill("admin@sunrise-demo.in")
        await p.get_by_test_id("login-password-input").fill(PW)
        await p.get_by_test_id("login-submit-btn").click()
        await p.wait_for_url("**/app/**", timeout=15000)
        await p.goto(f"{BASE}/app/users?q=aarav")
        await p.wait_for_timeout(3000)
        await p.screenshot(path="/app/docs/shots/p55_users_locked.png")
        sid = requests.Session()
        r = sid.post(f"{API}/auth/login", json={"identifier": "admin@sunrise-demo.in", "password": PW, "slug": "sunrise"})
        stu = [x for x in sid.get(f"{API}/res/students", params={"search": "Aarav", "limit": 5}).json()["items"] if x.get("admission_no") == "SPS-001"][0]
        await p.goto(f"{BASE}/app/students/{stu['id']}")
        await p.get_by_test_id("account-locked-badge").wait_for(timeout=15000)
        print("badge:", await p.get_by_test_id("account-locked-badge").inner_text())
        await p.screenshot(path="/app/docs/shots/p55_student_locked.png")
        await p.get_by_test_id("unlock-account-btn").click()
        await p.get_by_text("Account unlocked").wait_for(timeout=8000)
        await p.wait_for_timeout(400)
        await p.screenshot(path="/app/docs/shots/p55_unlock_toast.png")
        print("badge gone:", await p.get_by_test_id("account-locked-badge").count() == 0)
        r = requests.post(f"{API}/auth/login", json={"identifier": "aarav@sunrise-demo.in", "password": PW, "slug": "sunrise"})
        print("aarav after unlock:", r.status_code)
        await b.close()

asyncio.run(main())
