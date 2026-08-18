from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import sys
import time
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.auth.mcp_keys import hash_mcp_api_key  # noqa: E402
from server.db.session import AsyncSessionFactory  # noqa: E402
from server.models.mcp_api_key import MCPAPIKey  # noqa: E402
from server.models.tenant import Tenant  # noqa: E402
from server.models.tenant_member import TenantMember, TenantRole  # noqa: E402
from server.models.semantic_models import SemanticModel  # noqa: E402
from server.services.community_setup import get_local_bootstrap  # noqa: E402
from server.utils.config_loader import is_self_hosted  # noqa: E402


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


async def _api(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    headers: dict[str, str],
    **kwargs: Any,
) -> Any:
    response = await client.request(method, path, headers=headers, **kwargs)
    text = response.text
    try:
        body = response.json()
    except ValueError:
        body = {"raw": text}
    if response.status_code >= 400 or body.get("success") is False:
        raise RuntimeError(f"{method} {path} failed: {response.status_code} {body}")
    return body.get("data", body)


async def _external(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    api_key: str,
    **kwargs: Any,
) -> Any:
    return await _api(
        client,
        method,
        path,
        headers={"Authorization": f"Bearer {api_key}"},
        **kwargs,
    )


async def _login_team_owner(
    client: httpx.AsyncClient,
    *,
    email: str,
    password: str,
    preferred_tenant_name: str | None = None,
) -> dict[str, Any]:
    response = await client.post(
        "/api/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text}
    if response.status_code >= 400:
        raise RuntimeError(f"Team login failed: {response.status_code} {body}")
    token = body.get("access_token") or body.get("data", {}).get("access_token")
    if not token:
        raise RuntimeError(f"Team login response did not include an access token: {body}")
    tenants = await _api(
        client,
        "GET",
        "/api/scopes/all",
        headers={"Authorization": f"Bearer {token}"},
    )
    tenant_items = tenants.get("tenants") or []
    owner_tenant = next(
        (
            item
            for item in tenant_items
            if item.get("role") == TenantRole.OWNER.value and item.get("tenant_name") == preferred_tenant_name
        ),
        None,
    )
    owner_tenant = owner_tenant or next((item for item in tenant_items if item.get("role") == TenantRole.OWNER.value), None)
    selected = owner_tenant or (tenant_items[0] if tenant_items else None)
    if not selected:
        raise RuntimeError("Team login succeeded but no tenant scopes were returned")
    user = await _api(
        client,
        "GET",
        "/api/users/me",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-ID": selected["tenant_id"]},
    )
    return {
        "accessToken": token,
        "tenantId": selected["tenant_id"],
        "tenantName": selected["tenant_name"],
        "role": selected["role"],
        "scopes": selected.get("scopes") or [],
        "features": selected.get("features") or {},
        "userId": str(user["id"]),
        "email": user["email"],
    }


async def _ensure_external_key(tenant_id: str, user_id: str, run_id: str) -> str:
    api_key = f"byaan_{secrets.token_urlsafe(32)}_{run_id}"
    key_hash = hash_mcp_api_key(api_key)
    tenant_uuid = UUID(tenant_id)
    user_uuid = UUID(user_id)
    async with AsyncSessionFactory() as session:
        existing = await session.scalar(
            select(MCPAPIKey).where(MCPAPIKey.key_hash == key_hash)
        )
        if existing is None:
            session.add(
                MCPAPIKey(
                    tenant_id=tenant_uuid,
                    user_id=user_uuid,
                    name=f"knowledge-center-live-{run_id}",
                    key_hash=key_hash,
                    key_prefix=api_key[:20],
                )
            )
            await session.commit()
    return api_key


async def _team_database_identity(master_email: str) -> dict[str, Any]:
    async with AsyncSessionFactory() as session:
        result = await session.execute(select(Tenant, TenantMember).join(TenantMember, TenantMember.tenant_id == Tenant.id))
        memberships = result.all()
        for tenant, member in memberships:
            if tenant.owner_id == member.user_id and member.role == TenantRole.OWNER.value:
                return {
                    "tenantId": str(tenant.id),
                    "tenantName": tenant.name,
                    "userId": str(member.user_id),
                    "role": member.role,
                }
        raise RuntimeError(f"Could not resolve self-hosted owner tenant for {master_email}")


async def main() -> None:
    base_url = os.getenv("BYAAN_BASE_URL", "http://127.0.0.1:18000").rstrip("/")
    out_dir = Path(
        os.getenv(
            "REPORT_DIR",
            ROOT / "artifacts/data-modeling/knowledge-center/session-reports/live",
        )
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = os.getenv("RUN_ID") or str(int(time.time()))
    secret_env_path = Path(
        os.getenv("SECRET_ENV_PATH", f"/tmp/byaan-live-env-{run_id}.sh")
    )

    source_name = f"KC Live Revenue {run_id}"
    model_slug = f"kc-live-revenue-{run_id}-{uuid4().hex[:8]}"
    model_name = f"KC Live Revenue {run_id}"
    csv_bytes = (
        b"order_id,region,revenue,paid_at\n"
        b"1,East,120,2026-08-01\n"
        b"2,West,80,2026-08-02\n"
        b"3,East,30,2026-08-03\n"
    )

    async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
        config = await _api(client, "GET", "/api/app/config", headers={})
        app_features = config.get("features") or {}
        team_mode = is_self_hosted()
        if team_mode:
            master_email = os.getenv("MASTER_USER_EMAIL", "")
            master_password = os.getenv("MASTER_USER_PASSWORD", "")
            if not master_email or not master_password:
                raise RuntimeError("MASTER_USER_EMAIL and MASTER_USER_PASSWORD are required for Team live seed")
            if not app_features.get("enterprise_licensed") or not app_features.get("team_sharing_enabled"):
                raise RuntimeError(f"Team app config flags are disabled: {config}")
            if config.get("local_bootstrap") or config.get("community_bootstrap"):
                raise RuntimeError(f"Team app config exposed local/community bootstrap: {config}")
            login = await _login_team_owner(
                client,
                email=master_email,
                password=master_password,
                preferred_tenant_name=config.get("org_name"),
            )
            db_identity = await _team_database_identity(master_email)
            tenant_id = login["tenantId"]
            user_id = login["userId"]
            auth_headers = {
                "Authorization": f"Bearer {login['accessToken']}",
                "X-Tenant-ID": tenant_id,
            }
            auth_artifact = {
                "mode": "self-hosted",
                "tenantId": tenant_id,
                "tenantName": login["tenantName"],
                "userId": user_id,
                "email": "<redacted>",
                "role": login["role"],
                "scopesCount": len(login["scopes"]),
                "dbIdentity": db_identity,
            }
        else:
            async with AsyncSessionFactory() as session:
                bootstrap = await get_local_bootstrap(session)
            tenant_id = str(bootstrap["tenant_id"])
            user_id = str(bootstrap["user_id"])
            auth_headers = {
                "X-Tenant-ID": tenant_id,
                "X-Local-User-ID": user_id,
            }
            auth_artifact = {
                "mode": "community",
                "tenantId": tenant_id,
                "userId": user_id,
                "email": "<redacted>",
                "role": "owner",
            }
        api_key = await _ensure_external_key(tenant_id, user_id, run_id)

        uploaded = await _api(
            client,
            "POST",
            "/api/source-resources/files",
            headers=auth_headers,
            files={
                "file": (
                    "revenue.csv",
                    csv_bytes,
                    "text/csv",
                )
            },
            data={"name": source_name},
        )
        projected_dataset_id = uploaded["projected_dataset_id"]
        try:
            await _api(
                client,
                "POST",
                f"/api/source-resources/{uploaded['id']}/projection/review",
                headers=auth_headers,
                json={
                    "status": "verified",
                    "reviewed_by": "knowledge-center-live-gate",
                    "note": "Verified by Knowledge Center live release gate.",
                },
            )
        except RuntimeError:
            # Older local states may not require projection review for published
            # projected datasets. Keep the live query path authoritative.
            pass

        analyzed = await _api(
            client,
            "POST",
            f"/api/datasources/{projected_dataset_id}/understanding/analyze",
            headers=auth_headers,
            json={},
        )
        selected = [
            item
            for item in analyzed.get("candidates", [])
            if item.get("candidate_type") in {"schema_map", "data_truth", "relationship"}
        ]
        if not any(item.get("candidate_type") == "schema_map" for item in selected):
            raise RuntimeError("Projected dataset did not produce schema_map evidence")
        if not any(item.get("candidate_type") == "data_truth" for item in selected):
            raise RuntimeError("Projected dataset did not produce data_truth evidence")

        accepted_ids: list[str] = []
        for candidate in selected:
            await _api(
                client,
                "POST",
                f"/api/datasources/{projected_dataset_id}/understanding/candidates/{candidate['id']}/review",
                headers=auth_headers,
                json={
                    "action": "accept",
                    "note": "Accepted by Knowledge Center live release gate.",
                },
            )
            accepted_ids.append(candidate["id"])

        drafted = await _api(
            client,
            "POST",
            f"/api/datasources/{projected_dataset_id}/understanding/semantic-model-draft",
            headers=auth_headers,
            json={
                "model_id": model_slug,
                "name": model_name,
                "domain": "Sales / Orders",
                "owner": "Knowledge Center Live Gate",
                "candidate_ids": accepted_ids,
            },
        )
        model = drafted["model"]
        validated = await _api(
            client,
            "POST",
            f"/api/data-models/{model['id']}/validate",
            headers=auth_headers,
        )
        blockers = validated.get("readinessDetail", {}).get("blockers") or []
        if blockers:
            raise RuntimeError(f"Semantic model readiness blockers: {blockers}")
        published = await _api(
            client,
            "POST",
            f"/api/data-models/{model['id']}/publish",
            headers=auth_headers,
        )

        async with AsyncSessionFactory() as session:
            db_model = await session.scalar(
                select(SemanticModel).where(
                    SemanticModel.tenant_id == UUID(tenant_id),
                    SemanticModel.slug == model_slug,
                )
            )
            if db_model is None:
                raise RuntimeError("Published semantic model not found in database")
            external_asset_id = str(db_model.id)

        asset = await _external(
            client,
            "GET",
            f"/api/external/assets/semantic_model/{external_asset_id}",
            api_key=api_key,
        )
        listed = await _external(
            client,
            "GET",
            "/api/external/assets?types=dashboard,semantic_model&limit=100",
            api_key=api_key,
        )
        query = await _external(
            client,
            "POST",
            f"/api/external/assets/semantic_model/{external_asset_id}/query",
            api_key=api_key,
            json={
                "metric": "revenue_revenue",
                "dimension": "revenue_region",
                "limit": 10,
            },
        )

    if query.get("status") not in {"completed", "success"}:
        raise RuntimeError(f"Live query did not complete: {query}")
    if not query.get("result"):
        raise RuntimeError(f"Live query returned no rows: {query}")
    evidence_kinds = {item.get("kind") for item in query.get("evidence") or []}
    required = {"sql", "metric_definition", "permission_policy"}
    if not required.issubset(evidence_kinds):
        raise RuntimeError(f"Live query evidence missing {required - evidence_kinds}: {query}")

    artifact = {
        "ok": True,
        "runId": run_id,
        "baseUrl": base_url,
        "deployment": {
            "mode": "self-hosted" if team_mode else "community",
            "appConfig": _jsonable(config),
            "featureFlags": _jsonable(app_features),
            "auth": _jsonable(auth_artifact),
            "communityBootstrapPresent": bool(config.get("local_bootstrap") or config.get("community_bootstrap")),
            "knowledgeProvider": {
                "provider": os.getenv("KNOWLEDGE_PROVIDER") or "native",
                "allowNativeLocalDiagnostics": os.getenv("KNOWLEDGE_PROVIDER_ALLOW_NATIVE", "").lower()
                in {"1", "true", "yes", "on"},
            },
        },
        "tenantId": tenant_id,
        "userId": user_id,
        "source": {
            "name": source_name,
            "resourceId": uploaded["id"],
            "projectedDatasetId": projected_dataset_id,
            "csvSha256": hashlib.sha256(csv_bytes).hexdigest(),
        },
        "model": {
            "slug": model_slug,
            "name": model_name,
            "externalAssetId": external_asset_id,
            "publishedVersion": published.get("publishedVersion")
            or published.get("published_version"),
        },
        "externalApi": {
            "apiKeyEnv": "BYAAN_MCP_API_KEY",
            "apiKey": "<redacted>",
            "asset": _jsonable(asset),
            "listCount": len(listed.get("items") or listed.get("assets") or []),
            "query": _jsonable(query),
        },
        "secretEnvPath": str(secret_env_path),
    }
    (out_dir / "byaan-live-seed-result.json").write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (out_dir / "byaan-live-env.sh").write_text(
        "\n".join(
            [
                f"export BYAAN_BASE_URL={json.dumps(base_url)}",
                f"export DATASTUDIO_BASE_URL={json.dumps(base_url)}",
                "export BYAAN_MCP_API_KEY=<redacted>",
                "export DATASTUDIO_API_KEY=<redacted>",
                f"export DATASTUDIO_ASSET_ID={json.dumps(external_asset_id)}",
                f"export DATASTUDIO_ASSET_TYPE={json.dumps('semantic_model')}",
                f"export DATASTUDIO_QUERY_URL={json.dumps(asset['query_url'])}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    secret_env_path.parent.mkdir(parents=True, exist_ok=True)
    secret_env_path.write_text(
        "\n".join(
            [
                f"export BYAAN_BASE_URL={json.dumps(base_url)}",
                f"export DATASTUDIO_BASE_URL={json.dumps(base_url)}",
                f"export BYAAN_MCP_API_KEY={json.dumps(api_key)}",
                f"export DATASTUDIO_API_KEY={json.dumps(api_key)}",
                f"export DATASTUDIO_ASSET_ID={json.dumps(external_asset_id)}",
                f"export DATASTUDIO_ASSET_TYPE={json.dumps('semantic_model')}",
                f"export DATASTUDIO_QUERY_URL={json.dumps(asset['query_url'])}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    secret_env_path.chmod(0o600)
    print(json.dumps(artifact, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
