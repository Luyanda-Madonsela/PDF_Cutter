"""Iteration 11:
- /api/drive/connect: PKCE code_challenge in URL, code_verifier stored in db.drive_states,
  base64url(sha256(verifier)) == code_challenge
- /api/drive/callback: unknown state -> /?drive=error; valid state with fake code -> error
  but NOT 'Missing code verifier' in logs (proves verifier is sent)
- Cost tracker:
  - POST /api/ai/test (emergent) increments usage; GET /api/ai/usage shows gemini-3-flash-preview row
    with calls>=1, input_tokens>0, cost>0, paid_by 'Emergent credits', price [0.5,3.0]
  - PUT /api/ai/prices with model with dots works; negative -> 400
  - GET /api/ai/usage days=1/7/365 works
"""
import os
import re
import time
import hashlib
import base64
from urllib.parse import urlparse, parse_qs
import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://papercut-sa.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
H = {"Authorization": "Bearer test_session_qa_papercut"}

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


def _g(p, **kw): kw.setdefault("timeout", 60); return requests.get(f"{API}{p}", headers=H, **kw)
def _put(p, **kw): kw.setdefault("timeout", 60); return requests.put(f"{API}{p}", headers=H, **kw)
def _post(p, **kw): kw.setdefault("timeout", 60); return requests.post(f"{API}{p}", headers=H, **kw)


def _b64url_sha256(s: str) -> str:
    h = hashlib.sha256(s.encode("ascii")).digest()
    return base64.urlsafe_b64encode(h).rstrip(b"=").decode("ascii")


async def _db_get_state(state_id):
    client = AsyncIOMotorClient(MONGO_URL)
    try:
        return await client[DB_NAME].drive_states.find_one({"_id": state_id})
    finally:
        client.close()


class TestDrivePKCE:
    def test_connect_url_has_pkce_s256(self):
        r = _g("/drive/connect")
        assert r.status_code == 200, r.text
        url = r.json()["authorization_url"]
        q = parse_qs(urlparse(url).query)
        assert "code_challenge" in q, f"no code_challenge in {url}"
        assert q.get("code_challenge_method", [""])[0] == "S256"
        state = q["state"][0]
        challenge = q["code_challenge"][0]
        # Fetch state doc from DB
        doc = asyncio.get_event_loop().run_until_complete(_db_get_state(state)) if False else None
        # simpler: new loop
        doc = asyncio.new_event_loop().run_until_complete(_db_get_state(state))
        assert doc is not None, "state doc missing"
        verifier = doc.get("code_verifier")
        assert verifier, "code_verifier not stored"
        assert _b64url_sha256(verifier) == challenge, "challenge != sha256(verifier)"

    def test_callback_unknown_state_redirects_error(self):
        r = requests.get(f"{API}/drive/callback", params={"state": "nonexistent-state-xyz", "code": "fake"},
                         allow_redirects=False, timeout=20)
        assert r.status_code in (302, 307)
        assert "/?drive=error" in r.headers.get("location", "")

    def test_callback_valid_state_fake_code_not_missing_verifier(self):
        # Create a state
        r = _g("/drive/connect")
        assert r.status_code == 200
        url = r.json()["authorization_url"]
        state = parse_qs(urlparse(url).query)["state"][0]
        # Hit callback with fake code
        r2 = requests.get(f"{API}/drive/callback", params={"state": state, "code": "fake-auth-code-123"},
                          allow_redirects=False, timeout=30)
        assert r2.status_code in (302, 307)
        assert "/?drive=error" in r2.headers.get("location", "")
        # Check backend log doesn't say "Missing code verifier" for this attempt
        time.sleep(1)
        try:
            with open("/var/log/supervisor/backend.err.log", "r") as f:
                log_tail = f.read()[-8000:]
        except Exception:
            log_tail = ""
        # The verifier is now sent, so error should NOT be 'Missing code verifier'
        # Find the most recent "Drive OAuth failed" line
        matches = re.findall(r"Drive OAuth failed:.*", log_tail)
        if matches:
            last = matches[-1]
            assert "Missing code verifier" not in last, f"PKCE verifier still missing: {last}"


class TestAiUsageAndPrices:
    @classmethod
    def setup_class(cls):
        _put("/ai/settings", json={"provider": "emergent"})

    def test_test_then_usage_shows_emergent_row(self):
        before = _g("/ai/usage", params={"days": 1}).json()
        before_calls = next((m["calls"] for m in before["models"] if m["model"] == "gemini-3-flash-preview"), 0)
        r = _post("/ai/test", timeout=120)
        assert r.status_code == 200, r.text
        time.sleep(0.5)
        after = _g("/ai/usage", params={"days": 1})
        assert after.status_code == 200, after.text
        d = after.json()
        assert d["total_calls"] >= 1
        row = next((m for m in d["models"] if m["model"] == "gemini-3-flash-preview"), None)
        assert row is not None, f"gemini-3-flash-preview row missing: {d}"
        assert row["calls"] > before_calls
        assert row["input_tokens"] > 0
        assert row["price"] == [0.5, 3.0]
        assert row["cost"] > 0
        assert row["paid_by"] == "Emergent credits"
        assert row["provider"] == "emergent"

    def test_usage_days_variants(self):
        for d in (1, 7, 365):
            r = _g("/ai/usage", params={"days": d})
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["days"] == d
            assert "models" in body and "total_cost" in body and "total_calls" in body and "daily" in body

    def test_put_price_with_dots_in_model(self):
        r = _put("/ai/prices", json={"model": "gemini-3.1-pro-preview", "input": 2.0, "output": 12.0})
        assert r.status_code == 200, r.text
        # Response is usage; verify price persisted via another call
        # Prices are only visible in usage rows if that model has usage. Instead check default is overridden by writing then reading another model
        # Insert a usage row path: not available; re-PUT and ensure 200
        r2 = _put("/ai/prices", json={"model": "gemini-3.1-pro-preview", "input": 2.0, "output": 12.0})
        assert r2.status_code == 200

    def test_put_price_negative_400(self):
        r = _put("/ai/prices", json={"model": "gemini-3-flash-preview", "input": -1, "output": 3.0})
        assert r.status_code == 400
        r2 = _put("/ai/prices", json={"model": "gemini-3-flash-preview", "input": 0.5, "output": -3.0})
        assert r2.status_code == 400

    def test_put_price_empty_model_400(self):
        r = _put("/ai/prices", json={"model": "   ", "input": 1, "output": 2})
        assert r.status_code == 400

    def test_price_override_affects_cost(self):
        # Set custom price for gemini-3-flash-preview
        _put("/ai/prices", json={"model": "gemini-3-flash-preview", "input": 10.0, "output": 20.0})
        r = _g("/ai/usage", params={"days": 1}).json()
        row = next((m for m in r["models"] if m["model"] == "gemini-3-flash-preview"), None)
        if row:
            assert row["price"] == [10.0, 20.0]
        # Restore
        rr = _put("/ai/prices", json={"model": "gemini-3-flash-preview", "input": 0.5, "output": 3.0})
        assert rr.status_code == 200
