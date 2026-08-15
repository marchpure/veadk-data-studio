from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import AuthContext, require_any_scope, require_scope
from server.auth.scopes import Scope
from server.constants.models import MODELS_BY_PROVIDER, configured_model_for_provider
from server.db.session import get_async_session
from server.models.tenant_member import TenantMember
from server.repositories.llm_connections import LLMConnectionRepository
from server.schemas.llm_connections import (
    LLMConnectionCreate,
    LLMConnectionListResponse,
    LLMConnectionRead,
    LLMConnectionUpdate,
)
from server.services.crypto_service import CryptoService
from server.services.llm_service import ModelService
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

router = APIRouter()

MASKED_API_KEY = "••••••••"


def validate_provider_config(provider_type: str, config: dict) -> None:
    """
    Validate configuration based on provider type.
    Raises HTTPException if required fields are missing.
    """
    if provider_type in ("claude_code", "codex"):
        return

    if not config:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Configuration is required")

    providers = ModelService.get_supported_providers()
    provider_info = providers.get(provider_type)

    if not provider_info:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown provider type: {provider_type}")

    required_fields = provider_info.get("required_fields", [])
    missing_fields = []

    for field in required_fields:
        value = config.get(field)
        if not value or (isinstance(value, str) and not value.strip()):
            missing_fields.append(field)

    if missing_fields:
        if provider_type == "bedrock":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing required fields for Bedrock: {', '.join(missing_fields)}. Bedrock requires AWS credentials (aws_access_key_id, aws_secret_access_key, aws_region_name), not an API key.",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing required fields for {provider_type}: {', '.join(missing_fields)}",
            )


@router.get("/llm-connections", response_model=LLMConnectionListResponse)
async def list_llm_connections(
    auth: AuthContext = Depends(require_scope(Scope.LLM_CONNECTION_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        repo = LLMConnectionRepository(session)
        connections = await repo.list()

        tenant_members_result = await session.execute(
            select(TenantMember).where(TenantMember.tenant_id == auth.tenant_id)
        )
        tenant_members = {str(tm.user_id): tm.role for tm in tenant_members_result.scalars().all()}

        items = []
        for conn in connections:
            # Filter based on creator role: owner/admin visible to all, member visible to creator only
            created_by = conn.created_by

            if created_by:
                creator_role = tenant_members.get(str(created_by))

                # Member creations: only visible to creator
                if creator_role == "member" and str(created_by) != str(auth.user_id):
                    continue
                # Unknown role: show to creator only (safe default)
                elif creator_role not in ("owner", "admin", "member") and str(created_by) != str(auth.user_id):
                    continue

            if conn.config:
                try:
                    decrypted_config = await CryptoService.decrypt_config(conn.config, session)
                    safe_config = {k: v for k, v in decrypted_config.items() if k not in ["api_key"]}
                    safe_config["api_key"] = MASKED_API_KEY if decrypted_config.get("api_key") else None

                    conn_data = LLMConnectionRead(
                        id=conn.id,
                        type=conn.type,
                        name=conn.name,
                        config=safe_config,
                        created_at=conn.created_at,
                        created_by=str(created_by) if created_by else None,
                    )
                    items.append(conn_data)
                except Exception:
                    conn_data = LLMConnectionRead(
                        id=conn.id,
                        type=conn.type or "unknown",
                        name=conn.name,
                        config={"error": "Failed to decrypt configuration"},
                        created_at=conn.created_at,
                        created_by=str(created_by) if created_by else None,
                    )
                    items.append(conn_data)
            else:
                conn_data = LLMConnectionRead(
                    id=conn.id,
                    type=conn.type or "unknown",
                    name=conn.name,
                    config={},
                    created_at=conn.created_at,
                    created_by=str(created_by) if created_by else None,
                )
                items.append(conn_data)

        return LLMConnectionListResponse(items=items, total=len(items))
    except Exception as e:
        logger.error(
            f"Unexpected error in list_llm_connections: {str(e)}", posthog_context={"function": "list_llm_connections"}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while listing LLM connections",
        )


@router.post("/llm-connections", response_model=LLMConnectionRead)
async def create_llm_connection(
    connection_data: LLMConnectionCreate,
    auth: AuthContext = Depends(require_scope(Scope.LLM_CONNECTION_CREATE)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        repo = LLMConnectionRepository(session)

        # Check for existing connection with same provider type
        existing = await repo.get_by_type(connection_data.type)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A connection for provider '{connection_data.type}' already exists",
            )

        config = connection_data.config
        validate_provider_config(connection_data.type, config)

        create_data = {
            "type": connection_data.type,
            "name": connection_data.name,
            "config_dict": config,
            "tenant_id": auth.tenant_id,
            "created_by": auth.user_id,
        }

        connection = await repo.create(create_data)

        decrypted_config = await CryptoService.decrypt_config(connection.config, session)
        safe_config = {k: v for k, v in decrypted_config.items() if k not in ["api_key"]}
        safe_config["api_key"] = MASKED_API_KEY

        return LLMConnectionRead(
            id=connection.id,
            type=connection.type,
            name=connection.name,
            config=safe_config,
            created_at=connection.created_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error in create_llm_connection: {str(e)}",
            posthog_context={"function": "create_llm_connection", "type": connection_data.type},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating LLM connection",
        )


@router.get("/llm-connections/providers")
async def get_supported_providers(
    auth: AuthContext = Depends(require_scope(Scope.LLM_CONNECTION_READ)),
):
    try:
        return ModelService.get_supported_providers()
    except Exception as e:
        logger.error(
            f"Unexpected error in get_supported_providers: {str(e)}",
            posthog_context={"function": "get_supported_providers"},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while retrieving supported providers",
        )


@router.get("/llm-connections/models")
async def get_available_models(
    auth: AuthContext = Depends(require_scope(Scope.LLM_CONNECTION_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        repo = LLMConnectionRepository(session)
        connections = await repo.list()

        models_by_provider: dict[str, list[str]] = {}

        for connection in connections:
            provider = connection.type
            existing = set(models_by_provider.get(provider, []))

            # Providers with an explicitly configured model should expose that
            # model in addition to any built-in catalog entries. This is needed
            # for OpenAI-compatible endpoints such as Volcengine Ark.
            if connection.config:
                try:
                    decrypted = await CryptoService.decrypt_config(connection.config, session)
                    models = decrypted.get("models", []) if provider in {"azure", "bedrock"} else []

                    if isinstance(models, str):
                        models = [m.strip() for m in models.split(",") if m.strip()]
                    elif not isinstance(models, list):
                        models = []

                    existing.update(models)

                    configured_model = configured_model_for_provider(provider, decrypted)
                    if configured_model:
                        existing.add(configured_model)

                except Exception as e:
                    logger.error(f"Failed to decrypt config for {provider}: {e}")

            catalog = MODELS_BY_PROVIDER.get(provider, [])
            existing.update(catalog)

            models_by_provider[provider] = list(existing)

        return {"models_by_provider": models_by_provider}

    except Exception as e:
        logger.error(
            f"Unexpected error in get_available_models: {str(e)}", posthog_context={"function": "get_available_models"}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve available models",
        )


@router.get("/llm-connections/{connection_id}/models")
async def get_connection_models(
    connection_id: str,
    auth: AuthContext = Depends(require_scope(Scope.LLM_CONNECTION_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        repo = LLMConnectionRepository(session)
        connection = await repo.get(connection_id)

        if not connection:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LLM connection not found")

        # For Azure and Bedrock, return user-provided models from config
        if connection.type in ["azure", "bedrock"]:
            user_models = []
            if connection.config:
                try:
                    decrypted_config = await CryptoService.decrypt_config(connection.config, session)
                    models_config = decrypted_config.get("models", [])

                    # Handle both string and array formats
                    if isinstance(models_config, str):
                        # Split by comma if it's a comma-separated string
                        model_list = [m.strip() for m in models_config.split(",") if m.strip()]
                    elif isinstance(models_config, list):
                        model_list = models_config
                    else:
                        model_list = []

                    # Format as model objects
                    for model_id in model_list:
                        user_models.append(
                            {
                                "id": model_id,
                                "name": model_id,
                                "source": "user_provided",
                            }
                        )

                except Exception as e:
                    logger.warning(f"Failed to decrypt config for connection {connection_id}: {str(e)}")

            return {
                "connection_id": connection_id,
                "provider": connection.type,
                "models": user_models,
            }

        # For other providers, return catalog models
        catalog_models_raw = ModelService.get_available_models(connection.type)

        # Format catalog models
        catalog_models = []
        if isinstance(catalog_models_raw, list):
            for model in catalog_models_raw:
                # Remove provider prefix for cleaner display
                model_id = model
                if "/" in model_id:
                    model_id = model_id.split("/", 1)[1]

                catalog_models.append(
                    {
                        "id": model_id,
                        "name": model_id,
                        "source": "catalog",
                    }
                )

        return {
            "connection_id": connection_id,
            "provider": connection.type,
            "models": catalog_models,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error in get_connection_models: {str(e)}",
            posthog_context={"function": "get_connection_models", "connection_id": connection_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while retrieving connection models",
        )


@router.get("/llm-connections/{connection_id}", response_model=LLMConnectionRead)
async def get_llm_connection(
    connection_id: str,
    auth: AuthContext = Depends(require_scope(Scope.LLM_CONNECTION_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        repo = LLMConnectionRepository(session)
        connection = await repo.get(connection_id)

        if not connection:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LLM connection not found")

        if connection.config:
            try:
                decrypted_config = await CryptoService.decrypt_config(connection.config, session)
                safe_config = {k: v for k, v in decrypted_config.items() if k not in ["api_key"]}
                safe_config["api_key"] = MASKED_API_KEY if decrypted_config.get("api_key") else None
            except Exception:
                safe_config = {"error": "Failed to decrypt configuration"}
        else:
            safe_config = {}

        return LLMConnectionRead(
            id=connection.id,
            type=connection.type,
            name=connection.name,
            config=safe_config,
            created_at=connection.created_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error in get_llm_connection: {str(e)}",
            posthog_context={"function": "get_llm_connection", "connection_id": connection_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while retrieving LLM connection",
        )


@router.put("/llm-connections/{connection_id}", response_model=LLMConnectionRead)
async def update_llm_connection(
    connection_id: str,
    connection_data: LLMConnectionUpdate,
    auth: AuthContext = Depends(require_any_scope(Scope.LLM_CONNECTION_UPDATE, Scope.LLM_CONNECTION_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        repo = LLMConnectionRepository(session)

        existing = await repo.get(connection_id)
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LLM connection not found")

        # If user only has UPDATE_OWN scope, verify ownership
        if not auth.has_scope(Scope.LLM_CONNECTION_UPDATE):
            if existing.created_by is None or str(existing.created_by) != str(auth.user_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can only update LLM connections you created",
                )

        update_data = {}
        if connection_data.type is not None:
            update_data["type"] = connection_data.type

        if connection_data.name is not None:
            update_data["name"] = connection_data.name

        if connection_data.config is not None:
            incoming_config = dict(connection_data.config)

            existing_decrypted: dict[str, Any] = {}
            if existing.config:
                try:
                    existing_decrypted = await CryptoService.decrypt_config(existing.config, session)
                except Exception:
                    existing_decrypted = {}

            # Preserve stored api_key when client sends the masked sentinel or no value
            incoming_api_key = incoming_config.get("api_key")
            if incoming_api_key in (MASKED_API_KEY, "", None):
                existing_api_key = existing_decrypted.get("api_key")
                if existing_api_key:
                    incoming_config["api_key"] = existing_api_key
                else:
                    incoming_config.pop("api_key", None)

            provider_type = connection_data.type if connection_data.type is not None else existing.type
            validate_provider_config(provider_type, incoming_config)

            update_data["config_dict"] = incoming_config

        connection = await repo.update(connection_id, update_data)

        if not connection:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LLM connection not found")

        if connection.config:
            try:
                decrypted_config = await CryptoService.decrypt_config(connection.config, session)
                safe_config = {k: v for k, v in decrypted_config.items() if k not in ["api_key"]}
                safe_config["api_key"] = MASKED_API_KEY
            except Exception:
                safe_config = {"error": "Failed to decrypt configuration"}
        else:
            safe_config = {}

        return LLMConnectionRead(
            id=connection.id,
            type=connection.type,
            name=connection.name,
            config=safe_config,
            created_at=connection.created_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error in update_llm_connection: {str(e)}",
            posthog_context={"function": "update_llm_connection", "connection_id": connection_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while updating LLM connection",
        )


@router.delete("/llm-connections/{connection_id}")
async def delete_llm_connection(
    connection_id: str,
    auth: AuthContext = Depends(require_any_scope(Scope.LLM_CONNECTION_DELETE, Scope.LLM_CONNECTION_DELETE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        repo = LLMConnectionRepository(session)

        existing = await repo.get(connection_id)
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LLM connection not found")

        # If user only has DELETE_OWN scope, verify ownership
        if not auth.has_scope(Scope.LLM_CONNECTION_DELETE):
            if existing.created_by is None or str(existing.created_by) != str(auth.user_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can only delete LLM connections you created",
                )

        success = await repo.delete(connection_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete LLM connection"
            )

        return {"message": "LLM connection deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error in delete_llm_connection: {str(e)}",
            posthog_context={"function": "delete_llm_connection", "connection_id": connection_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while deleting LLM connection",
        )
