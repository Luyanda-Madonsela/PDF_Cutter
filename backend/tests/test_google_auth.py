import asyncio
import os
import sys
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import auth as auth_mod  # noqa: E402
from core import db  # noqa: E402

_LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(_LOOP)


def _run(coro):
    return _LOOP.run_until_complete(coro)


class _FakeCredentials:
    id_token = "fake-google-id-token"


class _FakeFlow:
    def __init__(self):
        self.code_verifier = "test-code-verifier"
        self.credentials = _FakeCredentials()
        self.authorization_options = None
        self.fetched_code = None

    def authorization_url(self, **kwargs):
        self.authorization_options = kwargs
        return (
            "https://accounts.google.com/o/oauth2/auth?"
            f"state={kwargs['state']}&code_challenge_method={kwargs['code_challenge_method']}",
            None,
        )

    def fetch_token(self, code=None):
        self.fetched_code = code


def test_google_login_and_callback_create_local_session(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("GOOGLE_AUTH_REDIRECT_URI", "https://app.example.test/api/auth/google/callback")
    monkeypatch.setenv("FRONTEND_URL", "https://app.example.test")
    assert auth_mod.GOOGLE_AUTH_SCOPES == [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ]

    flows = []
    expected_nonce = None

    def make_flow():
        flow = _FakeFlow()
        flows.append(flow)
        return flow

    def verified_claims(token, request, audience):
        return {
            "sub": "google-user-test-123",
            "email": "google-oauth-test@example.test",
            "email_verified": True,
            "name": "Google OAuth Test",
            "picture": "https://example.test/avatar.png",
            "nonce": expected_nonce,
        }

    monkeypatch.setattr(auth_mod, "_auth_flow", make_flow)
    monkeypatch.setattr(auth_mod.id_token, "verify_oauth2_token", verified_claims)

    login_response = _run(auth_mod.google_login())
    params = parse_qs(urlparse(login_response.headers["location"]).query)
    state = params["state"][0]
    assert params["code_challenge_method"] == ["S256"]
    state_doc = _run(db.auth_states.find_one({"_id": state}, {"_id": 0}))
    expected_nonce = state_doc["nonce"]
    assert flows[0].authorization_options["prompt"] == "select_account"
    assert flows[0].authorization_options["nonce"] == expected_nonce

    callback_response = _run(auth_mod.google_callback(state=state, code="fake-code"))
    assert callback_response.status_code in (302, 307)
    assert callback_response.headers["location"] == "https://app.example.test/"
    assert flows[1].fetched_code == "fake-code"

    user = _run(db.users.find_one({"google_sub": "google-user-test-123"}, {"_id": 0}))
    assert user["email"] == "google-oauth-test@example.test"
    assert user["name"] == "Google OAuth Test"

    cookie = callback_response.headers["set-cookie"]
    assert "session_token=" in cookie and "HttpOnly" in cookie and "Secure" in cookie
    session_token = cookie.split("session_token=", 1)[1].split(";", 1)[0]
    session = _run(db.user_sessions.find_one({"session_token": session_token}, {"_id": 0}))
    assert session["user_id"] == user["user_id"]
    expires_at = session["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    assert expires_at > datetime.now(timezone.utc)

    _run(db.user_sessions.delete_one({"session_token": session_token}))
    _run(db.users.delete_one({"google_sub": "google-user-test-123"}))
