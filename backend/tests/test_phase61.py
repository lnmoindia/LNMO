"""Phase 61: class teacher for parents, chat by child, consecutive WS delivery, photos, submission review/redo, upload limits."""
import asyncio
import io
import json
import uuid

import pytest
import requests
import websockets
from PIL import Image

from tests.test_phase58 import API, db, login
from tests.test_phase58 import ctx as _p58_ctx  # noqa: F401

WS = API.replace("https://", "wss://") + "/ws/chat"


@pytest.fixture(scope="module")
def c(request):
    return request.getfixturevalue("_p58_ctx")


def _cookie(s):
    return "; ".join(f"{k}={v}" for k, v in s.cookies.get_dict().items())


def _jpeg(w, h, noise=True, q=95):
    import numpy as np
    arr = (np.random.rand(h, w, 3) * 255).astype("uint8") if noise else np.full((h, w, 3), 120, "uint8")
    b = io.BytesIO()
    Image.fromarray(arr).save(b, "JPEG", quality=q)
    return b.getvalue()


def test_class_teacher_for_parent(c):
    U, S = c["U"], c["S"]
    p1 = login(U["p1"]["email"])
    d = p1.get(f"{API}/parent/child/{S['s8']['id']}").json()
    assert d["class_teacher"]["id"] == U["ct"]["id"] and d["class_teacher"]["name"] == "Class Teacher 8A"
    assert "photo_url" in d["class_teacher"] and "subject_teachers" in d
    tt = p1.get(f"{API}/parent/child/{S['s8']['id']}/timetable").json()
    assert tt["class_teacher"]["id"] == U["ct"]["id"]


def test_chat_threads_by_child(c):
    U, S = c["U"], c["S"]
    db.users.update_one({"id": U["p1"]["id"]}, {"$addToSet": {"student_ids": S["s4"]["id"]}})
    ct, p1 = login(U["ct"]["email"]), login(U["p1"]["email"])
    tid = ct.post(f"{API}/chat/threads", data={"student_id": S["s8"]["id"], "parent_id": U["p1"]["id"], "body": "hi"}).json()["thread"]["id"]
    a = p1.get(f"{API}/chat/threads", params={"student_id": S["s8"]["id"]}).json()
    assert tid in [t["id"] for t in a["threads"]] and all(t["student_id"] == S["s8"]["id"] for t in a["threads"])
    b = p1.get(f"{API}/chat/threads", params={"student_id": S["s4"]["id"]}).json()
    assert b["threads"] == [] and b["unread_selected"] == 0
    assert a["unread_by_student"].get(S["s8"]["id"], 0) >= 1
    u = p1.get(f"{API}/chat/unread").json()
    assert u["by_student"][S["s8"]["id"]] == a["unread_by_student"][S["s8"]["id"]]
    det = p1.get(f"{API}/chat/threads/{tid}").json()
    assert {x["id"] for x in det["participants"]} >= {U["ct"]["id"], U["p1"]["id"]}
    db.users.update_one({"id": U["p1"]["id"]}, {"$pull": {"student_ids": S["s4"]["id"]}})


def test_three_consecutive_messages_arrive_in_order(c):
    U, S = c["U"], c["S"]
    ct, p1 = login(U["ct"]["email"]), login(U["p1"]["email"])
    tid = ct.post(f"{API}/chat/threads", data={"student_id": S["s8"]["id"], "parent_id": U["p1"]["id"], "subject": "ws order"}).json()["thread"]["id"]

    async def run():
        async with websockets.connect(WS, additional_headers={"Cookie": _cookie(p1)}) as wp:
            assert json.loads(await asyncio.wait_for(wp.recv(), 5))["type"] == "hello"
            ids = []
            for i in range(3):
                r = await asyncio.to_thread(ct.post, f"{API}/chat/threads/{tid}/messages", data={"body": f"msg {i}"})
                ids.append(r.json()["message"]["id"])
            got = []
            while len(got) < 3:
                ev = json.loads(await asyncio.wait_for(wp.recv(), 5))
                if ev["type"] == "message" and ev["thread_id"] == tid:
                    got.append(ev["message_id"])
            assert got == ids
    asyncio.run(run())


def test_photos_resized_signed_and_scoped(c):
    U, S = c["U"], c["S"]
    a, p1 = login(U["admin"]["email"]), login(U["p1"]["email"])
    r = a.post(f"{API}/photos/students/{S['s8']['id']}", files={"file": ("p.jpg", _jpeg(1600, 1200, noise=False), "image/jpeg")})
    assert r.status_code == 200, r.text
    full, thumb = r.json()["photo_url"], r.json()["thumb_url"]
    img = requests.get(full)  # no cookies: signed URL
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(img.content)).size == (512, 512)
    assert Image.open(io.BytesIO(requests.get(thumb).content)).size == (128, 128)
    assert requests.get(full.split("?")[0] + "?sig=bad").status_code == 404
    assert p1.post(f"{API}/photos/users/{U['ct']['id']}", files={"file": ("p.jpg", _jpeg(300, 300), "image/jpeg")}).status_code == 403
    assert p1.post(f"{API}/photos/me", files={"file": ("p.jpg", _jpeg(300, 300), "image/jpeg")}).status_code == 200
    assert p1.get(f"{API}/auth/me").json()["photo_url"]
    kid = p1.get(f"{API}/parent/child/{S['s8']['id']}").json()["student"]
    assert kid["thumb_url"]
    assert db.audit_logs.find_one({"entity_id": S["s8"]["id"], "action": "upload_photo"})


def test_submission_review_and_redo(c):
    U, S, iid = c["U"], c["S"], c["iid"]
    hw = {"id": str(uuid.uuid4()), "institution_id": iid, "academic_year": "2026-27", "class_name": "Grade 8", "section": "A",
          "subject": "Science", "teacher_id": U["ct"]["id"], "title": "P61 cells", "instructions": "", "attachments": [],
          "due_date": "2099-12-31", "status": "open", "created_at": "2026-10-14T00:00:00+00:00"}
    db.homework.insert_one(dict(hw))
    st, ct, plain = login(U["stu"]["email"]), login(U["ct"]["email"]), login(U["plain"]["email"])
    r = st.post(f"{API}/homework/{hw['id']}/submit", data={"note": "first try"}, files=[("files", ("a.jpg", _jpeg(800, 600), "image/jpeg"))])
    assert r.status_code == 200, r.text
    sub_id = r.json()["submission"]["id"]
    b = ct.get(f"{API}/homework/{hw['id']}/submission-board").json()
    assert b["counts"]["submitted"] == 1 and b["counts"]["not_submitted"] >= 1
    assert ct.get(f"{API}/homework/{hw['id']}/submission-board", params={"filter": "not_submitted"}).json()["rows"][0]["state"] == "not_submitted"
    assert plain.get(f"{API}/homework/{hw['id']}/submission-board").status_code == 403
    assert ct.post(f"{API}/submissions/homework/{sub_id}/redo", json={"feedback": " "}).status_code == 400
    d = ct.post(f"{API}/submissions/homework/{sub_id}/redo", json={"feedback": "Label the nucleus", "due_date": "2099-12-30"}).json()
    assert d["submission"]["state"] == "redo_requested" and d["submission"]["redo_due_date"] == "2099-12-30"
    assert db.notifications.find_one({"user_id": U["stu"]["id"], "type": "homework_redo"})
    assert db.notifications.find_one({"user_id": U["p1"]["id"], "type": "homework_redo"})
    mine = st.get(f"{API}/submissions/homework/{sub_id}").json()
    assert mine["can_review"] is False and mine["submission"]["feedback"] == "Label the nucleus"
    r = st.post(f"{API}/homework/{hw['id']}/submit", data={"note": "second try"}, files=[("files", ("b.jpg", _jpeg(400, 300), "image/jpeg"))])
    assert r.status_code == 200
    d = ct.get(f"{API}/submissions/homework/{sub_id}").json()
    assert d["submission"]["attempt"] == 2 and d["submission"]["state"] == "submitted"
    assert len(d["previous_attempts"]) == 1 and d["previous_attempts"][0]["note"] == "first try"
    assert d["previous_attempts"][0]["feedback"] == "Label the nucleus"
    old = ct.get(f"{API}{d['previous_attempts'][0]['attachments'][0]['url'][4:]}")
    assert old.status_code == 200 and old.headers["content-type"] == "image/jpeg"
    d = ct.post(f"{API}/submissions/homework/{sub_id}/review", json={"feedback": "Great"}).json()
    assert d["submission"]["state"] == "reviewed"
    assert ct.get(f"{API}/homework/{hw['id']}/submission-board", params={"filter": "reviewed"}).json()["rows"][0]["submission_id"] == sub_id
    # assignments share the same model; marks validated against max_marks
    asg = {**hw, "id": str(uuid.uuid4()), "title": "P61 project", "max_marks": 20, "counts_toward_report": True}
    db.assignments.insert_one(dict(asg))
    sid2 = st.post(f"{API}/assignments/{asg['id']}/submit", data={"note": "done"}).json()["submission"]["id"]
    assert ct.post(f"{API}/submissions/assignments/{sid2}/review", json={"score": 25}).status_code == 400
    d = ct.post(f"{API}/submissions/assignments/{sid2}/review", json={"score": 18, "feedback": "Nice"}).json()
    assert d["submission"]["score"] == 18 and d["supports_marks"] is True


def test_upload_limits_json(c):
    U, S = c["U"], c["S"]
    ct = login(U["ct"]["email"])
    tid = ct.post(f"{API}/chat/threads", data={"student_id": S["s8"]["id"], "parent_id": U["p1"]["id"], "subject": "big photo"}).json()["thread"]["id"]
    big = _jpeg(4000, 3000)
    assert len(big) > 5 * 1024 * 1024
    r = ct.post(f"{API}/chat/threads/{tid}/messages", data={"body": "photo"}, files={"file": ("big.jpg", big, "image/jpeg")})
    assert r.status_code == 200, r.text
    assert r.json()["message"]["attachment"]["size"] < 5 * 1024 * 1024
    r = requests.post(f"{API}/scan/process", data=b"x" * (26 * 1024 * 1024), headers={"Content-Type": "application/octet-stream"})
    assert r.status_code == 413 and r.json()["code"] == "PAYLOAD_TOO_LARGE"
    a = login(U["admin"]["email"])
    d = a.get(f"{API}/diag/uploads").json()
    assert d["storage"]["ok"] and d["scanner_ready"] and d["max_body_mb"] == 25
    assert ct.get(f"{API}/diag/uploads").status_code == 403
