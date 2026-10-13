"""Phase 52: mobile portal shots scrolled to the substitute badge."""
import asyncio
from playwright.async_api import async_playwright
from common import PW, shot, login


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await (await b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True)).new_page()
        await login(pg, "aarav@sunrise-demo.in", PW, slug="sunrise")
        await pg.wait_for_timeout(3000)
        await pg.locator("[data-testid=portal-today]").scroll_into_view_if_needed()
        await pg.locator("[data-testid=portal-today-cover-7]").scroll_into_view_if_needed()
        await pg.evaluate("() => document.querySelector('[data-testid=portal-today]').scrollIntoView({block: 'center'})")
        await pg.wait_for_timeout(800)
        await shot(pg, "p52_student_today_covered_m")
        await login(pg, "parent.menon@sunrise-demo.in", PW, slug="sunrise")
        await pg.wait_for_timeout(3000)
        await pg.evaluate("() => document.querySelector('[data-testid=parent-today-p7]').scrollIntoView({block: 'end'})")
        await pg.evaluate("() => window.scrollBy(0, 120)")
        await pg.wait_for_timeout(800)
        await shot(pg, "p52_parent_today_covered_m")
        await b.close()

asyncio.run(main())
