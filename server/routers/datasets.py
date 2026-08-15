"""Router for Dataset CRUD operations."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import AuthContext, require_any_scope, require_scope
from server.auth.scopes import Scope
from server.config.storage import dataset_directory
from server.db.session import get_async_session
from server.schemas.datasets import DatasetCreate, DatasetListResponse, DatasetRead, DatasetUpdate
from server.schemas.notebook_datasets import DatasetAssociateRequest, NotebookDatasetRead
from server.schemas.standard_response import success_response
from server.services.dataset import DatasetService
from server.services.dataset_storage import DatasetStorageService
from server.services.file_operations import DataFrameFileService
from server.services.notebook import NotebookService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/datasets", status_code=status.HTTP_201_CREATED)
async def create_dataset_endpoint(
    payload: DatasetCreate,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_CREATE)),
    session: AsyncSession = Depends(get_async_session),
):
    """Create a new dataset (independent from notebooks)."""
    try:
        dataset = await DatasetService.create_dataset(
            session=session,
            type=payload.type,
            connection_id=payload.connection_id,
            notebook_id=payload.notebook_id,
            name=payload.name,
            created_by=auth.user_id,
        )

        response = DatasetRead.model_validate(dataset)
        return success_response(data=response.model_dump(), message=f"Dataset created successfully ({payload.type})")

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating dataset: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create dataset: {str(e)}"
        )


@router.get("/notebooks/{notebook_id}/datasets")
async def get_notebook_datasets_endpoint(
    notebook_id: str,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    """Get all datasets for a notebook."""
    try:
        datasets = await DatasetService.get_datasets_by_notebook(session, notebook_id)

        response_items = []
        for dataset in datasets:
            item = DatasetRead.model_validate(dataset)
            response_items.append(item)

        response = DatasetListResponse(items=response_items, total=len(response_items))
        return success_response(data=response.model_dump(), message=f"Retrieved {len(response_items)} dataset(s)")

    except Exception as e:
        logger.error(f"Error retrieving datasets: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve datasets: {str(e)}"
        )


@router.get("/datasets/{dataset_id}")
async def get_dataset_endpoint(
    dataset_id: str,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    """Get dataset with full details."""
    try:
        dataset_dict = await DatasetService.get_dataset_with_details(session, dataset_id)

        if not dataset_dict:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

        return success_response(data=dataset_dict, message="Dataset details retrieved")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving dataset: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve dataset: {str(e)}"
        )


@router.delete("/datasets/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dataset_endpoint(
    dataset_id: str,
    auth: AuthContext = Depends(require_any_scope(Scope.DATASET_DELETE, Scope.DATASET_DELETE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    """Delete a dataset (cascades to files)."""
    try:
        # Get dataset first to check ownership
        dataset = await DatasetService.get_dataset(session, dataset_id)
        if not dataset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

        # If user only has DELETE_OWN scope, verify ownership
        if not auth.has_scope(Scope.DATASET_DELETE):
            if dataset.created_by is None or str(dataset.created_by) != str(auth.user_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can only delete datasets you created",
                )

        deleted = await DatasetService.delete_dataset(session, dataset_id)

        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting dataset: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete dataset: {str(e)}"
        )


@router.get("/datasets/{dataset_id}/files/{file_id}/download")
async def download_file_endpoint(
    dataset_id: str,
    file_id: str,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    """Download file content from database."""
    try:
        dataset = await DatasetService.get_dataset(session, dataset_id)
        if not dataset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

        file = next((f for f in dataset.files if f.id == file_id), None)
        if not file:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found in dataset")

        if file.storage_path:
            base_dir = Path(dataset.storage_path) if dataset.storage_path else dataset_directory(str(dataset.id))
            base_dir = base_dir.resolve()
            file_path = (base_dir / file.storage_path).resolve()

            if not file_path.is_relative_to(base_dir):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file path")
            if not file_path.exists():
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stored file not found on disk")

            iterator = DatasetStorageService.read_in_chunks(file_path)
            response = StreamingResponse(
                iterator,
                media_type="application/octet-stream",
            )
            response.headers["Content-Disposition"] = f'attachment; filename="{file.name}"'
            return response

        if file.content is not None:
            return Response(
                content=file.content,
                media_type="application/octet-stream",
                headers={"Content-Disposition": f'attachment; filename="{file.name}"'},
            )

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File content unavailable")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading file: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to download file: {str(e)}"
        )


@router.get("/datasets/{dataset_id}/schema")
async def get_dataset_schema_endpoint(
    dataset_id: str,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    """Get schema for dataset files."""
    try:
        dataset = await DatasetService.get_dataset(session, dataset_id)
        if not dataset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

        if dataset.type != "file":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Schema endpoint only supports file-type datasets"
            )

        # Get schema from files (use cache if available)
        schema = await DataFrameFileService.get_file_schema_multi(
            dataset.files,
            session=session,
            dataset=dataset,
            use_cache=True,
            save_to_cache=True,
        )

        return success_response(data=schema, message="Dataset schema retrieved")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving dataset schema: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve schema: {str(e)}"
        )


@router.post("/datasets/{dataset_id}/notebooks/{notebook_id}", status_code=status.HTTP_201_CREATED)
async def associate_dataset_with_notebook_endpoint(
    dataset_id: str,
    notebook_id: str,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_CREATE)),
    session: AsyncSession = Depends(get_async_session),
):
    """Associate a dataset with a notebook."""
    try:
        association = await DatasetService.associate_dataset_with_notebook(
            session=session, dataset_id=dataset_id, notebook_id=notebook_id
        )

        return success_response(
            data={
                "id": association.id,
                "dataset_id": association.dataset_id,
                "notebook_id": association.notebook_id,
                "created_at": association.created_at.isoformat(),
            },
            message="Dataset associated with notebook successfully",
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error associating dataset with notebook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to associate dataset: {str(e)}"
        )


@router.put("/datasets/{dataset_id}")
async def update_dataset_endpoint(
    request: Request,
    dataset_id: str,
    auth: AuthContext = Depends(require_any_scope(Scope.DATASET_UPDATE, Scope.DATASET_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
    payload: DatasetUpdate | None = None,
    name: str | None = Form(None),
    files_to_keep: str | None = Form(None),
    new_files: list[UploadFile] | None = File(None),
    is_public: bool | None = Form(None),
):
    """
    Update a file dataset: remove files, update name, and/or add new files.

    Supports both JSON (for name/file removal only - backward compatible) and
    multipart/form-data (when adding files).

    For JSON requests:
        - Send { "name": "...", "files": [...] }

    For multipart requests (with file uploads):
        - name: Optional new dataset name
        - files_to_keep: JSON string array of file IDs to keep
        - new_files: Optional list of new files to add

    Args:
        request: FastAPI request object
        dataset_id: Dataset ID to update
        session: Database session
        payload: JSON payload (for backward compatibility)
        name: Form field for dataset name (multipart only)
        files_to_keep: Form field with JSON array of file IDs (multipart only)
        new_files: File uploads (multipart only)

    Returns:
        Updated dataset details with all files
    """
    try:
        import json

        from server.routers.file_upload import FILE_EXTENSIONS

        # Get dataset first to check ownership
        dataset = await DatasetService.get_dataset(session, dataset_id)
        if not dataset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

        # If user only has UPDATE_OWN scope, verify ownership
        if not auth.has_scope(Scope.DATASET_UPDATE):
            if dataset.created_by is None or str(dataset.created_by) != str(auth.user_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can only update datasets you created",
                )

        content_type = request.headers.get("content-type", "")

        # Determine if this is a JSON or multipart request
        if "application/json" in content_type:
            # JSON request - backward compatible path
            if payload is None:
                payload = DatasetUpdate(**(await request.json()))

            if not payload.files:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Files list is required for update")

            files_to_keep_list = [
                f.get("file_id") or f.get("id") for f in payload.files if f.get("file_id") or f.get("id")
            ]

            await DatasetService.update_dataset_files(
                session=session,
                dataset_id=dataset_id,
                files_to_keep=files_to_keep_list,
                name=payload.name,
                is_public=payload.is_public,
            )

            dataset_details = await DatasetService.get_dataset_with_details(session, dataset_id)

            return success_response(
                data=dataset_details,
                message=f"Dataset updated successfully ({len(files_to_keep_list)} file(s) remaining)",
            )

        elif "multipart/form-data" in content_type:
            # Multipart request - supports file uploads
            if files_to_keep is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="files_to_keep is required for multipart requests"
                )

            # Parse files_to_keep JSON string
            try:
                files_to_keep_list = json.loads(files_to_keep)
                if not isinstance(files_to_keep_list, list):
                    raise ValueError("files_to_keep must be a JSON array")
            except json.JSONDecodeError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid files_to_keep JSON: {str(e)}"
                )

            # Get dataset to determine file type
            dataset = await DatasetService.get_dataset(session, dataset_id)
            if not dataset:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Dataset {dataset_id} not found")

            if dataset.type != "file":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=f"Dataset {dataset_id} is not a file-type dataset"
                )

            # Update existing files (remove files not in keep list, update name)
            await DatasetService.update_dataset_files(
                session=session,
                dataset_id=dataset_id,
                files_to_keep=files_to_keep_list,
                name=name,
                is_public=is_public,
            )

            # Process new file uploads if provided
            new_files_count = 0
            if new_files and len(new_files) > 0:
                # Determine file type from existing files or first new file
                file_type = None
                if dataset.files:
                    file_type = dataset.files[0].type
                else:
                    # If no existing files, try to infer from first new file
                    first_file = new_files[0].filename.lower()
                    for ftype, extensions in FILE_EXTENSIONS.items():
                        if any(first_file.endswith(ext) for ext in extensions):
                            file_type = ftype
                            break

                    if not file_type:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Cannot determine file type from '{new_files[0].filename}'",
                        )

                # Validate and upload each new file
                allowed_extensions = FILE_EXTENSIONS.get(file_type, [])
                for upload_file in new_files:
                    if not upload_file.filename:
                        continue

                    file_lower = upload_file.filename.lower()

                    # Validate extension
                    if not any(file_lower.endswith(ext) for ext in allowed_extensions):
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"File '{upload_file.filename}' is not a valid {file_type.upper()} file. "
                            f"Allowed extensions: {', '.join(allowed_extensions)}",
                        )

                    # Save the file to filesystem
                    storage_metadata = await DatasetStorageService.save_upload(
                        dataset_id=dataset_id,
                        upload=upload_file,
                        desired_name=upload_file.filename,
                    )

                    if storage_metadata.size == 0:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST, detail=f"File '{upload_file.filename}' is empty"
                        )

                    # Create file record in database
                    file_record = await DataFrameFileService.save_file_to_db(
                        session=session,
                        filename=upload_file.filename,
                        dataset_id=dataset_id,
                        file_type=file_type,
                        storage_metadata=storage_metadata,
                        tenant_id=dataset.tenant_id,
                    )

                    # Optimize file if needed (CSV/JSON -> Parquet)
                    optimized_record = await DataFrameFileService.ensure_columnar_artifact(
                        session=session,
                        dataset=dataset,
                        file_record=file_record,
                        storage_metadata=storage_metadata,
                    )
                    if optimized_record is not None:
                        file_record = optimized_record

                    new_files_count += 1
                    logger.info(f"Added new file {upload_file.filename} to dataset {dataset_id}")

            # Refresh schema if new files were added
            schema_refresh_error = None
            if new_files_count > 0:
                try:
                    session.expire_all()
                    await DatasetService.refresh_dataset_schema(session, dataset_id)
                except Exception as e:
                    schema_refresh_error = str(e)
                    logger.warning(f"Failed to refresh schema for dataset {dataset_id}: {e}")

            # Get updated dataset details with schema
            dataset_details = await DatasetService.get_dataset_with_details(session, dataset_id)

            total_files = len(dataset_details["files"]) if dataset_details.get("files") else 0
            message = f"Dataset updated successfully: {total_files} total file(s)"
            if new_files_count > 0:
                message += f" (added {new_files_count} new file(s))"

            if schema_refresh_error:
                message += f" (Warning: Schema refresh failed - {schema_refresh_error})"
                dataset_details["schema_refresh_warning"] = schema_refresh_error

            return success_response(data=dataset_details, message=message)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported content type: {content_type}. Use application/json or multipart/form-data",
            )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating dataset {dataset_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update dataset: {str(e)}"
        )


@router.delete("/datasets/{dataset_id}/notebooks/{notebook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def dissociate_dataset_from_notebook_endpoint(
    dataset_id: str,
    notebook_id: str,
    auth: AuthContext = Depends(require_any_scope(Scope.DATASET_UPDATE, Scope.DATASET_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    """Dissociate a dataset from a notebook."""
    try:
        # Get dataset first to check ownership
        dataset = await DatasetService.get_dataset(session, dataset_id)
        if not dataset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

        # If user only has UPDATE_OWN scope, verify ownership
        if not auth.has_scope(Scope.DATASET_UPDATE):
            if dataset.created_by is None or str(dataset.created_by) != str(auth.user_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can only update datasets you created",
                )

        deleted = await DatasetService.dissociate_dataset_from_notebook(
            session=session, dataset_id=dataset_id, notebook_id=notebook_id
        )

        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Association not found")

        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error dissociating dataset from notebook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to dissociate dataset: {str(e)}"
        )


@router.post("/notebooks/{notebook_id}/datasets/associate", status_code=status.HTTP_201_CREATED)
async def batch_associate_datasets_endpoint(
    notebook_id: str,
    payload: DatasetAssociateRequest,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_CREATE)),
    session: AsyncSession = Depends(get_async_session),
):
    """Batch associate multiple datasets with a notebook."""
    try:
        notebook = await NotebookService.get_notebook(session, notebook_id)
        if notebook is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notebook not found")

        # Validate that dataset_ids is provided
        if not payload.dataset_ids or len(payload.dataset_ids) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="dataset_ids must be provided and non-empty"
            )

        # Get existing associations to avoid duplicates
        existing_datasets = await DatasetService.get_datasets_by_notebook(session, notebook_id)
        existing_dataset_ids = {d.id for d in existing_datasets}

        # Associate each dataset
        created_associations = []
        errors = []

        for dataset_id in payload.dataset_ids:
            try:
                if dataset_id in existing_dataset_ids:
                    errors.append(f"Dataset {dataset_id}: Already associated with this notebook")
                    continue

                # Verify dataset exists
                dataset = await DatasetService.get_dataset(session, dataset_id)
                if not dataset:
                    errors.append(f"Dataset {dataset_id}: Not found")
                    continue

                # Associate dataset with notebook
                association = await DatasetService.associate_dataset_with_notebook(
                    session=session, dataset_id=dataset_id, notebook_id=notebook_id
                )

                created_associations.append(
                    NotebookDatasetRead(
                        id=association.id,
                        notebook_id=association.notebook_id,
                        dataset_id=association.dataset_id,
                        dataset_type=dataset.type,
                        connection_id=dataset.connection_id if dataset.type == "connection" else None,
                        created_at=association.created_at,
                    )
                )

            except Exception as e:
                errors.append(f"Dataset {dataset_id}: Failed to associate - {str(e)}")

        # Return error if no datasets were associated
        if not created_associations:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Failed to associate any datasets", "errors": errors},
            )

        message = f"Successfully associated {len(created_associations)} dataset(s)"
        if errors:
            message += f" with {len(errors)} error(s)"

        return success_response(
            data={
                "associations": [assoc.model_dump() for assoc in created_associations],
                "total_associated": len(created_associations),
                "errors": errors if errors else None,
            },
            message=message,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error batch associating datasets: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to batch associate datasets: {str(e)}"
        )
