from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import AuthContext, require_scope
from server.auth.scopes import Scope
from server.db.session import get_async_session
from server.repositories.learning import LearningRepository
from server.schemas.standard_response import error_response, success_response
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/learnings")
async def list_learnings(
    auth: AuthContext = Depends(require_scope(Scope.USER_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        from server.auth.tenant_context import get_tenant_id

        current_tenant = get_tenant_id()
        logger.info(f"[LEARNING] Listing learnings for tenant_id={current_tenant}")

        repo = LearningRepository(session)
        results = await repo.list_by_tenant(limit=200)

        learnings = [
            {
                "id": str(r.id),
                "title": r.title,
                "learning": r.learning,
                "dataset_id": str(r.dataset_id) if r.dataset_id else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in results
        ]

        logger.info(f"[LEARNING] Found {len(learnings)} learnings for tenant {current_tenant}")
        return success_response(data=learnings, message=f"Found {len(learnings)} learnings")
    except Exception as e:
        logger.error(f"Error listing learnings: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/learnings/{learning_id}")
async def delete_learning(
    learning_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.USER_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        repo = LearningRepository(session)
        deleted = await repo.delete(learning_id)
        if deleted:
            return success_response(data={"id": str(learning_id)}, message="Learning deleted")
        return error_response(error="Not found", message=f"Learning {learning_id} not found", status_code=404)
    except Exception as e:
        logger.error(f"Error deleting learning: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
