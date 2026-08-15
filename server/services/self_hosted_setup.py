import asyncio
import re
from datetime import datetime
from uuid import uuid4

import httpx
from fastapi_users.password import PasswordHelper
from sqlalchemy import select, text

from server.auth.tenant_context import set_tenant_id
from server.db.session import AsyncSessionFactory
from server.models.tenant import Tenant
from server.models.tenant_member import TenantMember, TenantRole
from server.models.user import User
from server.services.settings import SettingsService
from server.utils.config_loader import (
    get_self_hosted_config,
    get_waitlist_config,
    is_self_hosted,
    validate_self_hosted_config,
)
from server.utils.custom_logger import get_logger
from server.utils.seed_notebook import seed_demo_notebooks_for_user

logger = get_logger(__name__)

SELF_HOSTED_SETUP_LOCK_ID = 2026081401


def _generate_slug(name: str) -> str:
    """Generate a URL-safe slug from name."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "org"


async def _generate_enterprise_api_key() -> str:
    """
    Generate an API key for self-hosted teams mode by calling the worker.

    Returns:
        API key string (sk_...)

    Raises:
        Exception if worker call fails
    """
    worker_config = get_waitlist_config()
    worker_url = worker_config.get("worker_url")
    if not worker_url:
        raise ValueError("WORKER_URL is not configured")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{worker_url}/api/enterprise/generate-key")
            response.raise_for_status()
            data = response.json()
            api_key = data.get("api_key")
            if not api_key:
                raise ValueError("Worker did not return an API key")
            logger.info("Successfully generated enterprise API key from worker")
            return api_key
    except httpx.HTTPStatusError as e:
        logger.error(f"Worker returned error {e.response.status_code}: {e.response.text}")
        raise Exception(f"Failed to generate API key: {e.response.text}")
    except Exception as e:
        logger.error(f"Failed to generate enterprise API key: {e}")
        raise


async def _acquire_setup_lock(session) -> None:
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        await session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": SELF_HOSTED_SETUP_LOCK_ID})


async def setup_self_hosted_environment() -> None:
    """
    Initialize the self-hosted environment with master user and tenant.

    This function is idempotent - it will skip creation if entities already exist.
    Called during app startup when APP_MODE=self-hosted.
    """
    if not is_self_hosted():
        return

    is_valid, error = validate_self_hosted_config()
    if not is_valid:
        logger.error(f"Self-hosted configuration error: {error}")
        raise ValueError(error)

    config = get_self_hosted_config()
    password_helper = PasswordHelper()

    async with AsyncSessionFactory() as session:
        await _acquire_setup_lock(session)

        result = await session.execute(select(User).where(User.email == config["master_email"]))
        existing_user = result.scalar_one_or_none()

        if existing_user:
            logger.info(f"Master user already exists: {config['master_email']}")

            result = await session.execute(select(Tenant).where(Tenant.owner_id == existing_user.id))
            existing_tenant = result.scalar_one_or_none()

            if existing_tenant:
                logger.info(f"Tenant already exists: {existing_tenant.name}")

                # Check if API key exists, generate if missing
                set_tenant_id(existing_tenant.id)
                api_key_setting = await SettingsService.get_setting_by_key(session, "api_key")
                if not api_key_setting:
                    logger.info("API key missing, generating...")
                    try:
                        api_key = await _generate_enterprise_api_key()
                        await SettingsService.upsert_setting(
                            session=session,
                            setting_key="api_key",
                            setting_value=api_key,
                            description="Enterprise API key for worker authentication",
                            is_encrypted=True,
                        )
                        logger.info("  - API key generated and stored")
                    except Exception as e:
                        logger.warning(f"Failed to generate API key (non-fatal): {e}")

                # Still seed demo notebooks if not already seeded for this user
                user_id_copy = existing_user.id
                tenant_id_copy = existing_tenant.id

                async def seed_in_background():
                    try:
                        async with AsyncSessionFactory() as seed_session:
                            await seed_demo_notebooks_for_user(seed_session, user_id_copy, tenant_id_copy)
                    except Exception as e:
                        logger.error(f"Failed to seed demo notebooks for master user: {e}")

                asyncio.create_task(seed_in_background())
                return

            user = existing_user
        else:
            logger.info(f"Creating master user: {config['master_email']}")

            user = User(
                id=uuid4(),
                email=config["master_email"],
                hashed_password=password_helper.hash(config["master_password"]),
                is_active=True,
                is_verified=True,
                is_superuser=True,
                full_name="Administrator",
            )
            session.add(user)
            await session.flush()

            logger.info(f"Master user created: {user.email}")

        base_slug = _generate_slug(config["org_name"])
        slug = base_slug
        counter = 1

        while True:
            result = await session.execute(select(Tenant).where(Tenant.slug == slug))
            if not result.scalar_one_or_none():
                break
            slug = f"{base_slug}-{counter}"
            counter += 1

        tenant = Tenant(
            id=uuid4(),
            name=config["org_name"],
            slug=slug,
            owner_id=user.id,
            is_personal=False,
        )
        session.add(tenant)
        await session.flush()

        member = TenantMember(
            id=uuid4(),
            user_id=user.id,
            tenant_id=tenant.id,
            role=TenantRole.OWNER.value,
            joined_at=datetime.utcnow(),
        )
        session.add(member)

        await session.commit()

        logger.info("Self-hosted setup complete:")
        logger.info(f"  - Master user: {user.email}")
        logger.info(f"  - Tenant: {tenant.name} (slug: {tenant.slug})")

        # Generate and store API key for enterprise customer
        set_tenant_id(tenant.id)
        try:
            api_key = await _generate_enterprise_api_key()
            await SettingsService.upsert_setting(
                session=session,
                setting_key="api_key",
                setting_value=api_key,
                description="Enterprise API key for worker authentication",
                is_encrypted=True,
            )
            logger.info("  - API key generated and stored")
        except Exception as e:
            logger.warning(f"Failed to generate API key (non-fatal): {e}")
            logger.warning("Screenshot/PDF generation will not work without API key")

        # Seed demo notebooks for the master user in background
        user_id_copy = user.id
        tenant_id_copy = tenant.id

        async def seed_in_background():
            try:
                async with AsyncSessionFactory() as seed_session:
                    await seed_demo_notebooks_for_user(seed_session, user_id_copy, tenant_id_copy)
            except Exception as e:
                logger.error(f"Failed to seed demo notebooks for master user: {e}")

        asyncio.create_task(seed_in_background())
