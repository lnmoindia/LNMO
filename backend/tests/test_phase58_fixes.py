"""Phase 58 follow-ups: link-child search by admission no, admission-no generation/uniqueness, server-side forced password change."""
import pytest

from tests.test_phase58 import API, TAG, db, login
from tests.test_phase58 import ctx as _p58_ctx  # noqa: F401  (fixture reused via getfixturevalue)


@pytest.fixture(scope="module")
def c(request):
    return request.getfixturevalue("_p58_ctx")


def test_link_child_search_by_admission(c):
    U, S = c["U"], c["S"]
    db.students.update_one({"id": S["s4"]["id"]}, {"$set": {"admission_no": f"SPS-{TAG}-001"}})
    a = login(U["admin"]["email"])
    url = f"{API}/parents/{U['p1']['id']}/link-candidates"
    for q in (f"SPS-{TAG}-001", f" sps {TAG} 001 ", f"sps{TAG}001".upper(), "001", TAG):
        res = a.get(url, params={"q": q}).json()["results"]
        hit = [r for r in res if r["id"] == S["s4"]["id"]]
        assert hit, q
        assert hit[0]["admission_no"] == f"SPS-{TAG}-001" and hit[0]["class_name"] == "Grade 4" and hit[0]["section"] == "A"
        assert hit[0]["parents"][0]["id"] == U["p2"]["id"] and hit[0]["already_linked"] is False
    assert a.get(url, params={"q": f"SPS-{TAG}-001"}).json()["results"][0]["id"] == S["s4"]["id"]  # exact ranks first
    named = a.get(url, params={"q": "lina das"}).json()["results"]
    assert [r["id"] for r in named] == [S["s4"]["id"]]
    mine = a.get(url, params={"q": "kiran"}).json()["results"]
    assert mine[0]["id"] == S["s8"]["id"] and mine[0]["already_linked"] is True
    assert a.get(url, params={"q": "zzzz-nothing"}).json()["results"] == []
    # other institutions never appear
    assert all(db.students.find_one({"id": r["id"]})["institution_id"] == c["iid"] for r in a.get(url, params={"q": "1"}).json()["results"])
    assert login(U["ct"]["email"]).get(url, params={"q": "001"}).status_code == 403


def test_admission_number_generation_and_uniqueness(c):
    U = c["U"]
    a = login(U["admin"]["email"])
    r = a.get(f"{API}/students/next-admission-no", params={"class_name": "Grade 8"}).json()
    assert "-G8-" in r["admission_no"] and r["provisional"] is False
    r = a.get(f"{API}/students/next-admission-no").json()
    assert "-GX-" in r["admission_no"] and r["provisional"] is True
    ok = a.post(f"{API}/students/enroll", json={"first_name": "Uniq", "admission_no": f"U-{TAG}", "enroll": False})
    assert ok.status_code == 200 and ok.json()["student"]["admission_no"] == f"U-{TAG}" if "student" in ok.json() else ok.status_code == 200
    dup = a.post(f"{API}/students/enroll", json={"first_name": "Dup", "admission_no": f" u-{TAG.upper()} ", "enroll": False})
    assert dup.status_code == 409
    assert a.post(f"{API}/res/students", json={"first_name": "Dup2", "admission_no": f"U-{TAG}"}).status_code == 409
    sid = db.students.find_one({"institution_id": c["iid"], "first_name": "Kiran"})["id"]
    assert a.put(f"{API}/res/students/{sid}", json={"admission_no": f"U-{TAG}"}).status_code == 409
    assert a.put(f"{API}/res/students/{sid}", json={"first_name": "Kiran"}).status_code == 200  # unchanged number is fine
    gen = a.post(f"{API}/students/enroll", json={"first_name": "Auto", "enroll": False}).json()
    assert db.students.find_one({"institution_id": c["iid"], "first_name": "Auto"})["admission_no"]
    assert gen


def test_forced_password_change_enforced_on_server(c):
    U = c["U"]
    a = login(U["admin"]["email"])
    a.post(f"{API}/users/{U['plain']['id']}/set-password", json={"password": "Temp@2026x"})
    s = login(U["plain"]["email"], "Temp@2026x")
    for path in ("/notifications", "/chat/unread", "/parents", "/res/students"):
        r = s.get(f"{API}{path}")
        assert r.status_code == 403 and r.json()["detail"]["code"] == "PASSWORD_CHANGE_REQUIRED", path
    assert s.get(f"{API}/auth/me").json()["must_change_password"] is True
    assert s.get(f"{API}/platform/branding").status_code in (200, 403) and "PASSWORD_CHANGE_REQUIRED" not in s.get(f"{API}/platform/branding").text
    assert s.get(f"{API}/public/institutions/branding").status_code != 403
    assert s.post(f"{API}/auth/change-password", json={"new_password": "Own@2026yy"}).status_code == 200
    assert s.get(f"{API}/notifications").status_code == 200
    s2 = login(U["plain"]["email"], "Own@2026yy")
    assert s2.post(f"{API}/auth/logout").status_code == 200
