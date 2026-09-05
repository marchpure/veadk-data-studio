from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from server.db.session import get_async_session
from server.services.delegation_broker import resolve

router = APIRouter(prefix="/internal/delegations", tags=["internal-delegations"])


class DelegationResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intended_audience: str = Field(min_length=1, max_length=255)
    tenant_id: str = Field(min_length=36, max_length=36)
    request_id: str = Field(min_length=1, max_length=160)


@router.post("/{opaque_ref}:resolve")
async def resolve_delegation_route(
    request: Request,
    opaque_ref: str,
    body: DelegationResolveRequest,
    session: AsyncSession = Depends(get_async_session),
):
    return await resolve(request, opaque_ref, body.model_dump(), session)
