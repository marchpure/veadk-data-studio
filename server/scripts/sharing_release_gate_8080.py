from __future__ import annotations

import asyncio
import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any

import httpx

FORBIDDEN = (
    "release-gate-folder-password",
    "release-gate-html-password",
    "release-gate-json-password",
    "release-gate-json-rotated-password",
    "raw-share-token",
    "raw-verifier",
    "verifier_hash",
    "token_digest",
    "restricted_table",
)


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


async def _request(client: httpx.AsyncClient, method: str, path: str, operation: str, **kwargs) -> httpx.Response:
    response = await client.request(method, path, **kwargs)
    if response.status_code >= 400:
        try:
            payload = response.json()
        except json.JSONDecodeError:
            payload = response.text
        _assert_redacted(payload, operation)
        raise AssertionError(f"{operation} failed {response.status_code}: {payload}")
    if response.content:
        _assert_redacted(response.json(), operation)
    return response


async def _login(client: httpx.AsyncClient, email: str, password: str) -> Auth:
    response = await client.post(
        "/api/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    payload = response.json()
    token = _data(payload, "login")["access_token"]
    scoped_client = httpx.AsyncClient(base_url=str(client.base_url), headers={"Authorization": f"Bearer {token}"})
    try:
        scopes_response = await scoped_client.get("/api/scopes/all")
        scopes = _data(scopes_response.json(), "scopes")
    finally:
        await scoped_client.aclose()
    tenant = scopes["tenants"][0]
    claims = _jwt_claims(token)
    return Auth(token=token, tenant_id=tenant["tenant_id"], user_id=claims["sub"])


def _jwt_claims(token: str) -> dict[str, Any]:
    import base64

    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))


async def _create_fixture(client: httpx.AsyncClient, auth: Auth, run_id: str) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {auth.token}", "X-Tenant-ID": auth.tenant_id}
    folder = _data(
        (
            await _request(
                client,
                "POST",
                "/api/folders",
                "create folder",
                headers=headers,
                json={"name": f"Governance Release Gate {run_id}", "description": "temporary release-gate fixture"},
            )
        ).json(),
        "create folder",
    )
    notebook = _data(
        (
            await _request(
                client,
                "POST",
                "/api/notebooks",
                "create notebook",
                headers=headers,
                json={
                    "notebook_name": f"Governance Release Gate {run_id}",
                    "description": "temporary release-gate fixture",
                },
            )
        ).json(),
        "create notebook",
    )
    dashboard_id = _seed_dashboard_in_container(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        notebook_id=notebook["id"],
        run_id=run_id,
    )
    return {"folder_id": folder["id"], "notebook_id": notebook["id"], "dashboard_id": dashboard_id}


def _seed_dashboard_in_container(*, tenant_id: str, user_id: str, notebook_id: str, run_id: str) -> str:
    container = os.environ.get("CONTAINER", "byaan-governance-p0-976c5cf-8080")
    code = f"""
import asyncio
import uuid

import asyncpg

creds = open('/data/.db_credentials').read().strip()
db_user, db_password = creds.split(':', 1)

async def main():
    dashboard_id = uuid.uuid4()
    conn = await asyncpg.connect(user=db_user, password=db_password, database='byaan', host='localhost')
    try:
        async with conn.transaction():
            await conn.execute(
                '''
            INSERT INTO dashboards (
                id, tenant_id, notebook_id, version_num, html_content, content_hash,
                status, created_by, actor_type, change_summary, is_published_immutable, created_at
            ) VALUES (
                $1, $2, $3, 1, $4, $5,
                'published', $6, 'human', 'release gate fixture', true, now()
            )
                ''',
                str(dashboard_id),
                {tenant_id!r},
                {notebook_id!r},
                '<html><body>Governance release gate {run_id}</body></html>',
                'sha256:release-gate-{run_id}',
                {user_id!r},
            )
    finally:
        await conn.close()
    print(dashboard_id)

asyncio.run(main())
"""
    result = subprocess.run(
        ["docker", "exec", container, "bash", "-lc", f"/app/.venv/bin/python - <<'PY'\n{code}\nPY"],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise AssertionError(f"dashboard fixture seed failed: {result.stderr or result.stdout}")
    return result.stdout.strip().splitlines()[-1]


async def _verify_folder_sharing(client: httpx.AsyncClient, auth: Auth, fixture: dict[str, str]) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {auth.token}", "X-Tenant-ID": auth.tenant_id}
    folder_id = fixture["folder_id"]
    notebook_id = fixture["notebook_id"]
    dashboard_id = fixture["dashboard_id"]

    folder_notebook = _data(
        (
            await _request(
                client,
                "POST",
                f"/api/folders/{folder_id}/notebooks",
                "folder notebook share",
                headers=headers,
                json={"notebook_id": notebook_id, "is_snapshot": False},
            )
        ).json(),
        "folder notebook share",
    )
    folder_dashboard = _data(
        (
            await _request(
                client,
                "POST",
                f"/api/folders/{folder_id}/dashboards",
                "folder dashboard share",
                headers=headers,
                json={"dashboard_id": dashboard_id, "is_snapshot": False},
            )
        ).json(),
        "folder dashboard share",
    )

    notebook_grants = _data(
        (
            await _request(
                client,
                "GET",
                "/api/sharing/grants?legacy_surface=folder_notebook",
                "folder notebook canonical grants",
                headers=headers,
            )
        ).json(),
        "folder notebook canonical grants",
    )
    dashboard_grants = _data(
        (
            await _request(
                client,
                "GET",
                "/api/sharing/grants?legacy_surface=folder_dashboard",
                "folder dashboard canonical grants",
                headers=headers,
            )
        ).json(),
        "folder dashboard canonical grants",
    )

    notebook_evidence = await _evidence_for_legacy_id(client, headers, notebook_grants["items"], folder_notebook["id"])
    dashboard_evidence = await _evidence_for_legacy_id(client, headers, dashboard_grants["items"], folder_dashboard["id"])

    await _request(
        client,
        "DELETE",
        f"/api/folders/{folder_id}/notebooks/{notebook_id}",
        "folder notebook unshare",
        headers=headers,
    )
    await _request(
        client,
        "DELETE",
        f"/api/folders/{folder_id}/dashboards/{dashboard_id}",
        "folder dashboard unshare",
        headers=headers,
    )

    revoked_notebook = _data(
        (
            await _request(
                client,
                "GET",
                f"/api/sharing/grants/{notebook_evidence['grant']['id']}",
                "revoked folder notebook evidence",
                headers=headers,
            )
        ).json(),
        "revoked folder notebook evidence",
    )
    return {
        "folder_notebook_share_id": folder_notebook["id"],
        "folder_dashboard_share_id": folder_dashboard["id"],
        "folder_notebook_surface": notebook_evidence["compatibility_links"][0]["legacy_surface"],
        "folder_dashboard_surface": dashboard_evidence["compatibility_links"][0]["legacy_surface"],
        "folder_notebook_revoked_status": revoked_notebook["grant"]["status"],
    }


async def _evidence_for_legacy_id(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    grant_items: list[dict[str, Any]],
    legacy_id: str,
) -> dict[str, Any]:
    for item in grant_items:
        evidence = _data(
            (
                await _request(
                    client,
                    "GET",
                    f"/api/sharing/grants/{item['id']}",
                    f"sharing evidence {item['id']}",
                    headers=headers,
                )
            ).json(),
            f"sharing evidence {item['id']}",
        )
        if any(link["legacy_id"] == legacy_id for link in evidence["compatibility_links"]):
            return evidence
    raise AssertionError(f"canonical grant evidence not found for legacy id {legacy_id}")


async def _verify_worker_backed_notebook_sharing_is_gated(
    client: httpx.AsyncClient,
    auth: Auth,
    notebook_id: str,
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {auth.token}", "X-Tenant-ID": auth.tenant_id}
    response = await client.post(
        f"/api/notebooks/{notebook_id}/share?password=release-gate-html-password",
        headers=headers,
    )
    try:
        payload = response.json()
    except json.JSONDecodeError:
        payload = {"raw": response.text}
    _assert_redacted(payload, "worker-backed HTML share gate")
    if response.status_code not in {401, 403, 503}:
        raise AssertionError(f"unexpected worker-backed share response: {response.status_code} {payload}")
    return {"status_code": response.status_code, "message": payload.get("message") or payload.get("detail")}


async def _cleanup_fixture(client: httpx.AsyncClient, auth: Auth, fixture: dict[str, str]) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {auth.token}", "X-Tenant-ID": auth.tenant_id}
    cleanup: dict[str, Any] = {}
    for key, path in (
        ("folder", f"/api/folders/{fixture['folder_id']}"),
        ("notebook", f"/api/notebooks/{fixture['notebook_id']}"),
    ):
        response = await client.delete(path, headers=headers)
        cleanup[key] = response.status_code
        if response.status_code not in {204, 404}:
            raise AssertionError(f"cleanup {key} failed {response.status_code}: {response.text}")
    return cleanup


async def _verify_registered_folder_cleanup(client: httpx.AsyncClient, auth: Auth) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {auth.token}", "X-Tenant-ID": auth.tenant_id}
    folder_id = os.environ.get("REGISTERED_FOLDER_ID", "b268fd5a-8bb4-4ee6-9447-03edc9c142f0")
    response = await client.get(f"/api/folders/{folder_id}", headers=headers)
    if response.status_code == 404:
        return {"folder_id": folder_id, "pre_existing": False, "cleanup": "already_absent"}
    if response.status_code >= 400:
        raise AssertionError(f"registered folder lookup failed {response.status_code}: {response.text}")
    delete_response = await client.delete(f"/api/folders/{folder_id}", headers=headers)
    if delete_response.status_code not in {204, 404}:
        raise AssertionError(f"registered folder cleanup failed {delete_response.status_code}: {delete_response.text}")
    verify_response = await client.get(f"/api/folders/{folder_id}", headers=headers)
    return {
        "folder_id": folder_id,
        "pre_existing": True,
        "delete_status": delete_response.status_code,
        "post_delete_status": verify_response.status_code,
    }


async def main() -> None:
    base_url = os.environ.get("BASE_URL", "http://127.0.0.1:8080")
    email = os.environ.get("ADMIN_EMAIL", "admin@example.com")
    password = os.environ.get("ADMIN_PASSWORD", "password")
    run_id = os.environ.get("RUN_ID", "976c5cf")

    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        auth = await _login(client, email, password)
        fixture = await _create_fixture(client, auth, run_id)
        try:
            folder_result = await _verify_folder_sharing(client, auth, fixture)
            worker_gate = await _verify_worker_backed_notebook_sharing_is_gated(client, auth, fixture["notebook_id"])
        finally:
            fixture_cleanup = await _cleanup_fixture(client, auth, fixture)
        registered_cleanup = await _verify_registered_folder_cleanup(client, auth)

    result = {
        "ok": True,
        "base_url": base_url,
        "tenant_id": auth.tenant_id,
        "fixture": fixture,
        "folder_sharing": folder_result,
        "worker_backed_notebook_sharing": worker_gate,
        "fixture_cleanup": fixture_cleanup,
        "registered_folder_cleanup": registered_cleanup,
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
