from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from server.models.dashboard import Dashboard
from server.models.files import File
from server.models.notebooks import NotebookDataset
from server.models.queries import Query
from server.repositories.datasets import DatasetRepository
from server.repositories.messages import MessageRepository
from server.repositories.notebooks import NotebookRepository
from server.repositories.threads import ThreadRepository
from server.services.dataset_storage import DatasetStorageService
from server.services.settings import SettingsService
from server.services.url_download_service import URLDownloadService
from server.utils.config_loader import get_resource_path
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

DEMO_SEEDED_KEY = "demo_notebooks_seeded"
DEMO_VERSION_KEY = "demo_notebooks_version"


async def seed_demo_notebooks_for_user(session: AsyncSession, user_id: UUID, tenant_id: UUID) -> None:
    """
    Seed demo notebooks directly for a user.

    Args:
        session: Database session
        user_id: User ID who will own the demo notebooks
        tenant_id: The tenant to seed into
    """
    from server.auth.tenant_context import set_tenant_id

    # Set tenant context so repositories auto-inject tenant_id
    set_tenant_id(tenant_id)

    try:
        if not await should_seed_demos(session, user_id):
            seeded_version_setting = await SettingsService.get_setting_by_key_for_user(
                session, DEMO_VERSION_KEY, user_id
            )
            seeded_version = seeded_version_setting.setting_value if seeded_version_setting else "unknown"
            logger.info(f"Demo notebooks already seeded for user {user_id} (version {seeded_version}), skipping...")
            return

        config_file = get_resource_path("example_data/demo_notebooks.json")
        if not config_file:
            logger.warning("Demo config file not found - skipping demo notebook seeding")
            return

        with open(config_file, encoding="utf-8") as f:
            config = json.load(f)

        config_version = config.get("version", 1)
        notebooks_config = config.get("notebooks", [])

        if not notebooks_config:
            logger.warning("No notebooks found in configuration")
            return

        logger.info(f"Seeding demo notebooks for user {user_id} (version {config_version})...")

        successfully_seeded = 0
        for idx, notebook_config in enumerate(notebooks_config, 1):
            try:
                logger.info(f"[{idx}/{len(notebooks_config)}] Processing notebook...")
                await _seed_notebook(session, notebook_config, tenant_id, user_id)
                successfully_seeded += 1
            except Exception as e:
                logger.error(f"[{idx}/{len(notebooks_config)}] Failed to seed notebook: {e}", exc_info=True)
                continue

        await mark_demos_seeded(session, config_version, user_id)

        if successfully_seeded == 0:
            logger.warning(f"No demo notebooks were successfully seeded (0/{len(notebooks_config)})")
        else:
            logger.info(f"Seeded {successfully_seeded}/{len(notebooks_config)} demo notebook(s) for user {user_id}")

    except Exception as e:
        logger.error(f"Failed to seed demo notebooks for user {user_id}: {e}", exc_info=True)


async def should_seed_demos(session: AsyncSession, user_id: UUID) -> bool:
    """
    Check if demo notebooks should be seeded for a user by comparing versions.
    Returns True if:
    - No seeded version exists for this user (first time)
    - JSON version > seeded version (update available)
    """
    config_file = get_resource_path("example_data/demo_notebooks.json")
    if not config_file:
        logger.warning("Demo config file not found - skipping demo seeding")
        return False

    # Get version from config file
    try:
        with open(config_file, encoding="utf-8") as f:
            config = json.load(f)
        config_version = config.get("version", 1)
    except Exception as e:
        logger.error(f"Failed to read demo config version: {e}")
        return False

    # Get seeded version from user-scoped settings
    seeded_version_setting = await SettingsService.get_setting_by_key_for_user(session, DEMO_VERSION_KEY, user_id)

    if seeded_version_setting is None:
        # Never seeded before for this user
        return True

    try:
        seeded_version = int(seeded_version_setting.setting_value)
    except (ValueError, AttributeError):
        # Invalid version in DB, reseed
        return True

    # Seed if config version is higher
    return config_version > seeded_version


async def mark_demos_seeded(session: AsyncSession, version: int, user_id: UUID) -> None:
    """Mark demo notebooks as seeded with the given version for a user."""
    # Update version key for this user
    await SettingsService.upsert_setting_for_user(
        session,
        setting_key=DEMO_VERSION_KEY,
        setting_value=str(version),
        user_id=user_id,
        description="Version of demo notebooks that have been seeded for this user",
        is_encrypted=False,
    )

    # Also update timestamp for reference
    await SettingsService.upsert_setting_for_user(
        session,
        setting_key=DEMO_SEEDED_KEY,
        setting_value=datetime.utcnow().isoformat(),
        user_id=user_id,
        description="Timestamp when demo notebooks were last seeded for this user",
        is_encrypted=False,
    )


def json_array_to_csv_bytes(data: list[dict[str, Any]]) -> bytes:
    if not data:
        return b""

    output = io.StringIO()
    fieldnames = list(data[0].keys())
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(data)
    csv_string = output.getvalue()
    return csv_string.encode("utf-8")


async def _seed_notebook(session: AsyncSession, config: dict[str, Any], tenant_id: UUID, user_id: UUID):
    """Seed a single notebook and return it."""
    notebook_name = config.get("name", "Untitled Notebook")
    logger.info(f"Creating demo notebook: {notebook_name}")

    try:
        notebook_repo = NotebookRepository(session)
        notebook = await notebook_repo.create(
            {
                "notebook_name": notebook_name,
                "description": config.get("description", ""),
                "created_by": user_id,
            }
        )

        thread_repo = ThreadRepository(session)
        await thread_repo.create(
            {
                "id": notebook.id,
                "notebook_id": notebook.id,
                "thread_title": None,
            }
        )

        dataset_ids = []
        datasets_config = config.get("datasets", [])

        if not datasets_config:
            logger.warning(f"Notebook '{notebook_name}' has no datasets configured")
        else:
            logger.info(f"Creating {len(datasets_config)} dataset(s) for notebook '{notebook_name}'...")

            for idx, dataset_config in enumerate(datasets_config, 1):
                try:
                    logger.info(f"  [{idx}/{len(datasets_config)}] Creating dataset...")
                    dataset_id = await _create_dataset(session, dataset_config, tenant_id, user_id)
                    dataset_ids.append(dataset_id)
                except Exception as e:
                    logger.error(f"  Failed to create dataset {idx}: {e}", exc_info=True)
                    continue

        # Associate datasets with notebook
        for dataset_id in dataset_ids:
            notebook_dataset = NotebookDataset(
                notebook_id=notebook.id,
                dataset_id=dataset_id,
            )
            session.add(notebook_dataset)
        await session.commit()

        # Create messages
        messages_config = config.get("messages", [])
        if messages_config:
            logger.info(f"Adding {len(messages_config)} message(s)...")
            await _create_messages(session, notebook.id, messages_config)

        # Create saved queries
        if dataset_ids:
            primary_dataset_id = dataset_ids[0]
            queries_config = config.get("saved_queries", [])
            if queries_config:
                logger.info(f"Adding {len(queries_config)} saved query/queries...")
                await _create_saved_queries(
                    session, notebook.id, primary_dataset_id, queries_config, tenant_id, user_id
                )

        # Create dashboards
        dashboards_config = config.get("dashboards", [])
        if dashboards_config:
            logger.info(f"Adding {len(dashboards_config)} dashboard(s)...")
            await _create_dashboards(session, notebook.id, dashboards_config, tenant_id)

        logger.info(f"Demo notebook '{notebook_name}' created (ID: {notebook.id}, {len(dataset_ids)} dataset(s))")
        return notebook

    except Exception as e:
        logger.error(f"Failed to create notebook '{notebook_name}': {e}", exc_info=True)
        raise


async def _create_dataset(session: AsyncSession, config: dict[str, Any], tenant_id: UUID, user_id: UUID) -> str:
    dataset_name = config.get("name", "Dataset")
    dataset_repo = DatasetRepository(session)
    dataset = await dataset_repo.create(
        {
            "type": "file",
            "name": dataset_name,
            "created_by": user_id,
        }
    )

    files_created = 0
    files_to_create = config.get("files", [])

    if not files_to_create:
        logger.warning(f"Dataset '{dataset_name}' has no files configured")
        await session.commit()
        return dataset.id

    logger.info(f"Creating dataset '{dataset_name}' with {len(files_to_create)} file(s)...")

    for idx, file_config in enumerate(files_to_create, 1):
        filename = file_config.get("filename", "data.csv")
        source_url = file_config.get("source_url")

        if not source_url:
            logger.warning(f"[{idx}/{len(files_to_create)}] File '{filename}' has no source_url, skipping...")
            continue

        try:
            logger.info(f"[{idx}/{len(files_to_create)}] Downloading '{filename}' from: {source_url}")

            # Download file from URL
            file_content, downloaded_filename = await URLDownloadService.download_file_from_url(url=source_url)

            # Save to disk storage
            storage_metadata = await DatasetStorageService.save_bytes(
                dataset_id=str(dataset.id),
                filename=filename,
                data=file_content,
            )

            # Detect file type from filename
            file_type = "csv"
            if filename.lower().endswith((".xlsx", ".xls")):
                file_type = "excel"
            elif filename.lower().endswith(".json"):
                file_type = "json"
            elif filename.lower().endswith(".parquet"):
                file_type = "parquet"

            # Create file record with source_url
            file_record = File(
                name=filename,
                type=file_type,
                size=storage_metadata.size,
                dataset_id=dataset.id,
                storage_path=str(storage_metadata.relative_path),
                checksum=storage_metadata.checksum,
                source_url=source_url,
                tenant_id=tenant_id,
            )
            session.add(file_record)
            files_created += 1

            logger.info(
                f"[{idx}/{len(files_to_create)}] Created file '{filename}' (size: {storage_metadata.size / (1024 * 1024):.2f} MB)"
            )

        except Exception as e:
            logger.error(f"[{idx}/{len(files_to_create)}] Failed to download '{filename}' from {source_url}: {e}")
            continue

    await session.commit()

    if files_created == 0:
        logger.warning(f"Dataset '{dataset_name}' created but no files were successfully downloaded")
    else:
        logger.info(f"Dataset '{dataset_name}' created with {files_created}/{len(files_to_create)} file(s)")

    return dataset.id


async def _create_messages(session: AsyncSession, thread_id: str, messages_config: list[dict[str, Any]]) -> None:
    message_repo = MessageRepository(session)

    for msg_config in messages_config:
        await message_repo.create(
            {
                "thread_id": thread_id,
                "role": msg_config.get("role", "user"),
                "content": msg_config.get("content", ""),
            }
        )


async def _create_saved_queries(
    session: AsyncSession,
    notebook_id: str,
    dataset_id: str,
    queries_config: list[dict[str, Any]],
    tenant_id: UUID,
    created_by: UUID,
) -> None:
    from sqlalchemy import select

    for query_config in queries_config:
        query_id = query_config.get("id")

        # If an ID is provided, check if it already exists
        if query_id:
            existing = await session.execute(select(Query).where(Query.id == query_id))
            if existing.scalar_one_or_none():
                # Query with this ID already exists, skip it
                continue

        query = Query(
            id=query_id,  # Use provided ID if available, otherwise SQLAlchemy generates one
            notebook_id=notebook_id,
            dataset_id=dataset_id,
            name=query_config.get("name", "Untitled Query"),
            query=query_config.get("query", ""),
            output_schema=query_config.get("output_schema", "{}"),
            tenant_id=tenant_id,
            created_by=created_by,
        )
        session.add(query)

    await session.commit()


async def _create_dashboards(
    session: AsyncSession, notebook_id: str, dashboards_config: list[dict[str, Any]], tenant_id: UUID
) -> None:
    for dash_config in dashboards_config:
        dashboard = Dashboard(
            notebook_id=notebook_id,
            version_num=dash_config.get("version", 1),
            html_content=dash_config.get("html", ""),
            tenant_id=tenant_id,
        )
        session.add(dashboard)

    await session.commit()
