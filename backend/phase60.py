# Phase 60: bulk enrol from a bulk-run's "not enrolled" rows + single-use parent setup tokens (email-only parents).
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Body, Depends, HTTPException, Response

import phase59 as B
import server as S

api, db = S.api, S.db
SETUP_TTL_HOURS = 72


# ---------- Single-use setup tokens (hashed, 72h, invalidated on re-invite) ----------
def _h(token):
    return hashlib.sha256(token.encode()).hexdigest()


async def mint_setup_link(iid, uid):
    now = datetime.now(timezone.utc)
    await db.parent_setup_tokens.update_many({"user_id": uid, "used_at": None, "invalidated_at": None}, {"$set": {"invalidated_at": now.isoformat()}})
    token = secrets.token_urlsafe(32)
    await db.parent_setup_tokens.insert_one({"id": str(uuid.uuid4()), "institution_id": iid, "user_id": uid, "token_hash": _h(token),
                                             "created_at": now.isoformat(), "expires_at": (now + timedelta(hours=SETUP_TTL_HOURS)).isoformat(),
                                             "opened_at": None, "used_at": None, "invalidated_at": None})
    return f"{S.os.environ['PUBLIC_BASE_URL'].rstrip('/')}/setup/parent/{token}"


async def token_doc(token):
    t = await db.parent_setup_tokens.find_one({"token_hash": _h(token)}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=400, detail="This invite link is invalid or has expired")
    if t.get("used_at"):
        raise HTTPException(status_code=410, detail="This setup link has already been used — sign in with your email and password")
    if t.get("invalidated_at"):
        raise HTTPException(status_code=410, detail="This link was replaced by a newer invite — use the latest email from the school")
    if datetime.now(timezone.utc) > datetime.fromisoformat(t["expires_at"]):
        raise HTTPException(status_code=410, detail="This setup link has expired — ask the school to resend the invite")
    return t


def setup_status(p, tok):
    """invited / link_opened / expired / linked (completed)."""
    if not (p.get("invited") and p.get("must_change_password") and not p.get("pw_set_by_staff")):
        return "linked"
    if tok:
        if not tok.get("used_at") and not tok.get("invalidated_at") and datetime.now(timezone.utc) > datetime.fromisoformat(tok["expires_at"]):
            return "expired"
        if tok.get("opened_at"):
            return "link_opened"
    return "invited"


async def latest_tokens(uids):
    out = {}
    async for t in db.parent_setup_tokens.find({"user_id": {"$in": list(uids)}}, {"_id": 0}).sort("created_at", 1):
        out[t["user_id"]] = t
    return out


async def resolve_new_token(token):
    t = await token_doc(token)
    if not t.get("opened_at"):
        await db.parent_setup_tokens.update_one({"token_hash": t["token_hash"]}, {"$set": {"opened_at": S.now_iso()}})
    return t["user_id"], t


async def complete_new_token(token, response: Response, payload: dict):
    t = await token_doc(token)
    u = await db.users.find_one({"id": t["user_id"], "role": "parent"})
    if not u:
        raise HTTPException(status_code=404, detail="Account not found")
    pw = payload.get("password") or ""
    if not S._pw_strong(pw):
        raise HTTPException(status_code=400, detail=S.PW_RULE)
    sets = {"password_hash": S.hash_password(pw), "must_change_password": False, "setup_completed_at": S.now_iso(), "setup_method": "email_link"}
    name = (payload.get("name") or "").strip()
    if name:
        sets["name"] = name[:120]
    if payload.get("phone"):
        ph = S._norm_phone(payload["phone"])
        if len(ph) != 10:
            raise HTTPException(status_code=400, detail="Enter a 10-digit mobile number, or leave it blank")
        if ph != u.get("phone") and await db.users.find_one({"institution_id": u["institution_id"], "role": "parent", "phone": ph, "id": {"$ne": u["id"]}}):
            raise HTTPException(status_code=409, detail="That mobile number is already linked to another parent account — contact the school")
        sets["phone"] = ph
    claimed = await db.parent_setup_tokens.update_one({"token_hash": t["token_hash"], "used_at": None}, {"$set": {"used_at": S.now_iso()}})
    if not claimed.modified_count:
        raise HTTPException(status_code=410, detail="This setup link has already been used — sign in with your email and password")
    await db.users.update_one({"id": u["id"]}, {"$set": sets})
    u.update(sets)
    await S.audit({"id": u["id"], "email": u.get("email"), "role": "parent", "name": u.get("name")}, "parent_setup_complete", "users", u["id"],
                  f"{u.get('name')} · email link" + (" + phone" if sets.get("phone") else ""), u["institution_id"])
    access, refresh = S.make_tokens(u)
    S.set_auth_cookies(response, access, refresh)
    return await S.public_user(u)


# ---------- Bulk enrol from a run's "not enrolled" rows ----------
async def _run_or_404(user, rid):
    r = await db.bulk_runs.find_one({"id": rid, "institution_id": user["institution_id"]}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="Result not found")
    return r


async def _run_year(r):
    if r["kind"] == "fee_apply":
        st = await db.fee_structures.find_one({"id": r["ref_id"]}, {"_id": 0, "academic_year": 1, "name": 1})
        if st:
            return st["academic_year"]
    y = await db.academic_years.find_one({"institution_id": r["institution_id"], "is_current": True}, {"_id": 0, "name": 1})
    return (y or {}).get("name")


async def _allowed_classes(user):
    iid = user["institution_id"]
    ps = await S.principal_scope(user)
    names = None if not ps or ps.get("whole_school") else set(ps.get("class_names") or [])
    secs = {}
    async for c in db.classes.find({"institution_id": iid}, {"_id": 0, "name": 1}):
        if names is None or c["name"] in names:
            secs[c["name"]] = []
    async for x in db.sections.find({"institution_id": iid}, {"_id": 0, "class_name": 1, "name": 1}):
        if x.get("class_name") in secs:
            secs[x["class_name"]].append(x["name"])
    return {k: sorted(v) for k, v in sorted(secs.items())}


@api.get("/bulk-runs/{rid}/enrol-preview")
async def enrol_preview(rid: str, user: dict = Depends(S.require_admin_or_principal)):
    r = await _run_or_404(user, rid)
    ids = [i["id"] for i in r["items"] if i.get("reason_code") in ("not_enrolled", "inactive")]
    year = await _run_year(r)
    classes = await _allowed_classes(user)
    rows = []
    async for s in db.students.find({"institution_id": r["institution_id"], "id": {"$in": ids}}, {"_id": 0}):
        name = f"{s.get('first_name', '')} {s.get('last_name', '')}".strip()
        cn, sec = s.get("class_name"), s.get("section")
        row = {"student_id": s["id"], "name": name, "admission_no": s.get("admission_no"), "class_name": cn if cn in classes else None,
               "section": sec if cn in classes and sec in classes.get(cn, []) else None, "status": "ready", "reason": None, "warning": None}
        if s.get("status") == "inactive":
            row.update(status="skip", reason="Student inactive — open student")
        elif year and await db.enrollments.find_one({"institution_id": r["institution_id"], "student_id": s["id"], "academic_year": year}):
            row.update(status="skip", reason=f"Already enrolled for {year}")
        elif cn and cn not in classes:
            row.update(status="pick", reason=f"Recorded class {cn} is outside your classes — pick one")
        elif not row["class_name"] or (classes.get(row["class_name"]) and not row["section"]):
            row["status"] = "pick"
        if row["class_name"] and row["section"]:
            row["warning"] = await S._capacity_warning(r["institution_id"], row["class_name"], row["section"])
        rows.append(row)
    rows.sort(key=lambda x: x["name"])
    return {"run_id": rid, "kind": r["kind"], "academic_year": year, "classes": classes, "rows": rows,
            "can_retry": r["kind"] == "fee_apply"}


@api.post("/bulk-runs/{rid}/enrol")
async def bulk_enrol(rid: str, payload: dict = Body(...), user: dict = Depends(S.require_admin_or_principal)):
    r = await _run_or_404(user, rid)
    iid = r["institution_id"]
    year = (payload.get("academic_year") or await _run_year(r) or "").strip()
    if not year:
        raise HTTPException(status_code=400, detail="Pick the academic year")
    eligible = {i["id"] for i in r["items"] if i.get("reason_code") in ("not_enrolled", "inactive")}
    classes = await _allowed_classes(user)
    items, enrolled = [], []
    for row in payload.get("rows") or []:
        sid = row.get("student_id")
        s = await db.students.find_one({"id": sid, "institution_id": iid}, {"_id": 0})
        name = f"{(s or {}).get('first_name', '')} {(s or {}).get('last_name', '')}".strip() or sid
        cn, sec = row.get("class_name"), row.get("section") or None
        sub = f"{(s or {}).get('admission_no') or '—'} · {cn or '—'} {sec or ''}".strip()

        def add(status, reason, code, fx="open_student"):
            items.append(B.item(sid, name, status, reason, code, sub, B.fix(fx, sid)))
        if not s or sid not in eligible:
            add("skipped", "Not part of this result", "not_in_run")
            continue
        if s.get("status") == "inactive":
            add("skipped", "Student inactive — open student", "inactive")
            continue
        if not cn or cn not in classes:
            add("skipped", "Pick a class you manage" if cn else "Pick a class", "no_class")
            continue
        if classes[cn] and sec not in classes[cn]:
            add("skipped", f"Pick a section of {cn}", "no_section")
            continue
        doc = {"student_id": sid, "academic_year": year, "class_name": cn, "section": sec, "id": str(uuid.uuid4())}
        try:
            await S.enrich_institution_doc("enrollments", doc, user)
        except HTTPException as e:
            add("skipped", str(e.detail), "enrol_rule")
            continue
        doc.update(institution_id=iid, created_at=S.now_iso())
        await db.enrollments.insert_one(dict(doc))
        w = await S._capacity_warning(iid, cn, sec)
        add("created", f"Enrolled in {cn}{' ' + sec if sec else ''} for {year}" + (f" — {w}" if w else ""), "enrolled")
        enrolled.append(sid)
    await S.audit(user, "bulk_enrol", "enrollments", rid, f"{len(enrolled)} enrolled from result {r['title']}", iid)
    run = await B.save_run(user, "bulk_enrol", f"Enrol not-enrolled students ({year})", items, ref_id=r.get("ref_id"), parent_run_id=rid)
    retry = None
    if payload.get("retry", True) and enrolled and r["kind"] == "fee_apply":
        res = await S._apply_structure(r["ref_id"], user, only_ids=enrolled, parent_run_id=run["run_id"])
        retry = {"title": "Retry: " + r["title"], **res}
    return {**run, "enrolled": len(enrolled), "retry": retry}


@S.app.on_event("startup")
async def _phase60_indexes():
    await db.parent_setup_tokens.create_index("token_hash", unique=True)
    await db.parent_setup_tokens.create_index([("user_id", 1), ("created_at", -1)])
