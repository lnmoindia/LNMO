# Phase 59: bulk-action run records, chat quick replies, real-time chat over WebSockets.
import asyncio
import re
import uuid

from fastapi import Body, Depends, HTTPException, WebSocket, WebSocketDisconnect

import phase58 as P
import server as S
from realtime import hub

api, db = S.api, S.db

# ---------- 1/2) Bulk-action run records ----------
OK_STATUSES = ("created", "sent", "linked")


def item(id_, label, status, reason="", reason_code=None, sub_label=None, fix=None):
    return {"id": id_, "label": label, "sub_label": sub_label, "status": status, "reason_code": reason_code or status,
            "reason": reason, "fix": fix}


def fix(type_, target):
    return {"type": type_, "target": target}


async def save_run(user, kind, title, items, ref_id=None, extra=None, notify=True, parent_run_id=None):
    """Persist one bulk run and return {run_id, summary, items} to merge into the endpoint's legacy response."""
    summary = {k: 0 for k in ("created", "sent", "linked", "skipped", "failed")}
    for it in items:
        summary[it["status"]] = summary.get(it["status"], 0) + 1
    summary["total"] = len(items)
    summary.update(extra or {})
    run = {"id": str(uuid.uuid4()), "institution_id": user.get("institution_id"), "kind": kind, "ref_id": ref_id, "title": title,
           "summary": summary, "items": items, "parent_run_id": parent_run_id, "actor_id": user["id"], "actor_name": user.get("name"), "created_at": S.now_iso()}
    await db.bulk_runs.insert_one(dict(run))
    if notify and user.get("institution_id"):
        bits = ", ".join(f"{v} {k}" for k, v in summary.items() if k in ("created", "sent", "linked", "skipped", "failed") and v)
        await S._notify(user["institution_id"], user["id"], "bulk_result", title, bits or "Nothing to do", run["id"])
    return {"run_id": run["id"], "summary": summary, "items": items, "parent_run_id": parent_run_id}


@api.get("/bulk-runs/{rid}")
async def get_bulk_run(rid: str, user: dict = Depends(S.get_current_user)):
    r = await db.bulk_runs.find_one({"id": rid, "institution_id": user.get("institution_id")}, {"_id": 0})
    if not r or user.get("role") not in ("institution_admin", "teacher"):
        raise HTTPException(status_code=404, detail="Result not found")
    if user["role"] == "teacher" and r["actor_id"] != user["id"] and not await S.active_principal(user):
        raise HTTPException(status_code=404, detail="Result not found")
    return r


@api.get("/bulk-runs")
async def list_bulk_runs(kind: str = "", ref_id: str = "", limit: int = 10, user: dict = Depends(S.require_admin_or_principal)):
    q = {"institution_id": user["institution_id"]}
    if kind:
        q["kind"] = kind
    if ref_id:
        q["ref_id"] = ref_id
    rows = await db.bulk_runs.find(q, {"_id": 0, "items": 0}).sort("created_at", -1).limit(min(limit, 50)).to_list(50)
    return {"runs": rows}


async def last_run(iid, kind, ref_id):
    return await db.bulk_runs.find_one({"institution_id": iid, "kind": kind, "ref_id": ref_id}, {"_id": 0, "items": 0}, sort=[("created_at", -1)])


REMIND_REASON = {
    "sent": ("sent", "Reminder sent"), "deduped": ("skipped", "Already reminded today"), "skipped_throttled": ("skipped", "Already reminded today"),
    "bell_only_no_phone": ("skipped", "No phone on file — bell notification only"), "no_contact": ("skipped", "No phone on file — bell notification only"),
    "bell_only_failed": ("failed", "Message failed — bell notification only"), "failed": ("failed", "Message failed"),
    "paid": ("skipped", "Already fully paid"), "no_dues": ("skipped", "Nothing due"), "out_of_scope": ("skipped", "Outside your scope"),
    "not_found": ("failed", "Student not found"),
}


async def reminder_items(results):
    inv_ids = [r["invoice_id"] for r in results if r.get("invoice_id")]
    accs = {i["id"]: i for i in await db.fee_invoices.find({"id": {"$in": inv_ids}}, {"_id": 0, "id": 1, "account_id": 1, "period_label": 1,
                                                                                         "class_name": 1, "section": 1, "student_id": 1}).to_list(10000)}
    out = []
    for r in results:
        inv = accs.get(r.get("invoice_id")) or {}
        st, reason = REMIND_REASON.get(r["status"], ("failed", r["status"]))
        sub = " · ".join(x for x in [f"{inv.get('class_name') or ''} {inv.get('section') or ''}".strip(), inv.get("period_label")] if x)
        f = fix("open_ledger", inv["account_id"]) if inv.get("account_id") else (fix("open_student", r.get("student_id")) if r.get("student_id") else None)
        out.append(item(r.get("invoice_id") or r.get("student_id"), r.get("student_name") or "Student", st, reason, r["status"], sub, f))
    return out


def invite_items(res):
    out = []
    for r in res.get("invited", []):
        per = r.get("channels") or {}
        failed = r.get("delivery") == "failed"
        chan = ", ".join(f"{k}: {v.replace('skipped_no_', 'no ').replace('skipped_', 'skipped ').replace('_', ' ')}" for k, v in per.items() if k in P.INVITE_CHANNELS)
        reason = ("Linked to sibling's parent account" if r.get("action") == "linked_sibling" else "Invite sent") + (f" ({chan})" if chan else "")
        out.append(item(r["student_id"], r["student_name"], "failed" if failed else ("linked" if r.get("action") == "linked_sibling" else "sent"),
                        "Delivery failed on every channel" + (f" ({chan})" if chan else "") if failed else reason,
                        "delivery_failed" if failed else r.get("action"), f"{r.get('class') or ''} · {r.get('phone') or r.get('email') or ''}", fix("open_student", r["student_id"])))
    for r in res.get("already_linked", []):
        out.append(item(r["student_id"], r["student_name"], "skipped", "A parent account is already linked", "already_linked", r.get("class"), fix("open_student", r["student_id"])))
    for r in res.get("skipped_no_phone", []):
        out.append(item(r["student_id"], r["student_name"], "skipped",
                        "No phone — select Email" if r.get("email_only") else "No guardian phone or email on file — add one or print a paper slip",
                        "no_phone_select_email" if r.get("email_only") else "no_phone", r.get("class"), fix("open_student", r["student_id"])))
    for r in res.get("collisions_for_review", []):
        out.append(item(r["student_id"], r["student_name"], "skipped", r.get("reason") or "Phone number is shared with a different guardian name — review before inviting",
                        "phone_collision", r.get("class"), fix("open_student", r["student_id"])))
    return out


# ---------- 3) Quick replies ----------
QR_MAX = 50
PLACEHOLDERS = ("parent_name", "child_name", "class", "school_name", "fee_due", "next_due_date", "teacher_name")
SUGGESTED = [
    ("Fee due reminder", "Dear {parent_name}, a gentle reminder that {child_name}'s fee of {fee_due} is due on {next_due_date}. Please pay at the office or online. Thank you — {school_name}"),
    ("School timings", "Dear {parent_name}, school runs from 9:00 am to 3:30 pm, Monday to Friday. The office is open 8:30 am – 4:30 pm."),
    ("Homework query received", "Thank you, {parent_name}. I've noted your question about {child_name}'s homework and will reply after checking with the subject teacher. — {teacher_name}"),
    ("Leave application received", "Dear {parent_name}, we've received the leave request for {child_name} ({class}). It has been recorded. Thank you for letting us know."),
    ("Meeting request", "Dear {parent_name}, I'd like to meet you briefly about {child_name}. Could you let me know a convenient day and time this week? — {teacher_name}"),
    ("We'll get back to you", "Thank you for your message, {parent_name}. We're looking into it and will get back to you shortly. — {school_name}"),
]


def qr_view(q, uid):
    return {"id": q["id"], "title": q["title"], "text": q["text"], "scope": "personal" if q.get("owner_id") else "school",
            "mine": q.get("owner_id") == uid, "updated_at": q.get("updated_at") or q.get("created_at")}


@api.get("/chat/quick-replies")
async def list_quick_replies(user: dict = Depends(S.get_current_user)):
    await P.staff_scope(user)
    iid = user["institution_id"]
    rows = await db.quick_replies.find({"institution_id": iid, "deleted": {"$ne": True}, "$or": [{"owner_id": None}, {"owner_id": user["id"]}]},
                                       {"_id": 0}).sort("title", 1).to_list(200)
    return {"replies": [qr_view(q, user["id"]) for q in rows], "can_manage": user["role"] == "institution_admin",
            "placeholders": list(PLACEHOLDERS), "max": QR_MAX}


def _clean_qr(body):
    title, text = (body.get("title") or "").strip()[:80], (body.get("text") or "").strip()
    if not title or not text:
        raise HTTPException(status_code=400, detail="Title and text are required")
    if len(text) > P.CHAT_MAX:
        raise HTTPException(status_code=400, detail=f"Text can be at most {P.CHAT_MAX} characters")
    bad = set(re.findall(r"\{(\w+)\}", text)) - set(PLACEHOLDERS)
    if bad:
        raise HTTPException(status_code=400, detail=f"Unknown placeholder {{{sorted(bad)[0]}}}. Use: " + ", ".join(f"{{{p}}}" for p in PLACEHOLDERS))
    return title, text


@api.post("/chat/quick-replies")
async def create_quick_reply(body: dict = Body(...), user: dict = Depends(S.get_current_user)):
    await P.staff_scope(user)
    iid = user["institution_id"]
    school = body.get("scope", "personal") == "school"
    if school and user["role"] != "institution_admin":
        raise HTTPException(status_code=403, detail="Only school admins manage school-wide quick replies")
    title, text = _clean_qr(body)
    owner = None if school else user["id"]
    if await db.quick_replies.count_documents({"institution_id": iid, "owner_id": owner, "deleted": {"$ne": True}}) >= QR_MAX:
        raise HTTPException(status_code=400, detail=f"You can have at most {QR_MAX} quick replies here")
    q = {"id": str(uuid.uuid4()), "institution_id": iid, "owner_id": owner, "title": title, "text": text, "created_by": user["id"],
         "created_at": S.now_iso(), "deleted": False}
    await db.quick_replies.insert_one(dict(q))
    await S.audit(user, "quick_reply_create", "quick_replies", q["id"], f"{'school' if school else 'personal'} · {title}", iid)
    return qr_view(q, user["id"])


async def _own_qr(user, qid):
    q = await db.quick_replies.find_one({"id": qid, "institution_id": user.get("institution_id"), "deleted": {"$ne": True}}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Quick reply not found")
    if (q.get("owner_id") and q["owner_id"] != user["id"]) or (not q.get("owner_id") and user["role"] != "institution_admin"):
        raise HTTPException(status_code=403, detail="You can't change this quick reply")
    return q


@api.patch("/chat/quick-replies/{qid}")
async def update_quick_reply(qid: str, body: dict = Body(...), user: dict = Depends(S.get_current_user)):
    q = await _own_qr(user, qid)
    title, text = _clean_qr({"title": body.get("title", q["title"]), "text": body.get("text", q["text"])})
    await db.quick_replies.update_one({"id": qid}, {"$set": {"title": title, "text": text, "updated_at": S.now_iso()}})
    await S.audit(user, "quick_reply_update", "quick_replies", qid, title, q["institution_id"])
    return qr_view({**q, "title": title, "text": text}, user["id"])


@api.delete("/chat/quick-replies/{qid}")
async def delete_quick_reply(qid: str, user: dict = Depends(S.get_current_user)):
    q = await _own_qr(user, qid)
    await db.quick_replies.update_one({"id": qid}, {"$set": {"deleted": True, "deleted_at": S.now_iso(), "deleted_by": user["id"]}})
    await S.audit(user, "quick_reply_delete", "quick_replies", qid, q["title"], q["institution_id"])
    return {"ok": True}


@api.post("/chat/quick-replies/suggested")
async def add_suggested_replies(user: dict = Depends(S.require_roles("institution_admin"))):
    iid = user["institution_id"]
    have = {q["title"] for q in await db.quick_replies.find({"institution_id": iid, "owner_id": None, "deleted": {"$ne": True}}, {"title": 1}).to_list(200)}
    add = [{"id": str(uuid.uuid4()), "institution_id": iid, "owner_id": None, "title": t, "text": x, "created_by": user["id"],
            "created_at": S.now_iso(), "deleted": False, "suggested": True} for t, x in SUGGESTED if t not in have]
    room = QR_MAX - len(have)
    add = add[:max(room, 0)]
    if add:
        await db.quick_replies.insert_many([dict(a) for a in add])
    await S.audit(user, "quick_reply_suggested", "quick_replies", None, f"{len(add)} added", iid)
    return {"added": len(add)}


@api.get("/chat/threads/{tid}/placeholders")
async def thread_placeholders(tid: str, user: dict = Depends(S.get_current_user)):
    if user["role"] == "parent":
        raise HTTPException(status_code=403, detail="Access denied")
    t = await P.thread_access(user, tid)
    iid = t["institution_id"]
    inst = await db.institutions.find_one({"id": iid}, {"_id": 0, "name": 1}) or {}
    fees = await S._student_fees(iid, t["student_id"])
    nd = fees["summary"].get("next_due")
    return {"parent_name": t.get("parent_name") or "Parent", "child_name": t.get("student_name") or "",
            "class": f"{t.get('class_name') or ''}{(' ' + t['section']) if t.get('section') else ''}".strip(), "school_name": inst.get("name") or "",
            "fee_due": f"₹{fees['summary']['balance']:,.0f}", "next_due_date": (nd or {}).get("due_date") if isinstance(nd, dict) else (nd or "—"),
            "teacher_name": user.get("name") or ""}


# ---------- 4) Real-time chat ----------
async def participants(t):
    return {t["parent_id"]} | await P.thread_staff_ids(t)


async def emit(t, event, exclude=None):
    """Thread event → everyone allowed to see the thread (+ an unread nudge so badges refresh)."""
    who = await participants(t)
    await hub.publish(who, {**event, "thread_id": t["id"]}, exclude=exclude)
    if event["type"] in ("message", "read", "status"):
        await hub.publish(who, {"type": "unread", "thread_id": t["id"]}, exclude=exclude if event["type"] == "message" else None)


@api.websocket("/ws/chat")
async def chat_socket(ws: WebSocket):
    try:
        user = await S.get_current_user(ws)
    except HTTPException as e:
        code = 4403 if isinstance(e.detail, dict) else 4401
        await ws.close(code=code)
        return
    if user["role"] not in ("parent", "teacher", "institution_admin"):
        await ws.close(code=4400)
        return
    await ws.accept()
    uid, allowed = user["id"], {}
    hub.add(uid, ws)
    await ws.send_json({"type": "hello", "user_id": uid})
    try:
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "ping":
                await ws.send_json({"type": "pong"})
            elif msg.get("type") == "typing" and msg.get("thread_id"):
                tid = msg["thread_id"]
                if tid not in allowed:
                    try:
                        allowed[tid] = await P.thread_access(user, tid)
                    except HTTPException:
                        allowed[tid] = None
                if allowed[tid]:
                    await emit(allowed[tid], {"type": "typing", "user_id": uid, "name": (user.get("name") or "").split(" ")[0]}, exclude=uid)
    except (WebSocketDisconnect, RuntimeError, ValueError):
        pass
    finally:
        hub.remove(uid, ws)


def fire(coro):
    asyncio.get_event_loop().create_task(coro)
