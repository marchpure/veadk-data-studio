"""Router for file upload backed by filesystem storage and DuckDB analysis."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import AuthContext, require_scope
from server.auth.scopes import Scope
from server.db.session import get_async_session
from server.models.files import File as FileModel
from server.schemas.standard_response import success_response
from server.services.dataset import DatasetService
from server.services.dataset_storage import DatasetStorageService
from server.services.file_operations import DataFrameFileService
from server.services.url_download_service import URLDownloadService

logger = logging.getLogger(__name__)

router = APIRouter()

# Supported file extensions by type
FILE_EXTENSIONS = {"csv": [".csv"], "excel": [".xlsx", ".xls"], "parquet": [".parquet"], "json": [".json"]}


@router.post("/datasets/upload-files", status_code=status.HTTP_201_CREATED)
async def upload_files_to_dataset(
    files: list[UploadFile] = File(...),
    notebook_id: str | None = Form(None),
    name: str = Form(...),
    file_type: str = Form("csv"),
    aliases: str | None = Form(None),
    auth: AuthContext = Depends(require_scope(Scope.DATASET_CREATE)),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Upload multiple files and create a dataset with database storage.

    Args:
        files: List of files to upload
        notebook_id: Optional notebook ID to associate dataset with immediately
        name: Dataset name
        file_type: File type - csv, excel, parquet, or json
        auth: Authenticated user context
        session: Database session

    Returns:
        Dataset details with file information and schema
    """
    try:
        tenant_id = auth.tenant_id

        file_type = file_type.lower()
        if file_type not in FILE_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type: {file_type}. Must be one of: csv, excel, parquet, json",
            )

        if not files or len(files) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No files provided. Please upload at least one {file_type.upper()} file.",
            )

        allowed_extensions = FILE_EXTENSIONS[file_type]

        for upload in files:
            filename = upload.filename or ""
            file_lower = filename.lower()
            if not filename or not any(file_lower.endswith(ext) for ext in allowed_extensions):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File '{filename}' is not a valid {file_type.upper()} file. Allowed: {', '.join(allowed_extensions)}",
                )

        alias_values: dict[str, str] = {}
        if aliases:
            provided_aliases = [alias.strip() for alias in aliases.split(",")]
            for upload, alias in zip(files, provided_aliases, strict=False):
                if alias:
                    alias_values[upload.filename] = alias

        dataset = await DatasetService.create_dataset(
            session=session,
            type="file",
            notebook_id=notebook_id,
            name=name,
            tenant_id=tenant_id,
            created_by=auth.user_id,
        )

        log_msg = f"Created dataset {dataset.id}"
        if notebook_id:
            log_msg += f" and associated with notebook {notebook_id}"
        logger.info(log_msg)

        uploaded_files = []
        total_size = 0

        try:
            for file in files:
                storage_metadata = None
                try:
                    storage_metadata = await DatasetStorageService.save_upload(
                        dataset_id=dataset.id,
                        upload=file,
                        desired_name=file.filename,
                    )

                    if storage_metadata.size == 0:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"File '{file.filename}' is empty. Please upload a valid file.",
                        )

                    display_name = alias_values.get(file.filename, file.filename or storage_metadata.stored_filename)

                    file_record = await DataFrameFileService.save_file_to_db(
                        session=session,
                        filename=display_name,
                        dataset_id=dataset.id,
                        file_type=file_type,
                        storage_metadata=storage_metadata,
                        tenant_id=tenant_id,
                    )

                    optimized_record = await DataFrameFileService.ensure_columnar_artifact(
                        session=session,
                        dataset=dataset,
                        file_record=file_record,
                        storage_metadata=storage_metadata,
                    )
                    if optimized_record is not None:
                        file_record = optimized_record

                    total_size += storage_metadata.size
                    uploaded_files.append(file_record)
                    logger.info(
                        "Stored file %s for dataset %s to %s (%s bytes)",
                        display_name,
                        dataset.id,
                        storage_metadata.relative_path,
                        storage_metadata.size,
                    )
                except HTTPException as http_exc:
                    if storage_metadata:
                        await DatasetStorageService.delete_file(dataset.id, storage_metadata.relative_path)
                    raise http_exc
                except Exception as file_error:
                    if storage_metadata:
                        await DatasetStorageService.delete_file(dataset.id, storage_metadata.relative_path)
                    logger.exception(
                        "Unexpected error while storing file %s for dataset %s",
                        file.filename,
                        dataset.id,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Failed to store file '{file.filename}': {file_error}",
                    ) from file_error
                finally:
                    try:
                        await file.close()
                    except Exception:
                        pass
        except HTTPException:
            await DatasetService.delete_dataset(session, dataset.id)
            raise
        except Exception as exc:
            await DatasetService.delete_dataset(session, dataset.id)
            logger.exception("Failed to ingest dataset %s", dataset.id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload files: {exc}",
            ) from exc

        if not uploaded_files:
            await DatasetService.delete_dataset(session, dataset.id)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files were uploaded successfully.")

        schema = await DataFrameFileService.get_file_schema_multi(
            uploaded_files,
            session=session,
            dataset=dataset,
            use_cache=False,
            save_to_cache=True,
        )

        response_files = [
            {
                "id": f.id,
                "filename": f.name,
                "size": f.size,
                "uploaded_at": f.uploaded_at.isoformat(),
                "storage_path": f.storage_path,
                "checksum": f.checksum,
            }
            for f in uploaded_files
        ]

        response_data = {
            "dataset_id": dataset.id,
            "type": "file",
            "db_type": "duckdb",
            "files_count": len(uploaded_files),
            "file_type": file_type,
            "files": response_files,
            "schema": schema,
            "total_size": total_size,
        }

        if notebook_id:
            response_data["notebook_id"] = notebook_id

        return success_response(
            data=response_data,
            message=f"Successfully uploaded {len(uploaded_files)} {file_type.upper()} file(s) to database",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading files: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to upload files: {str(e)}"
        )


@router.post("/datasets/upload-from-url", status_code=status.HTTP_201_CREATED)
async def upload_from_url(
    urls: list[str] = Form(...),
    notebook_id: str | None = Form(None),
    name: str = Form(...),
    file_type: str | None = Form(None),
    auth: AuthContext = Depends(require_scope(Scope.DATASET_CREATE)),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Create dataset from file URLs with auto file type detection.

    Args:
        urls: List of public URLs to download files from
        notebook_id: Optional notebook ID to associate dataset with
        name: Dataset name
        file_type: Optional file type - csv, excel, parquet, or json.
                  If not provided, type will be auto-detected from downloaded files.
        auth: Authenticated user context
        session: Database session

    Returns:
        Dataset details with file information
    """
    try:
        tenant_id = auth.tenant_id

        if file_type:
            file_type = file_type.lower()
            if file_type not in FILE_EXTENSIONS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unsupported file type: {file_type}. Must be one of: csv, excel, parquet, json",
                )

        if not urls or len(urls) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="No URLs provided. Please provide at least one URL."
            )

        # Create dataset first
        dataset = await DatasetService.create_dataset(
            session=session,
            type="file",
            notebook_id=notebook_id,
            name=name,
            tenant_id=tenant_id,
            created_by=auth.user_id,
        )

        log_msg = f"Created dataset {dataset.id} for URL-based upload"
        if notebook_id:
            log_msg += f" and associated with notebook {notebook_id}"
        logger.info(log_msg)

        # Download and save each file
        uploaded_files = []
        total_size = 0
        detected_file_type = file_type

        try:
            for idx, url in enumerate(urls):
                try:
                    logger.info(f"Downloading file {idx + 1}/{len(urls)} from URL: {url}")

                    file_content, filename = await URLDownloadService.download_file_from_url(
                        url=url, expected_file_type=file_type
                    )

                    # Check if downloaded file is a ZIP archive
                    if filename.lower().endswith(".zip"):
                        logger.info(f"Detected ZIP file: {filename}. Extracting contents...")

                        # Extract all files from ZIP
                        extracted_files = URLDownloadService.extract_zip_files(
                            zip_content=file_content, expected_file_type=file_type
                        )

                        # Save each extracted file to filesystem
                        for extracted_content, extracted_filename in extracted_files:
                            if not detected_file_type:
                                file_type_detected = URLDownloadService.detect_file_type(extracted_filename)
                                if not file_type_detected:
                                    raise ValueError(f"Unable to detect file type from filename: {extracted_filename}")

                                if detected_file_type is None:
                                    detected_file_type = file_type_detected
                                    logger.info(f"Auto-detected file type: {detected_file_type}")
                                elif detected_file_type != file_type_detected:
                                    raise ValueError(
                                        f"Mixed file types detected: expected {detected_file_type}, "
                                        f"but found {file_type_detected} for file {extracted_filename}. "
                                        f"All files must be of the same type."
                                    )

                            storage_metadata = await DatasetStorageService.save_bytes(
                                dataset_id=dataset.id,
                                filename=extracted_filename,
                                data=extracted_content,
                            )

                            file_record = FileModel(
                                name=extracted_filename,
                                type=detected_file_type,
                                size=storage_metadata.size,
                                dataset_id=dataset.id,
                                storage_path=str(storage_metadata.relative_path),
                                checksum=storage_metadata.checksum,
                                source_url=url,
                                tenant_id=tenant_id,
                            )
                            session.add(file_record)
                            await session.flush()

                            uploaded_files.append(file_record)
                            total_size += storage_metadata.size
                            logger.info(
                                f"Saved extracted file: {extracted_filename} ({storage_metadata.size / (1024 * 1024):.2f} MB)"
                            )

                        logger.info(f"Successfully extracted and saved {len(extracted_files)} file(s) from ZIP")

                    else:
                        if not detected_file_type:
                            file_type_detected = URLDownloadService.detect_file_type(filename)
                            if not file_type_detected:
                                raise ValueError(f"Unable to detect file type from filename: {filename}")

                            if detected_file_type is None:
                                detected_file_type = file_type_detected
                                logger.info(f"Auto-detected file type: {detected_file_type}")
                            elif detected_file_type != file_type_detected:
                                raise ValueError(
                                    f"Mixed file types detected: expected {detected_file_type}, "
                                    f"but found {file_type_detected} for file {filename}. "
                                    f"All files must be of the same type."
                                )

                        storage_metadata = await DatasetStorageService.save_bytes(
                            dataset_id=dataset.id,
                            filename=filename,
                            data=file_content,
                        )

                        file_record = FileModel(
                            name=filename,
                            type=detected_file_type,
                            size=storage_metadata.size,
                            dataset_id=dataset.id,
                            storage_path=str(storage_metadata.relative_path),
                            checksum=storage_metadata.checksum,
                            source_url=url,
                            tenant_id=tenant_id,
                        )
                        session.add(file_record)
                        await session.flush()

                        uploaded_files.append(file_record)
                        total_size += storage_metadata.size
                        logger.info(
                            f"Saved file from URL {url}: {filename} ({storage_metadata.size / (1024 * 1024):.2f} MB)"
                        )

                except ValueError as e:
                    logger.error(f"Error downloading from URL {url}: {str(e)}")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to download from URL '{url}': {str(e)}"
                    )
                except Exception as e:
                    logger.exception(f"Unexpected error processing URL {url}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Failed to process URL '{url}': {str(e)}",
                    )

            await session.commit()

        except HTTPException:
            # Clean up dataset if any error occurred
            await DatasetService.delete_dataset(session, dataset.id)
            raise
        except Exception as exc:
            # Clean up dataset on unexpected errors
            await DatasetService.delete_dataset(session, dataset.id)
            logger.exception("Failed to create dataset from URLs")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create dataset from URLs: {exc}"
            ) from exc

        if not uploaded_files:
            await DatasetService.delete_dataset(session, dataset.id)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files were uploaded successfully.")

        if not detected_file_type:
            await DatasetService.delete_dataset(session, dataset.id)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unable to detect file type from downloaded files. Please ensure URLs point to valid data files.",
            )

        # Get schema for uploaded files
        schema = await DataFrameFileService.get_file_schema_multi(
            uploaded_files,
            session=session,
            dataset=dataset,
            use_cache=False,
            save_to_cache=True,
        )

        response_files = [
            {
                "id": f.id,
                "filename": f.name,
                "size": f.size,
                "uploaded_at": f.uploaded_at.isoformat(),
                "storage_path": f.storage_path,
                "checksum": f.checksum,
            }
            for f in uploaded_files
        ]

        response_data = {
            "dataset_id": dataset.id,
            "type": "file",
            "db_type": "duckdb",
            "files_count": len(uploaded_files),
            "file_type": detected_file_type,
            "files": response_files,
            "schema": schema,
            "total_size": total_size,
        }

        if notebook_id:
            response_data["notebook_id"] = notebook_id

        return success_response(
            data=response_data,
            message=f"Successfully downloaded and saved {len(uploaded_files)} {detected_file_type.upper()} file(s) from URL(s)",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating dataset from URLs: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create dataset from URLs: {str(e)}"
        )


@router.get("/datasets/{dataset_id}/preview")
async def get_dataset_preview(
    dataset_id: str,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Get preview data from dataset files (first 10 rows from each file).

    Args:
        dataset_id: Dataset ID
        session: Database session

    Returns:
        Preview data with columns and rows
    """
    try:
        dataset = await DatasetService.get_dataset(session, dataset_id)

        if not dataset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

        if dataset.type != "file":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Preview only supported for file datasets"
            )

        if not dataset.files:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No files found in dataset")

        first_file = dataset.files[0]

        file_path = await DataFrameFileService._ensure_file_materialized(session, dataset, first_file)

        schema = await DataFrameFileService.get_file_schema(
            None,
            first_file.name,
            first_file.type,
            file_path=file_path,
        )

        return success_response(
            data={
                "filename": schema["filename"],
                "columns": [col["name"] for col in schema["columns"]],
                "data": schema["sample_data"],
                "total_rows": schema["row_count"],
                "preview_rows": len(schema["sample_data"]),
            },
            message=f"Retrieved preview for {schema['filename']}",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting dataset preview: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get preview: {str(e)}"
        )
