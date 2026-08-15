"""
Notebook Import Router

API endpoints for importing notebooks from shared notebook IDs.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import AuthContext, require_scope
from server.auth.scopes import Scope
from server.db.session import get_async_session
from server.schemas.notebook_import import (
    FetchNotebookRequest,
    FetchNotebookResponse,
    ImportNotebookRequest,
    ImportNotebookResponse,
    TestQueryRequest,
    TestQueryResponse,
)
from server.schemas.standard_response import success_response
from server.services.notebook_import_service import NotebookImportService
from server.utils.custom_logger import get_logger
from server.utils.deployment import is_feature_enabled

router = APIRouter()
logger = get_logger(__name__)


def check_import_available():
    """Raise 403 if notebook import is not available."""
    if not is_feature_enabled("notebook_import_enabled"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Import from shared notebooks is not available in this deployment mode",
        )


@router.post("/imports/fetch-notebook")
async def fetch_notebook(
    request: FetchNotebookRequest,
    auth: AuthContext = Depends(require_scope(Scope.NOTEBOOK_CREATE)),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Fetch and validate a shared notebook using its share ID.

    This fetches the notebook JSON from the sharing service and returns
    summary information needed for the import wizard.

    Args:
        request: Contains the share ID (UUID) and optional password

    Returns:
        NotebookExport data and summary statistics
    """
    check_import_available()
    try:
        notebook_export, summary = await NotebookImportService.fetch_from_worker(
            share_id=request.share_id,
            password=request.password,
        )

        return success_response(
            data=FetchNotebookResponse(
                notebook_export=notebook_export,
                summary=summary,
            ).model_dump(),
            message="Notebook fetched successfully",
        )

    except ValueError as e:
        logger.warning(f"Failed to fetch notebook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error fetching notebook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch notebook: {str(e)}",
        )


@router.post("/imports/test-query")
async def test_query(
    request: TestQueryRequest,
    auth: AuthContext = Depends(require_scope(Scope.NOTEBOOK_CREATE)),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Run a test query on an existing connection or dataset to validate compatibility.

    This is used during import to verify that the selected connection or dataset
    can execute the queries from the imported notebook.

    Args:
        request: Connection ID or Dataset ID and query to test

    Returns:
        Success status and any error message
    """
    try:
        # Validate that at least one ID is provided
        if not request.connection_id and not request.dataset_id:
            return success_response(
                data=TestQueryResponse(
                    success=False,
                    error="Either connection_id or dataset_id must be provided",
                ).model_dump(),
                message="Test query failed",
            )

        success, error = await NotebookImportService.test_query(
            session=session,
            connection_id=request.connection_id,
            dataset_id=request.dataset_id,
            query=request.query,
        )

        return success_response(
            data=TestQueryResponse(
                success=success,
                error=error,
            ).model_dump(),
            message="Test query completed" if success else "Test query failed",
        )

    except Exception as e:
        logger.error(f"Error running test query: {str(e)}")
        return success_response(
            data=TestQueryResponse(
                success=False,
                error=str(e),
            ).model_dump(),
            message="Test query failed",
        )


@router.post("/imports/import-notebook")
async def import_notebook(
    request: ImportNotebookRequest,
    auth: AuthContext = Depends(require_scope(Scope.NOTEBOOK_CREATE)),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Import a notebook with mapped dataset connections.

    This creates a new notebook with:
    - Mapped datasets connected to local connections
    - Imported queries associated with the new datasets
    - Restored chat history
    - Restored dashboard versions

    Args:
        request: NotebookExport data and dataset mappings

    Returns:
        New notebook ID and import statistics
    """
    check_import_available()
    try:
        # Validate that at least one dataset is mapped (not skipped)
        # Check for either connection_id (new dataset) or dataset_id (existing dataset)
        active_mappings = [m for m in request.dataset_mappings if not m.skipped and (m.connection_id or m.dataset_id)]
        if not active_mappings and len(request.notebook_export.datasets) > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one dataset must be connected to import the notebook",
            )

        notebook_id, imported = await NotebookImportService.import_notebook(
            session=session,
            notebook_export=request.notebook_export,
            dataset_mappings=request.dataset_mappings,
            user_id=auth.user.id,
        )

        skipped_count = len(request.notebook_export.datasets) - imported.datasets

        return success_response(
            data=ImportNotebookResponse(
                notebook_id=notebook_id,
                imported=imported,
                skipped_datasets=skipped_count,
            ).model_dump(),
            message="Notebook imported successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error importing notebook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to import notebook: {str(e)}",
        )
