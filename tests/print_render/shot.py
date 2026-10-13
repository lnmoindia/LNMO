import asyncio, sys
import pypdfium2 as pdfium
from playwright.async_api import async_playwright

tag = sys.argv[1]


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 794, "height": 1123})  # A4 @96dpi
        for n in ("defaulters", "monthly", "daybook"):
            await pg.goto(f"file:///app/tests/print_render/{n}_{tag}.html")
            await pg.emulate_media(media="print")
            await pg.screenshot(path=f"/app/tests/print_render/{n}_{tag}.png", full_page=True)
            await pg.pdf(path=f"/app/tests/print_render/{n}_{tag}_a4.pdf", format="A4", print_background=True)
        await b.close()
    pdf = pdfium.PdfDocument(f"/app/tests/print_render/receipt_{tag}.pdf")
    pdf[0].render(scale=1.6).to_pil().save(f"/app/tests/print_render/receipt_{tag}.png")
    for n in ("defaulters", "monthly", "daybook"):
        d = pdfium.PdfDocument(f"/app/tests/print_render/{n}_{tag}_a4.pdf")
        print(n, "A4 pages:", len(d))

asyncio.run(main())
