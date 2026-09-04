"""Server-side OpenViking profile storage and strict upstream BFF proxy.

This is a target-side adaptation of the frozen OpenViking donor service. The
browser receives profile metadata only; the base URL and API key stay here.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import os
import re
import secrets
import socket
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
ALLOWED_UPLOAD_EXTENSIONS = {".csv", ".json", ".md", ".pdf", ".txt", ".xlsx"}
SAFE_RESOURCE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,127}$")


class OpenVikingError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class OpenVikingConfig:
    encryption_key: bytes
    timeout_seconds: float = 30.0
    allow_loopback: bool = False

    @classmethod
    def from_env(cls) -> "OpenVikingConfig":
        raw = os.getenv("OPENVIKING_PROFILE_ENCRYPTION_KEY", "")
        if not raw:
            raise OpenVikingError("OPENVIKING_UNAVAILABLE", "OpenViking profile encryption is not configured", 503)
        try:
            key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        except (ValueError, base64.binascii.Error) as exc:
            raise OpenVikingError("OPENVIKING_UNAVAILABLE", "OpenViking encryption key is invalid", 503) from exc
        if len(key) != 32:
            raise OpenVikingError("OPENVIKING_UNAVAILABLE", "OpenViking encryption key must be 32 bytes", 503)
        return cls(key, float(os.getenv("OPENVIKING_TIMEOUT_SECONDS", "30")), os.getenv("OPENVIKING_ALLOW_LOOPBACK") == "1")


@dataclass(frozen=True)
class OpenVikingProfile:
    profile_id: str
    tenant_id: str
    workspace_id: str
    display_name: str
    encrypted_base_url: bytes
    encrypted_api_key: bytes
    workspace_uri: str
    status: str
    created_at: float
    updated_at: float


class OpenVikingProfileRepository:
    def __init__(self, database: str | Path) -> None:
        Path(database).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(database), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS openviking_profiles (
              profile_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
              workspace_id TEXT NOT NULL, display_name TEXT NOT NULL,
              encrypted_base_url BLOB NOT NULL, encrypted_api_key BLOB NOT NULL,
              workspace_uri TEXT NOT NULL, status TEXT NOT NULL,
              created_at REAL NOT NULL, updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS openviking_profile_scope
              ON openviking_profiles(tenant_id, workspace_id);
            CREATE TABLE IF NOT EXISTS openviking_task_history (
              tenant_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
              profile_id TEXT NOT NULL, task_id TEXT NOT NULL,
              task_json TEXT NOT NULL, observed_at REAL NOT NULL,
              PRIMARY KEY(tenant_id, workspace_id, profile_id, task_id)
            );
            CREATE TABLE IF NOT EXISTS openviking_idempotency (
              scope_key TEXT PRIMARY KEY, response_json TEXT NOT NULL,
              observed_at REAL NOT NULL
            );
            """
        )
        self._db.commit()

    def list(self, tenant_id: str, workspace_id: str) -> list[OpenVikingProfile]:
        rows = self._db.execute(
            "SELECT * FROM openviking_profiles WHERE tenant_id=? AND workspace_id=? ORDER BY created_at",
            (tenant_id, workspace_id),
        ).fetchall()
        return [OpenVikingProfile(**dict(row)) for row in rows]

    def get(self, profile_id: str, tenant_id: str, workspace_id: str) -> OpenVikingProfile | None:
        row = self._db.execute(
            "SELECT * FROM openviking_profiles WHERE profile_id=? AND tenant_id=? AND workspace_id=?",
            (profile_id, tenant_id, workspace_id),
        ).fetchone()
        return OpenVikingProfile(**dict(row)) if row else None

    def save(self, profile: OpenVikingProfile) -> OpenVikingProfile:
        self._db.execute(
            """INSERT INTO openviking_profiles VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(profile_id) DO UPDATE SET display_name=excluded.display_name,
            encrypted_base_url=excluded.encrypted_base_url, encrypted_api_key=excluded.encrypted_api_key,
            workspace_uri=excluded.workspace_uri, status=excluded.status, updated_at=excluded.updated_at""",
            tuple(profile.__dict__.values()),
        )
        self._db.commit()
        return profile

    def delete(self, profile_id: str, tenant_id: str, workspace_id: str) -> None:
        self._db.execute(
            "DELETE FROM openviking_profiles WHERE profile_id=? AND tenant_id=? AND workspace_id=?",
            (profile_id, tenant_id, workspace_id),
        )
        self._db.commit()

    def save_tasks(self, profile: OpenVikingProfile, tasks: list[dict[str, Any]]) -> None:
        now = time.time()
        self._db.executemany(
            """INSERT INTO openviking_task_history VALUES(?,?,?,?,?,?)
            ON CONFLICT(tenant_id,workspace_id,profile_id,task_id)
            DO UPDATE SET task_json=excluded.task_json, observed_at=excluded.observed_at""",
            [
                (profile.tenant_id, profile.workspace_id, profile.profile_id, str(item["task_id"]), json.dumps(item), now)
                for item in tasks if item.get("task_id")
            ],
        )
        self._db.commit()

    def tasks(self, profile: OpenVikingProfile) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT task_json FROM openviking_task_history WHERE profile_id=? ORDER BY observed_at DESC",
            (profile.profile_id,),
        ).fetchall()
        return [json.loads(row["task_json"]) for row in rows]

    def get_idempotent(self, key: str) -> Any | None:
        row = self._db.execute(
            "SELECT response_json FROM openviking_idempotency WHERE scope_key=?",
            (key,),
        ).fetchone()
        return json.loads(row["response_json"]) if row else None

    def save_idempotent(self, key: str, value: Any) -> None:
        self._db.execute(
            """INSERT INTO openviking_idempotency VALUES(?,?,?)
            ON CONFLICT(scope_key) DO UPDATE SET response_json=excluded.response_json,
            observed_at=excluded.observed_at""",
            (key, json.dumps(value, ensure_ascii=False), time.time()),
        )
        self._db.commit()


OPERATIONS: dict[str, tuple[str, str]] = {
    "fs_list": ("GET", "/api/v1/fs/ls"), "fs_tree": ("GET", "/api/v1/fs/tree"),
    "fs_stat": ("GET", "/api/v1/fs/stat"), "fs_delete": ("DELETE", "/api/v1/fs"),
    "content_read": ("GET", "/api/v1/content/read"), "content_abstract": ("GET", "/api/v1/content/abstract"),
    "content_overview": ("GET", "/api/v1/content/overview"), "content_write": ("POST", "/api/v1/content/write"),
    "content_reindex": ("POST", "/api/v1/content/reindex"),
    "resource_import": ("POST", "/api/v1/resources"), "find": ("POST", "/api/v1/search/find"),
    "search": ("POST", "/api/v1/search/search"), "grep": ("POST", "/api/v1/search/grep"),
    "glob": ("POST", "/api/v1/search/glob"), "tasks": ("GET", "/api/v1/tasks"),
    "watches": ("GET", "/api/v1/watches"),
}

ITEM_OPERATIONS: dict[str, tuple[str, str]] = {
    "task_get": ("GET", "/api/v1/tasks"),
    "watch_get": ("GET", "/api/v1/watches"),
    "watch_update": ("PATCH", "/api/v1/watches"),
    "watch_delete": ("DELETE", "/api/v1/watches"),
    "watch_trigger": ("POST", "/api/v1/watches"),
}

OPERATION_FIELDS: dict[str, set[str]] = {
    "fs_list": {"resource_ref", "output", "node_limit", "limit", "recursive"},
    "fs_tree": {"resource_ref", "output", "node_limit", "limit", "level_limit"},
    "fs_stat": {"resource_ref"},
    "fs_delete": {"resource_ref", "recursive", "wait", "timeout"},
    "content_read": {"resource_ref", "offset", "limit", "raw"},
    "content_abstract": {"resource_ref"},
    "content_overview": {"resource_ref"},
    "content_write": {"resource_ref", "content", "mode", "wait", "timeout"},
    "content_reindex": {"resource_ref", "mode", "wait", "recursive"},
    "resource_import": {"path", "parent_ref", "destination_ref", "source_name", "wait", "watch_interval"},
    "find": {"query", "target_ref", "limit", "score_threshold", "read_content", "tags"},
    "search": {"query", "target_ref", "limit", "score_threshold", "read_content", "tags", "mode"},
    "grep": {"resource_ref", "pattern", "case_insensitive", "node_limit", "level_limit"},
    "glob": {"resource_ref", "pattern", "node_limit"},
    "tasks": {"task_type", "status", "limit"},
    "watches": {"active_only", "to_ref"},
    "task_get": set(),
    "watch_get": {"to_ref"},
    "watch_update": {"watch_interval", "is_active", "reason", "instruction", "to_ref"},
    "watch_delete": {"to_ref"},
    "watch_trigger": {"to_ref"},
}

FORBIDDEN_FIELDS = {
    "account", "account_id", "api_key", "authorization", "credential", "credentials",
    "password", "principal_id", "secret", "token", "user", "user_id",
}

def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize(item)
            for key, item in value.items()
            if str(key).casefold() not in FORBIDDEN_FIELDS
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _resource_ref(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized.startswith("viking://") or "\x00" in normalized:
        return None
    return normalized


def _item_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,256}", value):
        raise OpenVikingError("INVALID_ITEM_ID", "Item id is invalid", 422)
    return value


class OpenVikingService:
    def __init__(self, repository: OpenVikingProfileRepository, config: OpenVikingConfig) -> None:
        self.repository = repository
        self.config = config
        self._cipher = AESGCM(config.encryption_key)

    def _crypt(self, value: str, scope: str) -> bytes:
        nonce = secrets.token_bytes(12)
        return nonce + self._cipher.encrypt(nonce, value.encode(), scope.encode())

    def _decrypt(self, value: bytes, scope: str) -> str:
        try:
            return self._cipher.decrypt(value[:12], value[12:], scope.encode()).decode()
        except Exception as exc:
            raise OpenVikingError("OPENVIKING_PROFILE_CORRUPT", "OpenViking profile cannot be decrypted", 500) from exc

    def _credentials(self, profile: OpenVikingProfile) -> tuple[str, str]:
        return self._decrypt(profile.encrypted_base_url, f"url:{profile.profile_id}"), self._decrypt(profile.encrypted_api_key, f"key:{profile.profile_id}")

    @staticmethod
    def public(profile: OpenVikingProfile) -> dict[str, Any]:
        return {
            "profile_id": profile.profile_id, "display_name": profile.display_name,
            "workspace_uri": profile.workspace_uri, "status": profile.status,
            "root_resource_ref": profile.workspace_uri,
            "base_url_configured": True, "api_key_configured": True,
            "created_at": profile.created_at, "updated_at": profile.updated_at,
            "api_key_masked": "••••••••" if profile.encrypted_api_key else "",
        }

    def create(self, tenant_id: str, workspace_id: str, display_name: str, base_url: str, api_key: str, workspace_uri: str) -> OpenVikingProfile:
        self._validate_url(base_url)
        profile_id = "ov_" + secrets.token_hex(12)
        now = time.time()
        return self.repository.save(OpenVikingProfile(
            profile_id, tenant_id, workspace_id, display_name.strip(),
            self._crypt(base_url.rstrip("/"), f"url:{profile_id}"),
            self._crypt(api_key, f"key:{profile_id}"), workspace_uri or "viking://resources/",
            "pending", now, now,
        ))

    def update(self, profile: OpenVikingProfile, **values: Any) -> OpenVikingProfile:
        base_url = values.get("base_url")
        if base_url:
            self._validate_url(base_url)
        current_url, current_key = self._credentials(profile)
        profile = OpenVikingProfile(
            profile.profile_id, profile.tenant_id, profile.workspace_id,
            values.get("display_name", profile.display_name),
            self._crypt(base_url.rstrip("/"), f"url:{profile.profile_id}") if base_url else profile.encrypted_base_url,
            self._crypt(values["api_key"], f"key:{profile.profile_id}") if values.get("api_key") else profile.encrypted_api_key,
            values.get("workspace_uri", profile.workspace_uri), "pending", profile.created_at, time.time(),
        )
        return self.repository.save(profile)

    @staticmethod
    def _validate_url(value: str) -> None:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise OpenVikingError("INVALID_BASE_URL", "OpenViking URL must be http or https", 422)
        host = parsed.hostname or ""
        try:
            address = ipaddress.ip_address(socket.gethostbyname(host))
            if (address.is_loopback or address.is_private or address.is_link_local) and os.getenv("OPENVIKING_ALLOW_LOOPBACK") != "1":
                raise OpenVikingError("UPSTREAM_NOT_ALLOWED", "Private or loopback OpenViking endpoints are disabled", 422)
        except socket.gaierror as exc:
            raise OpenVikingError("UPSTREAM_NOT_ALLOWED", "OpenViking host cannot be resolved", 422) from exc

    async def validate(self, profile: OpenVikingProfile) -> OpenVikingProfile:
        base_url, api_key = self._credentials(profile)
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
                response = await client.get(f"{base_url}/api/v1/fs/stat", params={"resource_ref": profile.workspace_uri}, headers={"X-API-Key": api_key, "Accept": "application/json"})
            if response.status_code >= 400:
                raise OpenVikingError("UPSTREAM_REJECTED", "OpenViking validation failed", 502)
        except OpenVikingError:
            self.repository.save(OpenVikingProfile(**{**profile.__dict__, "status": "error", "updated_at": time.time()}))
            raise
        except httpx.HTTPError as exc:
            self.repository.save(OpenVikingProfile(**{**profile.__dict__, "status": "error", "updated_at": time.time()}))
            raise OpenVikingError("UPSTREAM_UNREACHABLE", "OpenViking endpoint is unreachable", 502) from exc
        updated = OpenVikingProfile(**{**profile.__dict__, "status": "ready", "updated_at": time.time()})
        return self.repository.save(updated)

    async def request(self, profile: OpenVikingProfile, operation: str, payload: dict[str, Any], item_id: str | None = None, idempotency_key: str | None = None) -> Any:
        operations = ITEM_OPERATIONS if item_id is not None else OPERATIONS
        if operation not in operations:
            raise OpenVikingError("UNSUPPORTED_OPERATION", "OpenViking operation is not allowed", 400)
        if item_id is not None:
            item_id = _item_id(item_id)
        clean = _sanitize(payload)
        allowed_fields = OPERATION_FIELDS.get(operation)
        if allowed_fields is not None:
            unknown = set(clean) - allowed_fields
            if unknown:
                raise OpenVikingError("INVALID_OPERATION_PAYLOAD", "Unsupported OpenViking operation field", 422)
        ref_keys = ("resource_ref", "target_ref", "parent_ref", "destination_ref")
        if item_id is None:
            ref_keys += ("to_ref",)
        for key in ref_keys:
            if key in clean and clean[key] is not None and _resource_ref(clean[key]) is None:
                raise OpenVikingError("INVALID_RESOURCE_REF", f"{key} must be a signed Viking resource reference", 422)
        method, path = operations[operation]
        if item_id:
            path = f"{path}/{item_id}"
            if operation == "watch_trigger":
                path += "/trigger"
        request_key = idempotency_key or hashlib.sha256(
            json.dumps([profile.profile_id, operation, item_id, clean], sort_keys=True).encode()
        ).hexdigest()
        cache_key = hashlib.sha256(f"{profile.tenant_id}:{profile.workspace_id}:{request_key}".encode()).hexdigest()
        if operation in {"content_write", "resource_import", "watch_update", "watch_delete", "watch_trigger"}:
            cached = self.repository.get_idempotent(cache_key)
            if cached is not None:
                return cached
        base_url, api_key = self._credentials(profile)
        kwargs: dict[str, Any] = {"headers": {"X-API-Key": api_key, "Accept": "application/json"}}
        if method in {"GET", "DELETE"}:
            kwargs["params"] = clean
        else:
            kwargs["json"] = clean
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
                response = await client.request(method, f"{base_url}{path}", **kwargs)
        except httpx.HTTPError as exc:
            raise OpenVikingError("UPSTREAM_UNREACHABLE", "OpenViking endpoint is unreachable", 502) from exc
        if response.status_code >= 400:
            raise OpenVikingError("UPSTREAM_REJECTED", "OpenViking request failed", 502)
        try:
            value = response.json()
        except ValueError:
            value = {"raw": response.text}
        value = _sanitize(value)
        if operation in {"tasks", "task_get"} and isinstance(value, list):
            self.repository.save_tasks(profile, value)
        if operation in {"content_write", "resource_import", "watch_update", "watch_delete", "watch_trigger"}:
            self.repository.save_idempotent(cache_key, value)
        return value

    async def item_request(
        self,
        profile: OpenVikingProfile,
        operation: str,
        item_id: str,
        payload: dict[str, Any],
    ) -> Any:
        clean = dict(payload)
        clean.setdefault("to_ref", item_id)
        return await self.request(profile, operation, clean, item_id=item_id)

    async def upload(self, profile: OpenVikingProfile, filename: str, content_type: str, content: bytes, parent_ref: str) -> Any:
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
            raise OpenVikingError("UNSUPPORTED_FILE_TYPE", "This file type cannot be imported", 422)
        if len(content) > MAX_UPLOAD_BYTES:
            raise OpenVikingError("PAYLOAD_TOO_LARGE", "Upload is too large", 413)
        base_url, api_key = self._credentials(profile)
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
                response = await client.post(
                    f"{base_url}/api/v1/resources",
                    files={"file": (filename, content, content_type)},
                    data={"parent_ref": parent_ref, "wait": "false"},
                    headers={"X-API-Key": api_key, "Accept": "application/json"},
                )
        except httpx.HTTPError as exc:
            raise OpenVikingError("UPSTREAM_UNREACHABLE", "OpenViking endpoint is unreachable", 502) from exc
        if response.status_code >= 400:
            raise OpenVikingError("UPSTREAM_REJECTED", "OpenViking import failed", 502)
        return response.json()

    async def import_connection_resource(
        self,
        profile: OpenVikingProfile,
        filename: str,
        parent_ref: str,
        document: dict[str, Any],
    ) -> Any:
        if not SAFE_RESOURCE_NAME.fullmatch(filename) or not filename.lower().endswith(".json"):
            raise OpenVikingError("INVALID_ARGUMENT", "Connection resource filename must use .json", 422)
        content = json.dumps(_sanitize(document), ensure_ascii=False, indent=2)
        return await self.request(
            profile,
            "content_write",
            {
                "resource_ref": parent_ref.rstrip("/") + "/" + filename,
                "content": content,
                "mode": "overwrite",
                "wait": False,
            },
        )
