"""
Migration Script: Move OpenRouter Keys from Local DB to D1

This script migrates existing OpenRouter API keys from the local SQLite database
to the Worker D1 database for multi-device syncing.

USAGE:
    python -m server.migrations.migrate_openrouter_to_d1

WHAT IT DOES:
1. Fetches all LLM connections (OpenRouter) from local database
2. Gets the user's API key from settings
3. Uploads OpenRouter key to Worker D1 database
4. Marks migration as complete

WHEN TO RUN:
- After deploying the D1 schema changes
- Before users start using the new multi-device flow
- Can be run multiple times (idempotent)
"""

import asyncio
import sys
import json
from pathlib import Path

# Add server directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from server.db.session import AsyncSessionFactory
from server.repositories.llm_connections import LLMConnectionRepository
from server.services.waitlist_service import WaitlistService
from server.services.settings import SettingsService
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)


async def migrate_openrouter_keys():
    """
    Main migration function to move OpenRouter keys to D1.
    """
    logger.info("=" * 60)
    logger.info("Starting OpenRouter Key Migration to D1")
    logger.info("=" * 60)

    try:
        async with AsyncSessionFactory() as session:
            # 1. Get user credentials
            logger.info("Step 1: Fetching user credentials from local database...")
            user_email_setting = await SettingsService.get_setting_by_key(session, "user_email")
            api_key_setting = await SettingsService.get_setting_by_key(session, "api_key")

            if not user_email_setting or not api_key_setting:
                logger.warning("⚠️  No user credentials found in local database.")
                logger.warning("   This likely means no user has onboarded yet.")
                logger.info("   Migration not needed - skipping.")
                return

            user_email = user_email_setting.setting_value
            user_api_key = api_key_setting.setting_value

            logger.info(f"✓ Found user: {user_email}")

            # 2. Get OpenRouter LLM connections
            logger.info("Step 2: Fetching OpenRouter connections from local database...")
            llm_repo = LLMConnectionRepository(session)
            all_connections = await llm_repo.list()

            openrouter_connections = [
                conn for conn in all_connections
                if conn.get("type") == "openrouter"
            ]

            if not openrouter_connections:
                logger.warning("⚠️  No OpenRouter connections found in local database.")
                logger.info("   Migration not needed - skipping.")
                return

            logger.info(f"✓ Found {len(openrouter_connections)} OpenRouter connection(s)")

            # 3. Extract OpenRouter API key
            for connection in openrouter_connections:
                config = connection.get("config_dict", {})
                openrouter_key = config.get("api_key")

                if not openrouter_key:
                    logger.warning(f"⚠️  Connection '{connection.get('name')}' has no API key - skipping")
                    continue

                logger.info(f"Step 3: Found OpenRouter key in connection '{connection.get('name')}'")

                # 4. Upload to Worker D1
                logger.info("Step 4: Uploading OpenRouter key to Worker D1...")
                waitlist_service = WaitlistService()

                success = await waitlist_service.store_openrouter_key_in_d1(
                    email=user_email,
                    openrouter_key=openrouter_key
                )

                if success:
                    logger.info("✅ Successfully uploaded OpenRouter key to D1!")

                    # 5. Mark migration as complete
                    await SettingsService.upsert_setting(
                        session=session,
                        setting_key="openrouter_migrated_to_d1",
                        setting_value="true",
                        description="OpenRouter key migrated to D1",
                        is_encrypted=False
                    )

                    logger.info("✅ Migration completed successfully!")
                    logger.info("=" * 60)
                    logger.info("Users can now access their OpenRouter key from any device")
                    logger.info("=" * 60)

                    return  # Only migrate the first OpenRouter connection

                else:
                    logger.error("❌ Failed to upload OpenRouter key to D1")
                    logger.error("   Please check the logs above for errors")
                    logger.error("   You can retry by running this script again")
                    return

            logger.warning("⚠️  No valid OpenRouter keys found to migrate")

    except Exception as e:
        logger.error(f"❌ Migration failed with error: {e}", exc_info=True)
        logger.error("   Please fix the error and retry")
        raise


if __name__ == "__main__":
    try:
        asyncio.run(migrate_openrouter_keys())
    except KeyboardInterrupt:
        logger.info("\n⚠️  Migration cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ Migration failed: {e}")
        sys.exit(1)
