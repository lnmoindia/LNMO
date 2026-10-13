"""Phase 17 LPGS data fix (additive, real DB): populate guardian_phone + admission_no on two
Grade 8 students so the parent self-link OTP flow is demoable. Emails are NOT touched."""
import os, asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

IID = "82d1ec4e-db71-4578-903b-bc986f1ebd3d"
FIX = [
    ("5ed50271-17ee-4cae-91df-bc0b19dc15fc", "LPGS-G8-001", "9847010001"),  # Fathima (Grade 8 A)
    ("e25660b3-b935-446c-9eaa-4a661c95310a", "LPGS-G8-002", "9847010002"),  # Haritha (Grade 8 A)
]
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


async def main():
    for sid, adm, phone in FIX:
        st = await db.students.find_one({"id": sid, "institution_id": IID}, {"_id": 0, "first_name": 1, "admission_no": 1, "guardian_phone": 1})
        upd = {}
        if not st.get("admission_no"):
            upd["admission_no"] = adm
        if not st.get("guardian_phone"):
            upd["guardian_phone"] = phone
        if upd:
            await db.students.update_one({"id": sid}, {"$set": upd})
        after = await db.students.find_one({"id": sid}, {"_id": 0, "first_name": 1, "admission_no": 1, "guardian_phone": 1})
        print("fixed:", after)


asyncio.run(main())
