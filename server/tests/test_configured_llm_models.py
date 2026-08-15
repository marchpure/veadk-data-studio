from server.constants.models import configured_model_for_provider
from server.models.llm_connections import LLMConnection
from server.services.crypto_service import CryptoService
from server.services.llm_service import build_litellm_params


def test_openai_compatible_custom_model_uses_provider_prefix() -> None:
    assert configured_model_for_provider("openai", {"model": "doubao-seed-test"}) == "openai/doubao-seed-test"


def test_existing_provider_prefix_is_preserved() -> None:
    assert configured_model_for_provider("openai", {"model": "openai/gpt-5.4"}) == "openai/gpt-5.4"


def test_missing_model_is_ignored() -> None:
    assert configured_model_for_provider("openai", {}) is None


async def test_openai_compatible_model_is_routed_through_openai(monkeypatch) -> None:
    async def decrypt_config(_config, _session):
        return {
            "api_key": "secret",
            "api_base": "https://ark.example/api/v3",
            "model": "doubao-seed-test",
        }

    monkeypatch.setattr(CryptoService, "decrypt_config", decrypt_config)
    connection = LLMConnection(type="openai", config="encrypted", tenant_id=None)

    params = await build_litellm_params(connection)

    assert params["model"] == "openai/doubao-seed-test"
    assert params["base_url"] == "https://ark.example/api/v3"


async def test_legacy_double_openai_prefix_is_normalized(monkeypatch) -> None:
    async def decrypt_config(_config, _session):
        return {"api_key": "secret", "model": "openai/openai/doubao-seed-test"}

    monkeypatch.setattr(CryptoService, "decrypt_config", decrypt_config)
    connection = LLMConnection(type="openai", config="encrypted", tenant_id=None)

    params = await build_litellm_params(connection, model="openai/openai/doubao-seed-test")

    assert params["model"] == "openai/doubao-seed-test"


async def test_custom_openai_endpoint_uses_its_configured_model_over_stale_preference(monkeypatch) -> None:
    async def decrypt_config(_config, _session):
        return {
            "api_key": "secret",
            "api_base": "https://ark.example/api/v3",
            "model": "openai/doubao-seed-test",
        }

    monkeypatch.setattr(CryptoService, "decrypt_config", decrypt_config)
    connection = LLMConnection(type="openai", config="encrypted", tenant_id=None)

    params = await build_litellm_params(connection, model="openai/gpt-does-not-exist")

    assert params["model"] == "openai/doubao-seed-test"
