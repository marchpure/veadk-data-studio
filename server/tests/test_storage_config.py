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


def test_external_oidc_self_hosted_uses_writable_faas_scratch(monkeypatch):
    import importlib
    import sys

    monkeypatch.delenv("DATA_DIR", raising=False)
    monkeypatch.setenv("APP_MODE", "self-hosted")
    monkeypatch.setenv("DWV1_EXTERNAL_OIDC_ENABLED", "true")
    original_storage = sys.modules.get("server.config.storage")
    sys.modules.pop("server.config.storage", None)
    try:
        storage = importlib.import_module("server.config.storage")
        assert storage.DEFAULT_DATA_DIR == storage.Path("/tmp/dwv1-data-studio")
    finally:
        if original_storage is not None:
            sys.modules["server.config.storage"] = original_storage
        else:
            sys.modules.pop("server.config.storage", None)
