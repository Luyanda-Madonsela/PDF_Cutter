"""Iteration 10:
- AI settings endpoint shape, PUT variations, masking, fallback
- /ai/test with emergent provider (real Gemini call ~5-20s) must include '1.1' in reply
- /ai/test with 'compatible' invalid base_url returns 400 with 'failed' message
- /drive/connect authorization_url contains login_hint and prompt=select_account consent
- Auth required
- Restores settings to emergent + clears fake keys at end
"""
import os
import re
import pytest
import requests
from urllib.parse import urlparse, parse_qs

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "https://papercut-sa.preview.emergentagent.com"
API = f"{BASE_URL}/api"
H = {"Authorization": "Bearer test_session_qa_papercut"}

PROVIDERS = {"emergent", "gemini", "openai", "anthropic", "openrouter", "compatible"}


def _g(p, **kw): kw.setdefault("timeout", 60); return requests.get(f"{API}{p}", headers=H, **kw)
def _put(p, **kw): kw.setdefault("timeout", 60); return requests.put(f"{API}{p}", headers=H, **kw)
def _post(p, **kw): kw.setdefault("timeout", 60); return requests.post(f"{API}{p}", headers=H, **kw)


@pytest.fixture(scope="module", autouse=True)
def restore_defaults():
    yield
    # Restore to emergent and clear fake keys
    for p in ("openai", "gemini", "anthropic", "openrouter", "compatible"):
        try:
            _put("/ai/settings", json={"provider": p, "key": ""})
        except Exception:
            pass
    _put("/ai/settings", json={"provider": "emergent"})


class TestAiSettingsShape:
    def test_get_settings_shape(self):
        r = _g("/ai/settings")
        assert r.status_code == 200, r.text
        d = r.json()
        for f in ("provider", "models", "base_url", "keys", "providers", "active"):
            assert f in d, f"missing {f}"
        assert set(d["providers"].keys()) == PROVIDERS
        # keys never raw; masked or null; emergent key not in keys dict
        assert "emergent" not in d["keys"]
        for v in d["keys"].values():
            assert v is None or v.startswith("••••")
        # active shape
        act = d["active"]
        for f in ("provider", "model", "fallback"):
            assert f in act

    def test_auth_required(self):
        r = requests.get(f"{API}/ai/settings", timeout=20)
        assert r.status_code == 401

    def test_unknown_provider_400(self):
        r = _put("/ai/settings", json={"provider": "nope"})
        assert r.status_code == 400

    def test_compatible_bad_base_url_400(self):
        r = _put("/ai/settings", json={"provider": "compatible", "base_url": "ftp://x"})
        assert r.status_code == 400

    def test_put_openai_no_key_falls_back(self):
        # Clear openai first
        _put("/ai/settings", json={"provider": "openai", "key": ""})
        r = _put("/ai/settings", json={"provider": "openai"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["active"]["provider"] == "emergent"
        assert d["active"]["fallback"] is True

    def test_put_openai_with_key_masked_and_active(self):
        r = _put("/ai/settings", json={"provider": "openai", "key": "sk-test-1234abcd"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["keys"]["openai"] == "••••abcd"
        assert d["active"]["provider"] == "openai"
        assert d["active"]["fallback"] is False

    def test_clear_openai_key(self):
        _put("/ai/settings", json={"provider": "openai", "key": "sk-test-xxxxabcd"})
        r = _put("/ai/settings", json={"provider": "openai", "key": ""})
        assert r.status_code == 200
        d = r.json()
        assert d["keys"]["openai"] is None
        # back to fallback
        assert d["active"]["provider"] == "emergent"
        assert d["active"]["fallback"] is True
        # restore to emergent for subsequent tests
        _put("/ai/settings", json={"provider": "emergent"})


class TestAiTest:
    def test_test_emergent_contains_1_1(self):
        _put("/ai/settings", json={"provider": "emergent"})
        r = _post("/ai/test", timeout=90)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert "1.1" in d.get("reply", ""), f"reply missing 1.1: {d}"

    def test_test_compatible_bad_url_400(self):
        _put("/ai/settings", json={"provider": "compatible", "base_url": "http://127.0.0.1:9/v1", "model": "llava"})
        r = _post("/ai/test", timeout=60)
        assert r.status_code == 400, r.text
        assert "failed" in r.text.lower()
        # restore
        _put("/ai/settings", json={"provider": "emergent"})


class TestDriveConnect:
    def test_connect_auth_required(self):
        r = requests.get(f"{API}/drive/connect", timeout=20)
        assert r.status_code == 401

    def test_connect_has_login_hint_and_prompt(self):
        r = _g("/drive/connect")
        assert r.status_code == 200, r.text
        url = r.json()["authorization_url"]
        q = parse_qs(urlparse(url).query)
        assert "login_hint" in q
        assert q["login_hint"][0] == "luyandasmadonselageneral@gmail.com"
        # prompt should be 'select_account consent' (space-separated, URL-decoded)
        assert q.get("prompt", [""])[0] == "select_account consent"
        # Also verify raw encoding in URL
        assert "login_hint=luyandasmadonselageneral%40gmail.com" in url
        assert "prompt=select_account+consent" in url or "prompt=select_account%20consent" in url
