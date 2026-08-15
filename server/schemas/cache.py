from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CacheRefreshResponse(BaseModel):
    success: bool
    invalidated_count: int
    message: str | None = None


class DashboardCacheStatusResponse(BaseModel):
    dashboard_id: str
    last_refreshed_at: datetime | None
    refreshed_by: str | None
    query_count: int | None
    is_stale: bool


class DashboardRefreshResponse(BaseModel):
    success: bool
    refreshed_queries: int
    failed_queries: int
    total_queries: int
    refreshed_at: str


class CacheStatsResponse(BaseModel):
    available: bool
    total_keys: int | None = None
    memory_usage_bytes: int | None = None
    memory_usage_human: str | None = None
    in_memory_keys: int | None = None
    message: str | None = None
    backend: str | None = None
    error: str | None = None


class SharedDashboardsRefreshResponse(BaseModel):
    success: bool
    message: str
    refreshed: int | None = None
    failed: int | None = None
    total: int | None = None
