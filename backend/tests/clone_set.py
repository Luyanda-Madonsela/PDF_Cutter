# Clone the IEB Physical Sciences done set (new ids, same storage). Run: cd /app/backend && PYTHONPATH=. python3 tests/clone_set.py
import asyncio
import uuid
import copy
from core import db


async def main():
    s = await db.sets.find_one({"is_deleted": False, "status": "done", "base_name": "PhysicalSciences_Gr12_2023_Nov_IEB_P2"})
    nid = str(uuid.uuid4())
    s2 = copy.deepcopy(s)
    s2.update({"_id": nid, "drive": None, "base_name": s["base_name"] + "_TEST"})
    await db.sets.insert_one(s2)
    async for j in db.jobs.find({"set_id": s["_id"], "is_deleted": False}):
        j["_id"], j["set_id"] = str(uuid.uuid4()), nid
        for q in j.get("questions", []):
            q["id"] = str(uuid.uuid4())
        await db.jobs.insert_one(j)
    print(nid)


asyncio.run(main())
