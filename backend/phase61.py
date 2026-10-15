# Phase 61: upload hardening + diagnostics, profile photos (resized, signed URLs), class teacher for parents,
# chat-by-child, submission detail / review / redo with attempt history (homework + assignments).
import asyncio
import hashlib
import hmac
import io
import os
import uuid

from fastapi import Body, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response

import server as S

api, db = S.api, S.db
MAX_BODY_MB = 25
SHRINK_SIDE, SHRINK_Q, SHRINK_OVER = 2000, 85, 1_500_000
IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
PHOTO_FULL, PHOTO_THUMB = 512, 128


# ---------------- 1) uploads ----------------
def _shrink(data: bytes, ctype: str, keep_type=False):
    """Downscale big phone photos (EXIF-rotated) to ≤2000px JPEG. Non-images / undecodable files pass through."""
    if (ctype or "").lower() not in IMAGE_TYPES:
        return data, ctype
    try:
        from PIL import Image, ImageOps
        im = Image.open(io.BytesIO(data))
        if len(data) <= SHRINK_OVER and max(im.size) <= SHRINK_SIDE:
            return data, ctype
        im = ImageOps.exif_transpose(im)
        im.thumbnail((SHRINK_SIDE, SHRINK_SIDE))
        if keep_type and ctype in ("image/png", "image/webp"):
            out = io.BytesIO()
            im.save(out, format="PNG" if ctype == "image/png" else "WEBP", optimize=True)
            return out.getvalue(), ctype
        if im.mode != "RGB":
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.convert("RGBA").split()[-1]) if im.mode in ("RGBA", "LA", "P") else bg.paste(im)
            im = bg
        out = io.BytesIO()
        im.save(out, format="JPEG", quality=SHRINK_Q, optimize=True)
        return out.getvalue(), "image/jpeg"
    except Exception:
        return data, ctype


async def shrink_upload(data, ctype, keep_type=False):
    return await asyncio.to_thread(_shrink, data, ctype, keep_type)


@S.app.middleware("http")
async def _body_limit(request: Request, call_next):
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > MAX_BODY_MB * 1024 * 1024:
        return JSONResponse(status_code=413, content={"detail": f"Upload too large — the limit is {MAX_BODY_MB} MB per request. "
                                                                "Photos are resized automatically; split large PDFs.", "code": "PAYLOAD_TOO_LARGE",
                                                      "max_mb": MAX_BODY_MB})
    return await call_next(request)


@S.app.exception_handler(Exception)
async def _json_500(request: Request, exc: Exception):
    S.logger.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong on the server — please try again.", "code": "SERVER_ERROR"})


@api.get("/diag/uploads")
async def diag_uploads(user: dict = Depends(S.require_roles("platform_admin", "institution_admin"))):
    import time
    out = {"pid": os.getpid(), "node": __import__("realtime").NODE, "max_body_mb": MAX_BODY_MB,
           "limits_mb": {"chat_attachment_pdf": 5, "fee_proof": 5, "homework_file": S.HW_MAX_MB, "scan_photo": 15},
           "images_auto_resized_to_px": SHRINK_SIDE, "libs": {}, "storage": {}}
    for mod in ("cv2", "numpy", "PIL", "reportlab"):
        try:
            m = __import__(mod)
            out["libs"][mod] = {"ok": True, "version": getattr(m, "__version__", "")}
        except Exception as e:
            out["libs"][mod] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}
    out["scanner_ready"] = all(out["libs"][m]["ok"] for m in ("cv2", "numpy", "PIL", "reportlab"))
    out["storage"]["key_configured"] = bool(os.environ.get("EMERGENT_LLM_KEY"))
    t = time.time()
    try:
        path = f"lnmo/diag/{uuid.uuid4()}.txt"
        await S._aput(path, b"ok", "text/plain")
        data, _ = await asyncio.to_thread(S._get_object, path)
        out["storage"].update(ok=data == b"ok", round_trip_ms=int((time.time() - t) * 1000))
    except Exception as e:
        out["storage"].update(ok=False, error=f"{type(e).__name__}: {e}"[:300], round_trip_ms=int((time.time() - t) * 1000))
    out["ws_local_users"] = len(__import__("realtime").hub.conns)
    return out


# ---------------- 5) profile photos ----------------
def _sig(kind, oid, ver, size):
    return hmac.new(S.JWT_SECRET.encode(), f"photo:{kind}:{oid}:{ver}:{size}".encode(), hashlib.sha256).hexdigest()[:32]


def _ver(doc):
    return doc.get("photo_ver") or hashlib.sha1((doc.get("photo_path") or "").encode()).hexdigest()[:10]


def photo_urls(kind, doc):
    """{photo_url, thumb_url}: signed, cookie-free URLs (usable directly by <img>/<Image>). kind: 'u' user | 's' student."""
    if not doc or not doc.get("photo_path"):
        return {"photo_url": None, "thumb_url": None}
    base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    v = _ver(doc)
    mk = lambda size: f"{base}/api/media/photo/{kind}/{doc['id']}/{v}/{size}.jpg?sig={_sig(kind, doc['id'], v, size)}"  # noqa: E731
    return {"photo_url": mk("full"), "thumb_url": mk("thumb")}


async def user_photo(uid):
    u = await db.users.find_one({"id": uid}, {"_id": 0, "id": 1, "photo_path": 1, "photo_ver": 1, "role": 1, "student_id": 1}) if uid else None
    if u and u.get("role") == "student" and not u.get("photo_path") and u.get("student_id"):
        st = await db.students.find_one({"id": u["student_id"]}, {"_id": 0, "id": 1, "photo_path": 1, "photo_ver": 1})
        if st and st.get("photo_path"):
            return photo_urls("s", st)
    return photo_urls("u", u)


@api.get("/media/photo/{kind}/{oid}/{ver}/{size}.jpg")
async def media_photo(kind: str, oid: str, ver: str, size: str, sig: str = ""):
    if kind not in ("u", "s") or size not in ("full", "thumb") or not hmac.compare_digest(sig, _sig(kind, oid, ver, size)):
        raise HTTPException(status_code=404, detail="Not found")
    doc = await (db.users if kind == "u" else db.students).find_one({"id": oid}, {"_id": 0})
    if not doc or not doc.get("photo_path"):
        raise HTTPException(status_code=404, detail="No photo")
    path = doc.get("photo_thumb_path") if size == "thumb" and doc.get("photo_thumb_path") else doc["photo_path"]
    try:
        data, ctype = await asyncio.to_thread(S._get_object, path)
    except Exception:
        raise HTTPException(status_code=404, detail="No photo")
    return Response(content=data, media_type=doc.get("photo_type") or ctype or "image/jpeg",
                    headers={"Cache-Control": "public, max-age=86400, immutable"})


def _square(data, side):
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    im = ImageOps.fit(im, (side, side), method=Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, format="JPEG", quality=86, optimize=True)
    return out.getvalue()


async def _store_photo(prefix, file: UploadFile):
    if (file.content_type or "").lower() not in IMAGE_TYPES | {"image/heic", "image/heif"}:
        raise HTTPException(status_code=400, detail="Please upload a JPG, PNG or WebP image")
    raw = await file.read()
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Photo must be under 20 MB")
    try:
        full, thumb = await asyncio.to_thread(_square, raw, PHOTO_FULL), await asyncio.to_thread(_square, raw, PHOTO_THUMB)
    except Exception:
        raise HTTPException(status_code=415, detail="Couldn't read that image — try a JPG or PNG photo")
    ver = uuid.uuid4().hex[:10]
    try:
        p1 = (await S._aput(f"{prefix}/{ver}-512.jpg", full, "image/jpeg"))["path"]
        p2 = (await S._aput(f"{prefix}/{ver}-128.jpg", thumb, "image/jpeg"))["path"]
    except Exception:
        raise HTTPException(status_code=502, detail="Photo storage is unavailable right now — try again shortly")
    return {"photo_path": p1, "photo_thumb_path": p2, "photo_type": "image/jpeg", "photo_ver": ver, "photo_updated_at": S.now_iso()}


async def _student_access(actor, sid, write=True):
    iid = actor.get("institution_id")
    st = await db.students.find_one({"id": sid, "institution_id": iid}, {"_id": 0})
    if not st:
        raise HTTPException(status_code=404, detail="Student not found")
    if actor["role"] == "institution_admin" or (actor["role"] == "student" and actor.get("student_id") == sid):
        return st
    scope = await S.principal_scope(actor)
    if scope and (scope["whole_school"] or st.get("class_name") in (scope["class_names"] or [])):
        return st
    raise HTTPException(status_code=403, detail="You can't change this student's photo")


async def _user_access(actor, uid):
    if uid == actor["id"]:
        return actor
    t = await db.users.find_one({"id": uid, "institution_id": actor.get("institution_id")}, {"_id": 0, "password_hash": 0})
    if not t:
        raise HTTPException(status_code=404, detail="User not found")
    if actor["role"] == "institution_admin" and t["role"] != "platform_admin":
        return t
    scope = await S.principal_scope(actor)
    if scope and t["role"] == "teacher" and await S._teacher_in_scope(scope, t):
        return t
    raise HTTPException(status_code=403, detail="You can't change this person's photo")


async def _set_student_photo(actor, st, file):
    fields = await _store_photo(f"lnmo/photos/students/{st['id']}", file)
    await db.students.update_one({"id": st["id"]}, {"$set": fields})
    await S.audit(actor, "upload_photo", "students", st["id"], f"{st.get('first_name', '')} {st.get('last_name', '')}".strip())
    return {"message": "Photo updated", **photo_urls("s", {**st, **fields})}


async def _set_user_photo(actor, t, file):
    if t["role"] == "student" and t.get("student_id"):
        return await _set_student_photo(actor, await db.students.find_one({"id": t["student_id"]}, {"_id": 0}), file)
    fields = await _store_photo(f"lnmo/photos/users/{t['id']}", file)
    await db.users.update_one({"id": t["id"]}, {"$set": fields})
    await S.audit(actor, "upload_photo", "users", t["id"], t.get("name"))
    return {"message": "Photo updated", **photo_urls("u", {**t, **fields})}


_UNSET = {"photo_path": "", "photo_thumb_path": "", "photo_type": "", "photo_ver": ""}


@api.post("/photos/me")
async def photo_me(file: UploadFile = File(...), user: dict = Depends(S.get_current_user)):
    return await _set_user_photo(user, user, file)


@api.delete("/photos/me")
async def photo_me_delete(user: dict = Depends(S.get_current_user)):
    col, oid = (db.students, user["student_id"]) if user["role"] == "student" and user.get("student_id") else (db.users, user["id"])
    await col.update_one({"id": oid}, {"$unset": _UNSET})
    await S.audit(user, "delete_photo", "students" if col is db.students else "users", oid, user.get("name"))
    return {"message": "Photo removed", "photo_url": None, "thumb_url": None}


@api.post("/photos/users/{uid}")
async def photo_user(uid: str, file: UploadFile = File(...), user: dict = Depends(S.get_current_user)):
    return await _set_user_photo(user, await _user_access(user, uid), file)


@api.delete("/photos/users/{uid}")
async def photo_user_delete(uid: str, user: dict = Depends(S.get_current_user)):
    t = await _user_access(user, uid)
    await db.users.update_one({"id": t["id"]}, {"$unset": _UNSET})
    await S.audit(user, "delete_photo", "users", t["id"], t.get("name"))
    return {"message": "Photo removed", "photo_url": None, "thumb_url": None}


@api.post("/photos/students/{sid}")
async def photo_student(sid: str, file: UploadFile = File(...), user: dict = Depends(S.get_current_user)):
    return await _set_student_photo(user, await _student_access(user, sid), file)


@api.delete("/photos/students/{sid}")
async def photo_student_delete(sid: str, user: dict = Depends(S.get_current_user)):
    st = await _student_access(user, sid)
    await db.students.update_one({"id": sid}, {"$unset": _UNSET})
    await S.audit(user, "delete_photo", "students", sid, f"{st.get('first_name', '')} {st.get('last_name', '')}".strip())
    return {"message": "Photo removed", "photo_url": None, "thumb_url": None}


async def add_photos(rows, kind, id_key="id"):
    """Bulk-decorate list rows with photo_url/thumb_url (one query)."""
    ids = [r.get(id_key) for r in rows if r.get(id_key)]
    if not ids:
        return rows
    col = db.users if kind == "u" else db.students
    docs = {d["id"]: d for d in await col.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "photo_path": 1, "photo_ver": 1}).to_list(len(ids))}
    for r in rows:
        r.update(photo_urls(kind, docs.get(r.get(id_key))))
    return rows


# ---------------- 2) class teacher for parents ----------------
async def class_teachers(iid, class_name, section):
    sec = await db.sections.find_one({"institution_id": iid, "class_name": class_name, "name": section}, {"_id": 0, "class_teacher_id": 1}) or {}
    ct = None
    if sec.get("class_teacher_id"):
        t = await db.users.find_one({"id": sec["class_teacher_id"], "status": {"$ne": "inactive"}}, {"_id": 0, "id": 1, "name": 1, "photo_path": 1, "photo_ver": 1})
        if t:
            ct = {"id": t["id"], "name": t.get("name"), **photo_urls("u", t)}
    subj = {}
    for a in await db.teacher_assignments.find({"institution_id": iid, "class_name": class_name, "section": {"$in": [section, ""]}}, {"_id": 0}).to_list(100):
        if a.get("teacher_id") and a.get("subject"):
            subj.setdefault(a["subject"], a["teacher_id"])
    users = {u["id"]: u for u in await db.users.find({"id": {"$in": list(subj.values())}}, {"_id": 0, "id": 1, "name": 1, "photo_path": 1, "photo_ver": 1}).to_list(100)}
    teachers = [{"subject": s, "id": tid, "name": users[tid].get("name"), **photo_urls("u", users[tid])}
                for s, tid in sorted(subj.items()) if tid in users]
    return {"class_teacher": ct, "subject_teachers": teachers}


async def decorate_entries(entries):
    """Timetable entries → + teacher_photo_url / teacher_thumb_url."""
    ids = list({e.get("teacher_id") for e in entries if e.get("teacher_id")})
    docs = {d["id"]: d for d in await db.users.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "photo_path": 1, "photo_ver": 1}).to_list(200)}
    for e in entries:
        p = photo_urls("u", docs.get(e.get("teacher_id")))
        e["teacher_photo_url"], e["teacher_thumb_url"] = p["photo_url"], p["thumb_url"]
    return entries


# ---------------- 6) submissions: detail, review, redo, attempts ----------------
KINDS = {"homework": ("homework", "homework_submissions", "homework_id", "homework"),
         "assignments": ("assignments", "assignment_submissions", "assignment_id", "assignment")}
STATES = ("submitted", "late", "redo_requested", "reviewed", "not_submitted")


def _kind(kind):
    if kind not in KINDS:
        raise HTTPException(status_code=404, detail="Unknown kind — use homework or assignments")
    return KINDS[kind]


def state_of(sub):
    if not sub:
        return "not_submitted"
    return {"redo": "redo_requested", "verified": "reviewed"}.get(sub.get("status"), "submitted")


async def _can_review(user, item):
    if user["role"] == "teacher" and not await S.active_principal(user):
        return item.get("teacher_id") == user["id"]
    if user["role"] in ("teacher", "institution_admin"):
        try:
            await S.guard_principal_class(user, item["class_name"])
            return True
        except HTTPException:
            return False
    return False


async def _load(kind, sub_id, user):
    icol, scol, fk, _ = _kind(kind)
    iid = user["institution_id"]
    sub = await db[scol].find_one({"id": sub_id, "institution_id": iid}, {"_id": 0})
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    item = await db[icol].find_one({"id": sub[fk], "institution_id": iid}, {"_id": 0})
    reviewer = await _can_review(user, item)
    own = (user["role"] == "student" and user.get("student_id") == sub["student_id"]) or \
          (user["role"] == "parent" and sub["student_id"] in (user.get("student_ids") or []))
    if not (reviewer or own):
        raise HTTPException(status_code=403, detail="Forbidden")
    return item, sub, reviewer


def _files(kind, sub_id, atts, attempt=None):
    q = f"?attempt={attempt}" if attempt else ""
    return [{"idx": i, "name": a.get("name"), "type": a.get("type"), "size": a.get("size"),
             "url": f"/api/submissions/{kind}/{sub_id}/files/{i}{q}", "is_image": (a.get("type") or "").startswith("image/"),
             "is_pdf": a.get("type") == "application/pdf"} for i, a in enumerate(atts or [])]


def _sub_view(kind, sub):
    return {k: sub.get(k) for k in ("id", "student_id", "submitted_at", "late", "note", "feedback", "score", "grade", "status",
                                    "verified_at", "verified_by", "redo_due_date", "redo_requested_at")} | {
        "state": state_of(sub), "attempt": sub.get("version", 1), "attempts_count": len(sub.get("attempts") or []) + 1,
        "attachments": _files(kind, sub["id"], sub.get("attachments"))}


@api.get("/{kind}/{item_id}/submission-board")
async def submission_board(kind: str, item_id: str, filter: str = "", user: dict = Depends(S.get_current_user)):
    icol, scol, fk, _ = _kind(kind)
    iid = user["institution_id"]
    item = await db[icol].find_one({"id": item_id, "institution_id": iid}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    if not await _can_review(user, item):
        raise HTTPException(status_code=403, detail="Forbidden")
    studs = await db.students.find({"institution_id": iid, "class_name": item["class_name"], "section": item.get("section"),
                                    "status": {"$ne": "inactive"}}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1,
                                                                     "admission_no": 1, "photo_path": 1, "photo_ver": 1}).to_list(2000)
    subs = {s["student_id"]: s for s in await db[scol].find({fk: item_id, "institution_id": iid}, {"_id": 0, "attempts": 0}).to_list(5000)}
    rows = []
    for st in studs:
        s = subs.get(st["id"])
        rows.append({"student_id": st["id"], "student_name": f"{st.get('first_name', '')} {st.get('last_name', '')}".strip(),
                     "admission_no": st.get("admission_no"), **photo_urls("s", st), "submission_id": s and s["id"],
                     "state": state_of(s), "late": bool(s and s.get("late")), "attempt": s.get("version", 1) if s else 0,
                     "submitted_at": s and s.get("submitted_at"), "score": s and s.get("score"), "feedback": s and s.get("feedback")})
    counts = {k: 0 for k in STATES}
    for r in rows:
        counts[r["state"]] += 1
        if r["late"] and r["state"] != "not_submitted":
            counts["late"] += 1
    if filter:
        if filter not in STATES:
            raise HTTPException(status_code=400, detail=f"filter must be one of {', '.join(STATES)}")
        if filter == "late":
            rows = [r for r in rows if r["late"] and r["state"] != "not_submitted"]
        else:
            rows = [r for r in rows if r["state"] == filter]
    rows.sort(key=lambda r: (STATES.index(r["state"]) if r["state"] in STATES else 9, r["student_name"]))
    return {"item": {k: item.get(k) for k in ("id", "title", "subject", "class_name", "section", "due_date", "status", "max_marks")},
            "kind": kind, "counts": {**counts, "all": len(studs)}, "rows": rows}


@api.get("/submissions/{kind}/{sub_id}")
async def submission_detail(kind: str, sub_id: str, user: dict = Depends(S.get_current_user)):
    item, sub, reviewer = await _load(kind, sub_id, user)
    st = await db.students.find_one({"id": sub["student_id"]}, {"_id": 0}) or {}
    rv = None
    if sub.get("verified_by"):
        u = await db.users.find_one({"id": sub["verified_by"]}, {"_id": 0, "name": 1})
        rv = (u or {}).get("name")
    attempts = [{"attempt": a.get("attempt"), "submitted_at": a.get("submitted_at"), "late": a.get("late"), "note": a.get("note"),
                 "status": a.get("status"), "state": state_of(a), "feedback": a.get("feedback"), "score": a.get("score"),
                 "reviewed_at": a.get("verified_at"), "redo_due_date": a.get("redo_due_date"),
                 "attachments": _files(kind, sub_id, a.get("attachments"), a.get("attempt"))}
                for a in sorted(sub.get("attempts") or [], key=lambda a: a.get("attempt") or 0, reverse=True)]
    return {"kind": kind, "item": {k: item.get(k) for k in ("id", "title", "subject", "class_name", "section", "due_date", "status", "max_marks", "instructions")},
            "student": {"id": st.get("id"), "name": f"{st.get('first_name', '')} {st.get('last_name', '')}".strip(),
                        "admission_no": st.get("admission_no"), "class_name": st.get("class_name"), "section": st.get("section"), **photo_urls("s", st)},
            "submission": {**_sub_view(kind, sub), "reviewed_by_name": rv}, "previous_attempts": attempts,
            "can_review": reviewer, "supports_marks": kind == "assignments" or bool(item.get("max_marks"))}


@api.get("/submissions/{kind}/{sub_id}/files/{idx}")
async def submission_file(kind: str, sub_id: str, idx: int, attempt: int = 0, user: dict = Depends(S.get_current_user)):
    _, sub, _ = await _load(kind, sub_id, user)
    atts = sub.get("attachments") or []
    if attempt and attempt != sub.get("version", 1):
        a = next((x for x in sub.get("attempts") or [] if x.get("attempt") == attempt), None)
        if not a:
            raise HTTPException(status_code=404, detail="Attempt not found")
        atts = a.get("attachments") or []
    if idx < 0 or idx >= len(atts):
        raise HTTPException(status_code=404, detail="File not found")
    f = atts[idx]
    try:
        data, ctype = await asyncio.to_thread(S._get_object, f["path"])
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")
    name = (f.get("name") or "file").replace('"', "")
    return Response(content=data, media_type=f.get("type") or ctype, headers={"Content-Disposition": f'inline; filename="{name}"',
                                                                               "Cache-Control": "private, max-age=300"})


async def _tell(iid, item, sub, ntype, title, body):
    su = await db.users.find_one({"institution_id": iid, "role": "student", "student_id": sub["student_id"]}, {"_id": 0, "id": 1})
    for uid in ([su["id"]] if su else []) + await S._student_parent_ids(iid, sub["student_id"]):
        await S._notify(iid, uid, ntype, title, body, item["id"])


@api.post("/submissions/{kind}/{sub_id}/review")
async def submission_review(kind: str, sub_id: str, payload: dict = Body(default={}), user: dict = Depends(S.get_current_user)):
    item, sub, reviewer = await _load(kind, sub_id, user)
    if not reviewer:
        raise HTTPException(status_code=403, detail="Only the teacher of this item can review it")
    _, scol, _, label = KINDS[kind]
    score = payload.get("score")
    if score not in (None, ""):
        try:
            score = float(score)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Marks must be a number")
        mx = item.get("max_marks")
        if score < 0 or (mx and score > mx):
            raise HTTPException(status_code=400, detail=f"Marks must be between 0 and {mx}")
    else:
        score = None
    fb = str(payload.get("feedback") or "").strip()[:2000]
    await db[scol].update_one({"id": sub_id}, {"$set": {"status": "verified", "feedback": fb, "score": score, "grade": payload.get("grade"),
                                                        "verified_by": user["id"], "verified_at": S.now_iso()}})
    await S.audit(user, f"{label}_reviewed", scol, sub_id, item["title"])
    await _tell(user["institution_id"], item, sub, f"{label}_verified", f"{label.title()} reviewed ✓: {item['title']}",
                fb or (f"Marks: {score:g}" + (f"/{item['max_marks']}" if item.get("max_marks") else "") if score is not None else item.get("subject") or ""))
    return await submission_detail(kind, sub_id, user)


@api.post("/submissions/{kind}/{sub_id}/redo")
async def submission_redo(kind: str, sub_id: str, payload: dict = Body(...), user: dict = Depends(S.get_current_user)):
    item, sub, reviewer = await _load(kind, sub_id, user)
    if not reviewer:
        raise HTTPException(status_code=403, detail="Only the teacher of this item can request a redo")
    fb = str(payload.get("feedback") or "").strip()[:2000]
    if not fb:
        raise HTTPException(status_code=400, detail="Tell the student what to fix — feedback is required for a redo")
    due = str(payload.get("due_date") or "").strip() or None
    if due and due < S.now_iso()[:10]:
        raise HTTPException(status_code=400, detail="The new due date can't be in the past")
    _, scol, _, label = KINDS[kind]
    await db[scol].update_one({"id": sub_id}, {"$set": {"status": "redo", "feedback": fb, "score": None, "redo_due_date": due,
                                                        "redo_requested_at": S.now_iso(), "verified_by": user["id"], "verified_at": S.now_iso()}})
    await S.audit(user, f"{label}_redo", scol, sub_id, item["title"])
    await _tell(user["institution_id"], item, sub, f"{label}_redo", f"Redo requested: {item['title']}", fb[:140])
    return await submission_detail(kind, sub_id, user)


def archive_attempt(existing):
    """Snapshot of the current attempt, kept read-only in `attempts` when a redo is resubmitted."""
    return {k: existing.get(k) for k in ("attachments", "note", "submitted_at", "late", "status", "feedback", "score", "grade",
                                          "verified_by", "verified_at", "redo_due_date")} | {"attempt": existing.get("version", 1)}


# ---------------- startup ----------------
@S.app.on_event("startup")
async def _phase61_startup():
    from realtime import hub
    await hub.start(db)
