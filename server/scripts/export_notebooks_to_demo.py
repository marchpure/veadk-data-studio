"""
Export Demo Notebooks Script

This script exports existing notebooks from the database into the demo_notebooks.json format.
Configure the NOTEBOOK_IDS list below with the IDs of notebooks you want to export.

Usage:
    python -m server.scripts.export_notebooks_to_demo
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from server.db.session import AsyncSessionFactory
from server.models.files import File
from server.models.messages import Message
from server.models.notebooks import Notebook, NotebookDataset
from server.models.threads import Thread
from server.repositories.queries import QueryRepository
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

# ============================================================================
# CONFIGURATION - Edit this array with the notebook IDs you want to export
# ============================================================================
NOTEBOOK_IDS = [
    "bfbd094a-b33f-44f3-b436-1ebd5119d95f",
    "dc8f1780-ba52-46a0-90e3-b948ff43f38b",
]

# ============================================================================
# Constants
# ============================================================================
OUTPUT_FILE = Path(__file__).parent.parent / "example_data" / "demo_notebooks.json"


def excel_bytes_to_json_array(excel_content: bytes) -> list[dict[str, Any]]:
    """
    Convert Excel bytes to a list of dictionaries.

    Args:
        excel_content: Excel data as bytes

    Returns:
        List of dictionaries representing Excel rows
    """
    if not excel_content:
        return []

    try:
        from io import BytesIO

        import openpyxl

        print(f"      [EXCEL] Loading Excel file from {len(excel_content)} bytes...")
        # Load Excel file from bytes
        workbook = openpyxl.load_workbook(BytesIO(excel_content), data_only=True)
        worksheet = workbook.active
        print(f"      [EXCEL] Active worksheet: {worksheet.title}")

        # Get headers from first row
        headers = []
        for cell in worksheet[1]:
            if cell.value is not None:
                headers.append(str(cell.value))

        print(f"      [EXCEL] Headers: {headers}")

        # Convert rows to list of dicts
        rows = []
        for row_idx, row in enumerate(worksheet.iter_rows(min_row=2, values_only=True), start=2):
            # Skip empty rows
            if all(v is None for v in row):
                continue

            row_dict = {}
            for col_idx, value in enumerate(row):
                if col_idx < len(headers):
                    header = headers[col_idx]
                    # Convert types
                    if value is None:
                        row_dict[header] = None
                    elif isinstance(value, bool):
                        row_dict[header] = value
                    elif isinstance(value, (int, float)):
                        row_dict[header] = value
                    else:
                        row_dict[header] = str(value)

            if row_dict:  # Only add non-empty rows
                rows.append(row_dict)

        print(f"      [EXCEL] Converted {len(rows)} rows")
        return rows

    except Exception as e:
        print(f"      [EXCEL ERROR] Failed to convert: {e}")
        import traceback

        traceback.print_exc()
        logger.error(f"Failed to convert Excel bytes to JSON: {e}")
        return []


def csv_bytes_to_json_array(csv_content: bytes) -> list[dict[str, Any]]:
    """
    Convert CSV bytes to a list of dictionaries.

    Args:
        csv_content: CSV data as bytes

    Returns:
        List of dictionaries representing CSV rows
    """
    if not csv_content:
        return []

    try:
        # Decode bytes to string
        csv_string = csv_content.decode("utf-8")

        # Parse CSV
        reader = csv.DictReader(io.StringIO(csv_string))
        rows = list(reader)

        # Convert values to appropriate types (numbers, booleans, etc.)
        converted_rows = []
        for row in rows:
            converted_row = {}
            for key, value in row.items():
                if value is None:
                    converted_row[key] = None
                elif value.lower() in ("true", "false"):
                    converted_row[key] = value.lower() == "true"
                else:
                    # Try to convert to number
                    try:
                        if "." in value:
                            converted_row[key] = float(value)
                        else:
                            converted_row[key] = int(value)
                    except (ValueError, TypeError):
                        # Keep as string
                        converted_row[key] = value
            converted_rows.append(converted_row)

        return converted_rows

    except Exception as e:
        logger.error(f"Failed to convert CSV bytes to JSON: {e}")
        return []


async def export_notebook(session: AsyncSession, notebook_id: str) -> dict[str, Any] | None:
    """
    Export a single notebook with all its associated data.

    Args:
        session: Database session
        notebook_id: ID of the notebook to export

    Returns:
        Notebook configuration dict or None if not found
    """
    try:
        print(f"  [export_notebook] Fetching notebook {notebook_id}...")
        logger.info(f"Exporting notebook: {notebook_id}")

        # Fetch notebook with eager loading of relationships
        result = await session.execute(
            select(Notebook)
            .where(Notebook.id == notebook_id)
            .options(
                selectinload(Notebook.notebook_datasets).selectinload(NotebookDataset.dataset),
                selectinload(Notebook.dashboards),
            )
        )
        notebook = result.scalar_one_or_none()

        if not notebook:
            print(f"  [export_notebook] Notebook not found: {notebook_id}")
            logger.warning(f"Notebook not found: {notebook_id}")
            return None

        print(f"  [export_notebook] Found notebook: {notebook.notebook_name}")

        logger.info(f"  - Notebook name: {notebook.notebook_name}")

        # Fetch datasets for this notebook
        datasets_config = []
        print(f"  [DEBUG] notebook.notebook_datasets = {notebook.notebook_datasets}")
        print(f"  [DEBUG] Number of notebook_datasets: {len(notebook.notebook_datasets)}")

        for nb_dataset in notebook.notebook_datasets:
            dataset = nb_dataset.dataset
            print(f"  [DEBUG] Processing dataset: {dataset.id}, name={dataset.name}")
            logger.info(f"  - Dataset: {dataset.name or 'Unnamed'}")

            # Fetch files for this dataset
            print(f"    [DEBUG] Fetching files for dataset {dataset.id}...")
            files_result = await session.execute(select(File).where(File.dataset_id == dataset.id))
            files = list(files_result.scalars().all())
            print(f"    [DEBUG] Found {len(files)} files for dataset")

            files_config = []
            for file in files:
                logger.info(f"    - File: {file.name}")

                # Check if file has source_url
                if not file.source_url:
                    print(f"      ⚠️ Skipping file '{file.name}' - no source URL (has inline data)")
                    continue

                # File has source_url, export it
                print(f"      ✓ File has source URL: {file.source_url}")
                files_config.append(
                    {
                        "filename": file.name,
                        "source_url": file.source_url,
                    }
                )

            # Skip datasets with no URL-based files
            if not files_config:
                print(f"  ⚠️ Skipping dataset '{dataset.name}' - no files with source URLs")
                continue

            datasets_config.append(
                {
                    "name": dataset.name or "Dataset",
                    "files": files_config,
                }
            )

        # Fetch messages from thread
        threads_result = await session.execute(select(Thread).where(Thread.notebook_id == notebook_id))
        threads = list(threads_result.scalars().all())

        messages_config = []
        if threads:
            # Get messages from first thread
            thread = threads[0]
            messages_result = await session.execute(
                select(Message).where(Message.thread_id == thread.id).order_by(Message.created_at)
            )
            messages = list(messages_result.scalars().all())

            for message in messages:
                messages_config.append(
                    {
                        "role": message.role,
                        "content": message.content,
                    }
                )

            logger.info(f"  - Messages: {len(messages)}")

        # Fetch saved queries
        print(f"  [DEBUG] Fetching queries for notebook {notebook_id}...")
        query_repo = QueryRepository(session)
        queries_result = await query_repo.list(
            filters={"notebook_id": notebook_id},
            limit=1000,  # Large limit to get all
        )
        queries = queries_result
        print(f"  [DEBUG] Found {len(queries)} queries")

        queries_config = []
        for query in queries:
            print(f"    [DEBUG] Processing query: {query.name}")
            queries_config.append(
                {
                    "id": query.id,
                    "name": query.name,
                    "query": query.query,
                    "output_schema": query.output_schema,
                }
            )

        logger.info(f"  - Saved queries: {len(queries)}")
        print(f"  [DEBUG] Queries config: {len(queries_config)} items")

        # Fetch dashboards
        print(f"  [DEBUG] Fetching dashboards, count={len(notebook.dashboards)}")
        dashboards_config = []
        for dashboard in notebook.dashboards:
            print(f"    [DEBUG] Processing dashboard version {dashboard.version_num}")
            dashboards_config.append(
                {
                    "version": dashboard.version_num,
                    "html": dashboard.html_content,
                }
            )

        logger.info(f"  - Dashboards: {len(notebook.dashboards)}")
        print(f"  [DEBUG] Dashboards config: {len(dashboards_config)} items")

        # Skip notebooks with no URL-based datasets
        if not datasets_config:
            print(f"  ⚠️ Skipping notebook '{notebook.notebook_name}' - contains only inline data, cannot use as demo")
            return None

        return {
            "name": notebook.notebook_name,
            "description": notebook.description or "",
            "datasets": datasets_config,
            "messages": messages_config,
            "saved_queries": queries_config,
            "dashboards": dashboards_config,
        }

    except Exception as e:
        print(f"  [export_notebook] ERROR: {e}")
        logger.error(f"Failed to export notebook {notebook_id}: {e}", exc_info=True)
        return None


async def main():
    """Main export function."""
    print(f"DEBUG: NOTEBOOK_IDS = {NOTEBOOK_IDS}")
    if not NOTEBOOK_IDS:
        print("❌ No notebook IDs configured. Edit NOTEBOOK_IDS in the script.")
        return

    print(f"🔄 Starting export of {len(NOTEBOOK_IDS)} notebook(s)...")
    logger.info(f"🔄 Starting export of {len(NOTEBOOK_IDS)} notebook(s)...")

    try:
        # Read current version
        if OUTPUT_FILE.exists():
            with open(OUTPUT_FILE, encoding="utf-8") as f:
                existing_config = json.load(f)
            current_version = existing_config.get("version", 1)
            new_version = current_version + 1
        else:
            new_version = 1
            logger.info("Creating new demo_notebooks.json")

        logger.info(f"📝 New version will be: {new_version}")

        # Export notebooks
        print("DEBUG: Opening AsyncSessionFactory...")
        async with AsyncSessionFactory() as session:
            print("DEBUG: Session opened, exporting notebooks...")
            notebooks_config = []

            for notebook_id in NOTEBOOK_IDS:
                print(f"DEBUG: Exporting notebook {notebook_id}...")
                notebook_config = await export_notebook(session, notebook_id)
                print(f"DEBUG: Got notebook_config type={type(notebook_config)}, is_none={notebook_config is None}")
                if notebook_config:
                    print(f"DEBUG: Appending notebook config with keys: {list(notebook_config.keys())}")
                    notebooks_config.append(notebook_config)
                else:
                    print(f"DEBUG: export_notebook returned None for {notebook_id}")

        print(f"DEBUG: Exported {len(notebooks_config)} notebooks")
        if not notebooks_config:
            print("❌ Failed to export any notebooks")
            logger.error("❌ Failed to export any notebooks")
            return

        print(f"DEBUG: Building output structure with {len(notebooks_config)} notebooks...")
        # Build output structure
        output_config = {
            "version": new_version,
            "notebooks": notebooks_config,
        }

        print(f"DEBUG: Writing to file: {OUTPUT_FILE}")
        # Write to file
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(output_config, f, indent=2, ensure_ascii=False)

        print(f"✅ Successfully exported {len(notebooks_config)} notebook(s)")
        print(f"📄 Config written to: {OUTPUT_FILE}")
        print(f"🔖 Version: {new_version}")

        logger.info(f"✅ Successfully exported {len(notebooks_config)} notebook(s)")
        logger.info(f"📄 Config written to: {OUTPUT_FILE}")
        logger.info(f"🔖 Version: {new_version}")

    except Exception as e:
        print(f"❌ Export failed: {e}")
        import traceback

        traceback.print_exc()
        logger.error(f"❌ Export failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback

        traceback.print_exc()
