from __future__ import annotations

import json
from datetime import UTC
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.dashboard import Dashboard, DashboardAsset
from server.models.notebooks import Notebook
from server.models.sharing import SharingAuditEvent, SharingGrant, SharingSecret
from server.models.tenant import Tenant
from server.models.user import User
from server.services.sharing import SharingService

pytestmark = pytest.mark.asyncio


async def _seed_dashboard_asset(test_session: AsyncSession) -> tuple[UUID, UUID, UUID, UUID, str]:
    owner = User(
        id=uuid4(),
        email=f"sharing-owner-{uuid4().hex[:8]}@example.test",
        hashed_password="fakehash",
        is_active=True,
        is_verified=True,
        is_superuser=False,
    )
    test_session.add(owner)
    await test_session.flush()
    tenant = Tenant(
        id=uuid4(),
        name="Sharing Tenant",
        slug=f"sharing-{uuid4().hex[:8]}",
        owner_id=owner.id,
        is_personal=True,
    )
    test_session.add(tenant)
    await test_session.flush()
    notebook = Notebook(
        id=uuid4(),
        tenant_id=tenant.id,
        created_by=owner.id,
        notebook_name="Sharing notebook",
        description="Canonical sharing fixture",
    )
    asset = DashboardAsset(
        id=uuid4(),
        tenant_id=tenant.id,
        notebook_id=notebook.id,
        slug=f"sharing-asset-{uuid4().hex[:8]}",
        name="Sharing dashboard asset",
        description="Governed dashboard",
        owner_id=owner.id,
        lifecycle="published",
        etag="sha256:asset",
    )
    version = Dashboard(
        id=uuid4(),
        tenant_id=tenant.id,
        notebook_id=notebook.id,
        asset_id=asset.id,
        version_num=3,
        html_content="<section>sharing</section>",
        content_hash="sha256:dashboard-version-3",
        status="published",
        created_by=owner.id,
        actor_type="human",
        is_published_immutable=True,
    )
    test_session.add(notebook)
    await test_session.flush()
    test_session.add(asset)
    await test_session.flush()
    test_session.add(version)
    await test_session.flush()
    asset.published_version_id = version.id
    await test_session.commit()
    return tenant.id, owner.id, asset.id, version.id, version.content_hash or ""


async def test_canonical_dashboard_share_pins_immutable_version_and_never_reads_secret(
    test_session: AsyncSession,
) -> None:
    tenant_id, owner_id, asset_id, version_id, version_hash = await _seed_dashboard_asset(test_session)
    service = SharingService(test_session)

    grant = await service.create_dashboard_public_link(
        tenant_id=tenant_id,
        actor_id=owner_id,
        asset_id=asset_id,
        version_id=version_id,
        password="plain-password",
        metadata={"password": "plain-password", "sql": "select * from restricted_table"},
    )

    assert grant.object_type == "dashboard"
    assert grant.object_id == asset_id
    assert grant.object_version_id == version_id
    assert grant.object_version_digest == version_hash
    assert grant.mode == "immutable_version"
    assert grant.status == "active"

    secret = (
        await test_session.execute(select(SharingSecret).where(SharingSecret.grant_id == grant.id))
    ).scalar_one()
    assert secret.secret_type == "password"
    assert secret.verifier_hash != "plain-password"
    assert secret.salt
    serialized_secret = json.dumps(
        {
            "hash": secret.verifier_hash,
            "salt": secret.salt,
            "algorithm": secret.algorithm,
        }
    )
    assert "plain-password" not in serialized_secret
    assert await service.verify_grant_secret(grant_id=grant.id, secret="plain-password") is True
    assert await service.verify_grant_secret(grant_id=grant.id, secret="wrong-password") is False

    audit_details = (
        await test_session.execute(
            select(SharingAuditEvent.details_json).where(SharingAuditEvent.action == "sharing.grant.create")
        )
    ).scalar_one()
    assert "plain-password" not in json.dumps(audit_details)
    assert "restricted_table" not in json.dumps(audit_details)


async def test_viewer_session_binds_grant_object_version_and_revocation(test_session: AsyncSession) -> None:
    tenant_id, owner_id, asset_id, version_id, _ = await _seed_dashboard_asset(test_session)
    service = SharingService(test_session)
    grant = await service.create_dashboard_public_link(
        tenant_id=tenant_id,
        actor_id=owner_id,
        asset_id=asset_id,
        version_id=version_id,
    )

    token, viewer_session = await service.issue_viewer_session(
        tenant_id=tenant_id,
        grant_id=grant.id,
        viewer_user_id=owner_id,
        principal={"email": "viewer@example.test", "token": "raw-token"},
    )

    assert viewer_session.grant_id == grant.id
    assert viewer_session.object_type == "dashboard"
    assert viewer_session.object_id == asset_id
    assert viewer_session.object_version_id == version_id
    assert viewer_session.token_digest.startswith("sha256:")
    assert token not in viewer_session.token_digest
    assert "raw-token" not in json.dumps(viewer_session.viewer_principal_json)

    resolved = await service.require_viewer_session(
        token=token,
        grant_id=grant.id,
        object_id=asset_id,
        object_version_id=version_id,
    )
    assert resolved.id == viewer_session.id

    wrong_version = await service.require_viewer_session(
        token=token,
        grant_id=grant.id,
        object_id=asset_id,
        object_version_id=uuid4(),
    )
    assert wrong_version is None

    await service.revoke_grant(
        tenant_id=tenant_id,
        grant_id=grant.id,
        actor_id=owner_id,
        reason="Owner rotated public link",
    )
    revoked = await test_session.get(SharingGrant, grant.id)
    assert revoked is not None and revoked.status == "revoked"
    assert revoked.revoked_at is not None
    assert await service.require_viewer_session(
        token=token,
        grant_id=grant.id,
        object_id=asset_id,
        object_version_id=version_id,
    ) is None

    audit_actions = (
        await test_session.execute(
            select(SharingAuditEvent.action, SharingAuditEvent.outcome).where(SharingAuditEvent.grant_id == grant.id)
        )
    ).all()
    assert ("sharing.viewer_session.issue", "issued") in audit_actions
    assert ("sharing.grant.revoke", "revoked") in audit_actions


async def test_canonical_share_requires_immutable_dashboard_version(test_session: AsyncSession) -> None:
    tenant_id, owner_id, asset_id, version_id, _ = await _seed_dashboard_asset(test_session)
    version = await test_session.get(Dashboard, version_id)
    assert version is not None
    version.is_published_immutable = False
    version.status = "draft"
    await test_session.commit()

    with pytest.raises(ValueError, match="immutable"):
        await SharingService(test_session).create_dashboard_public_link(
            tenant_id=tenant_id,
            actor_id=owner_id,
            asset_id=asset_id,
            version_id=version_id,
        )


def test_sharing_service_uses_timezone_aware_now() -> None:
    assert SharingService._now().tzinfo is UTC
