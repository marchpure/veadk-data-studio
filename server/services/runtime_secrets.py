"""Server-side secret resolution for hosted deployments.

Production values come from a Volcengine KMS secret identified by name. Tests
may opt into environment values explicitly; the default hosted path does not.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any


class RuntimeSecretError(RuntimeError):
    pass


def _allow_env_secrets() -> bool:
    return os.getenv("DWV1_ALLOW_ENV_SECRETS", "").strip().lower() in {"1", "true", "yes"}


@lru_cache(maxsize=8)
def _load_secret_document(secret_name: str) -> dict[str, Any]:
    if not secret_name:
        raise RuntimeSecretError("secret source is not configured")
    try:
        from volcenginesdkcore import ApiClient, Configuration
        from volcenginesdkkms import GetSecretValueRequest, KMSApi

        configuration = Configuration()
        configuration.region = os.getenv("REGION", "cn-beijing")
        configuration.connect_timeout = 5
        configuration.read_timeout = 10
        from server.services.faas_runtime import get_faas_credentials

        credentials = get_faas_credentials()
        if credentials is not None:
            configuration.credential_provider = credentials.credential_provider()
        response = KMSApi(ApiClient(configuration)).get_secret_value(GetSecretValueRequest(secret_name=secret_name))
        value = getattr(response, "secret_value", None)
    except Exception as exc:
        raise RuntimeSecretError("runtime secret is unavailable") from exc
    if not isinstance(value, str) or not value:
        raise RuntimeSecretError("runtime secret is empty")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeSecretError("runtime secret must contain a JSON object") from exc
    if not isinstance(parsed, dict):
        raise RuntimeSecretError("runtime secret must contain a JSON object")
    return parsed


def get_runtime_secret(
    field: str,
    *,
    env_name: str | None = None,
    required: bool = True,
    secret_name_env: str = "DWV1_RUNTIME_SECRET_NAME",
) -> str | None:
    secret_name = os.getenv(secret_name_env, "").strip()
    if secret_name:
        value = _load_secret_document(secret_name).get(field)
    elif (os.getenv("DWV1_EXTERNAL_OIDC_ENABLED", "").strip().lower() not in {"1", "true", "yes"} or _allow_env_secrets()) and env_name:
        value = os.getenv(env_name)
    else:
        value = None
    if isinstance(value, str) and value:
        return value
    if required:
        raise RuntimeSecretError(f"runtime secret field {field} is unavailable")
    return None
