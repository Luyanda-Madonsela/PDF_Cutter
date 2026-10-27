"""Auth gating tests for PaperCut (Google OAuth).

Uses an isolated requests.Session so the module-level requests.get monkey-patch
in test_papercut_api.py cannot leak Bearer headers into these tests.
"""
import os
import uuid
from datetime import datetime, timezone, timedelta
import pytest
import requests
from pymongo import MongoClient


def _load_frontend_env():
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip()
    except FileNotFoundError:
        return None


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _load_frontend_env() or "").rstrip("/")
API = f"{BASE_URL}/api"
QA_TOKEN = "test_session_qa_papercut"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

# Independent client, immune to module-level requests.get monkey patches.
unauth = requests.Session()
authed = requests.Session()
authed.headers.update({"Authorization": f"Bearer {QA_TOKEN}"})


@pytest.fixture(scope="module")
def mongo():
    return MongoClient(MONGO_URL)[DB_NAME]


@pytest.fixture
def throwaway_session(mongo):
    token = f"TEST_throwaway_{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc)
    mongo.user_sessions.insert_one({
        "user_id": "test-user-qa",
        "session_token": token,
        "expires_at": now + timedelta(days=7),
        "created_at": now,
    })
    yield token
    mongo.user_sessions.delete_one({"session_token": token})


PROTECTED_PATHS = [
    "/api/",
    "/api/sets",
    "/api/catalogues",
    "/api/sets/does-not-exist",
    "/api/sets/does-not-exist/zip",
    "/api/jobs/x/images/y",
    "/api/jobs/x/pages/0",
    "/api/catalogues/gr12-maths/download",
]


@pytest.mark.parametrize("path", PROTECTED_PATHS)
def test_unauth_returns_401(path):
    r = unauth.get(f"{BASE_URL}{path}")
    assert r.status_code == 401, f"{path}: expected 401 got {r.status_code}"


def test_unauth_auth_me_401():
    r = unauth.get(f"{API}/auth/me")
    assert r.status_code == 401


def test_bearer_auth_me_returns_qa_user():
    r = authed.get(f"{API}/auth/me")
    assert r.status_code == 200
    data = r.json()
    assert data["user_id"] == "test-user-qa"
    assert data["email"] == "qa.tester@example.com"
    assert data["name"] == "QA Tester"


def test_cookie_auth_also_works():
    s = requests.Session()
    s.cookies.set("session_token", QA_TOKEN)
    r = s.get(f"{API}/auth/me")
    assert r.status_code == 200
    assert r.json()["user_id"] == "test-user-qa"


def test_bearer_can_list_sets():
    r = authed.get(f"{API}/sets")
    assert r.status_code == 200
    assert "sets" in r.json() and "counts" in r.json()


def test_bearer_can_list_catalogues():
    r = authed.get(f"{API}/catalogues")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_invalid_bearer_token_401():
    s = requests.Session()
    s.headers.update({"Authorization": "Bearer this-is-not-a-real-token"})
    assert s.get(f"{API}/auth/me").status_code == 401


def test_logout_invalidates_session(throwaway_session, mongo):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {throwaway_session}"})
    # 1. Valid
    assert s.get(f"{API}/auth/me").status_code == 200
    # 2. Logout
    r = s.post(f"{API}/auth/logout")
    assert r.status_code == 200 and r.json().get("ok") is True
    # 3. Session gone from DB
    assert mongo.user_sessions.find_one({"session_token": throwaway_session}) is None
    # 4. Token no longer works
    assert s.get(f"{API}/auth/me").status_code == 401
    # 5. QA token still works (not nuked)
    assert authed.get(f"{API}/auth/me").status_code == 200


def test_image_endpoint_requires_auth():
    """<img> tags will send cookie; without session should 401, not 404."""
    r = unauth.get(f"{API}/jobs/anything/images/anything")
    assert r.status_code == 401
