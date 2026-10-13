import os, json, requests, pymongo
BASE = [l for l in open("/app/frontend/.env").read().splitlines() if l.startswith("REACT_APP_BACKEND_URL")][0].split("=",1)[1].strip()+"/api"
admin = requests.Session(); admin.post(f"{BASE}/auth/login", json={"email":"admin@lpgs.com","password":"admin123"}, timeout=30)
iid = admin.get(f"{BASE}/auth/me").json()["institution_id"]

mc = pymongo.MongoClient(os.popen('grep MONGO_URL /app/backend/.env | cut -d\'"\' -f2').read().strip())
dbn = os.popen('grep DB_NAME /app/backend/.env | cut -d\'"\' -f2').read().strip()
mc[dbn].users.update_many({"institution_id":iid,"role":"teacher"}, {"$set":{"must_change_password":False}})
print("cleared must_change for teachers")

studs = {(s["first_name"],s.get("last_name")):s for s in admin.get(f"{BASE}/res/students", params={"limit":200}).json()["items"]}
logins=[]
for (fn,ln), email in [(("Aarav","Menon"),"aarav.menon@lpgs.com"), (("Rahul","Varma"),"rahul.varma@lpgs.com")]:
    st = studs.get((fn,ln))
    if not st: continue
    if st.get("has_portal_access"):
        logins.append({"name":f"{fn} {ln}","email":email,"password":"student123 (existing)"}); continue
    r = admin.post(f"{BASE}/students/{st['id']}/portal-user", json={"email":email,"password":"student123"})
    print(f"portal {email}:", r.status_code, r.text[:160])
    if r.status_code<400: logins.append({"name":f"{fn} {ln}","email":email,"password":"student123","class":st.get("class_name")})

for who,pw in [("deepa@lpgs.com","teach123")]:
    s=requests.Session(); code=s.post(f"{BASE}/auth/login", json={"email":who,"password":pw}).status_code
    print(f"\n{who} login:", code)
    if code==200:
        me=s.get(f"{BASE}/auth/me").json()
        cls=sorted({c["name"] for c in s.get(f"{BASE}/res/classes", params={"limit":200}).json().get("items",[])})
        stv=sorted({x["first_name"] for x in s.get(f"{BASE}/res/students", params={"limit":200}).json().get("items",[])})
        print("  principal:", me.get("principal"))
        print("  classes:", cls, "| students:", stv)
        print("  /res/academic_units (should 403):", s.get(f"{BASE}/res/academic_units").status_code)
print("\nstudent_logins:", json.dumps(logins, indent=2))
