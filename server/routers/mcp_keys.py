import os
import secrets
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import AuthContext, require_scope
from server.auth.mcp_keys import hash_mcp_api_key
from server.auth.scopes import Scope
from server.db.session import get_async_session
from server.repositories.mcp_api_key import MCPAPIKeyRepository
from server.schemas.mcp import MCPAPIKeyCreate, MCPAPIKeyCreateResponse, MCPAPIKeyResponse
from server.schemas.standard_response import success_response
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/mcp/keys", tags=["mcp"])
mcp_router = APIRouter(prefix="/mcp", tags=["mcp"])


def generate_api_key() -> tuple[str, str, str]:
    random_part = secrets.token_urlsafe(32)
    api_key = f"byaan_{random_part}"
    key_hash = hash_mcp_api_key(api_key)
    key_prefix = api_key[:13]
    return api_key, key_hash, key_prefix


@router.post("", response_model=dict)
async def create_mcp_api_key(
    payload: MCPAPIKeyCreate,
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    repo = MCPAPIKeyRepository(session)

    api_key, key_hash, key_prefix = generate_api_key()

    db_key = await repo.create(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        name=payload.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
    )

    logger.info(
        f"Created MCP API key for user {auth.user_id}",
        extra={"posthog_context": {"tenant_id": str(auth.tenant_id), "user_id": str(auth.user_id)}},
    )

    return success_response(
        data=MCPAPIKeyCreateResponse(
            id=db_key.id,
            name=db_key.name,
            api_key=api_key,
            key_prefix=key_prefix,
            created_at=db_key.created_at,
        ).model_dump(),
        message="MCP API key created successfully. Save this key securely - it won't be shown again.",
    )


@router.get("", response_model=dict)
async def list_mcp_api_keys(
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    repo = MCPAPIKeyRepository(session)
    keys = await repo.list_by_user(auth.user_id)

    return success_response(
        data=[
            MCPAPIKeyResponse(
                id=key.id,
                name=key.name,
                key_prefix=key.key_prefix,
                is_active=key.is_active,
                last_used_at=key.last_used_at,
                created_at=key.created_at,
            ).model_dump()
            for key in keys
        ],
        message=f"Retrieved {len(keys)} API keys",
    )


@router.delete("/{key_id}", response_model=dict)
async def delete_mcp_api_key(
    key_id: str,
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    from uuid import UUID

    try:
        key_uuid = UUID(key_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid key ID format")

    repo = MCPAPIKeyRepository(session)

    key = await repo.get_by_id(key_uuid)
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    if key.tenant_id != auth.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    success = await repo.delete(key_uuid, auth.tenant_id)

    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    logger.info(
        f"Deleted MCP API key {key_id}",
        extra={"posthog_context": {"tenant_id": str(auth.tenant_id), "user_id": str(auth.user_id)}},
    )

    return success_response(message="API key deleted successfully")


@mcp_router.get("/stdio-config", response_model=dict)
async def get_stdio_config(
    auth: AuthContext = Depends(require_scope(Scope.SETTINGS_READ)),
):
    is_bundled = getattr(sys, "frozen", False)

    if is_bundled:
        exe = Path(sys.executable).resolve()
        # exe is e.g. .../runtime/0.0.1/backend/backend
        # Walk up to the runtime/ dir and ensure a "current" symlink points to the running version
        version_dir = exe.parent.parent  # .../runtime/0.0.1
        runtime_dir = version_dir.parent  # .../runtime
        current_link = runtime_dir / "current"
        try:
            if runtime_dir.is_dir() and version_dir.is_dir():
                if current_link.is_symlink() or current_link.exists():
                    current_link.unlink()
                current_link.symlink_to(version_dir)
            command = str(current_link / "backend" / "backend")
        except OSError:
            command = str(exe)
        args = ["-m", "server.mcp.stdio_server"]
        env = {}
    else:
        project_root = os.environ.get("BYAAN_HOST_PROJECT_DIR") or str(Path(__file__).resolve().parents[2])
        command = "uv"
        args = ["--directory", project_root, "run", "python", "-m", "server.mcp.stdio_server"]
        env = {}

    return success_response(
        data={"command": command, "args": args, "env": env},
        message="MCP stdio configuration",
    )
