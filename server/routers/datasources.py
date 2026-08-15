"""Router for unified Datasources (Connections + Datasets)."""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from server.auth.dependencies import AuthContext, require_any_scope, require_scope
from server.auth.scopes import Scope
from server.db.session import get_async_session
from server.models.datasets import Dataset
from server.models.source_resources import SourceResource
from server.models.connections import Connection
from server.repositories.connections import ConnectionRepository
from server.repositories.datasource_annotations import DatasourceAnnotationRepository
from server.schemas.datasource_annotations import (
    DatasourceAnnotationCreate,
    DatasourceAnnotationResponse,
    DatasourceAnnotationUpdate,
)
from server.schemas.standard_response import success_response
from server.schemas.source_understanding import (
    SourceAnalyzeRequest,
    SourceSkillReviewRequest,
    SourceToSemanticModelRequest,
    SourceToSemanticModelResponse,
    SourceUnderstandingRead,
)
from server.services.dataset import DatasetService
from server.services.source_analyzers import SourceUnderstandingService
from server.services.query_cache import query_result_cache
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


async def _invalidate_datasource_query_cache(datasource_id: str, session: AsyncSession) -> None:
    """Invalidate query result cache for all queries belonging to a datasource."""
    try:
        from server.models.queries import Query

        stmt = select(Query.id).where(Query.dataset_id == datasource_id)
        result = await session.execute(stmt)
        query_ids = [str(row[0]) for row in result.all()]
        for qid in query_ids:
            await query_result_cache.invalidate_query(qid, session=session)
        if query_ids:
            logger.info(f"Invalidated cache for {len(query_ids)} queries of datasource {datasource_id}")
    except Exception as e:
            logger.warning(f"Failed to invalidate query cache for datasource {datasource_id}: {e}")


async def _assert_datasource_editor(
    *,
    datasource_id: str,
    auth: AuthContext,
    session: AsyncSession,
) -> None:
    if auth.has_scope(Scope.DATASET_UPDATE):
        return
    if not auth.has_scope(Scope.DATASET_UPDATE_OWN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Datasource editor permission required")
    try:
        parsed_id = UUID(str(datasource_id))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Datasource not found")
    connection = await session.get(Connection, parsed_id)
    if connection is not None:
        if connection.tenant_id == auth.tenant_id and connection.created_by == auth.user_id:
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only update datasources you created")
    dataset = await session.get(Dataset, parsed_id)
    if dataset is not None:
        if dataset.tenant_id == auth.tenant_id and dataset.created_by == auth.user_id:
            return
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only update datasources you created")
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Datasource not found")


@router.get("/datasources")
async def list_all_datasources(
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Get all datasets (both connection-type and file-type).

    Returns a unified list of datasets with proper metadata.
    """
    try:
        # Get ALL datasets (both connection and file types) filtered by tenant
        datasets_result = await session.execute(
            select(Dataset)
            .where(Dataset.tenant_id == auth.tenant_id)
            .options(joinedload(Dataset.files), joinedload(Dataset.connection))
        )
        datasets = datasets_result.scalars().unique().all()

        # Build unified response
        datasources = []
        seen_connection_ids: set[str] = set()  # Track seen connections to avoid duplicates

        # Process each dataset
        for dataset in datasets:
            from server.services.file_operations import DataFrameFileService

            if dataset.type == "connection":
                # Connection-type dataset - deduplicate by connection_id
                if dataset.connection and dataset.connection_id not in seen_connection_ids:
                    seen_connection_ids.add(dataset.connection_id)
                    datasources.append(
                        {
                            "id": dataset.id,  # Use dataset ID, not connection ID!
                            "name": dataset.connection.name or "Database Connection",
                            "type": dataset.connection.type,  # postgres, mysql, etc.
                            "source_type": "connection",
                            "connection_id": dataset.connection_id,  # Include for reference
                            "created_by": str(dataset.created_by) if dataset.created_by else None,
                            "created_at": dataset.created_at.isoformat(),
                            "is_public": dataset.connection.is_public,
                        }
                    )
            elif dataset.type == "file":
                # File-type dataset
                dataset_name = dataset.name or "Unnamed Dataset"
                file_type = dataset.files[0].type if dataset.files else "unknown"

                # Include lightweight file metadata (no schema generation)
                files_data = []
                if dataset.files:
                    files_data = [
                        {
                            "id": f.id,
                            "file_id": f.id,
                            "name": f.name,
                            "filename": f.name,
                            "type": f.type,
                            "size": f.size,
                            "uploaded_at": f.uploaded_at.isoformat() if f.uploaded_at else None,
                            "storage_path": f.storage_path,
                            "alias": DataFrameFileService._alias_from_filename(f.name),
                        }
                        for f in dataset.files
                    ]

                datasources.append(
                    {
                        "id": dataset.id,
                        "name": dataset_name,
                        "type": file_type,
                        "db_type": "duckdb",
                        "source_type": "dataset",
                        "files_count": len(dataset.files) if dataset.files else 0,
                        "files": files_data,  # Include file metadata for fast editing
                        "created_by": str(dataset.created_by) if dataset.created_by else None,
                        "created_at": dataset.created_at.isoformat(),
                        "is_public": dataset.is_public,
                    }
                )

        source_resources_result = await session.execute(
            select(SourceResource).where(SourceResource.tenant_id == auth.tenant_id)
        )
        source_resources = source_resources_result.scalars().all()
        for resource in source_resources:
            is_public = resource.visibility == "workspace"
            created_by = str(resource.owner_id) if resource.owner_id else None
            if created_by == str(auth.user_id) or is_public or not created_by:
                datasources.append(
                    {
                        "id": str(resource.id),
                        "name": resource.name,
                        "type": resource.resource_type,
                        "source_type": "source_resource",
                        "source_url": resource.source_url,
                        "status": resource.status,
                        "latest_snapshot_id": str(resource.latest_snapshot_id) if resource.latest_snapshot_id else None,
                        "created_by": created_by,
                        "created_at": resource.created_at.isoformat(),
                        "updated_at": resource.updated_at.isoformat(),
                        "is_public": is_public,
                    }
                )

        filtered_datasources = []
        for datasource in datasources:
            created_by = datasource.get("created_by")
            is_public = datasource.get("is_public", False)

            # User owns the datasource - always show
            if created_by == str(auth.user_id):
                filtered_datasources.append(datasource)
            # User doesn't own it - only show if public
            elif is_public:
                filtered_datasources.append(datasource)
            # Legacy data with no creator - show to everyone
            elif not created_by:
                filtered_datasources.append(datasource)

        filtered_datasources.sort(key=lambda x: x["created_at"], reverse=True)

        return success_response(
            data={"items": filtered_datasources, "total": len(filtered_datasources)},
            message=f"Retrieved {len(filtered_datasources)} datasource(s)",
        )

    except Exception as e:
        logger.error(f"Error retrieving datasources: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve datasources: {str(e)}"
        )


@router.get("/datasources/{datasource_id}/schema")
async def get_datasource_schema(
    datasource_id: str,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Get schema for a datasource by ID (works for both connections and datasets).

    This endpoint auto-detects whether the ID belongs to a database connection
    or a file dataset and returns the appropriate schema.
    """
    try:
        conn_repo = ConnectionRepository(session)
        connection = await conn_repo.get(datasource_id)

        if connection:
            schema_data = None
            if connection.schema_cache:
                try:
                    schema_data = json.loads(connection.schema_cache)
                    if isinstance(schema_data, dict) and "schema" in schema_data:
                        schema_data = schema_data["schema"]
                except json.JSONDecodeError:
                    logger.warning(
                        f"Failed to parse schema_cache for connection {datasource_id}",
                        posthog_context={"function": "get_datasource_schema", "datasource_id": datasource_id},
                    )
                    schema_data = None

            return success_response(
                data={
                    "datasource_type": connection.type,
                    "datasource_name": connection.name or f"Connection {connection.id[:8]}",
                    "schema": schema_data or {},
                },
                message=f"Retrieved schema for {connection.type} connection",
            )

        dataset_details = await DatasetService.get_dataset_with_details(session, datasource_id)

        if dataset_details:
            schema_data = dataset_details.get("schema")

            if not schema_data:
                schema_data = {}

            # If schema_data is already structured correctly, use it directly
            if isinstance(schema_data, dict) and ("datasource_type" in schema_data or "database_type" in schema_data):
                inner_schema = schema_data.get("schema", {})
                if isinstance(inner_schema, dict) and (
                    "database_type" in inner_schema or "datasource_type" in inner_schema
                ):
                    inner_schema = inner_schema.get("schema", {})
                return success_response(
                    data={
                        "datasource_type": schema_data.get("datasource_type")
                        or schema_data.get("database_type", "file"),
                        "datasource_name": schema_data.get("datasource_name")
                        or schema_data.get("database_name", "Unnamed Dataset"),
                        "schema": inner_schema,
                    },
                    message="Retrieved schema for dataset",
                )
            else:
                return success_response(
                    data={"datasource_type": "file", "datasource_name": "Unnamed Dataset", "schema": schema_data},
                    message="Retrieved schema for dataset",
                )

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Datasource with ID {datasource_id} not found"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error in get_datasource_schema: {str(e)}",
            posthog_context={"function": "get_datasource_schema", "datasource_id": datasource_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while retrieving datasource schema",
        )


@router.get("/datasources/{datasource_id}/understanding")
async def get_datasource_understanding(
    datasource_id: str,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        data = await SourceUnderstandingService().get_understanding(
            session=session,
            datasource_id=datasource_id,
            tenant_id=auth.tenant_id,
        )
        response = SourceUnderstandingRead(**data)
        return success_response(data=response.model_dump(mode="json"), message="Retrieved datasource understanding")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except Exception as exc:
        logger.error(
            f"Unexpected error in get_datasource_understanding: {str(exc)}",
            posthog_context={"function": "get_datasource_understanding", "datasource_id": datasource_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while retrieving datasource understanding",
        )


@router.post("/datasources/{datasource_id}/understanding/analyze")
async def analyze_datasource_understanding(
    datasource_id: str,
    payload: SourceAnalyzeRequest,
    auth: AuthContext = Depends(require_any_scope(Scope.DATASET_UPDATE, Scope.DATASET_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        await _assert_datasource_editor(datasource_id=datasource_id, auth=auth, session=session)
        data = await SourceUnderstandingService().analyze_database(
            session=session,
            datasource_id=datasource_id,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            refresh_schema=payload.refresh_schema,
            scope=payload.scope,
        )
        response = SourceUnderstandingRead(**data)
        return success_response(data=response.model_dump(mode="json"), message="Datasource analyzed")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except ConnectionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f"Unexpected error in analyze_datasource_understanding: {str(exc)}",
            posthog_context={"function": "analyze_datasource_understanding", "datasource_id": datasource_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while analyzing datasource understanding",
        )


@router.post("/datasources/{datasource_id}/understanding/candidates/{candidate_id}/review")
async def review_source_skill_candidate(
    datasource_id: str,
    candidate_id: str,
    payload: SourceSkillReviewRequest,
    auth: AuthContext = Depends(require_any_scope(Scope.DATASET_UPDATE, Scope.DATASET_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        await _assert_datasource_editor(datasource_id=datasource_id, auth=auth, session=session)
        data = await SourceUnderstandingService().review_candidate(
            session=session,
            datasource_id=datasource_id,
            candidate_id=candidate_id,
            tenant_id=auth.tenant_id,
            action=payload.action,
            title=payload.title,
            statement=payload.statement,
            structured_payload=payload.structured_payload,
            note=payload.note,
        )
        response = SourceUnderstandingRead(**data)
        return success_response(data=response.model_dump(mode="json"), message="Source Skill candidate reviewed")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f"Unexpected error in review_source_skill_candidate: {str(exc)}",
            posthog_context={"function": "review_source_skill_candidate", "datasource_id": datasource_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while reviewing source candidate",
        )


@router.post("/datasources/{datasource_id}/understanding/semantic-model-draft")
async def create_semantic_model_draft_from_source_understanding(
    datasource_id: str,
    payload: SourceToSemanticModelRequest,
    auth: AuthContext = Depends(require_any_scope(Scope.DATASET_UPDATE, Scope.DATASET_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        await _assert_datasource_editor(datasource_id=datasource_id, auth=auth, session=session)
        data = await SourceUnderstandingService().create_or_update_semantic_model_from_verified(
            session=session,
            datasource_id=datasource_id,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            model_id=payload.model_id,
            name=payload.name,
            domain=payload.domain,
            owner=payload.owner,
            candidate_ids=payload.candidate_ids,
        )
        response = SourceToSemanticModelResponse(**data)
        return success_response(data=response.model_dump(mode="json"), message="Semantic Model draft updated")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            f"Unexpected error in create_semantic_model_draft_from_source_understanding: {str(exc)}",
            posthog_context={
                "function": "create_semantic_model_draft_from_source_understanding",
                "datasource_id": datasource_id,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while updating Semantic Model draft",
        )


@router.post("/datasources/{datasource_id}/refresh-schema")
async def refresh_datasource_schema(
    datasource_id: str,
    auth: AuthContext = Depends(require_any_scope(Scope.DATASET_UPDATE, Scope.DATASET_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Refresh schema cache for a datasource (works for both connections and datasets).

    For database connections, re-fetches schema from the database.
    For file datasets, regenerates schema from files.
    """
    try:
        # Check if it's a connection
        conn_repo = ConnectionRepository(session)
        connection = await conn_repo.get(datasource_id)

        if connection:
            # If user only has UPDATE_OWN scope, verify ownership
            if not auth.has_scope(Scope.DATASET_UPDATE):
                if connection.created_by is None or str(connection.created_by) != str(auth.user_id):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You can only update datasources you created",
                    )
            from server.services.connections import ConnectionService

            try:
                _, schema = await ConnectionService.refresh_connection_schema(datasource_id, session)
                return success_response(
                    data={
                        "datasource_type": connection.type,
                        "datasource_name": connection.name or f"Connection {connection.id[:8]}",
                        "schema": schema.get("schema", schema),
                        "schema_updated_at": connection.schema_updated_at.isoformat()
                        if connection.schema_updated_at
                        else None,
                    },
                    message=f"Schema refreshed successfully for {connection.type} connection",
                )
            except ConnectionError as e:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Failed to connect to database: {str(e)}"
                )

        # Check if it's a dataset
        dataset = await DatasetService.get_dataset(session, datasource_id)

        if dataset:
            # If user only has UPDATE_OWN scope, verify ownership
            if not auth.has_scope(Scope.DATASET_UPDATE):
                if dataset.created_by is None or str(dataset.created_by) != str(auth.user_id):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You can only update datasources you created",
                    )

            if dataset.type != "file":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot refresh schema for dataset type: {dataset.type}. Only file datasets support schema refresh.",
                )

            try:
                _, schema = await DatasetService.refresh_dataset_schema(session, datasource_id)
                return success_response(
                    data={
                        "datasource_type": schema.get("datasource_type", "duckdb"),
                        "datasource_name": dataset.name or f"Dataset {dataset.id[:8]}",
                        "schema": schema.get("schema", {}),
                        "schema_updated_at": dataset.schema_updated_at.isoformat()
                        if dataset.schema_updated_at
                        else None,
                    },
                    message="Schema refreshed successfully for file dataset",
                )
            except ValueError as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Datasource with ID {datasource_id} not found"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error in refresh_datasource_schema: {str(e)}",
            posthog_context={"function": "refresh_datasource_schema", "datasource_id": datasource_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred while refreshing schema: {str(e)}",
        )


@router.patch("/datasources/{datasource_id}/visibility")
async def update_datasource_visibility(
    datasource_id: str,
    is_public: bool,
    auth: AuthContext = Depends(require_any_scope(Scope.DATASET_UPDATE, Scope.DATASET_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Update just the visibility (is_public) of a datasource.

    This is a quick endpoint for toggling visibility without updating other fields.
    Works for both connections and file datasets.
    """
    try:
        # The frontend sends dataset IDs (not connection IDs), so check dataset first
        dataset = await DatasetService.get_dataset(session, datasource_id)
        if dataset:
            # Check ownership if user only has UPDATE_OWN scope
            if not auth.has_scope(Scope.DATASET_UPDATE):
                if dataset.created_by is None or str(dataset.created_by) != str(auth.user_id):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You can only update datasources you created",
                    )

            # For connection-type datasets, update the connection's is_public
            if dataset.type == "connection" and dataset.connection_id:
                conn_repo = ConnectionRepository(session)
                connection = await conn_repo.get(str(dataset.connection_id))
                if connection:
                    connection.is_public = is_public
                    await session.commit()
                    return success_response(
                        data={"id": str(dataset.id), "is_public": is_public},
                        message=f"Datasource visibility updated to {'public' if is_public else 'private'}",
                    )

            # For file-type datasets, update the dataset's is_public
            dataset.is_public = is_public
            await session.commit()
            return success_response(
                data={"id": str(dataset.id), "is_public": is_public},
                message=f"Datasource visibility updated to {'public' if is_public else 'private'}",
            )

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Datasource {datasource_id} not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating datasource visibility: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update visibility: {str(e)}"
        )


# Datasource Annotations Endpoints


@router.get("/datasources/{datasource_id}/annotations")
async def get_datasource_annotations(
    datasource_id: str,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Get all annotations for a specific datasource.

    Returns all table descriptions and column annotations for the given datasource.
    """
    try:
        repo = DatasourceAnnotationRepository(session)
        annotations = await repo.get_all_by_datasource(datasource_id)

        response_data = [DatasourceAnnotationResponse.model_validate(ann) for ann in annotations]

        return success_response(
            data=response_data, message=f"Retrieved {len(annotations)} annotation(s) for datasource"
        )

    except Exception as e:
        logger.error(f"Error fetching annotations for datasource {datasource_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch annotations: {str(e)}"
        )


@router.post("/datasources/{datasource_id}/annotations")
async def create_datasource_annotation(
    datasource_id: str,
    payload: DatasourceAnnotationCreate,
    auth: AuthContext = Depends(require_any_scope(Scope.DATASET_UPDATE, Scope.DATASET_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Create or update an annotation for a datasource.

    Uses upsert logic: if annotation exists, it updates; otherwise creates new.
    """
    try:
        # Check ownership if user only has UPDATE_OWN scope
        if not auth.has_scope(Scope.DATASET_UPDATE):
            # Try to find datasource (could be connection or dataset)
            conn_repo = ConnectionRepository(session)
            connection = await conn_repo.get(datasource_id)
            if connection:
                if connection.created_by is None or str(connection.created_by) != str(auth.user_id):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You can only update datasources you created",
                    )
            else:
                dataset = await DatasetService.get_dataset(session, datasource_id)
                if dataset:
                    if dataset.created_by is None or str(dataset.created_by) != str(auth.user_id):
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="You can only update datasources you created",
                        )

        repo = DatasourceAnnotationRepository(session)

        annotation = await repo.upsert(
            datasource_id=datasource_id,
            table_name=payload.table_name,
            annotation_type=payload.annotation_type,
            content=payload.content,
            column_name=payload.column_name,
        )

        if payload.annotation_type in ("column_redaction", "table_redaction"):
            await _invalidate_datasource_query_cache(datasource_id, session)

        response_data = DatasourceAnnotationResponse.model_validate(annotation)

        return success_response(data=response_data, message="Annotation saved successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating annotation for datasource {datasource_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create annotation: {str(e)}"
        )


@router.put("/datasources/{datasource_id}/annotations/{annotation_id}")
async def update_datasource_annotation(
    datasource_id: str,
    annotation_id: str,
    payload: DatasourceAnnotationUpdate,
    auth: AuthContext = Depends(require_any_scope(Scope.DATASET_UPDATE, Scope.DATASET_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Update an existing annotation by ID.
    """
    try:
        # Check ownership if user only has UPDATE_OWN scope
        if not auth.has_scope(Scope.DATASET_UPDATE):
            conn_repo = ConnectionRepository(session)
            connection = await conn_repo.get(datasource_id)
            if connection:
                if connection.created_by is None or str(connection.created_by) != str(auth.user_id):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You can only update datasources you created",
                    )
            else:
                dataset = await DatasetService.get_dataset(session, datasource_id)
                if dataset:
                    if dataset.created_by is None or str(dataset.created_by) != str(auth.user_id):
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="You can only update datasources you created",
                        )

        repo = DatasourceAnnotationRepository(session)

        annotation = await repo.get(annotation_id)

        if not annotation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Annotation with ID {annotation_id} not found"
            )

        if annotation.datasource_id != datasource_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Annotation does not belong to the specified datasource"
            )

        annotation.content = payload.content
        await session.commit()
        await session.refresh(annotation)

        response_data = DatasourceAnnotationResponse.model_validate(annotation)

        return success_response(data=response_data, message="Annotation updated successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating annotation {annotation_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update annotation: {str(e)}"
        )


@router.delete("/datasources/{datasource_id}/annotations/{annotation_id}")
async def delete_datasource_annotation(
    datasource_id: str,
    annotation_id: str,
    auth: AuthContext = Depends(require_any_scope(Scope.DATASET_UPDATE, Scope.DATASET_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Delete an annotation by ID.
    """
    try:
        # Check ownership if user only has UPDATE_OWN scope
        if not auth.has_scope(Scope.DATASET_UPDATE):
            conn_repo = ConnectionRepository(session)
            connection = await conn_repo.get(datasource_id)
            if connection:
                if connection.created_by is None or str(connection.created_by) != str(auth.user_id):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You can only update datasources you created",
                    )
            else:
                dataset = await DatasetService.get_dataset(session, datasource_id)
                if dataset:
                    if dataset.created_by is None or str(dataset.created_by) != str(auth.user_id):
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="You can only update datasources you created",
                        )

        repo = DatasourceAnnotationRepository(session)

        annotation = await repo.get(annotation_id)

        if not annotation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Annotation with ID {annotation_id} not found"
            )

        if annotation.datasource_id != datasource_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Annotation does not belong to the specified datasource"
            )

        is_redaction = annotation.annotation_type in ("column_redaction", "table_redaction")

        deleted = await repo.delete_by_id(annotation_id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Annotation with ID {annotation_id} not found"
            )

        if is_redaction:
            await _invalidate_datasource_query_cache(datasource_id, session)

        return success_response(data={"id": annotation_id}, message="Annotation deleted successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting annotation {annotation_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete annotation: {str(e)}"
        )


@router.get("/datasources/{datasource_id}/redactions")
async def get_datasource_redactions(
    datasource_id: str,
    auth: AuthContext = Depends(require_scope(Scope.DATASET_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    """Get all column redaction rules for a datasource."""
    try:
        repo = DatasourceAnnotationRepository(session)
        annotations = await repo.get_all_by_datasource(datasource_id)

        redactions = [
            DatasourceAnnotationResponse.model_validate(ann)
            for ann in annotations
            if ann.annotation_type in ("column_redaction", "table_redaction")
        ]

        return success_response(
            data=redactions, message=f"Retrieved {len(redactions)} redaction rule(s) for datasource"
        )

    except Exception as e:
        logger.error(f"Error fetching redactions for datasource {datasource_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch redactions: {str(e)}"
        )


@router.delete("/datasources/{datasource_id}/redactions")
async def delete_datasource_redaction(
    datasource_id: str,
    table_name: str = Query(...),
    column_name: str | None = Query(None),
    auth: AuthContext = Depends(require_any_scope(Scope.DATASET_UPDATE, Scope.DATASET_UPDATE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    """Remove a column or table redaction by table/column name."""
    try:
        if not auth.has_scope(Scope.DATASET_UPDATE):
            conn_repo = ConnectionRepository(session)
            connection = await conn_repo.get(datasource_id)
            if connection:
                if connection.created_by is None or str(connection.created_by) != str(auth.user_id):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You can only update datasources you created",
                    )
            else:
                dataset = await DatasetService.get_dataset(session, datasource_id)
                if dataset:
                    if dataset.created_by is None or str(dataset.created_by) != str(auth.user_id):
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="You can only update datasources you created",
                        )

        annotation_type = "column_redaction" if column_name else "table_redaction"

        repo = DatasourceAnnotationRepository(session)
        annotation = await repo.get_specific_annotation(datasource_id, table_name, annotation_type, column_name)

        if not annotation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No {annotation_type.replace('_', ' ')} found for table '{table_name}'"
                + (f", column '{column_name}'" if column_name else ""),
            )

        await repo.delete_by_id(annotation.id)
        await _invalidate_datasource_query_cache(datasource_id, session)

        return success_response(data={"id": str(annotation.id)}, message="Redaction removed successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing redaction for datasource {datasource_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to remove redaction: {str(e)}"
        )
