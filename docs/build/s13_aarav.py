"""Fresh-session student login check for aarav via /login/sunrise and /login (desktop + 390 mobile)."""
import asyncio
from playwright.async_api import async_playwright
from common import BASE


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        for path, mobile in (("/login/sunrise", False), ("/login/sunrise", True), ("/login", False)):
            c = await b.new_context(viewport={"width": 390, "height": 844} if mobile else {"width": 1440, "height": 900},
                                    is_mobile=mobile, device_scale_factor=2 if mobile else 1)
            p = await c.new_page()
            await p.goto(BASE + path)
            await p.get_by_test_id("login-email-input").fill("aarav@sunrise-demo.in")
            await p.get_by_test_id("login-password-input").fill("Sunrise@2026")
            await p.get_by_test_id("login-submit-btn").click()
            await p.wait_for_url("**/portal/**", timeout=15000)
            await p.wait_for_timeout(2500)
            hero = await p.get_by_text("Aarav Menon").first.is_visible()
            print(path, "mobile" if mobile else "desktop", "->", p.url, "| hero visible:", hero)
            await p.reload()
            await p.wait_for_timeout(2000)
            print("   after reload ->", p.url)
            if path == "/login/sunrise":
                await p.screenshot(path=f"/app/docs/shots/aarav_login_ok{'_m' if mobile else ''}.png")
            await c.close()
        c = await b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, device_scale_factor=2)
        p = await c.new_page()
        await p.goto(BASE + "/login/sunrise")
        await p.screenshot(path="/app/docs/shots/aarav_login_hint_m.png")
        await b.close()

asyncio.run(main())
