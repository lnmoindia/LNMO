"""Admin's first login (empty school → setup wizard) before seeding."""
import asyncio
from playwright.async_api import async_playwright
from common import BASE, ADMIN, shot, login


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()
        await login(page, *ADMIN, slug="sunrise", shot_name="ad_01_login")
        await page.goto(f"{BASE}/app/setup")
        await shot(page, "ad_02_setup_wizard", wait=2500)
        await b.close()

asyncio.run(main())
