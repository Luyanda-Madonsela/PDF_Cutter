import uuid
import httpx
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel
from core import db

auth_api = APIRouter(prefix="/api/auth")
SESSION_DATA_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"
SESSION_DAYS = 7


class User(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None


class SessionIn(BaseModel):
    session_id: str


def _token(request: Request) -> Optional[str]:
    token = request.cookies.get("session_token")
    if token:
        return token
    header = request.headers.get("Authorization", "")
    return header[7:] if header.startswith("Bearer ") else None


async def require_user(request: Request) -> User:
    token = _token(request)
    if not token:
        raise HTTPException(401, "Not authenticated")
    sess = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not sess:
        raise HTTPException(401, "Invalid session")
    expires = sess["expires_at"]
    if isinstance(expires, str):
        expires = datetime.fromisoformat(expires)
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        raise HTTPException(401, "Session expired")
    user = await db.users.find_one({"user_id": sess["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(401, "User not found")
    return User(**user)


@auth_api.post("/session")
async def create_session(body: SessionIn, response: Response):
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(SESSION_DATA_URL, headers={"X-Session-ID": body.session_id})
    if r.status_code != 200:
        raise HTTPException(401, "Invalid session id")
    data = r.json()
    existing = await db.users.find_one({"email": data["email"]}, {"_id": 0})
    user_id = existing["user_id"] if existing else f"user_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"email": data["email"], "name": data["name"], "picture": data.get("picture")},
         "$setOnInsert": {"user_id": user_id, "created_at": now}},
        upsert=True)
    await db.user_sessions.insert_one({"user_id": user_id, "session_token": data["session_token"],
                                       "expires_at": now + timedelta(days=SESSION_DAYS), "created_at": now})
    response.set_cookie("session_token", data["session_token"], httponly=True, secure=True, samesite="none",
                        path="/", max_age=SESSION_DAYS * 86400)
    return User(user_id=user_id, email=data["email"], name=data["name"], picture=data.get("picture"))


@auth_api.get("/me")
async def me(request: Request):
    return await require_user(request)


@auth_api.post("/logout")
async def logout(request: Request, response: Response):
    token = _token(request)
    if token:
        await db.user_sessions.delete_one({"session_token": token})
    response.delete_cookie("session_token", path="/", secure=True, samesite="none")
    return {"ok": True}
