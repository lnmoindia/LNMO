"""LNMO platform logo processing: remove the white tile/shadow, keep the eye white, trim, and emit icon sets."""
import io
import logging

import numpy as np
from PIL import Image
from scipy import ndimage

CORE_T = 60      # min distance-from-white that is certainly logo ink
EDGE_PX = 3      # anti-aliased fringe width searched around the ink


def _to_rgba(src: bytes) -> np.ndarray:
    im = Image.open(io.BytesIO(src))
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(bg, im)
    return np.asarray(im.convert("RGB")).astype(np.float32)


def _matte(rgb: np.ndarray):
    """Alpha by projecting each pixel onto the segment white→nearest-ink colour (no white halo)."""
    d = 255.0 - rgb.min(axis=2)
    core = d > CORE_T
    dist, (iy, ix) = ndimage.distance_transform_edt(~core, return_indices=True)
    fg = rgb[iy, ix]
    w_f, w_c = 255.0 - fg, 255.0 - rgb
    alpha = np.clip((w_c * w_f).sum(2) / np.maximum((w_f * w_f).sum(2), 1.0), 0, 1)
    alpha[dist > EDGE_PX] = 0
    alpha[core] = 1
    return core, alpha, fg


def _split_rows(core: np.ndarray):
    rows = np.where(core.any(1))[0]
    gaps = np.where(np.diff(rows) > 8)[0]
    if not len(gaps):
        return None
    g = gaps[np.argmax(np.diff(rows)[gaps])]
    return rows[0], rows[g], rows[g + 1], rows[-1]


def _crop(rgba: Image.Image, pad_frac=0.03):
    a = np.asarray(rgba)[..., 3]
    ys, xs = np.where(a > 4)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    pad = int(max(y1 - y0, x1 - x0) * pad_frac)
    return rgba.crop((max(0, x0 - pad), max(0, y0 - pad), min(rgba.width, x1 + pad), min(rgba.height, y1 + pad)))


def _resize(im: Image.Image, w: "int | None" = None, h: "int | None" = None):
    if w:
        h = round(im.height * w / im.width)
    else:
        w = round(im.width * h / im.height)
    return im.convert("RGBa").resize((w, h), Image.LANCZOS).convert("RGBA")


def _square(mark: Image.Image, size: int, fill_frac: float, bg=None):
    canvas = Image.new("RGBA", (size, size), bg or (0, 0, 0, 0))
    inner = int(size * fill_frac)
    m = _resize(mark, w=inner) if mark.width >= mark.height else _resize(mark, h=inner)
    canvas.alpha_composite(m, ((size - m.width) // 2, (size - m.height) // 2))
    return canvas


def _png(im: Image.Image) -> bytes:
    b = io.BytesIO()
    im.save(b, "PNG", optimize=True)
    return b.getvalue()


def _svg_mark(rgb, core, filled, top, bot):
    """Vector trace of the mark: potrace body outline + rainbow gradient, fitted circles for the eye."""
    import potrace
    sub = slice(top, bot + 1)
    ys, xs = np.where(filled[sub])
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    crop = (slice(y0, y1 + 1), slice(x0, x1 + 1))
    cols = rgb[sub][crop]
    lum = cols.mean(2)
    fm = filled[sub][crop]
    white_in, _ = ndimage.label(fm & ~core[sub][crop])
    eye_lbl = np.argmax(np.bincount(white_in.ravel())[1:]) + 1
    inner = ndimage.binary_fill_holes(white_in == eye_lbl)
    iy, ix = np.where(inner)
    cx, cy = ix.mean(), iy.mean()
    r_in = np.sqrt(inner.sum() / np.pi)
    top_ink = np.where(fm[:, int(round(cx))])[0].min()
    r_out = cy - top_ink
    yy, xx = np.mgrid[:fm.shape[0], :fm.shape[1]]
    eye_disc = (xx - cx) ** 2 + (yy - cy) ** 2 <= (r_out + 1.5) ** 2
    body_only = fm & ~eye_disc
    plist = potrace.Bitmap(~body_only).trace(turdsize=20, alphamax=1.0, opticurve=True, opttolerance=0.2)

    def pt(p):
        return f"{p[0] if isinstance(p, tuple) else p.x:.1f},{p[1] if isinstance(p, tuple) else p.y:.1f}"
    d = []
    for curve in plist:
        d.append(f"M{pt(curve.start_point)}")
        for s in curve.segments:
            d.append(f"L{pt(s.c)}L{pt(s.end_point)}" if s.is_corner else f"C{pt(s.c1)} {pt(s.c2)} {pt(s.end_point)}")
        d.append("Z")
    stops = []
    bx = np.where(body_only.any(0))[0]
    bx0, bx1 = bx.min(), bx.max() - 4
    for i in range(9):
        sx = int(bx0 + i / 8 * (bx1 - bx0))
        band = body_only[:, max(0, sx - 3):sx + 4]
        px = cols[:, max(0, sx - 3):sx + 4][band]
        if len(px):
            r, g, b = np.median(px, 0).astype(int)
            stops.append(f'<stop offset="{i / 8:.3f}" stop-color="#{r:02x}{g:02x}{b:02x}"/>')
    pupil_l, _ = ndimage.label(inner & (lum < 90))
    pl = np.argmax(np.bincount(pupil_l.ravel())[1:]) + 1
    pupil = ndimage.binary_fill_holes(pupil_l == pl)
    py, px_ = np.where(pupil)
    pcx, pcy, pr = px_.mean(), py.mean(), np.sqrt(len(px_) / np.pi)
    hl = pupil & (lum > 200)
    hy, hx = np.where(hl)
    ring_px = cols[eye_disc & ~inner & _magenta(cols)]
    ring = np.median(ring_px, 0).astype(int)
    pup = np.median(cols[pupil & (lum < 90)], 0).astype(int)

    def hex_(c):
        return f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}"
    hl_svg = f'<circle cx="{hx.mean():.1f}" cy="{hy.mean():.1f}" r="{np.sqrt(len(hx) / np.pi):.1f}" fill="#ffffff"/>' if len(hx) else ""
    W, H = x1 - x0 + 1, y1 - y0 + 1
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">'
            f'<defs><linearGradient id="lnmoG" x1="{bx0}" y1="0" x2="{bx1}" y2="0" gradientUnits="userSpaceOnUse">{"".join(stops)}</linearGradient></defs>'
            f'<path d="{" ".join(d)}" fill="url(#lnmoG)" fill-rule="evenodd"/>'
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r_out:.1f}" fill="{hex_(ring)}"/>'
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r_in:.1f}" fill="#ffffff"/>'
            f'<circle cx="{pcx:.1f}" cy="{pcy:.1f}" r="{pr:.1f}" fill="{hex_(pup)}"/>{hl_svg}</svg>')


def _magenta(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return (r - g > 50) & (b - g > 30) & (r > 60)


def process_logo(src: bytes) -> dict:
    """Return {filename: bytes} for the full logo, mark-only and icon sets."""
    rgb = _to_rgba(src)
    h0, w0 = rgb.shape[:2]
    if max(h0, w0) < 2600:  # 2x supersampled master → smoother edges once downscaled
        rgb = np.asarray(Image.fromarray(rgb.astype(np.uint8)).resize((w0 * 2, h0 * 2), Image.LANCZOS)).astype(np.float32)
    core, alpha, fg = _matte(rgb)
    split = _split_rows(core)
    filled = core.copy()
    if split:
        top, mark_bot, text_top, _ = split
        m = slice(top, mark_bot + 1)
        filled[m] = ndimage.binary_fill_holes(core[m])  # protect enclosed eye white + pupil highlight
    a = np.where(filled & ~core, 1.0, alpha)
    a = ndimage.gaussian_filter(a, 0.9)  # soften stair-steps on the outer edge
    col = np.where(filled[..., None], rgb, fg)
    rgba = np.dstack([col, a * 255]).clip(0, 255).astype(np.uint8)
    full_img = Image.fromarray(rgba, "RGBA")
    full = _crop(full_img)
    out = {}
    for s, w in (("", 256), ("@2x", 512), ("@3x", 768)):
        out[f"lnmo-logo{s}.png"] = _png(_resize(full, w=w))
    if split:
        cut = (mark_bot + text_top) // 2
        mark = _crop(full_img.crop((0, 0, full_img.width, cut)), pad_frac=0.02)
        try:
            out["lnmo-mark.svg"] = _svg_mark(rgb, core, filled, top, mark_bot).encode()
        except (ValueError, IndexError, ImportError) as e:  # vector trace is best-effort
            logging.getLogger("lnmo").warning("logo svg trace skipped: %s", e)
    else:
        mark = full
    for s, w in (("", 128), ("@2x", 256), ("@3x", 384)):
        out[f"lnmo-mark{s}.png"] = _png(_resize(mark, w=w))
    ico = _square(mark, 256, 0.96)
    b = io.BytesIO()
    ico.save(b, "ICO", sizes=[(16, 16), (32, 32), (48, 48)])
    out["favicon.ico"] = b.getvalue()
    out["apple-touch-icon.png"] = _png(_square(mark, 180, 0.80, (255, 255, 255, 255)).convert("RGB"))
    out["icon-192.png"] = _png(_square(mark, 192, 0.92))
    out["icon-512.png"] = _png(_square(mark, 512, 0.92))
    out["icon-maskable-512.png"] = _png(_square(mark, 512, 0.62, (255, 255, 255, 255)))
    return out
