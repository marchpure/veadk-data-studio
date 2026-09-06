from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from server.db.base import Base
from server.models.delegation import Delegation
from server.models.tenant import Tenant
from server.models.user import User
from server.services import delegation_broker


@pytest_asyncio.fixture
async def broker_db(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'broker.db'}")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[User.__table__, Tenant.__table__, Delegation.__table__],
        )

    async def encrypt(value, session=None):
        return _blob(value)

    async def decrypt(value, session=None):
        return _unblob(value)

    monkeypatch.setattr(delegation_broker.CryptoService, "encrypt_config", staticmethod(encrypt))
    monkeypatch.setattr(delegation_broker.CryptoService, "decrypt_config", staticmethod(decrypt))
    monkeypatch.setenv("I4A_DELEGATION_ISSUER", "https://issuer.example")
    monkeypatch.setenv("I4A_DELEGATION_USER_POOL", "pool-a")
    monkeypatch.setenv("I4A_DELEGATION_GROUP_UID", "group-a")
    monkeypatch.setenv("I4A_DELEGATION_AUDIENCE", "dwv1-skill-agent")
    monkeypatch.setenv("DWV1_OIDC_AUDIENCE", "dwv1-skill-agent")
    yield factory
    await engine.dispose()


def _blob(value: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(value).encode()).decode()


def _unblob(value: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(value.encode()))


@pytest.mark.asyncio
async def test_broker_issue_requires_verified_external_identity(broker_db):
    owner = SimpleNamespace(
        tenant_id=uuid4(),
        external_subject=None,
        external_groups=(),
        access_token=None,
        id_token=None,
        external_issuer=None,
        external_audience=None,
        external_user_pool=None,
    )
    async with broker_db() as db:
        with pytest.raises(delegation_broker.DelegationBrokerError) as error:
            await delegation_broker.issue_from_auth(owner, db)
        assert error.value.code == "BLOCKED_AUTH"


@pytest.mark.asyncio
async def test_broker_issue_rejects_identity_binding_drift(broker_db):
    owner = SimpleNamespace(
        tenant_id=uuid4(),
        external_subject="subject-a",
        external_groups=("group-a",),
        access_token="short-lived-token",
        id_token=None,
        external_issuer="https://other-issuer.example",
        external_audience="dwv1-skill-agent",
        external_user_pool="pool-a",
    )
    async with broker_db() as db:
        with pytest.raises(delegation_broker.DelegationBrokerError) as error:
            await delegation_broker.issue_from_auth(owner, db)
        assert error.value.code == "BLOCKED_AUTH"


@pytest.mark.asyncio
async def test_broker_issue_keeps_oidc_and_delegation_audiences_distinct(broker_db, monkeypatch):
    monkeypatch.setenv("DWV1_OIDC_AUDIENCE", "data-studio-oauth-client")
    owner = SimpleNamespace(
        tenant_id=uuid4(),
        external_subject="subject-a",
        external_groups=("group-a",),
        access_token="short-lived-token",
        id_token=None,
        external_issuer="https://issuer.example",
        external_audience="data-studio-oauth-client",
        external_user_pool="pool-a",
    )

    async with broker_db() as db:
        ref = await delegation_broker.issue_from_auth(owner, db)
        await db.commit()

        record = (
            await db.execute(
                delegation_broker.select(Delegation).where(
                    Delegation.ref_hash == delegation_broker._ref_hash(ref)
                )
            )
        ).scalar_one()
        assert record.audience == "dwv1-skill-agent"


@pytest.mark.asyncio
async def test_broker_exchanges_access_token_for_mcp_audience(broker_db, monkeypatch):
    monkeypatch.setenv("DWV1_OIDC_AUDIENCE", "data-studio-oauth-client")
    monkeypatch.setenv("DWV1_MCP_AUDIENCE", "openconnector-resource")
    owner = SimpleNamespace(
        tenant_id=uuid4(),
        external_subject="subject-a",
        external_groups=("group-a",),
        access_token="browser-token",
        id_token="browser-id-token",
        external_issuer="https://issuer.example",
        external_audience="data-studio-oauth-client",
        external_user_pool="pool-a",
    )

    async def exchange(_token, *, id_token=None):
        assert id_token == "browser-id-token"
        return "mcp-resource-token"

    monkeypatch.setattr(delegation_broker, "_exchange_for_mcp_audience", exchange)
    async with broker_db() as db:
        ref = await delegation_broker.issue_from_auth(owner, db)
        record = (
            await db.execute(
                delegation_broker.select(Delegation).where(
                    Delegation.ref_hash == delegation_broker._ref_hash(ref)
                )
            )
        ).scalar_one()
        encrypted = await delegation_broker.CryptoService.decrypt_config(record.encrypted_access_token, db)
        assert encrypted["access_token"] == "mcp-resource-token"


@pytest.mark.asyncio
async def test_exchange_uses_id_token_and_omits_empty_public_client_secret(monkeypatch):
    monkeypatch.setenv("DWV1_MCP_AUDIENCE", "mcp-audience")
    monkeypatch.setenv("DWV1_MCP_RESOURCE", "https://mcp.example/mcp")

    class Response:
        status_code = 200

        def json(self):
            return {"access_token": "exchanged-token"}

    calls = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, endpoint, **kwargs):
            calls.append((endpoint, kwargs))
            return Response()

    async def discovery():
        return {"token_endpoint": "https://issuer.example/oauth/token"}

    monkeypatch.setattr(delegation_broker.httpx, "AsyncClient", lambda **_kwargs: Client())
    from server.services import external_oidc

    async def client_secret():
        return ""

    monkeypatch.setattr(external_oidc, "_client_id", lambda: "public-client")
    monkeypatch.setattr(external_oidc, "_client_secret", client_secret)
    monkeypatch.setattr(external_oidc, "_discovery", discovery)

    result = await delegation_broker._exchange_for_mcp_audience(
        "access-token",
        id_token="id-token",
    )
    assert result == "exchanged-token"
    form = calls[0][1]["data"]
    assert form["subject_token"] == "id-token"
    assert form["subject_token_type"] == delegation_broker.ID_TOKEN_TYPE
    assert form["requested_token_type"] == delegation_broker.ACCESS_TOKEN_TYPE
    assert form["audience"] == "mcp-audience"
    assert form["resource"] == "https://mcp.example/mcp"
    assert "client_secret" not in form


@pytest.mark.asyncio
async def test_broker_issue_rejects_missing_required_group_as_auth_failure(broker_db):
    owner = SimpleNamespace(
        tenant_id=uuid4(),
        external_subject="subject-a",
        external_groups=("different-group",),
        access_token="short-lived-token",
        external_issuer="https://issuer.example",
        external_audience="dwv1-skill-agent",
        external_user_pool="pool-a",
    )
    async with broker_db() as db:
        with pytest.raises(delegation_broker.DelegationBrokerError) as error:
            await delegation_broker.issue_from_auth(owner, db)
        assert error.value.code == "BLOCKED_AUTH"


@pytest.mark.asyncio
async def test_broker_resolve_is_single_use_and_scope_bound(broker_db, monkeypatch):
    tenant_id = uuid4()
    owner = SimpleNamespace(
        tenant_id=tenant_id,
        external_subject="subject-a",
        external_groups=("group-a",),
        access_token="short-lived-token",
        external_issuer="https://issuer.example",
        external_audience="dwv1-skill-agent",
        external_user_pool="pool-a",
    )
    async with broker_db() as db:
        ref = await delegation_broker.issue_from_auth(owner, db)
        await db.commit()

    async def service_credential():
        return _credential()

    monkeypatch.setattr(delegation_broker, "_service_credential", service_credential)
    async with broker_db() as db:
        request = SimpleNamespace(headers={"authorization": f"Bearer {_credential()}"})
        body = {
            "intended_audience": "dwv1-skill-agent",
            "tenant_id": str(tenant_id),
            "request_id": "request-a",
        }
        resolved = await delegation_broker.resolve(request, ref, body, db)
        assert resolved["subject"] == "subject-a"
        assert resolved["access_token"] == "short-lived-token"
        with pytest.raises(HTTPException) as error:
            await delegation_broker.resolve(request, ref, body, db)
        assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_broker_resolve_rejects_origin_credentials_scope_and_ref_shape(broker_db, monkeypatch):
    tenant_id = uuid4()
    owner = SimpleNamespace(
        tenant_id=tenant_id,
        external_subject="subject-a",
        external_groups=("group-a",),
        access_token="short-lived-token",
        external_issuer="https://issuer.example",
        external_audience="dwv1-skill-agent",
        external_user_pool="pool-a",
    )
    async with broker_db() as db:
        ref = await delegation_broker.issue_from_auth(owner, db)
        await db.commit()

    async def service_credential():
        return _credential()

    monkeypatch.setattr(delegation_broker, "_service_credential", service_credential)
    body = {
        "intended_audience": "dwv1-skill-agent",
        "tenant_id": str(tenant_id),
        "request_id": "request-b",
    }

    origin_request = SimpleNamespace(
        headers={"authorization": f"Bearer {_credential()}", "origin": "https://frontend.example"}
    )
    async with broker_db() as db:
        with pytest.raises(HTTPException) as error:
            await delegation_broker.resolve(origin_request, ref, body, db)
        assert error.value.status_code == 403

    bad_credential = SimpleNamespace(headers={"authorization": "Bearer wrong"})
    async with broker_db() as db:
        with pytest.raises(HTTPException) as error:
            await delegation_broker.resolve(bad_credential, ref, body, db)
        assert error.value.status_code == 401

    wrong_tenant = {**body, "tenant_id": str(uuid4())}
    valid_request = SimpleNamespace(headers={"authorization": f"Bearer {_credential()}"})
    async with broker_db() as db:
        with pytest.raises(HTTPException) as error:
            await delegation_broker.resolve(valid_request, ref, wrong_tenant, db)
        assert error.value.status_code == 404

    wrong_audience = {**body, "intended_audience": "other-audience"}
    async with broker_db() as db:
        with pytest.raises(HTTPException) as error:
            await delegation_broker.resolve(valid_request, ref, wrong_audience, db)
        assert error.value.status_code == 404

    async with broker_db() as db:
        with pytest.raises(HTTPException) as error:
            await delegation_broker.resolve(valid_request, "viking://resources/legacy", body, db)
        assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_broker_expiry_and_revoke_fail_closed(broker_db, monkeypatch):
    tenant_id = uuid4()
    owner = SimpleNamespace(
        tenant_id=tenant_id,
        external_subject="subject-a",
        external_groups=("group-a",),
        access_token="short-lived-token",
        external_issuer="https://issuer.example",
        external_audience="dwv1-skill-agent",
        external_user_pool="pool-a",
    )

    async def service_credential():
        return _credential()

    monkeypatch.setattr(delegation_broker, "_service_credential", service_credential)
    async with broker_db() as db:
        expired_ref = await delegation_broker.issue_from_auth(owner, db)
        record = (
            await db.execute(
                delegation_broker.select(Delegation).where(
                    Delegation.ref_hash == delegation_broker._ref_hash(expired_ref)
                )
            )
        ).scalar_one()
        record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()

    request = SimpleNamespace(headers={"authorization": f"Bearer {_credential()}"})
    body = {
        "intended_audience": "dwv1-skill-agent",
        "tenant_id": str(tenant_id),
        "request_id": "request-expired",
    }
    async with broker_db() as db:
        with pytest.raises(HTTPException) as error:
            await delegation_broker.resolve(request, expired_ref, body, db)
        assert error.value.status_code == 404

    async with broker_db() as db:
        revoked_ref = await delegation_broker.issue_from_auth(owner, db)
        await delegation_broker.revoke(revoked_ref, tenant_id, db)
        await db.commit()
    async with broker_db() as db:
        with pytest.raises(HTTPException) as error:
            await delegation_broker.resolve(request, revoked_ref, body, db)
        assert error.value.status_code == 404


def _credential() -> str:
    return "broker-service-credential"
