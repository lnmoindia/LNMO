# Phase 58: parent profiles, parent chat, staff password resets, multi-channel parent invites.
import asyncio
import hashlib
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

import server as S

api, db = S.api, S.db
FAKE_EMAIL_SUFFIX = ".parent.invite"
INVITE_CHANNELS = ("whatsapp", "sms", "email")
CHAT_MAX = 2000
ATTACH_MAX = 5 * 1024 * 1024
ATTACH_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "application/pdf": "pdf"}
NUDGE_EVERY = timedelta(hours=1)
RELATIONS = ("father", "mother", "guardian", "grandparent", "other")


def real_email(u: dict):
    e = (u or {}).get("email") or ""
    return e if e and not e.endswith(FAKE_EMAIL_SUFFIX) else None


def sname(s):
    return f"{s.get('first_name', '')} {s.get('last_name', '')}".strip()


# ---------- staff scope ----------
async def staff_scope(user: dict):
    """None = whole school; else {"classes": set, "pairs": set((class, section))}. 403 for non-staff."""
    iid = user.get("institution_id")
    if user.get("role") == "institution_admin" and iid:
        return None
    if user.get("role") != "teacher" or not iid or user.get("status") == "inactive":
        raise HTTPException(status_code=403, detail="Access denied")
    ps = await S.principal_scope(user)
    if ps and ps.get("whole_school"):
        return None
    pairs = {(x.get("class_name"), x.get("name")) async for x in
             db.sections.find({"institution_id": iid, "class_teacher_id": user["id"]}, {"_id": 0, "class_name": 1, "name": 1})}
    classes = set((ps or {}).get("class_names") or [])
    if not classes and not pairs:
        raise HTTPException(status_code=403, detail="Only admins, principals and class teachers can see parents")
    return {"classes": classes, "pairs": pairs}


def in_scope(scope, s: dict) -> bool:
    if scope is None:
        return True
    return s.get("class_name") in scope["classes"] or (s.get("class_name"), s.get("section")) in scope["pairs"]


async def scoped_students(iid, scope):
    q = {"institution_id": iid}
    if scope is not None:
        ors = [{"class_name": {"$in": list(scope["classes"])}}] if scope["classes"] else []
        ors += [{"class_name": c, "section": sec} for c, sec in scope["pairs"]]
        q["$or"] = ors or [{"id": "__none__"}]
    return {s["id"]: s async for s in db.students.find(q, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "class_name": 1,
                                                             "section": 1, "admission_no": 1, "guardian_phone": 1,
                                                             "guardian_name": 1, "guardian_email": 1, "enrollment_status": 1})}


def onboarding_status(p: dict) -> str:
    return "invited" if p.get("invited") and p.get("must_change_password") and not p.get("pw_set_by_staff") else "linked"


async def parent_in_scope(user, pid):
    iid = user["institution_id"]
    p = await db.users.find_one({"id": pid, "institution_id": iid, "role": "parent"}, {"_id": 0, "password_hash": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Parent not found")
    scope = await staff_scope(user)
    kids = await scoped_students(iid, scope)
    mine = [kids[k] for k in (p.get("student_ids") or []) if k in kids]
    if scope is not None and not mine:
        raise HTTPException(status_code=403, detail="This parent has no children in your classes")
    return p, mine, scope


# ---------- 1) Parent profiles ----------
@api.get("/parents")
async def list_parents(search: str = "", class_name: str = "", section: str = "", status: str = "",
                       page: int = 1, limit: int = 25, user: dict = Depends(S.get_current_user)):
    iid = user.get("institution_id")
    scope = await staff_scope(user)
    kids = await scoped_students(iid, scope)
    facets = sorted({(v.get("class_name") or "", v.get("section") or "") for v in kids.values() if v.get("class_name")})
    if class_name:
        kids = {k: v for k, v in kids.items() if v.get("class_name") == class_name and (not section or v.get("section") == section)}
    rx = search.strip().lower()
    rows = []
    if status != "not_invited":
        q = {"institution_id": iid, "role": "parent"}
        if scope is not None or class_name:
            q["student_ids"] = {"$in": list(kids)}
        async for p in db.users.find(q, {"_id": 0, "password_hash": 0}):
            children = [kids[k] for k in (p.get("student_ids") or []) if k in kids]
            st = onboarding_status(p)
            if status and st != status:
                continue
            hay = " ".join([p.get("name") or "", p.get("phone") or "", real_email(p) or ""] + [sname(c) for c in children]).lower()
            if rx and rx not in hay:
                continue
            rows.append({"type": "parent", "id": p["id"], "name": p.get("name"), "phone": p.get("phone"), "email": real_email(p),
                         "relation": p.get("relation"), "status": st, "account_status": p.get("status") or "active",
                         "children": [{"id": c["id"], "name": sname(c), "class_name": c.get("class_name"), "section": c.get("section")} for c in children]})
    if status in ("", "not_invited"):
        linked = await S._linked_student_ids(iid)
        for s in kids.values():
            if s["id"] in linked or s.get("enrollment_status") not in (None, "enrolled"):
                continue
            hay = " ".join([s.get("guardian_name") or "", s.get("guardian_phone") or "", s.get("guardian_email") or "", sname(s)]).lower()
            if rx and rx not in hay:
                continue
            rows.append({"type": "guardian", "id": f"g-{s['id']}", "name": s.get("guardian_name") or f"Guardian of {sname(s)}",
                         "phone": S._norm_phone(s.get("guardian_phone")) or None, "email": s.get("guardian_email") or None,
                         "status": "not_invited", "children": [{"id": s["id"], "name": sname(s), "class_name": s.get("class_name"), "section": s.get("section")}]})
    rows.sort(key=lambda r: (r["type"] != "parent", (r["name"] or "").lower()))
    limit = min(max(limit, 1), 100)
    total = len(rows)
    start = (max(page, 1) - 1) * limit
    return {"items": rows[start:start + limit], "total": total, "page": max(page, 1),
            "pages": max((total + limit - 1) // limit, 1), "can_edit": user["role"] == "institution_admin",
            "classes": [{"class_name": c, "section": s} for c, s in facets]}


async def _parent_threads(iid, pid, uid, kids_ok=None):
    out = []
    async for t in db.parent_threads.find({"institution_id": iid, "parent_id": pid}, {"_id": 0}).sort("last_message_at", -1):
        if kids_ok is None or t["student_id"] in kids_ok:
            out.append(await thread_view(t, uid))
    return out


@api.get("/parents/{pid}")
async def parent_detail(pid: str, user: dict = Depends(S.get_current_user)):
    iid = user["institution_id"]
    p, mine, scope = await parent_in_scope(user, pid)
    if scope is None:
        ids = p.get("student_ids") or []
        mine = await db.students.find({"institution_id": iid, "id": {"$in": ids}}, {"_id": 0}).to_list(50)
    children = []
    for c in mine:
        fees = await S._student_fees(iid, c["id"])
        pays = fees["payments"]
        children.append({"id": c["id"], "name": sname(c), "class_name": c.get("class_name"), "section": c.get("section"),
                         "admission_no": c.get("admission_no"),
                         "fees": {"outstanding": fees["summary"]["balance"], "overdue_invoices": fees["summary"]["overdue"],
                                  "overdue_amount": S._r2(sum(i["balance"] for i in fees["invoices"] if i.get("status") == "overdue")),
                                  "next_due": fees["summary"]["next_due"],
                                  "last_payment": ({"amount": pays[0]["amount"], "at": pays[0].get("paid_on") or pays[0].get("collected_at"),
                                                    "receipt_no": pays[0].get("receipt_no")} if pays else None)}})
    invites = await db.parent_invites.find({"institution_id": iid, "parent_user_id": pid}, {"_id": 0}).sort("sent_at", 1).to_list(100)
    codes = await db.parent_setup_codes.find({"institution_id": iid, "student_id": {"$in": [c["id"] for c in children]}, "used": True},
                                             {"_id": 0, "used_at": 1, "student_id": 1}).to_list(20)
    method = "paper slip" if p.get("setup_method") == "setup_code" or (codes and not invites) else \
             "invite link" if invites else "OTP sign-up" if p.get("setup_method") == "otp" else "added by school"
    last = await db.audit_logs.find_one({"actor_email": p.get("email"), "action": "login"}, {"_id": 0, "timestamp": 1}, sort=[("timestamp", -1)])
    ors = [{"meta.parent_user_id": pid}]
    if p.get("phone"):
        ors.append({"recipient_phone": p["phone"]})
    if real_email(p):
        ors.append({"recipient_email": real_email(p)})
    comms = await db.messages.find({"institution_id": iid, "$or": ors},
                                   {"_id": 0, "id": 1, "channel": 1, "module": 1, "status": 1, "created_at": 1, "body": 1,
                                    "provider_message_id": 1, "error": 1, "recipient_email": 1, "recipient_phone": 1}).sort("created_at", -1).to_list(50)
    for m in comms:
        m["body"] = (m.get("body") or "")[:160]
    return {"parent": {"id": p["id"], "name": p.get("name"), "phone": p.get("phone"), "email": real_email(p),
                       "login_email": p.get("email"), "relation": p.get("relation"), "preferred_channel": p.get("preferred_channel"),
                       "account_status": p.get("status") or "active", "must_change_password": bool(p.get("must_change_password")),
                       "created_at": p.get("created_at")},
            "children": children,
            "onboarding": {"status": onboarding_status(p), "method": method, "invited_at": invites[0]["sent_at"] if invites else None,
                           "events": [{"at": i.get("sent_at"), "channel": i.get("channel"), "status": i.get("status"),
                                       "channels": i.get("channels")} for i in invites]},
            "last_login": (last or {}).get("timestamp"),
            "lock": await S._active_lock(await S._account_lock_keys(p)),
            "communications": comms,
            "threads": await _parent_threads(iid, pid, user["id"], None if scope is None else {c["id"] for c in mine}),
            "can_edit": user["role"] == "institution_admin", "timezone": str(await S._inst_tz(iid))}


class ParentEdit(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    relation: str | None = None
    preferred_channel: str | None = None


async def _notify_email_change(inst_name, old, new):
    html = S._support_email_html("Your parent portal login email was changed", [
        f"The login email for your {S._html_escape(inst_name or '')} parent account was changed from "
        f"<b>{S._html_escape(old or '(none)')}</b> to <b>{S._html_escape(new)}</b> by the school office.",
        "You can keep signing in with your mobile number too. Your password hasn't changed.",
        "If this wasn't expected, contact the school office straight away."])
    results = {}
    for addr in [a for a in dict.fromkeys([old, new]) if a]:
        try:
            mid = await S._support_send(addr, "Your parent portal login email was changed", html)
            results[addr] = {"message_id": mid} if mid else {"error": "email_not_configured"}
        except S.EmailSendError as e:
            results[addr] = {"error": e.reason}
    return results


@api.patch("/parents/{pid}")
async def edit_parent(pid: str, body: ParentEdit, user: dict = Depends(S.require_roles("institution_admin"))):
    iid = user["institution_id"]
    p = await db.users.find_one({"id": pid, "institution_id": iid, "role": "parent"}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Parent not found")
    sets, changes = {}, []
    if body.name is not None:
        if not body.name.strip():
            raise HTTPException(status_code=400, detail="Name can't be empty")
        sets["name"] = body.name.strip()
    if body.relation is not None:
        if body.relation and body.relation not in RELATIONS:
            raise HTTPException(status_code=400, detail=f"Relation must be one of {', '.join(RELATIONS)}")
        sets["relation"] = body.relation or None
    if body.preferred_channel is not None:
        if body.preferred_channel and body.preferred_channel not in INVITE_CHANNELS:
            raise HTTPException(status_code=400, detail="Preferred channel must be whatsapp, sms or email")
        sets["preferred_channel"] = body.preferred_channel or None
    if body.phone is not None:
        ph = S._norm_phone(body.phone)
        if len(ph) != 10:
            raise HTTPException(status_code=400, detail="Enter a 10-digit mobile number")
        if ph != p.get("phone") and await db.users.find_one({"institution_id": iid, "role": "parent", "phone": ph, "id": {"$ne": pid}}):
            raise HTTPException(status_code=409, detail="Another parent at this school already uses that mobile number")
        sets["phone"] = ph
    old_email, new_email = real_email(p), None
    if body.email is not None:
        e = body.email.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e):
            raise HTTPException(status_code=400, detail="Enter a valid email address")
        if e != (p.get("email") or "").lower():
            if await db.users.find_one({"email": e, "id": {"$ne": pid}}, {"_id": 1}):
                raise HTTPException(status_code=409, detail="That email is already used by another account")
            sets["email"], new_email = e, e
    for k, v in sets.items():
        if (p.get(k) or None) != (v or None):
            changes.append(f"{k}: {p.get(k) or '—'} → {v or '—'}")
    if not changes:
        return {"ok": True, "changed": [], "notifications": {}}
    try:
        await db.users.update_one({"id": pid}, {"$set": {**sets, "updated_at": S.now_iso()}})
    except S.DuplicateKeyError:
        raise HTTPException(status_code=409, detail="That email is already used by another account")
    notes = {}
    if new_email:
        if p.get("email"):
            await db.login_attempts.delete_many({"identifier": p["email"].lower()})
        inst = await db.institutions.find_one({"id": iid}, {"_id": 0, "name": 1}) or {}
        notes = await _notify_email_change(inst.get("name"), old_email, new_email)
    await S.audit(user, "parent_edit", "users", pid, f"{p.get('name')} · " + "; ".join(changes)
                  + (" · notify " + ", ".join(f"{a}: {r.get('message_id') or r.get('error')}" for a, r in notes.items()) if notes else ""), iid)
    return {"ok": True, "changed": changes, "notifications": notes}


@api.post("/parents/{pid}/children")
async def link_child(pid: str, payload: dict = Body(...), user: dict = Depends(S.require_roles("institution_admin"))):
    iid = user["institution_id"]
    p = await db.users.find_one({"id": pid, "institution_id": iid, "role": "parent"}, {"_id": 0, "id": 1, "name": 1})
    s = await db.students.find_one({"id": payload.get("student_id"), "institution_id": iid}, {"_id": 0})
    if not p or not s:
        raise HTTPException(status_code=404, detail="Parent or student not found")
    await db.users.update_one({"id": pid}, {"$addToSet": {"student_ids": s["id"]}})
    await S.audit(user, "parent_link_child", "users", pid, f"{p.get('name')} + {sname(s)}", iid)
    return {"ok": True}


def _norm_adm(x):
    return re.sub(r"[^a-z0-9]", "", str(x or "").lower())


@api.get("/parents/{pid}/link-candidates")
async def link_candidates(pid: str, q: str = "", user: dict = Depends(S.require_roles("institution_admin"))):
    """Students to link: admission no (exact/partial, ignores case/spaces/dashes) or name."""
    iid = user["institution_id"]
    p = await db.users.find_one({"id": pid, "institution_id": iid, "role": "parent"}, {"_id": 0, "student_ids": 1})
    if not p:
        raise HTTPException(status_code=404, detail="Parent not found")
    term = q.strip()
    if len(term) < 2 and not term.isdigit():
        return {"results": []}
    na, words = _norm_adm(term), term.lower().split()
    mine = set(p.get("student_ids") or [])
    hits = []
    async for s in db.students.find({"institution_id": iid}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "admission_no": 1,
                                                               "class_name": 1, "section": 1, "enrollment_status": 1}):
        adm = _norm_adm(s.get("admission_no"))
        name = sname(s).lower()
        if na and adm == na:
            rank = 0
        elif na and na in adm:
            rank = 1
        elif words and all(w in name for w in words):
            rank = 2
        else:
            continue
        hits.append((rank, name, s))
    hits.sort(key=lambda h: (h[0], h[1]))
    ids = [h[2]["id"] for h in hits[:20]]
    linked = {}
    async for u in db.users.find({"institution_id": iid, "role": "parent", "student_ids": {"$in": ids}}, {"_id": 0, "id": 1, "name": 1, "student_ids": 1}):
        for sid in u.get("student_ids") or []:
            linked.setdefault(sid, []).append({"id": u["id"], "name": u.get("name")})
    return {"results": [{"id": s["id"], "name": sname(s), "admission_no": s.get("admission_no"), "class_name": s.get("class_name"),
                         "section": s.get("section"), "enrollment_status": s.get("enrollment_status"),
                         "already_linked": s["id"] in mine, "parents": linked.get(s["id"], [])} for _, _, s in hits[:20]]}


@api.post("/parents/{pid}/children/{sid}/unlink")
async def unlink_child(pid: str, sid: str, user: dict = Depends(S.require_roles("institution_admin"))):
    iid = user["institution_id"]
    p = await db.users.find_one({"id": pid, "institution_id": iid, "role": "parent", "student_ids": sid}, {"_id": 0, "name": 1})
    if not p:
        raise HTTPException(status_code=404, detail="That child isn't linked to this parent")
    s = await db.students.find_one({"id": sid}, {"_id": 0}) or {}
    await db.users.update_one({"id": pid}, {"$pull": {"student_ids": sid}})
    await S.audit(user, "parent_unlink_child", "users", pid, f"{p.get('name')} − {sname(s)}", iid)
    return {"ok": True}


@api.get("/students/{sid}/guardians")
async def student_guardians(sid: str, user: dict = Depends(S.get_current_user)):
    iid = user.get("institution_id")
    scope = await staff_scope(user)
    s = await db.students.find_one({"id": sid, "institution_id": iid}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")
    if not in_scope(scope, s):
        raise HTTPException(status_code=403, detail="This student is outside your classes")
    ps = await db.users.find({"institution_id": iid, "role": "parent", "student_ids": sid}, {"_id": 0, "password_hash": 0}).to_list(20)
    return {"parents": [{"id": p["id"], "name": p.get("name"), "phone": p.get("phone"), "email": real_email(p),
                         "relation": p.get("relation"), "status": onboarding_status(p)} for p in ps],
            "guardian": {"name": s.get("guardian_name"), "phone": s.get("guardian_phone"), "email": s.get("guardian_email")}}


# ---------- 2) Parent chat ----------
async def thread_access(user, tid):
    t = await db.parent_threads.find_one({"id": tid, "institution_id": user.get("institution_id")}, {"_id": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if user["role"] == "parent":
        if t["parent_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")
        return t
    scope = await staff_scope(user)
    s = await db.students.find_one({"id": t["student_id"]}, {"_id": 0, "class_name": 1, "section": 1}) or {}
    if not in_scope(scope, s):
        raise HTTPException(status_code=403, detail="This conversation is outside your classes")
    return t


async def _unread(t, uid):
    since = (t.get("reads") or {}).get(uid, "")
    return await db.parent_messages.count_documents({"thread_id": t["id"], "sender_id": {"$ne": uid}, "created_at": {"$gt": since}})


async def thread_view(t, uid):
    return {k: t.get(k) for k in ("id", "parent_id", "parent_name", "student_id", "student_name", "class_name", "section", "target",
                                  "subject", "status", "created_at", "last_message_at", "last_message_preview", "last_sender_role")} \
        | {"unread": await _unread(t, uid)}


async def thread_staff_ids(t):
    iid = t["institution_id"]
    ids = set(await S._manager_recipients(iid, [t["class_name"]] if t.get("class_name") else None))
    sec = await db.sections.find_one({"institution_id": iid, "class_name": t.get("class_name"), "name": t.get("section")}, {"_id": 0, "class_teacher_id": 1})
    if sec and sec.get("class_teacher_id"):
        ids.add(sec["class_teacher_id"])
    return ids


@api.get("/chat/threads")
async def list_threads(class_name: str = "", status: str = "", user: dict = Depends(S.get_current_user)):
    iid = user.get("institution_id")
    q = {"institution_id": iid}
    if user["role"] == "parent":
        q["parent_id"] = user["id"]
    else:
        scope = await staff_scope(user)
        if scope is not None:
            ors = [{"class_name": {"$in": list(scope["classes"])}}] if scope["classes"] else []
            ors += [{"class_name": c, "section": s} for c, s in scope["pairs"]]
            q["$or"] = ors
    if class_name:
        q["class_name"] = class_name
    if status:
        q["status"] = status
    rows = [await thread_view(t, user["id"]) async for t in db.parent_threads.find(q, {"_id": 0}).sort("last_message_at", -1).limit(500)]
    rows.sort(key=lambda r: (r["unread"] == 0,))
    return {"threads": rows, "unread_total": sum(r["unread"] for r in rows), "timezone": str(await S._inst_tz(iid))}


@api.get("/chat/unread")
async def chat_unread(user: dict = Depends(S.get_current_user)):
    if user["role"] not in ("parent", "teacher", "institution_admin"):
        return {"unread": 0}
    try:
        return {"unread": (await list_threads(user=user))["unread_total"]}
    except HTTPException:
        return {"unread": 0}


async def _store_attachment(iid, file: UploadFile):
    if not file or not file.filename:
        return None
    ct = (file.content_type or "").lower()
    if ct not in ATTACH_TYPES:
        raise HTTPException(status_code=400, detail="Attach a JPG, PNG, WEBP image or a PDF")
    data = await file.read()
    if len(data) > ATTACH_MAX:
        raise HTTPException(status_code=400, detail="Attachments can be at most 5 MB")
    path = f"lnmo/{iid}/chat/{uuid.uuid4()}.{ATTACH_TYPES[ct]}"
    await asyncio.to_thread(S._put_object, path, data, ct)
    return {"path": path, "name": file.filename[:120], "content_type": ct, "size": len(data)}


async def _nudge_parent(t, parent):
    """Optional nudge to the parent's preferred channel, at most once per thread per hour."""
    now = datetime.now(timezone.utc)
    last = t.get("last_nudge_at")
    if last and now - datetime.fromisoformat(last) < NUDGE_EVERY:
        return {"status": "throttled", "next_after": (datetime.fromisoformat(last) + NUDGE_EVERY).isoformat()}
    email = real_email(parent)
    ch = parent.get("preferred_channel") or ("email" if email else "whatsapp")
    inst = await db.institutions.find_one({"id": t["institution_id"]}, {"_id": 0, "name": 1, "slug": 1, "code": 1}) or {}
    key = inst.get("slug") or (inst.get("code") or "").lower()
    link = f"{S.os.environ['PUBLIC_BASE_URL']}/login/{key}" if key else f"{S.os.environ['PUBLIC_BASE_URL']}/login"
    text = f"{inst.get('name')}: you have a new message about {t['student_name']}. Open the parent portal to reply: {link}"
    res = {"channel": ch}
    if ch == "email":
        if not email:
            res["status"] = "skipped_no_email"
        else:
            html = S._support_email_html(f"New message from {inst.get('name') or 'school'}", [
                f"Hello {S._html_escape(parent.get('name') or '')},",
                f"The school sent you a new message about <b>{S._html_escape(t['student_name'])}</b>. Sign in to the parent portal to read and reply."],
                ("Open messages", link))
            try:
                mid = await S._support_send(email, f"New message about {t['student_name']}", html)
                res.update(status="sent" if mid else "failed", message_id=mid, error=None if mid else "email_not_configured")
            except S.EmailSendError as e:
                res.update(status="failed", error=e.reason)
            await db.messages.insert_one({"id": str(uuid.uuid4()), "institution_id": t["institution_id"], "channel": "email",
                                          "direction": "outbound", "provider": "resend", "provider_message_id": res.get("message_id"),
                                          "recipient_name": parent.get("name"), "recipient_email": email, "body": text,
                                          "module": "parent_chat_nudge", "status": res["status"], "error": res.get("error"),
                                          "meta": {"parent_user_id": parent["id"], "thread_id": t["id"]}, "created_at": S.now_iso()})
    elif not parent.get("phone"):
        res["status"] = "skipped_no_phone"
    else:
        try:
            r = await S.send_message(t["institution_id"], ch, [{"name": parent.get("name"), "phone": parent["phone"], "body": text,
                                                                "meta": {"parent_user_id": parent["id"], "thread_id": t["id"]}}],
                                     module="parent_chat_nudge")
            res["status"] = "sent" if r.get("sent") else (r.get("code") or (r.get("results") or [{}])[0].get("code") or "failed")
        except HTTPException as e:
            res.update(status="failed", error=str(e.detail))
    if res["status"] == "sent":
        await db.parent_threads.update_one({"id": t["id"]}, {"$set": {"last_nudge_at": now.isoformat()}})
    return res


async def _post_message(t, user, body, attachment, nudge=True):
    text = (body or "").strip()
    if not text and not attachment:
        raise HTTPException(status_code=400, detail="Write a message or attach a file")
    if len(text) > CHAT_MAX:
        raise HTTPException(status_code=400, detail=f"Messages can be at most {CHAT_MAX} characters")
    if t.get("status") == "closed":
        raise HTTPException(status_code=409, detail="This conversation is closed" + ("" if user["role"] == "parent" else " — reopen it to reply"))
    now = S.now_iso()
    m = {"id": str(uuid.uuid4()), "thread_id": t["id"], "institution_id": t["institution_id"], "sender_id": user["id"],
         "sender_role": "parent" if user["role"] == "parent" else "staff", "sender_name": user.get("name"),
         "sender_title": await _staff_title(user, t) if user["role"] != "parent" else "Parent",
         "body": text, "attachment": attachment, "hidden": False, "created_at": now}
    await db.parent_messages.insert_one(dict(m))
    preview = (text or f"Attachment: {attachment['name']}")[:120]
    await db.parent_threads.update_one({"id": t["id"]}, {"$set": {"last_message_at": now, "last_message_preview": preview,
                                                                  "last_sender_role": m["sender_role"], f"reads.{user['id']}": now}})
    await S.audit(user, "chat_message", "parent_threads", t["id"], f"{t['student_name']} · {len(text)} chars"
                  + (" + attachment" if attachment else ""), t["institution_id"])
    import phase59
    await phase59.emit(t, {"type": "message", "message_id": m["id"], "sender_id": user["id"]})
    nudge_res = None
    title = f"New message about {t['student_name']}"
    if m["sender_role"] == "staff":
        await S._notify(t["institution_id"], t["parent_id"], "parent_message", title, f"{user.get('name')}: {preview}", t["id"])
        parent = await db.users.find_one({"id": t["parent_id"]}, {"_id": 0, "password_hash": 0})
        if nudge and parent:
            t = await db.parent_threads.find_one({"id": t["id"]}, {"_id": 0})
            nudge_res = await _nudge_parent(t, parent)
            await db.parent_messages.update_one({"id": m["id"]}, {"$set": {"nudge": nudge_res}})
    else:
        for uid in await thread_staff_ids(t):
            await S._notify(t["institution_id"], uid, "parent_message", title, f"{user.get('name')}: {preview}", t["id"])
    m.pop("_id", None)
    return {"message": m, "nudge": nudge_res}


async def _staff_title(user, t):
    if user["role"] == "institution_admin":
        return "School office"
    if await S.active_principal(user):
        return "Principal"
    return "Class teacher"


@api.post("/chat/threads")
async def start_thread(student_id: str = Form(...), body: str = Form(""), parent_id: str = Form(""), target: str = Form("class_teacher"),
                       subject: str = Form(""), file: UploadFile | None = File(None), user: dict = Depends(S.get_current_user)):
    iid = user.get("institution_id")
    s = await db.students.find_one({"id": student_id, "institution_id": iid}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")
    if user["role"] == "parent":
        if student_id not in (user.get("student_ids") or []):
            raise HTTPException(status_code=403, detail="This student is not linked to your account")
        if target not in ("class_teacher", "office"):
            raise HTTPException(status_code=400, detail="Send to the class teacher or the school office")
        parent = user
    else:
        if not in_scope(await staff_scope(user), s):
            raise HTTPException(status_code=403, detail="This student is outside your classes")
        parent = await db.users.find_one({"id": parent_id, "institution_id": iid, "role": "parent", "student_ids": student_id}, {"_id": 0})
        if not parent:
            raise HTTPException(status_code=404, detail="That parent isn't linked to this student")
        target = "office" if user["role"] == "institution_admin" else "class_teacher"
    t = await db.parent_threads.find_one({"institution_id": iid, "parent_id": parent["id"], "student_id": student_id,
                                          "target": target, "status": "open"}, {"_id": 0})
    created = False
    if not t:
        t = {"id": str(uuid.uuid4()), "institution_id": iid, "parent_id": parent["id"], "parent_name": parent.get("name"),
             "student_id": student_id, "student_name": sname(s), "class_name": s.get("class_name"), "section": s.get("section"),
             "target": target, "subject": (subject or "").strip()[:120] or None, "status": "open", "created_by": user["id"],
             "created_at": S.now_iso(), "last_message_at": S.now_iso(), "reads": {}}
        await db.parent_threads.insert_one(dict(t))
        t.pop("_id", None)
        created = True
        await S.audit(user, "chat_thread_start", "parent_threads", t["id"], f"{parent.get('name')} · {t['student_name']} · {target}", iid)
    res = None
    if (body or "").strip() or (file and file.filename):
        res = await _post_message(t, user, body, await _store_attachment(iid, file))
    elif created and user["role"] == "parent":
        raise HTTPException(status_code=400, detail="Write a message to start the conversation")
    t = await db.parent_threads.find_one({"id": t["id"]}, {"_id": 0})
    return {"thread": await thread_view(t, user["id"]), "created": created, "nudge": (res or {}).get("nudge")}


@api.get("/chat/threads/{tid}")
async def get_thread(tid: str, user: dict = Depends(S.get_current_user)):
    t = await thread_access(user, tid)
    msgs = await db.parent_messages.find({"thread_id": tid}, {"_id": 0}).sort("created_at", 1).to_list(2000)
    reads = t.get("reads") or {}
    parent_read = reads.get(t["parent_id"], "")
    staff_read = max([v for k, v in reads.items() if k != t["parent_id"]] or [""])
    for m in msgs:
        m["seen"] = (parent_read if m["sender_role"] == "staff" else staff_read) >= m["created_at"]
        m["mine"] = m["sender_id"] == user["id"]
        if m.get("attachment"):
            m["attachment"] = {k: m["attachment"][k] for k in ("name", "content_type", "size")}
        if m.get("hidden") and user["role"] == "parent":
            m.update(body="This message was hidden by the school.", attachment=None)
        m.pop("nudge", None) if user["role"] == "parent" else None
    await db.parent_threads.update_one({"id": tid}, {"$set": {f"reads.{user['id']}": S.now_iso()}})
    import phase59
    if any(m["sender_id"] != user["id"] and m["created_at"] > reads.get(user["id"], "") for m in msgs):
        await phase59.emit(t, {"type": "read", "user_id": user["id"]}, exclude=user["id"])
    await db.notifications.update_many({"user_id": user["id"], "type": "parent_message", "related_id": tid, "read": False}, {"$set": {"read": True}})
    t = await db.parent_threads.find_one({"id": tid}, {"_id": 0})
    view = await thread_view(t, user["id"])
    parent = await db.users.find_one({"id": t["parent_id"]}, {"_id": 0, "phone": 1, "email": 1}) or {}
    return {"thread": view, "messages": msgs, "timezone": str(await S._inst_tz(t["institution_id"])),
            "parent_contact": None if user["role"] == "parent" else {"phone": parent.get("phone"), "email": real_email(parent)},
            "can_moderate": user["role"] != "parent"}


@api.post("/chat/threads/{tid}/messages")
async def post_message(tid: str, body: str = Form(""), file: UploadFile | None = File(None), user: dict = Depends(S.get_current_user)):
    t = await thread_access(user, tid)
    return await _post_message(t, user, body, await _store_attachment(t["institution_id"], file))


@api.get("/chat/messages/{mid}/attachment")
async def message_attachment(mid: str, user: dict = Depends(S.get_current_user)):
    m = await db.parent_messages.find_one({"id": mid, "institution_id": user.get("institution_id")}, {"_id": 0})
    if not m or not m.get("attachment"):
        raise HTTPException(status_code=404, detail="Attachment not found")
    await thread_access(user, m["thread_id"])
    if m.get("hidden") and user["role"] == "parent":
        raise HTTPException(status_code=404, detail="Attachment not found")
    data, ct = await asyncio.to_thread(S._get_object, m["attachment"]["path"])
    return Response(content=data, media_type=m["attachment"]["content_type"] or ct,
                    headers={"Content-Disposition": f'inline; filename="{m["attachment"]["name"]}"', "Cache-Control": "private, max-age=300"})


@api.post("/chat/threads/{tid}/status")
async def set_thread_status(tid: str, payload: dict = Body(...), user: dict = Depends(S.get_current_user)):
    if user["role"] == "parent":
        raise HTTPException(status_code=403, detail="Only school staff can close or reopen a conversation")
    t = await thread_access(user, tid)
    st = payload.get("status")
    if st not in ("open", "closed"):
        raise HTTPException(status_code=400, detail="status must be open or closed")
    if st == "open" and await db.parent_threads.find_one({"institution_id": t["institution_id"], "parent_id": t["parent_id"], "student_id": t["student_id"],
                                                          "target": t["target"], "status": "open", "id": {"$ne": tid}}):
        raise HTTPException(status_code=409, detail="There's already an open conversation for this child — continue there")
    await db.parent_threads.update_one({"id": tid}, {"$set": {"status": st, f"{st}_by": user.get("name"), f"{st}_at": S.now_iso()}})
    await S.audit(user, f"chat_thread_{st}", "parent_threads", tid, t["student_name"], t["institution_id"])
    import phase59
    await phase59.emit(t, {"type": "status", "status": st})
    return {"ok": True, "status": st}


@api.post("/chat/messages/{mid}/moderate")
async def moderate_message(mid: str, payload: dict = Body(...), user: dict = Depends(S.get_current_user)):
    if user["role"] == "parent":
        raise HTTPException(status_code=403, detail="Access denied")
    m = await db.parent_messages.find_one({"id": mid, "institution_id": user.get("institution_id")}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Message not found")
    t = await thread_access(user, m["thread_id"])
    action, reason = payload.get("action"), (payload.get("reason") or "").strip()[:300]
    if action not in ("hide", "unhide", "report"):
        raise HTTPException(status_code=400, detail="action must be hide, unhide or report")
    if action == "report":
        await db.parent_messages.update_one({"id": mid}, {"$push": {"reports": {"by": user.get("name"), "reason": reason, "at": S.now_iso()}}})
        for uid in await S._manager_recipients(t["institution_id"], [t["class_name"]]):
            if uid != user["id"]:
                await S._notify(t["institution_id"], uid, "parent_message_report", f"Message reported · {t['student_name']}",
                                f"{user.get('name')}: {reason or 'no reason given'}", t["id"])
    else:
        await db.parent_messages.update_one({"id": mid}, {"$set": {"hidden": action == "hide", "hidden_by": user.get("name"),
                                                                    "hidden_reason": reason or None, "hidden_at": S.now_iso()}})
    await S.audit(user, f"chat_message_{action}", "parent_messages", mid, f"{t['student_name']} · {reason}", t["institution_id"])
    return {"ok": True}


# ---------- 3) Staff-initiated password resets ----------
async def reset_target(actor, uid):
    iid = actor.get("institution_id")
    t = await db.users.find_one({"id": uid, "institution_id": iid}, {"_id": 0, "password_hash": 0})
    if not t:
        for col, key in (("students", "user_id"), ("teachers", "user_id")):
            r = await db[col].find_one({"id": uid, "institution_id": iid}, {"_id": 0, key: 1})
            if r and r.get(key):
                t = await db.users.find_one({"id": r[key], "institution_id": iid}, {"_id": 0, "password_hash": 0})
                break
    if not t or not iid or t.get("role") == "platform_admin":
        raise HTTPException(status_code=404, detail="Account not found")
    if t["id"] == actor["id"]:
        raise HTTPException(status_code=400, detail="Use Change password for your own account")
    if actor.get("role") == "institution_admin":
        return t
    ps = await S.principal_scope(actor)
    if not ps:
        raise HTTPException(status_code=403, detail="Access denied")
    if t.get("role") == "institution_admin" or (t.get("role") == "teacher" and await S.active_principal(t)):
        raise HTTPException(status_code=403, detail="Principals can't reset admin or principal passwords")
    if ps["whole_school"] and t.get("role") in ("student", "teacher", "parent"):
        return t
    names = set(ps.get("class_names") or [])
    if t.get("role") == "student":
        s = await db.students.find_one({"user_id": t["id"], "institution_id": iid}, {"_id": 0, "class_name": 1})
        if s and s.get("class_name") in names:
            return t
    elif t.get("role") == "teacher" and await S._absence_in_scope(actor, t["id"]):
        return t
    elif t.get("role") == "parent" and t.get("student_ids") and await db.students.find_one(
            {"institution_id": iid, "id": {"$in": t["student_ids"]}, "class_name": {"$in": list(names)}}):
        return t
    raise HTTPException(status_code=403, detail="This account is outside your divisions")


async def _force_change(t, extra=None):
    await db.users.update_one({"id": t["id"]}, {"$set": {"must_change_password": True, "pw_set_by_staff": True, **(extra or {})}, "$inc": {"tv": 1}})
    await db.login_attempts.delete_many({"identifier": {"$in": await S._account_lock_keys(t)}})


def _gen_password():
    alpha = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"
    while True:
        p = "".join(secrets.choice(alpha) for _ in range(10))
        if S._pw_strong(p):
            return p


@api.post("/users/{uid}/set-password")
async def staff_set_password(uid: str, payload: dict = Body(...), user: dict = Depends(S.get_current_user)):
    t = await reset_target(user, uid)
    gen = bool(payload.get("generate"))
    pw = _gen_password() if gen else (payload.get("password") or "")
    if not S._pw_strong(pw):
        raise HTTPException(status_code=400, detail=S.PW_RULE)
    await _force_change(t, {"password_hash": S.hash_password(pw), "password_changed_at": S.now_iso()})
    await db.password_resets.update_many({"user_id": t["id"], "used_at": None, "invalidated_at": None}, {"$set": {"invalidated_at": S.now_iso()}})
    await S.audit(user, "password_set_by_staff", "users", t["id"], f"{t.get('name')} ({t.get('role')}) · method={'generated' if gen else 'typed'}", t.get("institution_id"))
    return {"ok": True, "user": {"id": t["id"], "name": t.get("name"), "role": t.get("role"), "login": t.get("email") or t.get("phone")},
            "generated_password": pw if gen else None, "must_change_password": True}


@api.post("/users/{uid}/reset-link")
async def staff_reset_link(uid: str, user: dict = Depends(S.get_current_user)):
    t = await reset_target(user, uid)
    to = real_email(t)
    if not to or to.endswith(".invite"):
        raise HTTPException(status_code=400, detail="This account has no email address — use Set password instead")
    base = S.os.environ["PUBLIC_BASE_URL"].rstrip("/")
    inst = await db.institutions.find_one({"id": t["institution_id"]}, {"_id": 0, "name": 1}) or {}
    token, now = secrets.token_urlsafe(32), datetime.now(timezone.utc)
    await db.password_resets.update_many({"user_id": t["id"], "used_at": None, "invalidated_at": None}, {"$set": {"invalidated_at": now.isoformat()}})
    doc = {"id": str(uuid.uuid4()), "user_id": t["id"], "institution_id": t["institution_id"], "token_hash": hashlib.sha256(token.encode()).hexdigest(),
           "created_at": now.isoformat(), "expires_at": (now + timedelta(hours=S.RESET_TTL_HOURS)).isoformat(),
           "created_by": user.get("email"), "used_at": None, "invalidated_at": None, "message_id": None}
    await db.password_resets.insert_one(dict(doc))
    html = S._support_email_html("Reset your password", [
        f"Hello {S._html_escape(t.get('name') or '')},",
        f"{S._html_escape(user.get('name') or 'Your school')} at {S._html_escape(inst.get('name') or 'your school')} sent you a link to set a new password "
        f"for your account ({S._html_escape(to)}).",
        f"The link works once and expires in {S.RESET_TTL_HOURS} hours. You've been signed out on all devices.",
        "If you didn't expect this, contact the school office."], ("Set a new password", f"{base}/reset-password/{token}"))
    try:
        mid = await S._support_send(to, "Reset your password", html)
        err = None if mid else "email_not_configured"
    except S.EmailSendError as e:
        mid, err = None, e.reason
    if not mid:
        await db.password_resets.update_one({"id": doc["id"]}, {"$set": {"invalidated_at": S.now_iso(), "send_error": err}})
        await S.audit(user, "password_reset_email_failed", "users", t["id"], f"{to} · {err}", t["institution_id"])
        raise HTTPException(status_code=502, detail=f"The reset email could not be sent: {S.EMAIL_ERR_COPY.get(err, err)}. No link is active.")
    await db.password_resets.update_one({"id": doc["id"]}, {"$set": {"message_id": mid}})
    await _force_change(t)
    await S.audit(user, "password_reset_link_by_staff", "users", t["id"], f"{t.get('name')} ({t.get('role')}) · {to} · message {mid}", t["institution_id"])
    return {"ok": True, "sent_to": to, "message_id": mid, "expires_at": doc["expires_at"]}


@api.get("/users/{uid}/reset-info")
async def reset_info(uid: str, user: dict = Depends(S.get_current_user)):
    t = await reset_target(user, uid)
    return {"id": t["id"], "name": t.get("name"), "role": t.get("role"), "email": real_email(t), "rule": S.PW_RULE,
            "must_change_password": bool(t.get("must_change_password"))}


# ---------- 4) Multi-channel parent invites ----------
def parse_channels(payload: dict):
    chans = payload.get("channels")
    if chans is None:
        chans = [payload.get("channel") or "whatsapp"]
    if chans == "all" or payload.get("all_channels"):
        chans = list(INVITE_CHANNELS)
    chans = [c for c in dict.fromkeys(chans or []) if c]
    if not chans:
        raise HTTPException(status_code=400, detail="Pick at least one channel")
    bad = [c for c in chans if c not in INVITE_CHANNELS]
    if bad:
        raise HTTPException(status_code=400, detail="Channels must be whatsapp, sms or email")
    return chans


async def invite_email_html(iid, parent_name, children, link):
    inst = await db.institutions.find_one({"id": iid}, {"_id": 0}) or {}
    b = S._login_branding(inst)
    key = inst.get("slug") or (inst.get("code") or "").lower() or inst.get("domain") or ""
    base = S.os.environ["PUBLIC_BASE_URL"].rstrip("/")
    login = f"{base}/login/{key}" if key else f"{base}/login"
    logo = await S._school_logo_src(iid)
    e = S._html_escape
    kids = ", ".join(e(c) for c in children) or "your child"
    color = inst.get("primary_color") or "#4338ca"
    logo_html = f'<img src="{e(logo)}" alt="" height="48" style="height:48px;margin-bottom:12px">' if logo and logo.startswith("https://") else ""
    html = (f'<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif;color:#111;font-size:14px;line-height:1.55">'
            f'{logo_html}<h2 style="margin:0 0 4px;font-size:19px">{e(b.get("name") or inst.get("name") or "")}</h2>'
            f'<p style="margin:0 0 16px;color:#555">Parent portal invitation</p>'
            f'<p>Dear {e(parent_name or "Parent")},</p>'
            f'<p>You are invited to the {e(inst.get("name") or "school")} parent portal for <b>{kids}</b> — see attendance, homework, results, fees and message the school.</p>'
            f'<p style="margin:20px 0"><a href="{e(link)}" style="background:{e(color)};color:#fff;padding:12px 20px;border-radius:8px;text-decoration:none;font-weight:bold">Set up my account</a></p>'
            f'<ol style="padding-left:18px;margin:0 0 12px"><li>Tap <b>Set up my account</b> (the link works for 72 hours).</li>'
            f'<li>Choose your password.</li><li>Next time, sign in at <a href="{e(login)}">{e(login)}</a> with your mobile number.</li></ol>'
            f'<p style="font-size:12px;color:#666;word-break:break-all">Link not working? Paste this into your browser: {e(link)}</p>'
            f'<p style="font-size:12px;color:#888;margin-top:24px">Sent by {S.SUPPORT_FROM} for {e(inst.get("name") or "")}. '
            f'Questions? Contact the school office or {e(S._support_contact())}.</p></td></tr></table>')
    text = (f"Dear {parent_name or 'Parent'},\nYou are invited to the {inst.get('name')} parent portal for {', '.join(children)}.\n"
            f"1) Open {link} (valid 72 hours)\n2) Choose your password\n3) Sign in at {login} with your mobile number.\n"
            f"Questions? Contact the school office or {S._support_contact()}.")
    return html, text, inst.get("name")


async def send_invite_email(iid, parent_uid, parent_name, email, children, link):
    html, text, school = await invite_email_html(iid, parent_name, children, link)
    try:
        mid = await S._support_send(email, f"Your {school} parent portal invitation", html)
        status, err = ("sent", None) if mid else ("failed", "email_not_configured")
    except S.EmailSendError as e:
        mid, status, err = None, "failed", e.reason
    await db.messages.insert_one({"id": str(uuid.uuid4()), "institution_id": iid, "channel": "email", "direction": "outbound",
                                  "provider": "resend", "provider_message_id": mid, "recipient_name": parent_name,
                                  "recipient_email": email, "body": text, "module": "parent_invite", "status": status,
                                  "error": err, "meta": {"parent_user_id": parent_uid}, "created_at": S.now_iso()})
    await asyncio.sleep(0.6)  # keep bulk email under the provider's per-second limit
    return {"status": status, "message_id": mid, "error": err}


async def send_invite_multi(iid, school_name, parent, channels, children):
    """Per-channel delivery for one parent; returns {channel: status} plus email message id."""
    ref = "psetup:" + parent["id"]
    link = f"{S.os.environ['PUBLIC_BASE_URL']}/setup/parent/{S._make_secure_link(iid, ref, 72)}"
    out = {}
    for ch in channels:
        if ch == "email":
            em = real_email(parent) or parent.get("contact_email")
            if not em:
                out["email"] = "skipped_no_email"
                continue
            r = await send_invite_email(iid, parent["id"], parent.get("name"), em, children, link)
            out["email"] = r["status"]
            out["email_message_id"] = r["message_id"]
            if r["error"]:
                out["email_error"] = r["error"]
        elif not parent.get("phone"):
            out[ch] = "skipped_no_phone"
        else:
            out[ch] = await S._send_parent_invite(iid, school_name, parent["id"], parent.get("name"), parent["phone"], ch)
    return out


def overall(res: dict) -> str:
    vals = [v for k, v in res.items() if k in INVITE_CHANNELS]
    return "sent" if "sent" in vals else "failed" if "failed" in vals else "skipped"


@S.app.on_event("startup")
async def _phase58_indexes():
    await db.parent_threads.create_index([("institution_id", 1), ("parent_id", 1), ("last_message_at", -1)])
    await db.parent_threads.create_index([("institution_id", 1), ("class_name", 1)])
    await db.parent_messages.create_index([("thread_id", 1), ("created_at", 1)])
