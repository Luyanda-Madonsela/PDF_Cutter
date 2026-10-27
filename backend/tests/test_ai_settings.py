import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import ai
import llm
import core
from llm import normalize_openrouter_models


def test_openrouter_model_catalogue_returns_all_valid_models_sorted_by_name():
    entries = [
        {"id": "provider/z-model", "name": "Zulu Model"},
        {"id": "provider/a-model", "name": "Alpha Model"},
        {"name": "Missing model ID"},
        "invalid entry",
    ]

    assert normalize_openrouter_models({"data": entries}) == [
        {"id": "provider/a-model", "name": "Alpha Model", "supports_image": False},
        {"id": "provider/z-model", "name": "Zulu Model", "supports_image": False},
    ]


def test_openrouter_catalogue_marks_vision_models():
    models = normalize_openrouter_models({"data": [
        {"id": "provider/vision", "architecture": {"input_modalities": ["text", "image"]}},
        {"id": "provider/text", "architecture": {"input_modalities": ["text"]}},
    ]})

    assert {model["id"]: model["supports_image"] for model in models} == {
        "provider/text": False,
        "provider/vision": True,
    }


def test_openrouter_model_catalogue_rejects_unexpected_response():
    with pytest.raises(ValueError, match="invalid model catalogue"):
        normalize_openrouter_models({"models": []})


def test_openrouter_environment_key_is_used_when_no_saved_provider_key(monkeypatch):
    monkeypatch.setattr(llm, "OPENROUTER_KEY", "environment-openrouter-key")

    config = llm.resolve({"provider": "openrouter", "models": {}, "keys": {}})

    assert config["provider"] == "openrouter"
    assert config["key"] == "environment-openrouter-key"
    assert config["fallback"] is False


def test_unsaved_ai_settings_default_to_openrouter(monkeypatch):
    class EmptySettings:
        async def find_one(self, _query):
            return None

    monkeypatch.setattr(llm, "db", type("Database", (), {"settings": EmptySettings()})())

    settings = asyncio.run(llm.ai_settings())

    assert settings["provider"] == "openrouter"
    assert llm.resolve(settings)["model"] == "google/gemini-3-flash-preview"


def test_openrouter_without_key_does_not_fall_back_to_google(monkeypatch):
    monkeypatch.setattr(llm, "OPENROUTER_KEY", "")

    config = llm.resolve({"provider": "openrouter", "models": {}, "keys": {}})

    assert config["provider"] == "openrouter"
    assert config["key"] == "none"
    assert config["fallback"] is False
    assert "OPENROUTER_API_KEY" in llm._provider_error(config, RuntimeError("missing key"))


def test_saved_openrouter_key_takes_precedence_over_environment(monkeypatch):
    monkeypatch.setattr(llm, "OPENROUTER_KEY", "environment-openrouter-key")

    config = llm.resolve({
        "provider": "openrouter",
        "models": {},
        "keys": {"openrouter": "saved-openrouter-key"},
    })

    assert config["key"] == "saved-openrouter-key"


def test_google_invalid_api_key_gets_actionable_error_without_credentials():
    error = llm.invalid_api_key_message({"provider": "emergent"})

    assert "Google rejected the API key" in error
    assert "EMERGENT_LLM_KEY" in error
    assert "key-value" not in error
    assert llm.is_invalid_api_key_error(Exception("reason: API_KEY_INVALID"))


def test_ai_processing_stops_retrying_after_invalid_api_key(monkeypatch):
    calls = []

    async def fake_settings():
        return {}

    async def fake_complete(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("reason: API_KEY_INVALID")

    monkeypatch.setattr(ai, "ai_settings", fake_settings)
    monkeypatch.setattr(ai, "resolve", lambda _settings: {"provider": "emergent"})
    monkeypatch.setattr(ai, "complete", fake_complete)

    with pytest.raises(RuntimeError, match="Google rejected the API key"):
        asyncio.run(ai.ask_json("prompt", None, "session"))

    assert calls == [1]


def test_text_only_openrouter_model_is_rejected_before_request(monkeypatch):
    monkeypatch.setattr(llm, "fetch_openrouter_models", lambda: [
        {"id": "deepseek/deepseek-v4-pro", "name": "DeepSeek V4 Pro", "supports_image": False}
    ])

    with pytest.raises(RuntimeError, match="only supports text input"):
        asyncio.run(llm.validate_openrouter_image_model("deepseek/deepseek-v4-pro"))


def test_vision_openrouter_model_is_accepted(monkeypatch):
    monkeypatch.setattr(llm, "fetch_openrouter_models", lambda: [
        {"id": "anthropic/claude-fable-5", "name": "Claude Fable 5", "supports_image": True}
    ])

    asyncio.run(llm.validate_openrouter_image_model("anthropic/claude-fable-5"))


def test_local_database_snapshot_restores_sets_and_jobs(tmp_path):
    mongomock = pytest.importorskip("mongomock")
    original_client = mongomock.MongoClient()
    original_db = original_client["papercut"]
    original_db.sets.insert_one({"_id": "set-1", "status": "processing"})
    original_db.jobs.insert_one({"_id": "job-1", "set_id": "set-1", "status": "queued"})
    original_db.settings.insert_one({"_id": "ai", "provider": "openrouter"})
    snapshot_path = tmp_path / "metadata.json"

    core._save_local_snapshot(original_client, snapshot_path)

    restored_client = mongomock.MongoClient()
    core._restore_local_snapshot(restored_client, snapshot_path)

    assert restored_client["papercut"].sets.find_one({"_id": "set-1"})["status"] == "processing"
    assert restored_client["papercut"].jobs.find_one({"_id": "job-1"})["set_id"] == "set-1"
    assert restored_client["papercut"].settings.find_one({"_id": "ai"})["provider"] == "openrouter"


def test_local_database_snapshot_is_updated_after_set_job_writes(tmp_path, monkeypatch):
    mongomock = pytest.importorskip("mongomock")
    raw_client = mongomock.MongoClient()
    snapshot_path = tmp_path / "metadata.json"
    monkeypatch.setattr(core, "LOCAL_DB_SNAPSHOT", snapshot_path)
    wrapped_client = core._AsyncMongoClient(raw_client, lambda: core._save_local_snapshot(raw_client, snapshot_path))
    wrapped_db = wrapped_client["papercut"]

    asyncio.run(wrapped_db.jobs.insert_one({"_id": "job-1", "status": "queued"}))

    restored_client = mongomock.MongoClient()
    core._restore_local_snapshot(restored_client, snapshot_path)
    assert restored_client["papercut"].jobs.find_one({"_id": "job-1"})["status"] == "queued"


def test_local_database_aggregate_returns_async_iterable_cursor():
    mongomock = pytest.importorskip("mongomock")
    raw_client = mongomock.MongoClient()
    wrapped_db = core._AsyncMongoClient(raw_client)["papercut"]
    raw_client["papercut"].sets.insert_one({"_id": "set-1", "status": "done", "is_deleted": False})

    async def collect_counts():
        return [
            item async for item in wrapped_db.sets.aggregate([
                {"$match": {"is_deleted": False}},
                {"$group": {"_id": "$status", "n": {"$sum": 1}}},
            ])
        ]

    assert asyncio.run(collect_counts()) == [{"_id": "done", "n": 1}]
