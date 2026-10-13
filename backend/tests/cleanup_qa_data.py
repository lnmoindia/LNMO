"""Cleanup helper: removes QA-created throwaway data and restores seeded student fields."""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import dotenv_values

env = dotenv_values("/app/backend/.env")


async def main():
    client = AsyncIOMotorClient(env["MONGO_URL"])
    db = client[env["DB_NAME"]]

    # restore student academic year overwritten by throwaway enrollment
    r = await db.students.update_many({"academic_year": {"$in": ["TEST_QA-YEAR"]}},
                                      {"$set": {"academic_year": "2026-27"}})
    print("students restored:", r.modified_count)

    # remove QA attendance sheets
    r = await db.attendance.delete_many({"date": {"$in": ["2026-07-15", "2026-07-16", "2026-07-02"]}})
    print("attendance removed:", r.deleted_count)

    # remove orphaned marks (assessment no longer exists)
    aids = {a["id"] async for a in db.assessments.find({}, {"id": 1})}
    orphan = [m["_id"] async for m in db.marks.find({}, {"assessment_id": 1}) if m["assessment_id"] not in aids]
    if orphan:
        await db.marks.delete_many({"_id": {"$in": orphan}})
    print("orphan marks removed:", len(orphan))

    # remove leftover TEST_ records
    for col in ("academic_years", "enrollments", "teacher_assignments", "assessments", "students"):
        r = await db[col].delete_many({"$or": [{"name": {"$regex": "^TEST_"}},
                                               {"subject": {"$regex": "^TEST_"}},
                                               {"first_name": {"$regex": "^TESTQA"}},
                                               {"academic_year": "TEST_QA-YEAR"}]})
        print(col, "leftovers removed:", r.deleted_count)

    print("students now:", [ (s.get("first_name"), s.get("class_name"), s.get("section"), s.get("academic_year"))
                             async for s in db.students.find({}, {"_id": 0})])
    print("attendance dates:", [a["date"] async for a in db.attendance.find({}, {"_id": 0, "date": 1})])
    print("assessments:", [(a["name"], a.get("status")) async for a in db.assessments.find({}, {"_id": 0})])
    client.close()


asyncio.run(main())
