from uuid import UUID

import pytest
from cryptography.exceptions import InvalidTag
from sqlalchemy import func, select

from server.auth.dependencies import _get_auth_context_local
from server.auth.tenant_context import set_tenant_id
from server.models.llm_connections import LLMConnection
from server.models.settings import Setting
from server.models.tenant import Tenant
from server.models.tenant_member import TenantMember, TenantRole
from server.models.user import User
from server.services.community_setup import (
    DEFAULT_TENANT_ID,
    ensure_local_llm_connection,
    get_local_bootstrap,
    get_local_llm_config,
)
from server.services.crypto_service import CryptoService, clear_encryption_key_cache


async def _seed_default_workspace(session) -> None:
    session.add(
        User(
            id=DEFAULT_TENANT_ID,
            email="system@local",
            hashed_password="",
            is_active=True,
            is_verified=True,
            is_superuser=True,
        )
    )
    await session.flush()
    session.add(
        Tenant(
            id=DEFAULT_TENANT_ID,
            name="Default Workspace",
            slug="default",
            owner_id=DEFAULT_TENANT_ID,
            is_personal=False,
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_local_bootstrap_reuses_seed_workspace(test_session) -> None:
    await _seed_default_workspace(test_session)

    first = await get_local_bootstrap(test_session)
    second = await get_local_bootstrap(test_session)

    assert first == second
    assert first["tenant_id"] == str(DEFAULT_TENANT_ID)
    assert first["email"] == "community@local"

    tenant = await test_session.get(Tenant, DEFAULT_TENANT_ID)
    assert tenant is not None
    assert tenant.is_personal is True
    assert str(tenant.owner_id) == first["user_id"]
    assert tenant.owner_id != DEFAULT_TENANT_ID

    member_count = await test_session.scalar(
        select(func.count()).select_from(TenantMember).where(TenantMember.tenant_id == DEFAULT_TENANT_ID)
    )
    assert member_count == 1


@pytest.mark.asyncio
async def test_local_bootstrap_prefers_default_workspace_over_other_personal_tenants(test_session) -> None:
    await _seed_default_workspace(test_session)
    other_user = User(
        email="other-local-owner@test.com",
        hashed_password="x",
        is_active=True,
        is_verified=True,
    )
    test_session.add(other_user)
    await test_session.flush()
    test_session.add(
        Tenant(
            name="Other Personal",
            slug="other-personal",
            owner_id=other_user.id,
            is_personal=True,
        )
    )
    await test_session.commit()

    bootstrap = await get_local_bootstrap(test_session)

    assert bootstrap["tenant_id"] == str(DEFAULT_TENANT_ID)
    assert bootstrap["email"] == "community@local"


@pytest.mark.asyncio
async def test_local_auth_without_header_falls_back_to_default_workspace(test_session) -> None:
    await _seed_default_workspace(test_session)

    auth = await _get_auth_context_local(test_session, None)

    assert auth.tenant_id == DEFAULT_TENANT_ID
    assert auth.user.email == "system@local"
    assert auth.is_owner


@pytest.mark.asyncio
async def test_local_auth_impersonation_is_gated_and_uses_membership(
    test_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_default_workspace(test_session)
    tenant = await test_session.get(Tenant, DEFAULT_TENANT_ID)
    assert tenant is not None
    member = User(
        email="local-member@test.com",
        hashed_password="x",
        is_active=True,
        is_verified=True,
    )
    outsider = User(
        email="local-outsider@test.com",
        hashed_password="x",
        is_active=True,
        is_verified=True,
    )
    test_session.add_all([member, outsider])
    await test_session.flush()
    test_session.add(TenantMember(user_id=member.id, tenant_id=tenant.id, role=TenantRole.MEMBER.value))
    await test_session.commit()

    monkeypatch.delenv("BYAAN_LOCAL_AUTH_IMPERSONATION_ENABLED", raising=False)
    gated = await _get_auth_context_local(test_session, str(tenant.id), str(member.id))
    assert gated.user_id == tenant.owner_id
    assert gated.role == TenantRole.OWNER

    monkeypatch.setenv("BYAAN_LOCAL_AUTH_IMPERSONATION_ENABLED", "true")
    impersonated = await _get_auth_context_local(test_session, str(tenant.id), str(member.id))
    assert impersonated.user_id == member.id
    assert impersonated.role == TenantRole.MEMBER

    with pytest.raises(Exception) as exc_info:
        await _get_auth_context_local(test_session, str(tenant.id), str(outsider.id))
    assert getattr(exc_info.value, "status_code", None) == 403


def test_local_llm_config_prefers_dedicated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "dedicated-key")
    monkeypatch.setenv("ARK_API_KEY", "ark-key")
    monkeypatch.setenv("OPENAI_API_KEY", "generic-key")
    monkeypatch.setenv("LLM_ENDPOINT", "https://ark.example/api/v3")
    monkeypatch.setenv("LLM_MODEL", "doubao-test")

    assert get_local_llm_config() == {
        "api_key": "dedicated-key",
        "api_base": "https://ark.example/api/v3",
        "model": "doubao-test",
    }


@pytest.mark.asyncio
async def test_local_llm_connection_is_encrypted_and_idempotent(
    test_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_default_workspace(test_session)
    bootstrap = await get_local_bootstrap(test_session)
    tenant = await test_session.get(Tenant, UUID(bootstrap["tenant_id"]))
    user = await test_session.get(User, UUID(bootstrap["user_id"]))
    assert tenant is not None and user is not None

    monkeypatch.setenv("LLM_API_KEY", "secret-ark-key")
    monkeypatch.setenv("LLM_ENDPOINT", "https://ark.example/api/v3")
    monkeypatch.setenv("LLM_MODEL", "doubao-test")
    clear_encryption_key_cache()
    set_tenant_id(tenant.id)

    first = await ensure_local_llm_connection(test_session, tenant, user)
    second = await ensure_local_llm_connection(test_session, tenant, user)

    assert first is not None and second is not None
    assert first.id == second.id
    assert first.config is not None
    assert "secret-ark-key" not in first.config
    assert await CryptoService.decrypt_config(first.config, test_session) == {
        "api_key": "secret-ark-key",
        "api_base": "https://ark.example/api/v3",
        "model": "doubao-test",
    }

    connection_count = await test_session.scalar(
        select(func.count())
        .select_from(LLMConnection)
        .where(LLMConnection.tenant_id == tenant.id, LLMConnection.type == "openai")
    )
    assert connection_count == 1


@pytest.mark.asyncio
async def test_app_encryption_key_is_bound_to_current_tenant(test_session) -> None:
    await _seed_default_workspace(test_session)
    tenant = await test_session.get(Tenant, DEFAULT_TENANT_ID)
    assert tenant is not None
    other_user = User(
        email="second-tenant-owner@test.com",
        hashed_password="x",
        is_active=True,
        is_verified=True,
    )
    test_session.add(other_user)
    await test_session.flush()
    other_tenant = Tenant(
        name="Second Tenant",
        slug="second-tenant",
        owner_id=other_user.id,
        is_personal=True,
    )
    test_session.add(other_tenant)
    await test_session.commit()
    await test_session.refresh(other_tenant)

    tenant_key_value = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    other_key_value = "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE="
    test_session.add_all(
        [
            Setting(
                tenant_id=tenant.id,
                setting_key="app_encryption_key",
                setting_value=tenant_key_value,
                is_encrypted=False,
            ),
            Setting(
                tenant_id=other_tenant.id,
                setting_key="app_encryption_key",
                setting_value=other_key_value,
                is_encrypted=False,
            ),
        ]
    )
    await test_session.commit()

    clear_encryption_key_cache()
    set_tenant_id(tenant.id)
    encrypted = await CryptoService.encrypt_config({"api_key": "k", "api_base": "u", "model": "m"}, test_session)
    clear_encryption_key_cache()
    set_tenant_id(other_tenant.id)

    with pytest.raises(InvalidTag):
        await CryptoService.decrypt_config(encrypted, test_session)

    clear_encryption_key_cache()
    set_tenant_id(tenant.id)
    assert await CryptoService.decrypt_config(encrypted, test_session) == {"api_key": "k", "api_base": "u", "model": "m"}
