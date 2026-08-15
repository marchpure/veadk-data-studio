from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class StandardResponse(BaseModel, Generic[T]):
    success: bool = Field(..., description="Indicates if the request was successful")
    message: str = Field(..., description="Human-readable message about the operation")
    data: T | None = Field(None, description="The response data")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Operation completed successfully",
                "data": {"id": "123", "name": "Example"},
            }
        }


def success_response(
    data: Any = None,
    message: str = "Operation completed successfully",
) -> dict[str, Any]:
    return {"success": True, "message": message, "data": data}


def error_response(
    message: str = "An error occurred",
    data: Any = None,
) -> dict[str, Any]:
    return {"success": False, "message": message, "data": data}
