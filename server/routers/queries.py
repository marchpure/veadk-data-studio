from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import AuthContext, require_any_scope, require_scope
from server.auth.scopes import Scope
from server.db.session import get_async_session
from server.repositories.queries import QueryRepository
from server.schemas.query import (
    BatchExecuteSavedQueriesRequest,
    BatchExecuteSavedQueriesResponse,
    BatchFilterPreflightResponse,
    DeleteAllQueriesResponse,
    DeleteQueryResponse,
    ExecuteQueryRequest,
    ExecuteQueryResponse,
    ExecuteSavedQueryResponse,
    QueryListItem,
    QueryListResponse,
    QueryRead,
    UpdateQueryRequest,
    UpdateQueryResponse,
)
from server.services.query_service import QueryService
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.post("/execute-query", response_model=ExecuteQueryResponse)
async def execute_query(
    request: ExecuteQueryRequest,
    auth: AuthContext = Depends(require_scope(Scope.QUERY_EXECUTE)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        result = await QueryService.execute_and_save_query(
            session=session,
            query=request.query,
            connection_id=request.connection_id,
            notebook_id=request.notebook_id,
            db_type=request.db_type,
            name=request.name,
            created_by=str(auth.user_id) if auth.user_id else None,
        )

        if not result["success"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])

        return ExecuteQueryResponse(
            success=True,
            message=result.get("message"),
            data=result.get("data"),
            generated_schema=result.get("generated_schema"),
            query_id=result.get("query_id"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error in execute_query: {str(e)}",
            posthog_context={
                "function": "execute_query",
                "connection_id": request.connection_id,
                "notebook_id": request.notebook_id,
                "db_type": request.db_type,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while executing the query",
        )


def _dataset_type_to_query_type(dataset_type: str) -> str:
    """Convert dataset type to user-friendly query type."""
    if dataset_type == "skill_api":
        return "skill_api"
    elif dataset_type == "file":
        return "duckdb"
    else:
        return "sql"


@router.get("/queries", response_model=QueryListResponse)
async def list_queries(
    auth: AuthContext = Depends(require_any_scope(Scope.QUERY_READ, Scope.QUERY_READ_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        query_repo = QueryRepository(session)

        # If user only has READ_OWN scope, filter to their own queries
        if not auth.has_scope(Scope.QUERY_READ):
            queries_data = await query_repo.get_all_with_type(created_by=str(auth.user_id))
        else:
            queries_data = await query_repo.get_all_with_type()

        queries = [
            QueryListItem(
                id=query_id,
                name=name,
                query_type=_dataset_type_to_query_type(dataset_type),
                skill_name=skill_name,
            )
            for query_id, name, dataset_type, skill_name in queries_data
        ]

        return QueryListResponse(queries=queries)
    except Exception as e:
        logger.error(f"Unexpected error in list_queries: {str(e)}", posthog_context={"function": "list_queries"})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while listing queries",
        )


@router.get("/queries/{query_id}", response_model=QueryRead)
async def get_query(
    query_id: str,
    auth: AuthContext = Depends(require_any_scope(Scope.QUERY_READ, Scope.QUERY_READ_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        query_repo = QueryRepository(session)
        query = await query_repo.get_with_relations(query_id)

        if query is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Query not found")

        # If user only has READ_OWN scope, verify ownership
        if not auth.has_scope(Scope.QUERY_READ):
            if query.created_by is None or str(query.created_by) != str(auth.user_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can only access queries you created",
                )

        query_type = "sql"
        skill_name = None
        if query.dataset:
            query_type = _dataset_type_to_query_type(query.dataset.type)
            skill_name = query.dataset.skill_name

        return QueryRead(
            id=query.id,
            name=query.name,
            query=query.query,
            output_schema=query.output_schema,
            dataset_id=query.dataset_id,
            notebook_id=query.notebook_id,
            query_type=query_type,
            skill_name=skill_name,
            created_at=query.created_at.isoformat(),
            updated_at=query.updated_at.isoformat(),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error in get_query: {str(e)}", posthog_context={"function": "get_query", "query_id": query_id}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while retrieving the query",
        )


@router.post("/queries/{query_id}/execute", response_model=ExecuteSavedQueryResponse)
async def execute_saved_query(
    query_id: str,
    auth: AuthContext = Depends(require_scope(Scope.QUERY_EXECUTE)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        result = await QueryService.execute_saved_query(
            session=session,
            query_id=query_id,
            viewer_user_id=auth.user_id,
        )

        if not result["success"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])

        return ExecuteSavedQueryResponse(
            success=True,
            message=result.get("message"),
            data=result.get("data"),
            query_name=result.get("query_name"),
            query_id=result.get("query_id"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error in execute_saved_query: {str(e)}",
            posthog_context={"function": "execute_saved_query", "query_id": query_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while executing the saved query",
        )


@router.post("/queries/batch", response_model=BatchExecuteSavedQueriesResponse)
async def execute_batch_saved_queries(
    request: BatchExecuteSavedQueriesRequest,
    auth: AuthContext = Depends(require_scope(Scope.QUERY_EXECUTE)),
    session: AsyncSession = Depends(get_async_session),
):
    """Execute multiple saved queries in parallel and return their results collectively.

    Supports two formats:
    1. Legacy: query_ids - list of query IDs without filters
    2. New: queries_with_filters - list of queries with their associated filters
    """
    try:
        # Validate that we have queries to execute
        if not request.query_ids and not request.queries_with_filters:
            return BatchExecuteSavedQueriesResponse(
                success=True,
                message="No queries to execute",
                data=[],  # Changed from "results" to "data"
                partial_success=False,
                total_queries=0,
                successful_queries=0,
                failed_queries=0,
                total_execution_time_ms=0,
            )

        # Support both legacy query_ids and new queries_with_filters format
        if request.queries_with_filters:
            result = await QueryService.execute_batch_saved_queries(
                session=session,
                queries_with_filters=[q.dict() for q in request.queries_with_filters],
                max_parallel=request.max_parallel,
            )
        else:
            result = await QueryService.execute_batch_saved_queries(
                session=session,
                query_ids=request.query_ids,
                max_parallel=request.max_parallel,
            )

        return BatchExecuteSavedQueriesResponse(**result)
    except Exception as e:
        logger.error(
            f"Unexpected error in execute_batch_saved_queries: {str(e)}",
            posthog_context={
                "function": "execute_batch_saved_queries",
                "query_count": len(request.query_ids or []) + len(request.queries_with_filters or []),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while executing batch queries",
        )


@router.post("/queries/batch/preflight", response_model=BatchFilterPreflightResponse)
async def preflight_batch_saved_query_filters(
    request: BatchExecuteSavedQueriesRequest,
    auth: AuthContext = Depends(require_scope(Scope.QUERY_EXECUTE)),
    session: AsyncSession = Depends(get_async_session),
):
    """Validate/compile batch query filters without executing any database queries."""
    try:
        if not request.query_ids and not request.queries_with_filters:
            return BatchFilterPreflightResponse(
                success=True,
                message="No queries to preflight",
                data=[],
                partial_success=False,
                total_queries=0,
                successful_queries=0,
                failed_queries=0,
            )

        result = await QueryService.preflight_batch_query_filters(
            session=session,
            query_ids=request.query_ids,
            queries_with_filters=[q.model_dump() for q in request.queries_with_filters]
            if request.queries_with_filters
            else None,
        )
        return BatchFilterPreflightResponse(**result)
    except Exception as e:
        logger.error(
            f"Unexpected error in preflight_batch_saved_query_filters: {str(e)}",
            posthog_context={
                "function": "preflight_batch_saved_query_filters",
                "query_count": len(request.query_ids or []) + len(request.queries_with_filters or []),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while preflighting query filters",
        )


@router.put("/queries/{query_id}", response_model=UpdateQueryResponse)
async def update_query(
    query_id: str,
    request: UpdateQueryRequest,
    auth: AuthContext = Depends(require_scope(Scope.QUERY_EXECUTE)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        query_repo = QueryRepository(session)
        query = await query_repo.get(query_id)
        if not query:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Query not found")

        if query.created_by is None or str(query.created_by) != str(auth.user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update queries you created",
            )

        result = await QueryService.update_query(
            session=session,
            query_id=query_id,
            name=request.name,
            query=request.query,
        )

        if not result["success"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])

        return UpdateQueryResponse(
            success=True,
            message=result.get("message"),
            query_id=result.get("query_id"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error in update_query: {str(e)}",
            posthog_context={"function": "update_query", "query_id": query_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while updating the query",
        )


@router.delete("/queries/{query_id}", response_model=DeleteQueryResponse)
async def delete_query(
    query_id: str,
    auth: AuthContext = Depends(require_any_scope(Scope.QUERY_DELETE, Scope.QUERY_DELETE_OWN)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        # Get query first to check ownership
        query_repo = QueryRepository(session)
        query = await query_repo.get(query_id)
        if not query:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Query not found")

        # If user only has DELETE_OWN scope, verify ownership
        if not auth.has_scope(Scope.QUERY_DELETE):
            if query.created_by is None or str(query.created_by) != str(auth.user_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can only delete queries you created",
                )

        result = await QueryService.delete_query(session=session, query_id=query_id)

        if not result["success"]:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])

        return DeleteQueryResponse(success=True, message=result.get("message"))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error in delete_query: {str(e)}",
            posthog_context={"function": "delete_query", "query_id": query_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while deleting the query",
        )


@router.delete("/queries", response_model=DeleteAllQueriesResponse)
async def delete_all_queries(
    auth: AuthContext = Depends(require_scope(Scope.QUERY_DELETE)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        result = await QueryService.delete_all_queries(session=session)

        return DeleteAllQueriesResponse(
            success=True, message=result.get("message"), deleted_count=result.get("deleted_count")
        )
    except Exception as e:
        logger.error(
            f"Unexpected error in delete_all_queries: {str(e)}", posthog_context={"function": "delete_all_queries"}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while deleting all queries",
        )
