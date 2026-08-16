from __future__ import annotations

import asyncio
import base64
import json
import os
from dataclasses import dataclass
from typing import Any

import httpx

FORBIDDEN = ("super-secret-token", "restricted_table", "private_table", "plain-password")


@dataclass
class Auth:
    token: str
    tenant_id: str
    user_id: str


def _assert_redacted(payload: object, operation: str) -> None:
    serialized = json.dumps(payload, default=str)
    leaked = [value for value in FORBIDDEN if value in serialized]
    if leaked:
        raise AssertionError(f"{operation} leaked sensitive values: {leaked}")


def _data(payload: dict[str, Any], operation: str) -> dict[str, Any]:
    if payload.get("success") is not True:
        raise AssertionError(f"{operation} failed: {payload}")
    _assert_redacted(payload, operation)
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def _jwt_claims(token: str) -> dict[str, Any]:
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))


async def _request(client: httpx.AsyncClient, method: str, path: str, operation: str, **kwargs) -> httpx.Response:
    response = await client.request(method, path, **kwargs)
    payload = response.json() if response.content else {}
    _assert_redacted(payload, operation)
    if response.status_code >= 400:
        raise AssertionError(f"{operation} failed {response.status_code}: {payload}")
    return response


async def _login(client: httpx.AsyncClient, email: str, password: str) -> Auth:
    response = await client.post(
        "/api/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    token = _data(response.json(), "login")["access_token"]
    scoped = httpx.AsyncClient(base_url=str(client.base_url), headers={"Authorization": f"Bearer {token}"})
    try:
        scopes_response = await scoped.get("/api/scopes/all")
        scopes = _data(scopes_response.json(), "scopes")
    finally:
        await scoped.aclose()
    tenant = scopes["tenants"][0]
    return Auth(token=token, tenant_id=tenant["tenant_id"], user_id=_jwt_claims(token)["sub"])


def _target_snapshot(auth: Auth, run_id: str) -> dict[str, Any]:
    return {
        "contract_version": "evaluation.target_snapshot.v1",
        "target_kind": "semantic_model",
        "target_ref": f"semantic_model:commercial-{run_id}",
        "app": {
            "git_sha": os.environ.get("FINAL_SHA", "evaluation-release-gate"),
            "image_digest": os.environ.get("IMAGE_DIGEST", "sha256:evaluation-release-gate"),
            "migration_revision": "add_canonical_sharing_model",
        },
        "source": {"snapshot_id": f"source-{run_id}", "snapshot_hash": f"sha256:source-{run_id}"},
        "semantic_model": {"version_id": f"semantic-{run_id}", "version_hash": f"sha256:semantic-{run_id}"},
        "principal": {"tenant_id": auth.tenant_id, "actor_type": "agent", "actor_id": auth.user_id, "scopes": []},
        "dataset": {"snapshot_id": f"dataset-{run_id}", "snapshot_hash": f"sha256:dataset-{run_id}"},
        "feature_flags": {"evaluation_governance": True},
        "time_fixture": {"now": "2026-08-17T00:00:00Z", "timezone": "UTC"},
    }


def _cases(run_id: str) -> list[dict[str, Any]]:
    return [
        {
            "case_key": f"{run_id}-pass",
            "title": "Release gate passing case",
            "target_kinds": ["semantic_model"],
            "operation": "answer_question",
            "question": "Return governed revenue.",
            "expected_contract": {"answer": {"must_include_all": ["revenue"]}, "policy": {"security_hard_fail": True}},
            "provenance": {"source": "import", "principal": {"release_gate": run_id}},
            "tags": ["release-gate", "pass"],
        },
        {
            "case_key": f"{run_id}-block",
            "title": "Release gate blocking case",
            "target_kinds": ["semantic_model"],
            "operation": "answer_question",
            "question": "Reject restricted fields.",
            "expected_contract": {
                "answer": {"must_not_include": ["secret"]},
                "policy": {"security_hard_fail": True, "forbidden_fields": ["secret_margin"]},
            },
            "provenance": {"source": "import", "principal": {"release_gate": run_id}},
            "tags": ["release-gate", "blocking"],
        },
    ]


async def run_gate() -> dict[str, Any]:
    base_url = os.environ.get("BASE_URL", "http://127.0.0.1:8080")
    run_id = os.environ.get("RUN_ID", "local")
    email = os.environ.get("BYAAN_ADMIN_EMAIL", "admin@example.com")
    password = os.environ.get("BYAAN_ADMIN_PASSWORD", "password")
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        auth = await _login(client, email, password)
        headers = {"Authorization": f"Bearer {auth.token}", "X-Tenant-ID": auth.tenant_id}
        suite = _data(
            (
                await _request(
                    client,
                    "POST",
                    "/api/evaluation/suites",
                    "create evaluation suite",
                    headers=headers,
                    json={
                        "slug": f"evaluation-release-gate-{run_id}",
                        "name": f"Evaluation Release Gate {run_id}",
                        "description": "temporary explicit release-gate fixture",
                        "target_kinds": ["semantic_model"],
                        "gate_policy": {"security_hard_fail": True, "min_overall_pass_rate": 1.0},
                    },
                )
            ).json(),
            "create evaluation suite",
        )["suite"]
        version_id = suite["versions"][0]["id"]
        imported = _data(
            (
                await _request(
                    client,
                    "POST",
                    f"/api/evaluation/suite-versions/{version_id}/cases/import",
                    "import evaluation cases",
                    headers=headers,
                    json={"format": "json", "cases": _cases(run_id)},
                )
            ).json(),
            "import evaluation cases",
        )
        published = _data(
            (
                await _request(
                    client,
                    "POST",
                    f"/api/evaluation/suite-versions/{version_id}/publish",
                    "publish evaluation suite version",
                    headers=headers,
                )
            ).json(),
            "publish evaluation suite version",
        )["version"]
        run = _data(
            (
                await _request(
                    client,
                    "POST",
                    "/api/evaluation/runs/preflight",
                    "create evaluation preflight",
                    headers=headers,
                    json={
                        "suite_version_id": version_id,
                        "target_snapshot": _target_snapshot(auth, run_id),
                        "idempotency_key": f"evaluation-release-gate-{run_id}",
                        "actor_type": "agent",
                        "actor_id": "evaluation-release-gate",
                    },
                )
            ).json(),
            "create evaluation preflight",
        )
        claim = _data(
            (
                await _request(
                    client,
                    "POST",
                    "/api/evaluation/runs/claim",
                    "claim evaluation run",
                    headers=headers,
                    json={"worker_id": f"evaluation-release-gate-{run_id}", "lease_seconds": 60},
                )
            ).json(),
            "claim evaluation run",
        )
        completed = _data(
            (
                await _request(
                    client,
                    "POST",
                    f"/api/evaluation/runs/{run['id']}/complete",
                    "complete evaluation run",
                    headers=headers,
                    json={
                        "worker_id": f"evaluation-release-gate-{run_id}",
                        "case_results": [
                            {
                                "case_key": f"{run_id}-pass",
                                "status": "passed",
                                "assessments": [
                                    {"category": "answer", "status": "passed", "score": "1.0", "hard_fail": False}
                                ],
                                "result": {"answer": "revenue is governed"},
                            },
                            {
                                "case_key": f"{run_id}-block",
                                "status": "failed",
                                "assessments": [
                                    {"category": "security", "status": "failed", "score": "0", "hard_fail": True}
                                ],
                                "result": {"answer": "blocked"},
                                "error": {"token": "super-secret-token", "sql": "select * from restricted_table"},
                            },
                        ],
                    },
                )
            ).json(),
            "complete evaluation run",
        )
        failures = _data(
            (
                await _request(
                    client,
                    "GET",
                    f"/api/evaluation/runs/{run['id']}/failures",
                    "describe evaluation failures",
                    headers=headers,
                )
            ).json(),
            "describe evaluation failures",
        )
    return {
        "ok": True,
        "suite_id": suite["id"],
        "suite_version_id": version_id,
        "created_cases": imported["created_count"],
        "published_status": published["status"],
        "run_id": run["id"],
        "claimed_run_id": claim["id"],
        "run_status": completed["status"],
        "gate_decision": completed["summary"]["gate_decision"],
        "failure_count": failures["total"],
    }


def main() -> None:
    result = asyncio.run(run_gate())
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
