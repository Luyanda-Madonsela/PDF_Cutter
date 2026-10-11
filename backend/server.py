import os
import asyncio
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from core import client, db, init_storage, logger
from routes import api
from auth import auth_api
from drive import drive_api
from drive_import import import_api
from jobs import worker_loop

app = FastAPI()
app.include_router(auth_api)
app.include_router(drive_api)
app.include_router(import_api)
app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    try:
        await asyncio.to_thread(init_storage)
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
    await db.jobs.create_index([("status", 1), ("created_at", 1)])
    await db.jobs.create_index([("set_id", 1)])
    await db.sets.create_index([("is_deleted", 1), ("created_at", -1)])
    await db.user_sessions.create_index("session_token")
    await db.users.create_index("email")
    await db.jobs.update_many({"status": "classifying"}, {"$set": {"status": "queued"}})
    await db.jobs.update_many({"status": "processing"}, {"$set": {"status": "ready"}})
    await db.sets.update_many({"drive.status": {"$in": ["queued", "uploading"]}},
                              {"$set": {"drive.status": "error", "drive.error": "Interrupted by a server restart. Send again."}})
    app.state.worker = asyncio.create_task(worker_loop())


@app.on_event("shutdown")
async def shutdown_db_client():
    app.state.worker.cancel()
    client.close()
