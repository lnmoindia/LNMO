"""Phase 54 screenshots + console-error check (Sunrise; LPGS login pages are read-only views)."""
import asyncio
from playwright.async_api import async_playwright
from common import BASE, PW, login

ERR = []


async def shot(page, name, full=False):
    await page.wait_for_timeout(900)
    await page.screenshot(path=f"/app/docs/shots/{name}.png", full_page=full)
    print("shot", name)


async def ctx(b, mobile):
    c = await b.new_context(viewport={"width": 390, "height": 844} if mobile else {"width": 1440, "height": 900},
                            device_scale_factor=2 if mobile else 1, is_mobile=mobile)
    p = await c.new_page()
    p.on("console", lambda m: m.type == "error" and ERR.append((p.url, m.text[:160])))
    p.on("pageerror", lambda e: ERR.append((p.url, str(e)[:160])))
    return p


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        for mobile in (False, True):
            sfx = "_m" if mobile else ""
            p = await ctx(b, mobile)
            await login(p, "parent.menon@sunrise-demo.in", PW, slug="sunrise")
            await p.wait_for_timeout(3500)
            print("parent landed", p.url)
            for k in ("home", "attendance", "fees", "timetable"):
                await p.goto(p.url.split("/parents")[0] + f"/parents/{k}" + ("?" + p.url.split("?")[1] if "?" in p.url else ""))
                await p.wait_for_timeout(3500)
                await shot(p, f"p54_parent_{k}{sfx}")
            if mobile:
                await p.click("[data-testid=portal-bnav-more]"); await p.wait_for_timeout(800)
                await shot(p, "p54_parent_more_m")
            s = await ctx(b, mobile)
            await login(s, "aarav@sunrise-demo.in", PW, slug="sunrise")
            await s.wait_for_timeout(3500)
            print("student landed", s.url)
            for k in ("dashboard", "notices", "exams"):
                await s.goto(f"{BASE}/portal/{k}"); await s.wait_for_timeout(3500)
                await shot(s, f"p54_student_{k}{sfx}")
            t = await ctx(b, mobile)
            await login(t, "lakshmi@sunrise-demo.in", PW, slug="sunrise")
            await t.wait_for_timeout(3500)
            if mobile:
                await t.click("[data-testid=mobile-sidebar-toggle]"); await t.wait_for_timeout(800)
            await shot(t, f"p54_teacher_header{sfx}")
            print("teacher title:", await t.title())
            for u, n in ((f"{BASE}/login?domain=lpgs.com", "p54_login_lpgs_domain"), (f"{BASE}/login/lpgs", "p54_login_lpgs_code")):
                g = await ctx(b, mobile)
                await g.goto(u); await g.wait_for_timeout(3500)
                print(n, "branded:", await g.locator("[data-testid=branded-login]").count())
                await shot(g, n + sfx)
        # old links
        p = await ctx(b, False)
        await login(p, "parent.menon@sunrise-demo.in", PW, slug="sunrise")
        await p.wait_for_timeout(2500)
        cid = p.url.split("child=")[1] if "child=" in p.url else ""
        await p.goto(f"{BASE}/parents?child={cid}&fees=1"); await p.wait_for_timeout(3000)
        print("old ?fees=1 ->", p.url.replace(BASE, ""))
        await p.goto(f"{BASE}/parents/attendance?child={cid}"); await p.wait_for_timeout(2500)
        await p.reload(); await p.wait_for_timeout(3000)
        print("refresh stays:", p.url.replace(BASE, ""), await p.locator("[data-testid=parent-attendance]").count())
        await p.go_back(); await p.wait_for_timeout(2500)
        print("back ->", p.url.replace(BASE, ""))
        await b.close()
    print("console errors:", len(ERR))
    for e in ERR[:12]:
        print("  ", e)

asyncio.run(main())
