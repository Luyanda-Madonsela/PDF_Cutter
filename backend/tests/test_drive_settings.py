import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import drive  # noqa: E402


def test_drive_settings_load_without_optional_default_path(monkeypatch):
    async def no_saved_settings(query):
        return None

    monkeypatch.delenv("DRIVE_ROOT_PATH", raising=False)
    monkeypatch.delenv("DRIVE_ROOT_FOLDER_ID", raising=False)
    monkeypatch.setattr(drive.db.settings, "find_one", no_saved_settings)

    settings = asyncio.run(drive.drive_settings())

    assert settings == {"root_id": None, "root_path": ""}
