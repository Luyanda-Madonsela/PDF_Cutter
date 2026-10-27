import asyncio
import os
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow
from pydantic import BaseModel
from core import db

auth_api = APIRouter(prefix="/api/auth")
SESSION_DAYS = 7
GOOGLE_AUTH_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]


class User(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None


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


def _auth_flow():
    required = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_AUTH_REDIRECT_URI")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise HTTPException(503, f"Google sign-in is not configured: missing {', '.join(missing)}")
    redirect_uri = os.environ["GOOGLE_AUTH_REDIRECT_URI"]
    client_config = {"web": {
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [redirect_uri],
    }}
    return Flow.from_client_config(client_config, scopes=GOOGLE_AUTH_SCOPES, redirect_uri=redirect_uri)


def _frontend_url():
    frontend_url = os.environ.get("FRONTEND_URL", "").strip().rstrip("/")
    if not frontend_url:
        raise HTTPException(503, "Google sign-in is not configured: FRONTEND_URL is missing")
    return frontend_url


@auth_api.get("/google/login")
async def google_login():
    flow = _auth_flow()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    authorization_url, _ = flow.authorization_url(
        access_type="online",
        prompt="select_account",
        state=state,
        nonce=nonce,
        code_challenge_method="S256",
    )
    await db.auth_states.insert_one({
        "_id": state,
        "code_verifier": flow.code_verifier,
        "nonce": nonce,
        "created_at": datetime.now(timezone.utc),
    })
    return RedirectResponse(authorization_url)


@auth_api.get("/google/callback")
async def google_callback(
    state: Optional[str] = None,
    code: Optional[str] = None,
    error: Optional[str] = None,
):
    frontend_url = _frontend_url()
    login_error = RedirectResponse(f"{frontend_url}/?auth=error")
    if not state:
        return login_error

    auth_state = await db.auth_states.find_one_and_delete({"_id": state})
    if not auth_state:
        return login_error
    if not code or error:
        return login_error
    created_at = auth_state.get("created_at")
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    if not isinstance(created_at, datetime):
        return login_error
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - created_at > timedelta(minutes=10):
        return login_error

    try:
        flow = _auth_flow()
        flow.code_verifier = auth_state.get("code_verifier")
        await asyncio.to_thread(flow.fetch_token, code=code)
        claims = await asyncio.to_thread(
            id_token.verify_oauth2_token,
            flow.credentials.id_token,
            GoogleRequest(),
            os.environ["GOOGLE_CLIENT_ID"],
        )
        email = claims.get("email")
        if (not email or not claims.get("email_verified") or not claims.get("sub")
                or claims.get("nonce") != auth_state.get("nonce")):
            return login_error
    except Exception:
        from core import logger
        logger.warning("Google sign-in token exchange or verification failed", exc_info=True)
        return login_error

    now = datetime.now(timezone.utc)
    existing = await db.users.find_one(
        {"$or": [{"google_sub": claims["sub"]}, {"email": email}]},
        {"_id": 0},
    )
    user_id = existing["user_id"] if existing else f"user_{uuid.uuid4().hex[:12]}"
    user_data = {
        "google_sub": claims["sub"],
        "email": email,
        "name": claims.get("name") or email,
        "picture": claims.get("picture"),
    }
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": user_data, "$setOnInsert": {"user_id": user_id, "created_at": now}},
        upsert=True,
    )
    session_token = secrets.token_urlsafe(32)
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": now + timedelta(days=SESSION_DAYS),
        "created_at": now,
    })

    secure_cookie = frontend_url.startswith("https://")
    response = RedirectResponse(f"{frontend_url}/")
    response.set_cookie(
        "session_token",
        session_token,
        httponly=True,
        secure=secure_cookie,
        samesite="none" if secure_cookie else "lax",
        path="/",
        max_age=SESSION_DAYS * 86400,
    )
    return response


@auth_api.get("/me")
async def me(request: Request):
    return await require_user(request)


@auth_api.post("/logout")
async def logout(request: Request, response: Response):
    token = _token(request)
    if token:
        await db.user_sessions.delete_one({"session_token": token})
    secure_cookie = _frontend_url().startswith("https://")
    response.delete_cookie(
        "session_token",
        path="/",
        secure=secure_cookie,
        samesite="none" if secure_cookie else "lax",
    )
    return {"ok": True}
