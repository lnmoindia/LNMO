import requests
from dotenv import dotenv_values
BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
CLASS_ID = "db61baf7-67fb-4c66-b04c-f8f11196b9ac"
TEACHER = "6d90ce95-7c16-4401-a98d-d4c0e2d47914"
STUDENT = "9fa05e4b-3ec9-4e53-8fb2-8a69b517a4dc"
s = requests.Session()
s.post(f"{BASE}/auth/login", json={"email": "admin@greenwood.edu", "password": "Green@2026!"}, timeout=30)
r = s.put(f"{BASE}/res/classes/{CLASS_ID}", json={"class_teacher_id": TEACHER, "class_leader_id": STUDENT, "second_leader_id": ""}, timeout=30)
print(r.status_code, {k: r.json().get(k) for k in ("class_teacher", "class_teacher_id", "class_leader", "class_leader_id", "second_leader")})
