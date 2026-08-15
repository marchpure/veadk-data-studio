import asyncio
import os
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select

from server.auth.tenant_context import set_tenant_id
from server.db.session import AsyncSessionFactory
from server.models.connections import Connection
from server.models.datasets import Dataset
from server.models.llm_connections import LLMConnection
from server.models.notebooks import Notebook
from server.models.queries import Query
from server.models.tenant import Tenant
from server.models.tenant_member import TenantMember, TenantRole
from server.models.user import User
from server.repositories.llm_connections import LLMConnectionRepository
from server.utils.custom_logger import get_logger
from server.utils.seed_notebook import seed_demo_notebooks_for_user

logger = get_logger(__name__)

COMMUNITY_EMAIL = "community@local"
COMMUNITY_TENANT_NAME = "Community"
COMMUNITY_TENANT_SLUG = "community"
DEFAULT_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
DEFAULT_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")


def get_local_llm_config() -> dict[str, str] | None:
    """Return an OpenAI-compatible local LLM config without exposing its secret."""
    api_key = next(
        (
            os.getenv(name)
            for name in ("LLM_API_KEY", "ARK_API_KEY", "ARK_APIKEY", "OPENAI_API_KEY")
            if os.getenv(name)
        ),
        None,
    )
    if not api_key:
        return None

    return {
        "api_key": api_key,
        "api_base": os.getenv("LLM_ENDPOINT")
        or os.getenv("OPENAI_BASE_URL")
        or "https://api.openai.com/v1",
        "model": os.getenv("LLM_MODEL") or "gpt-5.4",
    }


async def ensure_local_llm_connection(session, tenant: Tenant, user: User) -> LLMConnection | None:
    """Create the environment-backed model connection once for a local workspace."""
    config = get_local_llm_config()
    if not config:
        return None

    set_tenant_id(tenant.id)
    existing_result = await session.execute(
        select(LLMConnection).where(
            LLMConnection.tenant_id == tenant.id,
            LLMConnection.type == "openai",
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        return existing

    connection = await LLMConnectionRepository(session).create(
        {
            "type": "openai",
            "name": "Ark Doubao",
            "config_dict": config,
            "tenant_id": tenant.id,
            "created_by": user.id,
        }
    )
    logger.info("Configured local OpenAI-compatible LLM connection from environment")
    return connection


async def _get_or_create_local_workspace(session) -> tuple[User, Tenant, bool]:
    """Resolve one usable local workspace, preserving the seeded default workspace."""
    result = await session.execute(select(Tenant).where(Tenant.slug == COMMUNITY_TENANT_SLUG))
    tenant = result.scalar_one_or_none()
    if tenant:
        result = await session.execute(select(User).where(User.id == tenant.owner_id))
        user = result.scalar_one_or_none()
        if user:
            return user, tenant, False

    result = await session.execute(select(Tenant).where(Tenant.id == DEFAULT_TENANT_ID))
    tenant = result.scalar_one_or_none()
    if tenant:
        result = await session.execute(select(User).where(User.id == tenant.owner_id))
        user = result.scalar_one_or_none()
        if user:
            resource_counts = []
            for model in (Connection, Dataset, LLMConnection, Notebook, Query):
                count_result = await session.execute(
                    select(func.count()).select_from(model).where(model.tenant_id == tenant.id)
                )
                resource_counts.append(count_result.scalar_one())

            # An untouched migration seed has no user data. Give it a real local
            # identity so desktop/bootstrap APIs can safely use it.
            if user.id == DEFAULT_USER_ID and not any(resource_counts):
                local_user = User(
                    id=uuid4(),
                    email=COMMUNITY_EMAIL,
                    hashed_password="community-no-auth",
                    is_active=True,
                    is_verified=True,
                    is_superuser=True,
                    full_name="Local User",
                )
                session.add(local_user)
                await session.flush()
                tenant.owner_id = local_user.id
                tenant.is_personal = True
                user = local_user

            membership_result = await session.execute(
                select(TenantMember).where(
                    TenantMember.user_id == user.id,
                    TenantMember.tenant_id == tenant.id,
                )
            )
            if not membership_result.scalar_one_or_none():
                session.add(
                    TenantMember(
                        id=uuid4(),
                        user_id=user.id,
                        tenant_id=tenant.id,
                        role=TenantRole.OWNER.value,
                        joined_at=datetime.utcnow(),
                    )
                )
                await session.commit()
            return user, tenant, False

    result = await session.execute(
        select(Tenant)
        .where(Tenant.is_personal.is_(True), Tenant.owner_id != DEFAULT_USER_ID)
        .order_by(Tenant.created_at.desc())
        .limit(1)
    )
    tenant = result.scalar_one_or_none()
    if tenant:
        result = await session.execute(select(User).where(User.id == tenant.owner_id))
        user = result.scalar_one_or_none()
        if user:
            return user, tenant, False

    result = await session.execute(select(User).where(User.email == COMMUNITY_EMAIL))
    user = result.scalar_one_or_none()
    if not user:
        user = User(
            id=uuid4(),
            email=COMMUNITY_EMAIL,
            hashed_password="community-no-auth",
            is_active=True,
            is_verified=True,
            is_superuser=True,
            full_name="Community User",
        )
        session.add(user)
        await session.flush()

    tenant = Tenant(
        id=uuid4(),
        name=COMMUNITY_TENANT_NAME,
        slug=COMMUNITY_TENANT_SLUG,
        owner_id=user.id,
        is_personal=True,
    )
    session.add(tenant)
    await session.flush()
    session.add(
        TenantMember(
            id=uuid4(),
            user_id=user.id,
            tenant_id=tenant.id,
            role=TenantRole.OWNER.value,
            joined_at=datetime.utcnow(),
        )
    )
    await session.commit()
    return user, tenant, True


async def get_local_bootstrap(session) -> dict[str, str | None]:
    """Return the bootstrap identity used by browser and desktop local modes."""
    user, tenant, _ = await _get_or_create_local_workspace(session)
    return {
        "user_id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "tenant_id": str(tenant.id),
    }


async def setup_community_environment() -> None:
    """
    Initialize any local environment with a default user, tenant, and optional model.
    No authentication or external waitlist is required. Existing local data is preserved.
    """
    async with AsyncSessionFactory() as session:
        user, tenant, created = await _get_or_create_local_workspace(session)
        await ensure_local_llm_connection(session, tenant, user)
        logger.info("Local environment ready (single-user, no auth)")

        if created:
            user_id_copy = user.id
            tenant_id_copy = tenant.id

            async def seed_in_background():
                try:
                    async with AsyncSessionFactory() as seed_session:
                        await seed_demo_notebooks_for_user(seed_session, user_id_copy, tenant_id_copy)
                except Exception as e:
                    logger.error(f"Failed to seed demo notebooks: {e}")

            asyncio.create_task(seed_in_background())
