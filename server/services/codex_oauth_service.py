import asyncio
import base64
import json
import secrets
from datetime import datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from server.repositories.llm_connections import LLMConnectionRepository
from server.services.crypto_service import CryptoService
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_AUTH_BASE = "https://auth.openai.com"
CODEX_TOKEN_URL = f"{CODEX_AUTH_BASE}/oauth/token"
CODEX_DEVICE_USERCODE_URL = f"{CODEX_AUTH_BASE}/api/accounts/deviceauth/usercode"
CODEX_DEVICE_TOKEN_URL = f"{CODEX_AUTH_BASE}/api/accounts/deviceauth/token"
CODEX_DEVICE_CALLBACK_URI = f"{CODEX_AUTH_BASE}/deviceauth/callback"
CODEX_DEVICE_VERIFICATION_URL = f"{CODEX_AUTH_BASE}/codex/device"

_device_auth_sessions: dict[str, dict] = {}


def extract_account_id_from_jwt(token: str) -> str | None:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload = parts[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding
        decoded = json.loads(base64.urlsafe_b64decode(payload))

        account_id = decoded.get("chatgpt_account_id")
        if account_id:
            return account_id

        auth_claim = decoded.get("https://api.openai.com/auth", {})
        if auth_claim.get("chatgpt_account_id"):
            return auth_claim["chatgpt_account_id"]

        orgs = decoded.get("organizations", [])
        if orgs and isinstance(orgs, list) and orgs[0].get("id"):
            return orgs[0]["id"]

        return None
    except Exception:
        logger.debug("[CODEX OAUTH] Failed to extract account_id from JWT")
        return None


async def start_device_code_auth() -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            CODEX_DEVICE_USERCODE_URL,
            json={"client_id": CODEX_CLIENT_ID},
            headers={"Content-Type": "application/json"},
        )

        if response.status_code != 200:
            error_detail = response.text
            logger.error(f"[CODEX OAUTH] Device code request failed: {response.status_code} - {error_detail}")
            raise ValueError(f"Failed to start device code auth: {error_detail}")

        data = response.json()
        device_auth_id = data["device_auth_id"]
        user_code = data.get("user_code") or data.get("usercode")
        interval = int(data.get("interval", 5))

        session_id = secrets.token_urlsafe(16)
        _device_auth_sessions[session_id] = {
            "device_auth_id": device_auth_id,
            "user_code": user_code,
            "interval": interval,
        }

        logger.info(f"[CODEX OAUTH] Device code auth started, session: {session_id[:8]}...")
        return {
            "session_id": session_id,
            "verification_url": CODEX_DEVICE_VERIFICATION_URL,
            "user_code": user_code,
        }


async def poll_device_code_auth(session_id: str) -> dict:
    session_data = _device_auth_sessions.get(session_id)
    if not session_data:
        raise ValueError("Invalid or expired session. Please restart the authentication flow.")

    device_auth_id = session_data["device_auth_id"]
    user_code = session_data["user_code"]
    interval = session_data["interval"]
    max_wait = 15 * 60
    elapsed = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        while elapsed < max_wait:
            response = await client.post(
                CODEX_DEVICE_TOKEN_URL,
                json={"device_auth_id": device_auth_id, "user_code": user_code},
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 200:
                code_data = response.json()
                _device_auth_sessions.pop(session_id, None)

                tokens = await _exchange_device_code(
                    code_data["authorization_code"],
                    code_data["code_verifier"],
                )
                return build_token_config(tokens)

            if response.status_code in (403, 404):
                await asyncio.sleep(interval)
                elapsed += interval
                continue

            error_detail = response.text
            _device_auth_sessions.pop(session_id, None)
            logger.error(f"[CODEX OAUTH] Device token poll failed: {response.status_code} - {error_detail}")
            raise ValueError(f"Device authentication failed: {error_detail}")

    _device_auth_sessions.pop(session_id, None)
    raise ValueError("Device authentication timed out after 15 minutes.")


async def _exchange_device_code(authorization_code: str, code_verifier: str) -> dict:
    logger.info("[CODEX OAUTH] Exchanging device authorization code for tokens...")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            CODEX_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": authorization_code,
                "redirect_uri": CODEX_DEVICE_CALLBACK_URI,
                "client_id": CODEX_CLIENT_ID,
                "code_verifier": code_verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            error_detail = response.text
            logger.error(f"[CODEX OAUTH] Token exchange failed: {response.status_code} - {error_detail}")
            raise ValueError(f"Token exchange failed: {error_detail}")

        tokens = response.json()
        logger.info("[CODEX OAUTH] Successfully obtained tokens via device code flow")
        return tokens


async def refresh_codex_tokens(refresh_token: str) -> dict | None:
    logger.info("[CODEX OAUTH] Refreshing access token...")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            CODEX_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": CODEX_CLIENT_ID,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            logger.error(f"[CODEX OAUTH] Token refresh failed: {response.status_code}")
            return None

        tokens = response.json()
        logger.info("[CODEX OAUTH] Token refreshed successfully")
        return tokens


async def get_valid_codex_token(connection_id: str, session: AsyncSession) -> tuple[str, str | None]:
    """Returns (access_token, account_id) tuple."""
    repo = LLMConnectionRepository(session)
    connection = await repo.get(connection_id)
    if not connection or not connection.config:
        raise ValueError(f"Codex connection not found: {connection_id}")

    cfg = await CryptoService.decrypt_config(connection.config, session)

    access_token = cfg.get("access_token")
    refresh_token = cfg.get("refresh_token")
    expires_at = cfg.get("expires_at", 0)
    account_id = cfg.get("account_id")

    if not access_token:
        raise ValueError("No access token found for Codex connection. Please re-authenticate.")

    current_time_ms = int(datetime.now().timestamp() * 1000)
    is_expired = current_time_ms >= (expires_at - 300000)

    if is_expired and refresh_token:
        logger.info(f"[CODEX OAUTH] Token expired for connection {connection_id}, refreshing...")
        new_tokens = await refresh_codex_tokens(refresh_token)
        if new_tokens:
            new_expires_at = int(datetime.now().timestamp() * 1000) + (new_tokens.get("expires_in", 3600) * 1000)
            cfg["access_token"] = new_tokens["access_token"]
            if new_tokens.get("refresh_token"):
                cfg["refresh_token"] = new_tokens["refresh_token"]
            cfg["expires_at"] = new_expires_at

            new_account_id = extract_account_id_from_jwt(new_tokens["access_token"])
            if new_account_id:
                cfg["account_id"] = new_account_id
                account_id = new_account_id

            encrypted_config = await CryptoService.encrypt_config(cfg, session)
            await repo.update(connection_id, {"config_encrypted": encrypted_config})

            return new_tokens["access_token"], account_id
        else:
            raise ValueError("Failed to refresh Codex token. Please re-authenticate.")

    if not account_id:
        account_id = extract_account_id_from_jwt(access_token)
        if account_id:
            cfg["account_id"] = account_id
            encrypted_config = await CryptoService.encrypt_config(cfg, session)
            await repo.update(connection_id, {"config_encrypted": encrypted_config})

    return access_token, account_id


def build_token_config(tokens: dict) -> dict:
    expires_at = int(datetime.now().timestamp() * 1000) + (tokens.get("expires_in", 3600) * 1000)

    account_id = None
    for token_key in ("id_token", "access_token"):
        token_val = tokens.get(token_key)
        if token_val:
            account_id = extract_account_id_from_jwt(token_val)
            if account_id:
                break

    config = {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token", ""),
        "expires_at": expires_at,
    }
    if account_id:
        config["account_id"] = account_id
    return config
