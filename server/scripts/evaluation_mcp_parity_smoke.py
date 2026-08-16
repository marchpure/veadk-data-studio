from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from uuid import UUID

from server.mcp.tool_wrappers import (
    compare_evaluation_runs_wrapper,
    describe_evaluation_failure_wrapper,
    describe_evaluation_suite_wrapper,
    get_evaluation_run_wrapper,
    list_evaluation_cases_wrapper,
    run_advisor_gate_wrapper,
    search_evaluation_suites_wrapper,
)


def _load_fixture() -> dict[str, str]:
    if os.getenv("EVALUATION_SMOKE_FIXTURE_JSON"):
        return json.loads(os.environ["EVALUATION_SMOKE_FIXTURE_JSON"])
    fixture_file = os.getenv("EVALUATION_SMOKE_FIXTURE_FILE")
    if fixture_file:
        return json.loads(Path(fixture_file).read_text())
    raise RuntimeError("Set EVALUATION_SMOKE_FIXTURE_JSON or EVALUATION_SMOKE_FIXTURE_FILE")


def _target_snapshot(fixture: dict[str, str], target_ref: str) -> dict:
    return {
        "contract_version": "evaluation.target_snapshot.v1",
        "target_kind": "agent_answer",
        "target_ref": target_ref,
        "app": {
            "git_sha": "evaluation-mcp-smoke",
            "image_digest": "sha256:evaluation-mcp-smoke",
            "migration_revision": "add_evaluation_authoritative_model",
        },
        "source": {"snapshot_id": "mcp-smoke-source", "snapshot_hash": "sha256:mcp-source"},
        "semantic_model": {"version_id": "mcp-smoke-model", "version_hash": "sha256:mcp-model"},
        "prompt": {"version": "mcp-smoke-prompt", "prompt_hash": "sha256:mcp-prompt"},
        "tool_registry_hash": "sha256:mcp-tools",
        "skill_registry_hash": "sha256:mcp-skills",
        "llm": {"provider": "openai", "model": "gpt-smoke", "params_hash": "sha256:mcp-params"},
        "principal": {
            "tenant_id": fixture["tenant_id"],
            "actor_type": "agent",
            "actor_id": "evaluation-mcp-smoke",
            "scopes": ["dashboard.read", "dashboard.query"],
        },
        "dataset": {"snapshot_id": "mcp-smoke-dataset", "snapshot_hash": "sha256:mcp-dataset"},
        "feature_flags": {"evaluation_governance": True},
        "time_fixture": {"now": "2026-08-16T00:00:00Z", "timezone": "UTC"},
    }


def _loads_success(payload: str, operation: str) -> dict:
    data = json.loads(payload)
    if data.get("success") is not True:
        raise AssertionError(f"{operation} failed: {data}")
    serialized = json.dumps(data)
    for forbidden in ("raw-token", "plain-password", "restricted_table", "secret_table"):
        if forbidden in serialized:
            raise AssertionError(f"{operation} leaked {forbidden}")
    return data


async def main() -> None:
    fixture = _load_fixture()
    tenant_id = UUID(fixture["tenant_id"])
    user_id = UUID(fixture["user_id"])

    search = _loads_success(
        await search_evaluation_suites_wrapper("Browser Evaluation Governance", "agent_answer", "published", tenant_id, user_id),
        "search_evaluation_suites",
    )
    assert any(item["id"] == fixture["suite_id"] for item in search["items"])

    suite = _loads_success(
        await describe_evaluation_suite_wrapper(fixture["suite_id"], tenant_id, user_id, True),
        "describe_evaluation_suite",
    )
    assert suite["suite"]["versions"][0]["id"] == fixture["suite_version_id"]

    cases = _loads_success(
        await list_evaluation_cases_wrapper(fixture["suite_version_id"], tenant_id, user_id, True),
        "list_evaluation_cases",
    )
    assert cases["total"] >= 3

    candidate = _loads_success(
        await get_evaluation_run_wrapper(fixture["candidate_run_id"], tenant_id, user_id),
        "get_evaluation_run",
    )
    assert candidate["run"]["summary"]["gate_decision"] == "failed"

    failures = _loads_success(
        await describe_evaluation_failure_wrapper(fixture["candidate_run_id"], tenant_id, user_id),
        "describe_evaluation_failure",
    )
    assert failures["total"] >= 1

    comparison = _loads_success(
        await compare_evaluation_runs_wrapper(
            fixture["baseline_run_id"],
            fixture["candidate_run_id"],
            tenant_id,
            user_id,
        ),
        "compare_evaluation_runs",
    )
    assert comparison["comparison"]["summary"]["regression_count"] >= 1

    verification = _loads_success(
        await get_evaluation_run_wrapper(fixture["verification_run_id"], tenant_id, user_id, False),
        "get_ready_verification_run",
    )
    regression = _loads_success(
        await get_evaluation_run_wrapper(fixture["regression_run_id"], tenant_id, user_id, False),
        "get_ready_regression_run",
    )
    assert verification["run"]["summary"]["gate_decision"] == "passed"
    assert regression["run"]["summary"]["gate_decision"] == "passed"

    queued_verify = _loads_success(
        await run_advisor_gate_wrapper(
            fixture["draft_change_set_id"],
            json.dumps(_target_snapshot(fixture, "custom_skill:mcp-draft-verification")),
            "verification",
            f"mcp-smoke-verification-{fixture['slug']}",
            tenant_id,
            user_id,
        ),
        "run_advisor_verification",
    )
    queued_regression = _loads_success(
        await run_advisor_gate_wrapper(
            fixture["draft_change_set_id"],
            json.dumps(_target_snapshot(fixture, "custom_skill:mcp-draft-regression")),
            "regression",
            f"mcp-smoke-regression-{fixture['slug']}",
            tenant_id,
            user_id,
        ),
        "run_advisor_regression",
    )
    assert queued_verify["run"]["status"] == "queued"
    assert queued_regression["run"]["status"] == "queued"

    print(
        json.dumps(
            {
                "ok": True,
                "suite_id": fixture["suite_id"],
                "case_count": cases["total"],
                "failure_count": failures["total"],
                "regression_count": comparison["comparison"]["summary"]["regression_count"],
                "advisor_verification_status": queued_verify["run"]["status"],
                "advisor_regression_status": queued_regression["run"]["status"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
