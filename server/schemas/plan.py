from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class PlanStepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PlanStep(BaseModel):
    id: str
    name: str
    description: str | None = None
    status: PlanStepStatus = PlanStepStatus.PENDING


class Plan(BaseModel):
    plan_id: str
    notebook_id: str
    steps: list[PlanStep]
    created_at: str
    approved: bool = False
