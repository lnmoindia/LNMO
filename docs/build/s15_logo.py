"""LNMO logo before/after captures: generic login, platform sidebar, platform settings, portal powered-by, school login."""
import asyncio
import sys
from playwright.async_api import async_playwright
from common import BASE

TAG = sys.argv[1] if len(sys.argv) > 1 else "after"


async def shot(p, name):
    await p.wait_for_timeout(1800)
    await p.screenshot(path=f"/app/docs/shots/logo_{TAG}_{name}.png")


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        for mobile in (False, True):
            c = await b.new_context(viewport={"width": 390, "height": 844} if mobile else {"width": 1440, "height": 900},
                                    is_mobile=mobile, device_scale_factor=2 if mobile else 1)
            p = await c.new_page()
            await p.goto(f"{BASE}/login")
            await shot(p, "login" + ("_m" if mobile else ""))
            if not mobile:
                fav = await p.evaluate("[...document.querySelectorAll('link[rel*=icon],link[rel=manifest]')].map(l=>l.rel+'='+l.href).join(' | ')")
                print("head links:", fav, "| title:", await p.title())
            await c.close()
        c = await b.new_context(viewport={"width": 1440, "height": 900})
        p = await c.new_page()
        await p.goto(f"{BASE}/lnmoplatformlogin")
        await p.locator("input").nth(0).fill("lnmopvt@gmail.com")
        await p.locator("input[type=password]").fill("Lnmo@2026!")
        await p.locator("button[type=submit]").click()
        await p.wait_for_url("**/platform/**", timeout=20000)
        await shot(p, "platform")
        if TAG != "before":
            await p.goto(f"{BASE}/platform/settings")
            await shot(p, "platform_settings")
        await c.close()
        c = await b.new_context(viewport={"width": 1440, "height": 900})
        p = await c.new_page()
        await p.goto(f"{BASE}/login/sunrise")
        await p.get_by_test_id("login-email-input").fill("parent.menon@sunrise-demo.in")
        await p.get_by_test_id("login-password-input").fill("Sunrise@2026")
        await p.get_by_test_id("login-submit-btn").click()
        await p.wait_for_url("**/parents/**", timeout=15000)
        await shot(p, "parent_portal")
        await c.close()
        await b.close()

asyncio.run(main())
