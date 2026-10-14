"""Phase 60: bulk enrol from a fee-apply result (+ retry), and email-only parent invites with single-use setup links."""
import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

from tests.test_phase58 import API, E, TAG, db, login
from tests.test_phase58 import ctx as _p58_ctx  # noqa: F401  (fixture reused via getfixturevalue)


@pytest.fixture(scope="module")
def c(request):
    return request.getfixturevalue("_p58_ctx")


def _student(c, **k):
    s = {"id": str(uuid.uuid4()), "institution_id": c["iid"], "enrollment_status": "enrolled", **k}
    db.students.insert_one(dict(s))
    return s


def test_bulk_enrol_then_retry_apply(c):
    iid = c["iid"]
    a = login(c["U"]["admin"]["email"])
    db.academic_years.insert_one({"id": str(uuid.uuid4()), "institution_id": iid, "name": "2026-27"})
    sid = str(uuid.uuid4())
    db.fee_structures.insert_one({"id": sid, "institution_id": iid, "name": f"P60 fees {TAG}", "academic_year": "2026-27", "class_name": "Grade 8",
                                  "active": True, "status": "active", "heads": [{"id": "h1", "title": "Tuition", "amount": 900, "frequency": "term"}]})
    ne1 = _student(c, first_name="Asha", last_name="NE", class_name="Grade 8", section="A", enrollment_status="not_enrolled", admission_no=f"NE1-{TAG}")
    ne2 = _student(c, first_name="Bina", last_name="NE", class_name="Grade 8", enrollment_status="not_enrolled")
    off = _student(c, first_name="Chet", last_name="Off", class_name="Grade 8", section="A", status="inactive")
    r = a.post(f"{API}/fees/structures/{sid}/apply").json()
    codes = {i["id"]: i["reason_code"] for i in r["items"]}
    assert codes[ne1["id"]] == codes[ne2["id"]] == "not_enrolled" and codes[off["id"]] == "inactive"
    pv = a.get(f"{API}/bulk-runs/{r['run_id']}/enrol-preview").json()
    rows = {x["student_id"]: x for x in pv["rows"]}
    assert pv["academic_year"] == "2026-27" and pv["classes"]["Grade 8"] == ["A"] and pv["can_retry"]
    assert rows[ne1["id"]]["status"] == "ready" and rows[ne1["id"]]["section"] == "A"
    assert rows[ne2["id"]]["status"] == "pick" and rows[ne2["id"]]["section"] is None
    assert rows[off["id"]]["status"] == "skip" and rows[off["id"]]["reason"] == "Student inactive — open student"
    assert login(c["U"]["plp"]["email"]).get(f"{API}/bulk-runs/{r['run_id']}/enrol-preview").json()["classes"].get("Grade 8") is None
    body = {"academic_year": "2026-27", "retry": True, "rows": [
        {"student_id": ne1["id"], "class_name": "Grade 8", "section": "A"},
        {"student_id": ne2["id"], "class_name": "Grade 8", "section": None},
        {"student_id": off["id"], "class_name": "Grade 8", "section": "A"}]}
    bad = a.post(f"{API}/bulk-runs/{r['run_id']}/enrol", json=body).json()
    by = {i["id"]: i for i in bad["items"]}
    assert by[ne2["id"]]["reason"] == "Pick a section of Grade 8" and by[off["id"]]["reason_code"] == "inactive"
    assert by[ne1["id"]]["status"] == "created" and bad["retry"]["created"] == 1  # only the enrolled student retried
    body["rows"][1]["section"] = "A"
    ok = a.post(f"{API}/bulk-runs/{r['run_id']}/enrol", json=body).json()
    by = {i["id"]: i for i in ok["items"]}
    assert by[ne1["id"]]["reason"] == "Already enrolled for this academic year" or by[ne1["id"]]["status"] == "skipped"
    assert by[ne2["id"]]["status"] == "created" and ok["parent_run_id"] == r["run_id"]
    assert ok["retry"]["created"] == 1 and ok["retry"]["parent_run_id"] == ok["run_id"]
    assert {i["id"] for i in ok["retry"]["items"]} == {ne2["id"]}
    assert db.students.find_one({"id": ne2["id"]})["enrollment_status"] == "enrolled"
    # idempotent: nothing duplicated on further runs
    again = a.post(f"{API}/fees/structures/{sid}/apply").json()
    assert again["created"] == 0
    for s in (ne1, ne2):
        assert db.fee_accounts.count_documents({"structure_id": sid, "student_id": s["id"]}) == 1
        assert db.enrollments.count_documents({"student_id": s["id"], "academic_year": "2026-27"}) == 1
    assert db.bulk_runs.find_one({"id": ok["retry"]["run_id"]})["parent_run_id"] == ok["run_id"]


def _setup_token(email):
    m = db.messages.find_one({"recipient_email": email, "module": "parent_invite"}, sort=[("created_at", -1)])
    assert m and m["provider_message_id"], m
    return re.search(r"/setup/parent/([\w-]+)", m["body"]).group(1)


def test_email_only_invite_and_setup(c):
    iid = c["iid"]
    a = login(c["U"]["admin"]["email"])
    em = E("eo")
    s1 = _student(c, first_name="Esha", last_name="Only", class_name="Grade 8", section="A", guardian_name="Mrs Only", guardian_email=em.upper())
    sms = a.post(f"{API}/students/{s1['id']}/invite-parent", json={"channels": ["sms", "whatsapp"]}).json()
    assert sms["items"][0]["reason"] == "No phone — select Email" and not db.users.find_one({"email": em})
    r = a.post(f"{API}/students/{s1['id']}/invite-parent", json={"channels": ["email", "sms"]}).json()
    inv = r["invited"][0]
    assert inv["channels"]["email"] == "sent" and inv["channels"]["email_message_id"] and inv["channels"]["sms"] == "skipped_no_phone"
    p = db.users.find_one({"email": em})
    assert p["role"] == "parent" and p["phone"] is None and p["student_ids"] == [s1["id"]]
    old = _setup_token(em)
    # already linked → no second account
    a.post(f"{API}/students/{s1['id']}/invite-parent", json={"channels": ["email"]})
    assert db.users.count_documents({"email": em}) == 1
    # reminder by email mints a fresh link and invalidates the old one
    cls = db.classes.find_one({"institution_id": iid, "name": "Grade 8"})
    rem = a.post(f"{API}/students/invite-reminder", json={"class_id": cls["id"], "channels": ["email"]}).json()
    assert any(x["parent_id"] == p["id"] and x["channels"]["email"] == "sent" for x in rem["results"])
    new = _setup_token(em)
    assert new != old
    assert requests.get(f"{API}/public/parent-setup/{old}").status_code == 410
    info = requests.get(f"{API}/public/parent-setup/{new}").json()
    assert info["single_use"] and info["children"][0]["name"].startswith("Esha")
    d = a.get(f"{API}/parents/{p['id']}").json()
    assert d["onboarding"]["status"] == "link_opened" and d["onboarding"]["link"]["opened_at"]
    assert a.get(f"{API}/parents", params={"status": "link_opened"}).json()["items"][0]["id"] == p["id"]
    assert requests.post(f"{API}/public/parent-setup/{new}", json={"password": "weak"}).status_code == 400
    sess = requests.Session()
    done = sess.post(f"{API}/public/parent-setup/{new}", json={"password": "Setup@2026a", "name": "Mrs Esha Only", "phone": "77" + TAG.encode().hex()[:8]})
    assert done.status_code == 200, done.text
    kids = sess.get(f"{API}/parent/children").json()
    assert [k["id"] for k in (kids if isinstance(kids, list) else kids.get("children", []))] == [s1["id"]]
    assert requests.post(f"{API}/public/parent-setup/{new}", json={"password": "Setup@2026b"}).status_code == 410
    assert login(em, "Setup@2026a").get(f"{API}/auth/me").json()["must_change_password"] is False
    u = db.users.find_one({"id": p["id"]})
    assert u["name"] == "Mrs Esha Only" and u["phone"] and a.get(f"{API}/parents/{p['id']}").json()["onboarding"]["status"] == "linked"
    # expired link is rejected
    s2 = _student(c, first_name="Exp", last_name="Kid", class_name="Grade 8", section="A", guardian_email=E("ex"))
    a.post(f"{API}/students/{s2['id']}/invite-parent", json={"channels": ["email"]})
    tok = _setup_token(E("ex"))
    db.parent_setup_tokens.update_many({"user_id": db.users.find_one({"email": E("ex")})["id"]},
                                       {"$set": {"expires_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()}})
    assert requests.get(f"{API}/public/parent-setup/{tok}").status_code == 410
    assert a.get(f"{API}/parents", params={"status": "expired"}).json()["total"] >= 1


def test_no_duplicate_parents(c):
    a = login(c["U"]["admin"]["email"])
    em = E("dup")
    s1 = _student(c, first_name="Dua", last_name="One", class_name="Grade 8", section="A", guardian_email=em)
    s2 = _student(c, first_name="Dua", last_name="Two", class_name="Grade 8", section="A", guardian_email=em)
    a.post(f"{API}/students/{s1['id']}/invite-parent", json={"channels": ["email"]})
    r = a.post(f"{API}/students/{s2['id']}/invite-parent", json={"channels": ["email"]}).json()
    assert r["invited"][0]["action"] == "linked_sibling"
    pid = db.users.find_one({"email": em})["id"]
    # a phone guardian with the same email → reuses the email-only parent and attaches the phone
    ph = "66" + TAG.encode().hex()[:8]
    s3 = _student(c, first_name="Dua", last_name="Three", class_name="Grade 8", section="A", guardian_email=em, guardian_phone=ph, guardian_name="Mr Dua")
    a.post(f"{API}/students/{s3['id']}/invite-parent", json={"channels": ["whatsapp"]})
    assert db.users.count_documents({"email": em}) == 1 and db.users.count_documents({"phone": ph, "role": "parent"}) == 1
    u = db.users.find_one({"id": pid})
    assert u["phone"] == ph and set(u["student_ids"]) == {s1["id"], s2["id"], s3["id"]}
    # admin adding a phone to an email-only parent keeps one account; a taken phone is refused
    s4 = _student(c, first_name="Solo", last_name="Mail", class_name="Grade 8", section="A", guardian_email=E("solo"))
    a.post(f"{API}/students/{s4['id']}/invite-parent", json={"channels": ["email"]})
    p4 = db.users.find_one({"email": E("solo")})
    assert a.patch(f"{API}/parents/{p4['id']}", json={"phone": ph}).status_code == 409
    assert a.patch(f"{API}/parents/{p4['id']}", json={"phone": "55" + TAG.encode().hex()[:8]}).status_code == 200
    assert db.users.count_documents({"email": E("solo")}) == 1
