from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class ErrorSeverity(str, Enum):
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ErrorCategory(str, Enum):
    SYNTAX = "syntax"
    CONNECTION = "connection"
    PERMISSION = "permission"
    TIMEOUT = "timeout"
    RESOURCE = "resource"
    VALIDATION = "validation"
    UNKNOWN = "unknown"


class RawQueryRequest(BaseModel):
    db_type: str
    query: str
    notebook_id: str | UUID | None = None
    connection_id: str | UUID | None = None
    limit: int = 500


class ErrorDetail(BaseModel):
    message: str
    category: ErrorCategory
    severity: ErrorSeverity
    original_query: str
    error_code: str | None = None
    position: dict[str, int] | None = None
    suggestions: list[str] | None = None
    stack_trace: str | None = None
    context: dict[str, Any] | None = None


class RawQueryResponse(BaseModel):
    success: bool
    result: dict[str, Any] | list[Any] | None = None
    error: str | None = None
    error_detail: ErrorDetail | None = None
    total_count: int | None = None
    returned_count: int | None = None
    limited: bool | None = None
