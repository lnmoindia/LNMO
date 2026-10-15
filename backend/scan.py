"""Document scanner (no AI): four-point perspective warp + enhance filters + multi-page PDF.

POST /api/scan/process        multipart: file, corners (JSON [[x,y]*4] in image px), img_w/img_h (optional, the
                              size the client measured the corners on), mode (original|document|grayscale),
                              rotation (0|90|180|270) → {id, width, height, size, preview (data URL)}
GET  /api/scan/pages/{id}.jpg full processed page (owner only)
POST /api/scan/pdf            JSON {page_ids:[...], name?} → {id, pages, size, name}; pages are consumed
GET  /api/scan/files/{id}.pdf download the combined PDF (owner only)
DELETE /api/scan/files/{id}   delete after it was attached
Temp docs live in Mongo `scan_temp` with a 24h TTL index (auto cleanup).
"""
import base64
import io
import json
import re
import uuid
from datetime import datetime, timezone

import cv2
import numpy as np
from bson import Binary
from fastapi import Body, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from PIL import Image, ImageOps
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

import server as S

MAX_BYTES = 15 * 1024 * 1024
MAX_SIDE = 2000
MAX_PAGES = 20
SCAN_RATE_MAX = 60  # requests per user per minute
MODES = {"original", "document", "grayscale"}


def _now():
    return datetime.now(timezone.utc)


def _rate(user):
    if not S._rate_ok("scan", user["id"], SCAN_RATE_MAX, 60):
        raise HTTPException(status_code=429, detail="Too many scan requests — wait a minute and try again.")


def _order(pts: np.ndarray) -> np.ndarray:
    """tl, tr, br, bl regardless of the order the client sent."""
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], dtype="float32")


def warp(img: np.ndarray, corners) -> np.ndarray:
    pts = _order(np.array(corners, dtype="float32"))
    tl, tr, br, bl = pts
    w = int(round(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))))
    h = int(round(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))))
    if w < 20 or h < 20:
        raise HTTPException(status_code=400, detail="The selected area is too small — drag the corners further apart.")
    dst = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype="float32")
    m = cv2.getPerspectiveTransform(pts, dst)
    return cv2.warpPerspective(img, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def enhance(img: np.ndarray, mode: str) -> np.ndarray:
    if mode == "original":
        return img
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if mode == "grayscale":
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    # document: remove shadows/uneven light (divide by a heavily blurred background estimate), then a local
    # adaptive threshold for crisp strokes; min() keeps big dark areas (headings, diagrams) dark.
    k = max(31, (min(gray.shape) // 6) | 1)
    bg = cv2.GaussianBlur(cv2.dilate(gray, np.ones((9, 9), np.uint8)), (k, k), 0)
    norm = cv2.divide(gray, bg, scale=255)
    block = max(31, (min(gray.shape) // 30) | 1)
    th = cv2.adaptiveThreshold(norm, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, 10)
    out = cv2.min(norm, th)
    lo, hi = np.percentile(out, 1), np.percentile(out, 60)
    out = np.clip((out.astype(np.float32) - lo) * 255.0 / max(1.0, hi - lo), 0, 255).astype(np.uint8)
    return cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)


_ROT = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}


def _rotate(img: np.ndarray, rot: int) -> np.ndarray:
    return cv2.rotate(img, _ROT[rot]) if rot in _ROT else img


def _fit(img: np.ndarray, side: int) -> np.ndarray:
    h, w = img.shape[:2]
    f = side / max(h, w)
    return cv2.resize(img, (int(w * f), int(h * f)), interpolation=cv2.INTER_AREA) if f < 1 else img


def _jpeg(img: np.ndarray, q: int) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q, cv2.IMWRITE_JPEG_OPTIMIZE, 1])
    if not ok:
        raise HTTPException(status_code=500, detail="Couldn't encode the page")
    return buf.tobytes()


def _decode(raw: bytes) -> np.ndarray:
    try:
        pil = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    except Exception:
        raise HTTPException(status_code=415, detail="Unsupported image — use a JPG, PNG or WEBP photo.")
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


async def _ensure_ttl():
    await S.db.scan_temp.create_index("created_at", expireAfterSeconds=86400)


@S.app.on_event("startup")
async def _scan_startup():
    try:
        await _ensure_ttl()
    except Exception as e:  # pragma: no cover
        S.logger.warning("scan_temp TTL index: %s", e)


@S.api.post("/scan/process")
async def scan_process(file: UploadFile = File(...), corners: str = Form(""), img_w: float = Form(0), img_h: float = Form(0),
                       mode: str = Form("document"), rotation: int = Form(0), user: dict = Depends(S.get_current_user)):
    _rate(user)
    raw = await file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="That photo is larger than 15 MB — take it again at a lower resolution.")
    if mode not in MODES:
        raise HTTPException(status_code=400, detail="mode must be original, document or grayscale")
    if rotation not in (0, 90, 180, 270):
        raise HTTPException(status_code=400, detail="rotation must be 0, 90, 180 or 270")
    img = _decode(raw)
    h, w = img.shape[:2]
    pts = None
    if corners.strip():
        try:
            pts = [[float(p[0]), float(p[1])] for p in json.loads(corners)]
            assert len(pts) == 4
        except Exception:
            raise HTTPException(status_code=400, detail="corners must be 4 [x, y] points")
        if img_w and img_h and (abs(img_w - w) > 1 or abs(img_h - h) > 1):  # client measured on a different size
            pts = [[x * w / img_w, y * h / img_h] for x, y in pts]
        pts = [[min(max(x, 0), w - 1), min(max(y, 0), h - 1)] for x, y in pts]
    out = warp(img, pts) if pts else img
    out = _rotate(enhance(_fit(out, MAX_SIDE), mode), rotation)
    data = _jpeg(out, 82)
    pid = str(uuid.uuid4())
    await S.db.scan_temp.insert_one({"id": pid, "kind": "page", "user_id": user["id"], "data": Binary(data), "size": len(data),
                                     "width": out.shape[1], "height": out.shape[0], "mode": mode, "created_at": _now()})
    prev = _jpeg(_fit(out, 700), 70)
    return {"id": pid, "width": out.shape[1], "height": out.shape[0], "size": len(data), "mode": mode, "rotation": rotation,
            "preview": "data:image/jpeg;base64," + base64.b64encode(prev).decode()}


async def _own(fid: str, kind: str, user: dict):
    d = await S.db.scan_temp.find_one({"id": fid, "kind": kind, "user_id": user["id"]})
    if not d:
        raise HTTPException(status_code=404, detail="Scan expired or not found — scan the page again.")
    return d


@S.api.get("/scan/pages/{pid}.jpg")
async def scan_page(pid: str, user: dict = Depends(S.get_current_user)):
    d = await _own(pid, "page", user)
    return Response(content=bytes(d["data"]), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


def build_pdf(images: list) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle("Scanned document")
    margin = 18
    for data in images:
        im = Image.open(io.BytesIO(data))
        iw, ih = im.size
        size = landscape(A4) if iw > ih * 1.15 else A4
        c.setPageSize(size)
        pw, ph = size
        f = min((pw - 2 * margin) / iw, (ph - 2 * margin) / ih)
        dw, dh = iw * f, ih * f
        c.drawImage(ImageReader(io.BytesIO(data)), (pw - dw) / 2, (ph - dh) / 2, dw, dh)
        c.showPage()
    c.save()
    return buf.getvalue()


@S.api.post("/scan/pdf")
async def scan_pdf(payload: dict = Body(...), user: dict = Depends(S.get_current_user)):
    _rate(user)
    ids = [str(x) for x in (payload.get("page_ids") or [])][:MAX_PAGES + 1]
    if not ids:
        raise HTTPException(status_code=400, detail="Add at least one page")
    if len(ids) > MAX_PAGES:
        raise HTTPException(status_code=400, detail=f"A scan can have at most {MAX_PAGES} pages")
    pages = [await _own(i, "page", user) for i in ids]
    pdf = build_pdf([bytes(p["data"]) for p in pages])
    if len(pdf) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="The PDF is too large — remove a few pages.")
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", str(payload.get("name") or "Scan.pdf")).strip("_")[:80] or "Scan.pdf"
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    fid = str(uuid.uuid4())
    await S.db.scan_temp.insert_one({"id": fid, "kind": "pdf", "user_id": user["id"], "data": Binary(pdf), "size": len(pdf),
                                     "pages": len(pages), "name": name, "created_at": _now()})
    await S.db.scan_temp.delete_many({"id": {"$in": ids}, "kind": "page", "user_id": user["id"]})
    return {"id": fid, "pages": len(pages), "size": len(pdf), "name": name}


@S.api.get("/scan/files/{fid}.pdf")
async def scan_file(fid: str, user: dict = Depends(S.get_current_user)):
    d = await _own(fid, "pdf", user)
    return Response(content=bytes(d["data"]), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{d.get("name") or "Scan.pdf"}"'})


@S.api.delete("/scan/files/{fid}")
async def scan_file_delete(fid: str, user: dict = Depends(S.get_current_user)):
    await S.db.scan_temp.delete_many({"id": fid, "user_id": user["id"]})
    return {"ok": True}
