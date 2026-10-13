"""Verify Platform Manager login links (LPGS/Sunrise/TEST) open branded pages and sign-in works."""
import asyncio
from playwright.async_api import async_playwright
from common import BASE

SCHOOLS = [
    ("lpgs", "82d1ec4e-db71-4578-903b-bc986f1ebd3d", "sreeja@lpgs.com", "teach123"),
    ("sunrise", "e8f49f14-df1b-41e1-ac30-499cdc81522c", "lakshmi@sunrise-demo.in", "Sunrise@2026"),
    ("test", "6490c719-2639-4eb4-b40c-d3a4fa3701a4", "classteacher@feesdemo.test", "teach123"),
]


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        c = await b.new_context(viewport={"width": 1440, "height": 900})
        await c.grant_permissions(["clipboard-read", "clipboard-write"], origin=BASE)
        p = await c.new_page()
        await p.goto(f"{BASE}/lnmoplatformlogin")
        await p.locator("input").nth(0).fill("lnmopvt@gmail.com")
        await p.locator("input[type=password]").fill("Lnmo@2026!")
        await p.locator("button[type=submit]").click()
        await p.wait_for_url("**/platform**", timeout=20000)
        links = {}
        for name, iid, _, _ in SCHOOLS:
            await p.goto(f"{BASE}/platform/institutions/{iid}")
            await p.get_by_test_id("inst-tab-domain").click()
            inp = p.get_by_test_id("login-link-input")
            await inp.wait_for(timeout=15000)
            await p.get_by_test_id("copy-login-link").click()
            clip = await p.evaluate("navigator.clipboard.readText()")
            links[name] = clip
            print(name, "field:", await inp.input_value(), "| clipboard:", clip)
            if name == "lpgs":
                await p.screenshot(path="/app/docs/shots/p54_platform_copy_link.png")
        for mobile in (False, True):
            for name, _, email, pwd in SCHOOLS:
                ctx = await b.new_context(viewport={"width": 390, "height": 844} if mobile else {"width": 1440, "height": 900},
                                          is_mobile=mobile, device_scale_factor=2 if mobile else 1)
                q = await ctx.new_page()
                await q.goto(links[name])
                await q.wait_for_timeout(2500)
                brand = await q.locator("h1, h2").first.inner_text()
                print(("mobile " if mobile else "desktop ") + name, q.url, "| heading:", brand.replace("\n", " "))
                await q.screenshot(path=f"/app/docs/shots/p54_login_{name}{'_m' if mobile else ''}.png")
                if not mobile:
                    await q.locator("input").nth(0).fill(email)
                    await q.locator("input[type=password]").fill(pwd)
                    await q.locator("button[type=submit]").click()
                    await q.wait_for_timeout(4000)
                    print("   signed in ->", q.url)
                await ctx.close()
        ctx = await b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, device_scale_factor=2)
        q = await ctx.new_page()
        await q.goto(f"{BASE}/login?domain=lpgs.com")
        await q.wait_for_timeout(2500)
        print("legacy ?domain= ->", q.url, "|", (await q.locator("h1, h2").first.inner_text()).replace("\n", " "))
        await q.screenshot(path="/app/docs/shots/p54_login_lpgs_domain_m.png")
        await q.locator("input").nth(0).fill("sreeja@lpgs.com")
        await q.locator("input[type=password]").fill("teach123")
        await q.locator("button[type=submit]").click()
        await q.wait_for_timeout(4000)
        print("   legacy signed in ->", q.url)
        await b.close()

asyncio.run(main())
