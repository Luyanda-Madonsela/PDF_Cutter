"""Iteration 12: Drive OAuth callback scope-grant fix.

Bug: in /api/drive/callback the Flow was built with scopes=None so flow.credentials.scopes
(from session.scope) was None, and the SCOPES ⊆ granted check always failed → toast
"Google Drive access was not granted" (redirect /?drive=scope).

Fix: granted scopes are now read from flow.oauth2session.token['scope'] (string split on
spaces, or list). Check SCOPES ⊆ granted; store credential scopes = granted.

Tests:
- Unit test callback via monkeypatch of Flow.fetch_token (no real Google) covering:
    * scope as space-delimited string with drive scope -> /?drive=connected, DB row has drive scope
    * scope as list including drive scope -> /?drive=connected
    * scope 'openid' only (no drive) -> /?drive=scope, no DB row written
- Real endpoint: GET /api/drive/callback?state=unknown&code=x -> /?drive=error
Teardown: delete db.drive_credentials {_id:'shared'} so the real user can connect.
"""
import os
import sys
import asyncio
import secrets
import pytest
import requests

# Allow import of backend modules (CWD may be /app/backend/tests)
sys.path.insert(0, "/app/backend")

import drive as drive_mod  # noqa: E402
from core import db  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://papercut-sa.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
CRED_ID = "shared"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"


_LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(_LOOP)


def _run(coro):
    return _LOOP.run_until_complete(coro)


class _FakeOauth2Session:
    def __init__(self, token):
        self.token = token


class _FakeCreds:
    def __init__(self):
        self.token = "ya29.fake"
        self.refresh_token = "1//fake"
        self.token_uri = "https://oauth2.googleapis.com/token"
        self.expiry = None


def _patch_flow(monkeypatch, token_dict):
    """Monkeypatch Flow.fetch_token so it only sets oauth2session.token and credentials."""
    from google_auth_oauthlib.flow import Flow

    def fake_fetch_token(self, code=None, **kw):
        self.oauth2session = _FakeOauth2Session(dict(token_dict))
        return self.oauth2session.token

    monkeypatch.setattr(Flow, "fetch_token", fake_fetch_token)
    monkeypatch.setattr(Flow, "credentials", property(lambda self: _FakeCreds()))


async def _seed_state():
    state = f"TEST_state_{secrets.token_urlsafe(8)}"
    await db.drive_states.insert_one({
        "_id": state,
        "user_email": "qa.tester@example.com",
        "code_verifier": "x" * 64,
    })
    return state


async def _cleanup():
    await db.drive_credentials.delete_one({"_id": CRED_ID})


@pytest.fixture(autouse=True)
def _ensure_env():
    # Guarantee FRONTEND_URL exists for the callback redirect.
    os.environ.setdefault("FRONTEND_URL", BASE_URL)
    yield
    # Always remove any fake credential doc we may have created in tests.
    _run(_cleanup())


def _call_callback(code, state):
    return _run(drive_mod.callback(code=code, state=state, error=None))


def test_callback_scope_string_grants_drive(monkeypatch):
    _patch_flow(monkeypatch, {
        "access_token": "ya29.fake", "refresh_token": "1//fake", "token_type": "Bearer",
        "expires_in": 3599, "scope": f"{DRIVE_SCOPE} openid",
    })
    state = _run(_seed_state())
    resp = _call_callback("c", state)
    assert resp.status_code in (302, 307)
    assert resp.headers["location"].endswith("/?drive=connected"), resp.headers["location"]
    doc = _run(db.drive_credentials.find_one({"_id": CRED_ID}))
    assert doc is not None
    assert DRIVE_SCOPE in doc["scopes"]
    assert doc["connected_by"] == "qa.tester@example.com"


def test_callback_scope_list_grants_drive(monkeypatch):
    _patch_flow(monkeypatch, {
        "access_token": "ya29.fake", "refresh_token": "1//fake", "token_type": "Bearer",
        "expires_in": 3599, "scope": [DRIVE_SCOPE, "openid"],
    })
    state = _run(_seed_state())
    resp = _call_callback("c", state)
    assert resp.status_code in (302, 307)
    assert resp.headers["location"].endswith("/?drive=connected")
    doc = _run(db.drive_credentials.find_one({"_id": CRED_ID}))
    assert doc is not None and DRIVE_SCOPE in doc["scopes"]


def test_callback_scope_missing_drive_redirects_scope(monkeypatch):
    # Ensure no stale cred doc from previous assertions
    _run(_cleanup())
    _patch_flow(monkeypatch, {
        "access_token": "ya29.fake", "refresh_token": "1//fake", "token_type": "Bearer",
        "expires_in": 3599, "scope": "openid",
    })
    state = _run(_seed_state())
    resp = _call_callback("c", state)
    assert resp.status_code in (302, 307)
    assert resp.headers["location"].endswith("/?drive=scope"), resp.headers["location"]
    # No credential should be written
    doc = _run(db.drive_credentials.find_one({"_id": CRED_ID}))
    assert doc is None, f"Credential should NOT be written when scope missing: {doc}"


def test_real_endpoint_unknown_state_redirects_error():
    r = requests.get(
        f"{API}/drive/callback",
        params={"state": "unknown-state-abc", "code": "x"},
        allow_redirects=False, timeout=20,
    )
    assert r.status_code in (302, 307)
    assert "/?drive=error" in r.headers.get("location", "")
