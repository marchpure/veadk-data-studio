from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.models.evaluation import EvaluationAuditEvent, EvaluationRun, EvaluationSuite, EvaluationSuiteVersion
from server.models.tenant import Tenant
from server.models.user import User
from server.services.evaluation import EvaluationService

pytestmark = pytest.mark.asyncio


async def _seed_suite_version(test_session: AsyncSession) -> tuple[str, str]:
    tenant = (await test_session.execute(select(Tenant))).scalars().first()
    if tenant is None:
        owner = User(
            id=uuid4(),
            email=f"evaluation-owner-{uuid4()}@example.test",
            hashed_password="fakehash",
            is_active=True,
            is_verified=True,
            is_superuser=False,
        )
        test_session.add(owner)
        await test_session.flush()
        tenant = Tenant(
            id=uuid4(),
            name="Evaluation Tenant",
            slug=f"evaluation-{uuid4().hex[:8]}",
            owner_id=owner.id,
            is_personal=True,
        )
        test_session.add(tenant)
        await test_session.flush()
    suite = EvaluationSuite(
        tenant_id=tenant.id,
        slug=f"eval-suite-{uuid4()}",
        name="Revenue suite",
        description="Evaluation suite for governed revenue answers",
        owner_id=tenant.owner_id,
        lifecycle="draft",
    )
    test_session.add(suite)
    await test_session.flush()
    version = EvaluationSuiteVersion(
        tenant_id=tenant.id,
        suite_id=suite.id,
        version_num=1,
        status="draft",
        contract_version="evaluation.suite_version.v1",
        manifest_json={"contract_version": "evaluation.suite_version.v1", "suite_id": "suite", "version": 1},
        gate_policy_json={"version": "gate-policy.v1", "security_hard_fail": True},
        case_count=0,
        content_hash="sha256:draft",
        created_by=tenant.owner_id,
    )
    test_session.add(version)
    await test_session.commit()
    return str(tenant.id), str(version.id)


def _incomplete_snapshot() -> dict:
    return {
        "contract_version": "evaluation.target_snapshot.v1",
        "target_kind": "semantic_model",
        "target_ref": "semantic_model:sales",
        "app": {"git_sha": "abc123"},
        "principal": {"tenant_id": "tenant-1", "actor_type": "human", "actor_id": "user-1", "scopes": []},
        "feature_flags": {},
        "time_fixture": {"timezone": "UTC"},
    }


async def test_evaluation_preflight_blocks_missing_required_target_pins(test_session: AsyncSession) -> None:
    tenant_id, suite_version_id = await _seed_suite_version(test_session)

    run = await EvaluationService(test_session).create_preflight_run(
        tenant_id=tenant_id,
        suite_version_id=suite_version_id,
        target_snapshot_payload=_incomplete_snapshot(),
        actor_id="agent-1",
        idempotency_key="preflight-missing-pins",
    )

    assert run.status == "blocked"
    assert "source.snapshot_hash" in run.preflight_blockers_json
    assert "semantic_model.version_hash" in run.preflight_blockers_json
    saved = await test_session.get(EvaluationRun, run.id)
    assert saved is not None and saved.status == "blocked"
    audit_actions = (
        await test_session.execute(
            select(EvaluationAuditEvent.action, EvaluationAuditEvent.outcome).where(EvaluationAuditEvent.run_id == run.id)
        )
    ).all()
    assert audit_actions == [("evaluation.run.preflight", "blocked")]


async def test_published_suite_version_is_immutable_through_service(test_session: AsyncSession) -> None:
    tenant_id, suite_version_id = await _seed_suite_version(test_session)
    service = EvaluationService(test_session)

    await service.publish_suite_version(tenant_id=tenant_id, suite_version_id=suite_version_id, actor_id="owner")

    with pytest.raises(ValueError, match="immutable"):
        await service.patch_suite_version_manifest(
            tenant_id=tenant_id,
            suite_version_id=suite_version_id,
            patch={"title": "mutated"},
        )
