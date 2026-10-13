"""Phase 53 screenshots: presets removed from Academic Units, wizard presets, fee structure menu + year dropdown,
Settings → Login page card, branded login pages (Sunrise uploaded photo; LPGS default background — read-only)."""
import asyncio
from playwright.async_api import async_playwright
from common import ADMIN, BASE, login


async def shot(page, name, full=False):
    await page.wait_for_timeout(700)
    await page.screenshot(path=f"/app/docs/shots/{name}.png", full_page=full)
    print("shot", name)

SETUP = ("admin@sunrise-setup.in", "SetupDemo@2026")
TEST = ("admin@feesdemo.test", "admin123")


async def safe(name, coro):
    try:
        await coro
    except Exception as e:
        print("MISS", name, str(e)[:180])


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()

        async def units(creds, slug, name):
            await login(pg, *creds, slug=slug)
            await pg.goto(BASE + "/app/academic-units"); await pg.wait_for_timeout(3500)
            print(name, "preset buttons:", await pg.locator("[data-testid=apply-preset-compact]").count())
            await shot(pg, name)
        await safe("u1", units(ADMIN, "sunrise", "p53_units_after"))
        await safe("u2", units(TEST, "p50demo", "p53_units_after_test"))

        async def wizard():
            await login(pg, *SETUP, slug="sunrise-setup")
            await pg.goto(BASE + "/app/setup"); await pg.wait_for_timeout(3000)
            await pg.locator("[data-testid^=setup-step-]").nth(1).click(); await pg.wait_for_timeout(2000)
            await pg.locator("[data-testid=apply-preset-cards]").scroll_into_view_if_needed()
            await shot(pg, "p53_wizard_presets")
            await pg.click("[data-testid=apply-preset-k12]"); await pg.wait_for_timeout(3000)
            await shot(pg, "p53_wizard_preset_applied")
        await safe("wiz", wizard())

        async def fees():
            await login(pg, *ADMIN, slug="sunrise")
            await pg.goto(BASE + "/app/fees"); await pg.wait_for_timeout(3000)
            await pg.get_by_role("tab", name="Structures").click(); await pg.wait_for_timeout(2500)
            await pg.locator("[data-testid^=fee-structure-menu-]").first.click(); await pg.wait_for_timeout(1200)
            await shot(pg, "p53_structures_menu")
            await pg.keyboard.press("Escape"); await pg.wait_for_timeout(500)
            await pg.click("[data-testid=fee-structure-new-btn]"); await pg.wait_for_timeout(2000)
            await pg.fill("[data-testid=fee-structure-name]", "Transport fees 2026-27")
            await shot(pg, "p53_structure_year_dropdown")
            opts = await pg.locator("[data-testid=fee-structure-year] option").all_inner_texts()
            print("year options", opts)
            await pg.keyboard.press("Escape"); await pg.wait_for_timeout(500)
            await pg.goto(BASE + "/app/settings"); await pg.wait_for_timeout(3000)
            await pg.locator("[data-testid=login-page-card]").scroll_into_view_if_needed(); await pg.wait_for_timeout(1500)
            await pg.evaluate("() => window.scrollBy(0, -80)")
            await shot(pg, "p53_settings_login_card")
        await safe("fees", fees())

        for slug in ("sunrise", "lpgs"):
            ctx = await b.new_context(viewport={"width": 1440, "height": 900})
            d = await ctx.new_page()
            await d.goto(f"{BASE}/login/{slug}"); await d.wait_for_timeout(3500)
            await shot(d, f"p53_login_{slug}")
            m = await (await b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True)).new_page()
            await m.goto(f"{BASE}/login/{slug}"); await m.wait_for_timeout(3500)
            await shot(m, f"p53_login_{slug}_m")
        g = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()
        await g.goto(f"{BASE}/login/no-such-school"); await g.wait_for_timeout(3000)
        print("unknown code branded:", await g.locator("[data-testid=branded-login]").count())
        await shot(g, "p53_login_unknown")
        await b.close()

asyncio.run(main())
