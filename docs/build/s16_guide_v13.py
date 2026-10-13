"""v1.3: same guide content, new LNMO logo on the cover + header; re-render to the same PDF path."""
import asyncio
import base64
import re
from pathlib import Path
from playwright.async_api import async_playwright

B = Path("/app/docs/build")
OUT = Path("/app/docs/LNMO_Product_Guide.pdf")
mark = base64.b64encode(Path("/app/backend/static/brand/lnmo-mark@3x.png").read_bytes()).decode()
html = (B / "guide.html").read_text(encoding="utf-8")
cover_logo = (f'<div class="lnmo-brand" style="display:flex;align-items:center;gap:14px">'
              f'<img src="data:image/png;base64,{mark}" style="height:64px;width:auto"/>'
              f'<span style="font-size:30px;font-weight:800;letter-spacing:.02em;color:#fff">LNMO</span></div>')
html = re.sub(r'<div class="logo">L</div>|<div class="lnmo-brand".*?</span></div>', cover_logo, html, count=1, flags=re.S)
html = html.replace("Version 1.2 · October 2026", "Version 1.3 · October 2026")
small = base64.b64encode(Path("/app/backend/static/brand/lnmo-mark.png").read_bytes()).decode()
(B / "guide.html").write_text(html, encoding="utf-8")


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page()
        await pg.goto("file:///app/docs/build/guide.html")
        await pg.wait_for_timeout(1500)
        foot = '<div style="font-size:7.5px;color:#64748b;width:100%;padding:0 14mm;display:flex;justify-content:space-between;font-family:Arial"><span>LNMO School ERP — Product Guide · v1.3 · Oct 2026</span><span>Page <span class="pageNumber"></span> / <span class="totalPages"></span></span></div>'
        head = (f'<div style="width:100%;padding:0 14mm;display:flex;align-items:center;gap:4px;font-family:Arial;font-size:7.5px;color:#4f46e5;font-weight:bold;letter-spacing:.1em">'
                f'<img src="data:image/png;base64,{small}" style="height:9px;width:auto"/>LNMO</div>')
        await pg.pdf(path=str(OUT), format="A4", print_background=True, display_header_footer=True, header_template=head, footer_template=foot,
                     margin={"top": "18mm", "bottom": "16mm", "left": "14mm", "right": "14mm"})
        await pg.set_viewport_size({"width": 794, "height": 1123})
        await pg.screenshot(path="/app/docs/shots/guide_v13_cover.png")
        await b.close()
    print("pdf", OUT, OUT.stat().st_size // 1024, "KB")

asyncio.run(main())
