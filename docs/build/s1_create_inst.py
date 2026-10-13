"""Step 1: Platform Manager creates the demo school through the REAL UI (screenshots along the way)."""
import asyncio
from playwright.async_api import async_playwright
from common import BASE, PA, ADMIN, shot, login


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await (await b.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)).new_page()
        await login(page, *PA, shot_name="pm_01_login")
        await page.goto(f"{BASE}/platform/dashboard")
        await shot(page, "pm_02_dashboard", wait=2500)
        await page.goto(f"{BASE}/platform/institutions")
        await page.wait_for_selector("[data-testid=add-record-btn]")
        await shot(page, "pm_03_institutions", [("[data-testid=add-record-btn]", "1 · Add institution")])
        await page.click("[data-testid=add-record-btn]")
        await page.wait_for_selector("[data-testid=form-dialog]")
        vals = {"name": "Sunrise Public School (Demo)", "code": "SPS", "domain": "sunrise-demo.in", "city": "Kochi",
                "contact_email": "office@sunrise-demo.in", "phone": "+91 98000 00100", "admin_name": "Anitha Varghese",
                "admin_email": ADMIN[0], "admin_password": ADMIN[1]}
        for k, v in vals.items():
            loc = page.locator(f"[data-testid=field-{k}]")
            if await loc.count():
                await loc.fill(v)
        if await page.locator("[data-testid=field-slug]").count():
            await page.locator("[data-testid=field-slug]").fill("sunrise")
        await shot(page, "pm_04_create_form", [("[data-testid=form-submit-btn]", "2 · Create")])
        await page.click("[data-testid=form-submit-btn]")
        await page.wait_for_timeout(2500)
        err = page.locator("[data-testid=form-error]")
        if await err.count():
            print("FORM ERROR", await err.inner_text())
        await shot(page, "pm_05_created")
        await b.close()

asyncio.run(main())
