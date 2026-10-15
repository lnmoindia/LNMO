"""Phase 58: parent profiles, parent chat, staff password resets, multi-channel invites.
Runs against the preview API on a throwaway school (never LPGS); real email only to delivered+*@resend.dev."""
import uuid

import bcrypt
import pytest
import requests
from pymongo import MongoClient

API = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].rstrip("/") + "/api"


def _env(k):
    for line in open("/app/backend/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


db = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]
TAG = uuid.uuid4().hex[:6]
PW = "Passw0rd!x"
H = bcrypt.hashpw(PW.encode(), bcrypt.gensalt()).decode()
E = lambda n: f"delivered+p58{n}{TAG}@resend.dev"  # noqa: E731
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8ffff3f0005fe02fea7d6a4b40000000049454e44ae426082")


def login(ident, pw=PW):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ident, "password": pw})
    assert r.status_code == 200, (ident, r.text)
    return s


@pytest.fixture(scope="module")
def ctx():
    iid = str(uuid.uuid4())
    db.institutions.insert_one({"id": iid, "name": f"P58 Throwaway {TAG}", "code": f"P58{TAG}".upper(), "slug": f"p58{TAG}",
                                "status": "active", "setup_complete": True, "created_at": "2026-10-14T00:00:00+00:00"})
    u = lambda **k: {"id": str(uuid.uuid4()), "institution_id": iid, "password_hash": H, "status": "active", **k}  # noqa: E731
    U = {
        "admin": u(name="Admin", email=f"admin{TAG}@p58.test", role="institution_admin"),
        "ct": u(name="Class Teacher 8A", email=f"ct{TAG}@p58.test", role="teacher"),
        "plain": u(name="Plain Teacher", email=f"plain{TAG}@p58.test", role="teacher"),
        "phs": u(name="Principal HS", email=f"phs{TAG}@p58.test", role="teacher"),
        "plp": u(name="Principal LP", email=f"plp{TAG}@p58.test", role="teacher"),
        "stu": u(name="Kiran Student", email=f"kiran{TAG}@p58.test", role="student"),
    }
    S = {k: {"id": str(uuid.uuid4()), "institution_id": iid, "enrollment_status": "enrolled", **v} for k, v in {
        "s8": dict(first_name="Kiran", last_name="Rao", class_name="Grade 8", section="A", admission_no=f"K{TAG}"),
        "s4": dict(first_name="Lina", last_name="Das", class_name="Grade 4", section="A"),
        "inv_all": dict(first_name="Mira", last_name="Shah", class_name="Grade 8", section="A", guardian_name="Mr Shah",
                        guardian_phone="98" + TAG[:4].encode().hex()[:8], guardian_email=E("inv")),
        "inv_noemail": dict(first_name="Nikhil", last_name="Jain", class_name="Grade 8", section="A", guardian_name="Mr Jain",
                            guardian_phone="97" + TAG[2:6].encode().hex()[:8]),
    }.items()}
    S["s8"]["user_id"] = U["stu"]["id"]
    U["stu"]["student_id"] = S["s8"]["id"]
    U["p1"] = u(name="Parent One", email=E("p1"), role="parent", phone="9" + TAG.encode().hex()[:9], student_ids=[S["s8"]["id"]])
    U["p2"] = u(name="Parent Two", email=f"p2{TAG}@p58.parent.invite", role="parent", phone="8" + TAG.encode().hex()[:9],
                student_ids=[S["s4"]["id"]], invited=True, must_change_password=True)
    db.users.insert_many([dict(x) for x in U.values()])
    db.students.insert_many([dict(x) for x in S.values()])
    db.academic_units.insert_many([{"id": "hs" + TAG, "institution_id": iid, "name": "HS"}, {"id": "lp" + TAG, "institution_id": iid, "name": "LP"}])
    db.classes.insert_many([{"id": str(uuid.uuid4()), "institution_id": iid, "name": "Grade 8", "academic_unit_id": "hs" + TAG},
                            {"id": str(uuid.uuid4()), "institution_id": iid, "name": "Grade 4", "academic_unit_id": "lp" + TAG}])
    db.sections.insert_many([{"id": str(uuid.uuid4()), "institution_id": iid, "class_name": "Grade 8", "name": "A", "class_teacher_id": U["ct"]["id"]},
                             {"id": str(uuid.uuid4()), "institution_id": iid, "class_name": "Grade 4", "name": "A"}])
    db.principal_assignments.insert_many([
        {"id": str(uuid.uuid4()), "institution_id": iid, "user_id": U["phs"]["id"], "scope_type": "units", "unit_ids": ["hs" + TAG], "designation": "principal"},
        {"id": str(uuid.uuid4()), "institution_id": iid, "user_id": U["plp"]["id"], "scope_type": "units", "unit_ids": ["lp" + TAG], "designation": "principal"}])
    yield {"iid": iid, "U": U, "S": S}
    for col in db.list_collection_names():
        db[col].delete_many({"institution_id": iid})
    db.institutions.delete_one({"id": iid})


def test_parent_scoping(ctx):
    U = ctx["U"]
    a = login(U["admin"]["email"])
    r = a.get(f"{API}/parents").json()
    ids = {x["id"] for x in r["items"] if x["type"] == "parent"}
    assert {U["p1"]["id"], U["p2"]["id"]} <= ids and r["can_edit"] is True
    assert any(x["status"] == "not_invited" for x in r["items"])
    assert a.get(f"{API}/parents", params={"status": "invited"}).json()["items"][0]["id"] == U["p2"]["id"]
    assert a.get(f"{API}/parents", params={"search": "kiran"}).json()["items"][0]["id"] == U["p1"]["id"]
    ct = login(U["ct"]["email"])
    r = ct.get(f"{API}/parents").json()
    assert {x["id"] for x in r["items"] if x["type"] == "parent"} == {U["p1"]["id"]} and r["can_edit"] is False
    d = ct.get(f"{API}/parents/{U['p1']['id']}").json()
    assert d["parent"]["phone"] == U["p1"]["phone"] and d["children"][0]["fees"]["outstanding"] == 0
    assert ct.get(f"{API}/parents/{U['p2']['id']}").status_code == 403
    assert login(U["phs"]["email"]).get(f"{API}/parents/{U['p2']['id']}").status_code == 403
    assert login(U["plp"]["email"]).get(f"{API}/parents/{U['p2']['id']}").status_code == 200
    assert login(U["plain"]["email"]).get(f"{API}/parents").status_code == 403
    assert login(U["p1"]["email"]).get(f"{API}/parents").status_code == 403
    assert ct.patch(f"{API}/parents/{U['p1']['id']}", json={"name": "X"}).status_code == 403
    g = ct.get(f"{API}/students/{ctx['S']['s8']['id']}/guardians").json()
    assert g["parents"][0]["id"] == U["p1"]["id"]
    assert ct.get(f"{API}/students/{ctx['S']['s4']['id']}/guardians").status_code == 403


def test_admin_edit_audited_and_email_change(ctx):
    U = ctx["U"]
    a = login(U["admin"]["email"])
    assert a.patch(f"{API}/parents/{U['p1']['id']}", json={"phone": U["p2"]["phone"]}).status_code == 409
    assert a.patch(f"{API}/parents/{U['p1']['id']}", json={"email": U["admin"]["email"]}).status_code == 409
    new = E("p1new")
    r = a.patch(f"{API}/parents/{U['p1']['id']}", json={"email": new, "relation": "mother", "name": "Parent One Edited"}).json()
    assert set(r["notifications"]) == {U["p1"]["email"], new}
    assert all(v.get("message_id") for v in r["notifications"].values()), r
    log = db.audit_logs.find_one({"institution_id": ctx["iid"], "action": "parent_edit", "entity_id": U["p1"]["id"]})
    assert log and "relation" in log["entity_name"] and new in log["entity_name"]
    U["p1"]["email"] = new
    # link / unlink with audit
    assert a.post(f"{API}/parents/{U['p1']['id']}/children", json={"student_id": ctx["S"]["inv_noemail"]["id"]}).status_code == 200
    assert a.post(f"{API}/parents/{U['p1']['id']}/children/{ctx['S']['inv_noemail']['id']}/unlink").status_code == 200
    assert db.audit_logs.count_documents({"institution_id": ctx["iid"], "action": {"$in": ["parent_link_child", "parent_unlink_child"]}}) == 2


def test_chat_flow(ctx):
    U, S = ctx["U"], ctx["S"]
    ct, p1 = login(U["ct"]["email"]), login(U["p1"]["email"])
    r = ct.post(f"{API}/chat/threads", data={"student_id": S["s8"]["id"], "parent_id": U["p1"]["id"], "body": "Hello from class teacher"}).json()
    tid = r["thread"]["id"]
    assert r["nudge"]["channel"] == "email" and r["nudge"]["status"] == "sent" and r["nudge"]["message_id"]
    r2 = ct.post(f"{API}/chat/threads/{tid}/messages", data={"body": "Second note"}).json()
    assert r2["nudge"]["status"] == "throttled"
    assert ct.post(f"{API}/chat/threads/{tid}/messages", data={"body": "x" * 2001}).status_code == 400
    assert p1.get(f"{API}/chat/unread").json()["unread"] == 2
    assert db.notifications.count_documents({"user_id": U["p1"]["id"], "type": "parent_message"}) == 2
    t = p1.get(f"{API}/chat/threads/{tid}").json()
    assert len(t["messages"]) == 2 and t["can_moderate"] is False
    assert p1.get(f"{API}/chat/unread").json()["unread"] == 0
    assert all(m["seen"] for m in ct.get(f"{API}/chat/threads/{tid}").json()["messages"])
    r = p1.post(f"{API}/chat/threads/{tid}/messages", data={"body": "Thanks!"}, files={"file": ("note.png", PNG, "image/png")}).json()
    mid = r["message"]["id"]
    assert r["message"]["attachment"]["size"] == len(PNG)
    big = p1.post(f"{API}/chat/threads/{tid}/messages", data={"body": "big"}, files={"file": ("b.pdf", b"0" * (5 * 1024 * 1024 + 1), "application/pdf")})
    assert big.status_code == 413  # Phase 61: oversize uploads return JSON 413
    inbox = ct.get(f"{API}/chat/threads").json()
    assert inbox["threads"][0]["id"] == tid and inbox["threads"][0]["unread"] == 1
    assert ct.get(f"{API}/chat/messages/{mid}/attachment").content == PNG
    a = login(U["admin"]["email"])
    assert a.get(f"{API}/chat/threads/{tid}").status_code == 200
    assert login(U["plp"]["email"]).get(f"{API}/chat/threads/{tid}").status_code == 403
    assert login(U["plain"]["email"]).get(f"{API}/chat/threads/{tid}").status_code == 403
    p2 = login(U["p2"]["email"])
    assert p2.get(f"{API}/chat/threads/{tid}").status_code == 403
    assert p2.post(f"{API}/chat/threads", data={"student_id": S["s8"]["id"], "body": "hi"}).status_code == 403
    # parent can start a thread to the office; office sees it
    r = p1.post(f"{API}/chat/threads", data={"student_id": S["s8"]["id"], "target": "office", "body": "Question for the office"}).json()
    assert r["thread"]["target"] == "office"
    assert any(n["user_id"] == U["admin"]["id"] for n in db.notifications.find({"related_id": r["thread"]["id"]}))
    # hide keeps the message but masks it for the parent
    assert ct.post(f"{API}/chat/messages/{mid}/moderate", json={"action": "hide", "reason": "test"}).status_code == 200
    pm = [m for m in p1.get(f"{API}/chat/threads/{tid}").json()["messages"] if m["id"] == mid][0]
    assert pm["hidden"] and pm["attachment"] is None and db.parent_messages.find_one({"id": mid})["body"] == "Thanks!"
    assert p1.post(f"{API}/chat/threads/{tid}/status", json={"status": "closed"}).status_code == 403
    assert ct.post(f"{API}/chat/threads/{tid}/status", json={"status": "closed"}).status_code == 200
    assert p1.post(f"{API}/chat/threads/{tid}/messages", data={"body": "late"}).status_code == 409
    assert ct.post(f"{API}/chat/threads/{tid}/status", json={"status": "open"}).status_code == 200
    assert db.audit_logs.count_documents({"institution_id": ctx["iid"], "resource": "parent_threads"}) >= 6


def test_staff_password_reset(ctx):
    U = ctx["U"]
    a = login(U["admin"]["email"])
    old = login(U["stu"]["email"])
    assert a.post(f"{API}/users/{U['stu']['id']}/set-password", json={"password": "weak"}).status_code == 400
    r = a.post(f"{API}/users/{U['stu']['id']}/set-password", json={"password": "Fresh@2026a"}).json()
    assert r["must_change_password"] and r["generated_password"] is None
    assert old.get(f"{API}/auth/me").status_code == 401
    s = login(U["stu"]["email"], "Fresh@2026a")
    assert s.get(f"{API}/auth/me").json()["must_change_password"] is True
    assert s.post(f"{API}/auth/change-password", json={"new_password": "Fresh@2026a"}).status_code == 400
    assert s.post(f"{API}/auth/change-password", json={"new_password": "short"}).status_code == 400
    assert s.post(f"{API}/auth/change-password", json={"new_password": "Mine@2026b"}).status_code == 200
    assert login(U["stu"]["email"], "Mine@2026b").get(f"{API}/auth/me").json()["must_change_password"] is False
    log = db.audit_logs.find_one({"institution_id": ctx["iid"], "action": "password_set_by_staff", "entity_id": U["stu"]["id"]})
    assert log and "Fresh" not in str(log)
    # generated password via student record id, principal scope
    phs = login(U["phs"]["email"])
    g = phs.post(f"{API}/users/{ctx['S']['s8']['id']}/set-password", json={"generate": True}).json()
    assert len(g["generated_password"]) == 10
    assert phs.post(f"{API}/users/{U['p2']['id']}/set-password", json={"generate": True}).status_code == 403
    assert phs.post(f"{API}/users/{U['plp']['id']}/set-password", json={"generate": True}).status_code == 403
    assert phs.post(f"{API}/users/{U['admin']['id']}/set-password", json={"generate": True}).status_code == 403
    assert login(U["ct"]["email"]).post(f"{API}/users/{U['stu']['id']}/set-password", json={"generate": True}).status_code == 403
    # reset link (real email) — needs an email
    assert a.post(f"{API}/users/{U['p2']['id']}/reset-link").status_code == 400
    r = phs.post(f"{API}/users/{U['p1']['id']}/reset-link").json()
    assert r["message_id"] and r["sent_to"] == U["p1"]["email"]
    assert db.users.find_one({"id": U["p1"]["id"]})["must_change_password"] is True


def test_invite_channels(ctx):
    S, U = ctx["S"], ctx["U"]
    a = login(U["admin"]["email"])
    assert a.post(f"{API}/students/{S['inv_all']['id']}/invite-parent", json={"channels": []}).status_code == 400
    assert a.post(f"{API}/students/{S['inv_all']['id']}/invite-parent", json={"channels": ["fax"]}).status_code == 400
    r = a.post(f"{API}/students/{S['inv_all']['id']}/invite-parent", json={"channels": ["whatsapp", "sms", "email"]}).json()
    ch = r["invited"][0]["channels"]
    assert ch["whatsapp"] == "sent" and ch["sms"] == "sent" and ch["email"] == "sent" and ch["email_message_id"]
    m = db.messages.find_one({"institution_id": ctx["iid"], "channel": "email", "module": "parent_invite"})
    assert m["provider_message_id"] == ch["email_message_id"] and m["recipient_email"] == S["inv_all"]["guardian_email"]
    r = a.post(f"{API}/students/{S['inv_noemail']['id']}/invite-parent", json={"all_channels": True}).json()
    ch = r["invited"][0]["channels"]
    assert ch["email"] == "skipped_no_email" and ch["whatsapp"] == "sent"
    # legacy single channel still works
    p = db.users.find_one({"institution_id": ctx["iid"], "role": "parent", "phone": S["inv_noemail"]["guardian_phone"]})
    assert p and p["invited"]
