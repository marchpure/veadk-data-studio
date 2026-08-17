"""
Tenant context middleware for automatic tenant isolation.

This middleware extracts the tenant_id from the X-Tenant-ID header and stores it
in a context variable that can be accessed throughout the request lifecycle.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import UUID

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

# ContextVar for storing tenant_id per request
# This is thread-safe and works with async
tenant_context: ContextVar[UUID | None] = ContextVar("tenant_id", default=None)


def get_tenant_id() -> UUID | None:
    """Get the current tenant_id from context."""
    return tenant_context.get()


def set_tenant_id(tenant_id: UUID | None) -> None:
    """Set the tenant_id in context."""
    tenant_context.set(tenant_id)


@contextmanager
def tenant_id_context(tenant_id: UUID | None) -> Iterator[None]:
    """Temporarily use an explicit tenant for context-aware repository calls."""
    token = tenant_context.set(tenant_id)
    try:
        yield
    finally:
        tenant_context.reset(token)


class TenantContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware that extracts X-Tenant-ID header and stores in context.

    This allows repositories and services to automatically access tenant_id
    without explicitly passing it as a parameter.
    """

    async def dispatch(self, request: Request, call_next):
        # Extract tenant_id from header
        tenant_id_header = request.headers.get("X-Tenant-ID")

        tenant_id = None
        if tenant_id_header:
            try:
                tenant_id = UUID(tenant_id_header)
            except ValueError:
                logger.warning(f"Invalid X-Tenant-ID header: {tenant_id_header}")

        # Set in context for this request
        token = tenant_context.set(tenant_id)

        try:
            response = await call_next(request)
            return response
        finally:
            # Reset context after request
            tenant_context.reset(token)
