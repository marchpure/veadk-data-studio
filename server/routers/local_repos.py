from __future__ import annotations

import asyncio
import os
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth.dependencies import AuthContext, require_scope
from server.auth.scopes import Scope
from server.db.session import get_async_session
from server.repositories.github_repository import GitHubRepoRepository
from server.schemas.github import AnalysisRequest, AnalysisStatusResponse, GitHubRepoResponse, LocalRepoConnect
from server.schemas.standard_response import error_response, success_response
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

router = APIRouter()

active_local_analysis_tasks: dict[str, asyncio.Task] = {}


@router.post("/local-repos/connect")
async def connect_local_repo(
    body: LocalRepoConnect,
    auth: AuthContext = Depends(require_scope(Scope.USER_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    path = os.path.realpath(body.path)
    if not os.path.isdir(path):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Directory does not exist")

    repo_repo = GitHubRepoRepository(session)
    existing = await repo_repo.get_by_local_path(auth.tenant_id, path)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Directory already connected")

    name = body.name or os.path.basename(path)
    repo = await repo_repo.create(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        repo_full_name=f"local/{name}",
        default_branch="",
        source="local",
        local_path=path,
    )
    return success_response(
        data=GitHubRepoResponse.model_validate(repo).model_dump(mode="json"),
        message="Local repository connected",
    )


@router.get("/local-repos/connected")
async def list_connected_local_repos(
    auth: AuthContext = Depends(require_scope(Scope.USER_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    repo_repo = GitHubRepoRepository(session)
    repos = await repo_repo.list_by_user_and_source(auth.tenant_id, auth.user_id, "local")
    return success_response(data=[GitHubRepoResponse.model_validate(r).model_dump(mode="json") for r in repos])


@router.delete("/local-repos/{repo_id}")
async def delete_local_repo(
    repo_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.USER_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    repo_repo = GitHubRepoRepository(session)
    repo = await repo_repo.get(repo_id, auth.tenant_id)
    if not repo or repo.source != "local":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Local repository not found")

    repo_id_str = str(repo_id)
    task = active_local_analysis_tasks.pop(repo_id_str, None)
    if task and not task.done():
        task.cancel()

    deleted = await repo_repo.delete(repo_id, auth.tenant_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Local repository not found")
    return success_response(message="Local repository disconnected")


@router.post("/local-repos/{repo_id}/analyze")
async def analyze_local_repo(
    repo_id: UUID,
    body: AnalysisRequest,
    auth: AuthContext = Depends(require_scope(Scope.USER_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    repo_repo = GitHubRepoRepository(session)
    repo = await repo_repo.get(repo_id, auth.tenant_id)
    if not repo or repo.source != "local":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Local repository not found")

    if not repo.local_path or not os.path.isdir(repo.local_path):
        return error_response(message="Local directory no longer exists")

    from server.services.repo_analysis_service import analyze_local_repository

    repo_id_str = str(repo_id)
    existing = active_local_analysis_tasks.get(repo_id_str)
    if existing and not existing.done():
        existing.cancel()

    task = asyncio.create_task(
        analyze_local_repository(
            repo_id=repo_id,
            tenant_id=auth.tenant_id,
            user_id=auth.user_id,
            llm_connection_id=body.llm_connection_id,
            local_path=repo.local_path,
            repo_name=repo.repo_full_name,
        )
    )
    active_local_analysis_tasks[repo_id_str] = task
    task.add_done_callback(lambda _: active_local_analysis_tasks.pop(repo_id_str, None))

    return success_response(data={"status": "analyzing"}, message="Analysis started")


@router.post("/local-repos/{repo_id}/analyze/cancel")
async def cancel_local_analysis(
    repo_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.USER_UPDATE)),
    session: AsyncSession = Depends(get_async_session),
):
    repo_id_str = str(repo_id)
    task = active_local_analysis_tasks.pop(repo_id_str, None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    repo_repo = GitHubRepoRepository(session)
    await repo_repo.update_analysis_status(repo_id, "cancelled")
    return success_response(message="Analysis cancelled")


@router.get("/local-repos/{repo_id}/status")
async def get_local_analysis_status(
    repo_id: UUID,
    auth: AuthContext = Depends(require_scope(Scope.USER_READ)),
    session: AsyncSession = Depends(get_async_session),
):
    repo_repo = GitHubRepoRepository(session)
    repo = await repo_repo.get(repo_id, auth.tenant_id)
    if not repo or repo.source != "local":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Local repository not found")

    from server.services.repo_analysis_service import get_analysis_progress

    progress = get_analysis_progress(str(repo_id))
    return success_response(
        data=AnalysisStatusResponse(
            status=repo.analysis_status,
            error=repo.analysis_error,
            progress_message=progress.message if progress else None,
            files_analyzed=progress.files_analyzed if progress else None,
            total_files=progress.total_files if progress else None,
        ).model_dump()
    )
