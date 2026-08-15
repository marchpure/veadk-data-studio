from __future__ import annotations

import importlib
import sys


def test_data_dir_overrides_default_storage_root(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "app-data"))
    original_storage = sys.modules.get("server.config.storage")
    sys.modules.pop("server.config.storage", None)

    try:
        storage = importlib.import_module("server.config.storage")

        assert storage.DEFAULT_DATA_DIR == tmp_path / "app-data"
        assert storage.DEFAULT_DATA_DIR.is_dir()
    finally:
        if original_storage is not None:
            sys.modules["server.config.storage"] = original_storage
        else:
            sys.modules.pop("server.config.storage", None)
