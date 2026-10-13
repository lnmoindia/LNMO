import os, json, requests
BASE = open("/app/frontend/.env").read()
BASE = [l for l in BASE.splitlines() if l.startswith("REACT_APP_BACKEND_URL")][0].split("=",1)[1].strip()+"/api"

def sess(e,pw):
    s=requests.Session(); r=s.post(f"{BASE}/auth/login",json={"email":e,"password":pw},timeout=30)
    return s, r.status_code

admin,_=sess("admin@lpgs.com","admin123")

# debug portal-user for one student
studs = admin.get(f"{BASE}/res/students", params={"limit":200}).json()["items"]
aarav = next((s for s in studs if s["first_name"]=="Aarav"), None)
print("Aarav has_portal_access:", aarav.get("has_portal_access"))
r = admin.post(f"{BASE}/students/{aarav['id']}/portal-user", json={})
print("portal-user status:", r.status_code, "resp:", r.text[:300])

# verify principals
for email in ["ramesh@lpgs.com","deepa@lpgs.com","lakshmi@lpgs.com","anita@lpgs.com"]:
    s, code = sess(email,"teach123")
    if code!=200:
        print(f"\n{email}: LOGIN FAILED {code}"); continue
    me = s.get(f"{BASE}/auth/me").json()
    cls = s.get(f"{BASE}/res/classes", params={"limit":200})
    st = s.get(f"{BASE}/res/students", params={"limit":200})
    cl_names = sorted({c["name"] for c in cls.json().get("items",[])}) if cls.status_code==200 else f"ERR{cls.status_code}"
    st_names = sorted({f'{x["first_name"]} {x.get("last_name","")}' for x in st.json().get("items",[])}) if st.status_code==200 else f"ERR{st.status_code}"
    print(f"\n=== {email} ===")
    print("  is_principal:", me.get("is_principal"), "| principal:", me.get("principal"))
    print("  classes visible:", cl_names)
    print("  students visible:", st_names)

print("\n=== admin view of /principals ===")
for pa in admin.get(f"{BASE}/principals").json()["items"]:
    print(" ", pa["teacher_name"], "|", pa["designation"], "|", pa["scope_type"], "|", [u["name"] for u in pa.get("units",[])])

print("\n=== counts ===")
for res in ["students","assessments","notices","teacher_assignments"]:
    print(" ", res, admin.get(f"{BASE}/res/{res}", params={"limit":1}).json().get("total"))
att = admin.get(f"{BASE}/attendance/records").json()
print("  attendance records:", att.get("total"))
