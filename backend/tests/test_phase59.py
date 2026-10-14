"""Phase 59: bulk-run details (fee apply reasons + retry), quick replies, real-time chat over WebSockets."""
import asyncio
import json
import uuid

import pytest
import requests
import websockets

from tests.test_phase58 import API, PW, TAG, db, login
from tests.test_phase58 import ctx as _p58_ctx  # noqa: F401  (fixture reused via getfixturevalue)

WS = API.replace("https://", "wss://") + "/ws/chat"


@pytest.fixture(scope="module")
def c(request):
    return request.getfixturevalue("_p58_ctx")


def _structure(c):
    sid = str(uuid.uuid4())
    db.fee_structures.insert_one({"id": sid, "institution_id": c["iid"], "name": f"P59 fees {TAG}", "academic_year": "2026-27",
                                  "class_name": "Grade 8", "active": True, "status": "active", "created_at": "2026-10-14T00:00:00+00:00",
                                  "heads": [{"id": "h1", "title": "Tuition", "amount": 1000, "frequency": "term", "optional": False}]})
    return sid


def test_fee_apply_reasons_fix_and_retry(c):
    iid = c["iid"]
    a = login(c["U"]["admin"]["email"])
    pending = {"id": str(uuid.uuid4()), "institution_id": iid, "first_name": "Pending", "last_name": "Kid", "class_name": "Grade 8",
               "section": "A", "admission_no": f"PEND-{TAG}", "enrollment_status": "not_enrolled"}
    gone = {"id": str(uuid.uuid4()), "institution_id": iid, "first_name": "Gone", "last_name": "Kid", "class_name": "Grade 8",
            "section": "A", "enrollment_status": "enrolled", "status": "inactive"}
    db.students.insert_many([dict(pending), dict(gone)])
    sid = _structure(c)
    r = a.post(f"{API}/fees/structures/{sid}/apply").json()
    by = {i["id"]: i for i in r["items"]}
    assert r["created"] == 3 and r["summary"]["created"] == 3 and r["summary"]["skipped"] == 2 and r["run_id"]
    assert by[pending["id"]]["reason_code"] == "not_enrolled" and by[pending["id"]]["fix"]["type"] == "enrol_student"
    assert by[pending["id"]]["sub_label"].startswith(f"PEND-{TAG}")
    assert by[gone["id"]]["reason"] == "Student inactive"
    assert all(len(x) == 2 for x in [r["skipped"]]) and {"student_name", "reason"} <= set(r["skipped"][0])  # legacy shape kept
    # the user's case: running again → 0 created, everyone skipped with a reason + ledger link
    r2 = a.post(f"{API}/fees/structures/{sid}/apply").json()
    assert r2["created"] == 0 and r2["summary"]["skipped"] == 5
    s8 = {i["id"]: i for i in r2["items"]}[c["S"]["s8"]["id"]]
    assert s8["reason"] == f"Already has an account for 2026-27 under 'P59 fees {TAG}'" and s8["fix"]["type"] == "open_ledger"
    assert db.fee_accounts.find_one({"id": s8["fix"]["target"]})["student_id"] == c["S"]["s8"]["id"]
    # fix (enrol) then retry → created
    db.students.update_one({"id": pending["id"]}, {"$set": {"enrollment_status": "enrolled"}})
    r3 = a.post(f"{API}/fees/structures/{sid}/apply").json()
    assert r3["created"] == 1 and {i["id"]: i for i in r3["items"]}[pending["id"]]["status"] == "created"
    # run is stored, linked from the structure card and from a notification
    run = a.get(f"{API}/bulk-runs/{r3['run_id']}").json()
    assert run["kind"] == "fee_apply" and len(run["items"]) == 5
    st = [x for x in a.get(f"{API}/fees/structures").json()["structures"] if x["id"] == sid][0]
    assert st["last_apply"]["id"] == r3["run_id"] and "items" not in st["last_apply"]
    assert db.notifications.find_one({"user_id": c["U"]["admin"]["id"], "type": "bulk_result", "related_id": r3["run_id"]})
    assert login(c["U"]["p1"]["email"]).get(f"{API}/bulk-runs/{r3['run_id']}").status_code == 404
    # generate invoices + defaulter reminders use the same shape
    g = a.post(f"{API}/fees/structures/{sid}/generate", json={"frequency": "term", "periods": [{"label": "T1", "due_date": "2026-06-10"}]}).json()
    assert g["created"] == 4 and g["summary"]["created"] == 4 and g["items"][0]["fix"]["type"] == "open_ledger"
    g2 = a.post(f"{API}/fees/structures/{sid}/generate", json={"frequency": "term", "periods": [{"label": "T1", "due_date": "2026-06-10"}]}).json()
    assert g2["skipped_existing"] == 4 and g2["summary"]["skipped"] == 4 and g2["items"][0]["reason"] == "All selected periods already invoiced"
    d = a.post(f"{API}/fees/defaulters/remind", json={"student_ids": [c["S"]["s8"]["id"]]}).json()
    assert d["run_id"] and d["items"][0]["label"] and d["items"][0]["fix"]["type"] == "open_ledger"
    inv = a.post(f"{API}/students/invite-parents", json={"all": True, "channels": ["whatsapp"]}).json()
    assert inv["run_id"] and inv["summary"]["total"] == len(inv["items"]) and "invited" in inv
    assert inv["items"] and all(i["reason"] for i in inv["items"])


def test_quick_replies(c):
    U = c["U"]
    a, ct = login(U["admin"]["email"]), login(U["ct"]["email"])
    assert ct.post(f"{API}/chat/quick-replies", json={"title": "x", "text": "y", "scope": "school"}).status_code == 403
    assert a.post(f"{API}/chat/quick-replies", json={"title": "Bad", "text": "{nope}", "scope": "school"}).status_code == 400
    s = a.post(f"{API}/chat/quick-replies", json={"title": "Fee", "text": "Dear {parent_name}, {child_name} ({class}) owes {fee_due}. — {teacher_name}, {school_name}", "scope": "school"}).json()
    mine = ct.post(f"{API}/chat/quick-replies", json={"title": "Mine", "text": "Hi {parent_name}", "scope": "personal"}).json()
    assert mine["scope"] == "personal"
    assert {r["id"] for r in ct.get(f"{API}/chat/quick-replies").json()["replies"]} >= {s["id"], mine["id"]}
    assert mine["id"] not in {r["id"] for r in a.get(f"{API}/chat/quick-replies").json()["replies"]}
    assert a.delete(f"{API}/chat/quick-replies/{mine['id']}").status_code == 403
    assert ct.patch(f"{API}/chat/quick-replies/{s['id']}", json={"text": "z"}).status_code == 403
    assert login(U["p1"]["email"]).get(f"{API}/chat/quick-replies").status_code == 403
    assert login(U["plain"]["email"]).get(f"{API}/chat/quick-replies").status_code == 403
    assert a.post(f"{API}/chat/quick-replies/suggested").json()["added"] == 6
    assert a.post(f"{API}/chat/quick-replies/suggested").json()["added"] == 0
    assert ct.delete(f"{API}/chat/quick-replies/{mine['id']}").status_code == 200
    assert db.quick_replies.find_one({"id": mine["id"]})["deleted"] is True
    t = ct.post(f"{API}/chat/threads", data={"student_id": c["S"]["s8"]["id"], "parent_id": U["p1"]["id"]}).json()["thread"]
    ph = ct.get(f"{API}/chat/threads/{t['id']}/placeholders").json()
    assert ph["child_name"] == "Kiran Rao" and ph["class"] == "Grade 8 A" and ph["teacher_name"] == "Class Teacher 8A" and ph["fee_due"].startswith("₹")
    assert login(U["p1"]["email"]).get(f"{API}/chat/threads/{t['id']}/placeholders").status_code == 403


def _cookie(sess):
    return "; ".join(f"{k}={v}" for k, v in sess.cookies.items())


def test_realtime_chat_ws(c):
    U, S = c["U"], c["S"]
    ct, p1, p2 = login(U["ct"]["email"]), login(U["p1"]["email"]), login(U["plp"]["email"])
    tid = ct.post(f"{API}/chat/threads", data={"student_id": S["s8"]["id"], "parent_id": U["p1"]["id"]}).json()["thread"]["id"]

    async def run():
        async with websockets.connect(WS, additional_headers={"Cookie": _cookie(ct)}) as wt, \
                websockets.connect(WS, additional_headers={"Cookie": _cookie(p1)}) as wp, \
                websockets.connect(WS, additional_headers={"Cookie": _cookie(p2)}) as wo:
            for w in (wt, wp, wo):
                assert json.loads(await asyncio.wait_for(w.recv(), 5))["type"] == "hello"

            async def wait_for(w, typ, timeout=2.0):
                while True:
                    ev = json.loads(await asyncio.wait_for(w.recv(), timeout))
                    if ev["type"] == typ:
                        return ev
            await wp.send(json.dumps({"type": "typing", "thread_id": tid}))
            ev = await wait_for(wt, "typing")
            assert ev["thread_id"] == tid and ev["user_id"] == U["p1"]["id"]
            await asyncio.to_thread(ct.post, f"{API}/chat/threads/{tid}/messages", data={"body": "live hello"})
            ev = await wait_for(wp, "message")
            assert ev["thread_id"] == tid
            assert (await wait_for(wp, "unread"))["thread_id"] == tid
            await asyncio.to_thread(p1.get, f"{API}/chat/threads/{tid}")
            assert (await wait_for(wt, "read"))["user_id"] == U["p1"]["id"]
            await wo.send(json.dumps({"type": "typing", "thread_id": tid}))  # not a participant → ignored
            with pytest.raises(asyncio.TimeoutError):
                await wait_for(wt, "typing", 1.0)
            with pytest.raises(asyncio.TimeoutError):
                await wait_for(wo, "message", 0.5)
    asyncio.run(run())


def test_ws_rejects_unauthenticated_and_forced_change(c):
    async def closed_code(headers):
        try:
            async with websockets.connect(WS, additional_headers=headers) as w:
                await asyncio.wait_for(w.recv(), 5)
        except websockets.exceptions.ConnectionClosed as e:
            return e.rcvd.code if e.rcvd else None
        except websockets.exceptions.InvalidStatus as e:
            return e.response.status_code
    assert asyncio.run(closed_code({})) in (4401, 403)
    s = requests.Session()
    a = login(c["U"]["admin"]["email"])
    a.post(f"{API}/users/{c['U']['plain']['id']}/set-password", json={"password": "Temp@2026q"})
    s = login(c["U"]["plain"]["email"], "Temp@2026q")
    assert asyncio.run(closed_code({"Cookie": _cookie(s)})) in (4403, 403)
    assert PW
