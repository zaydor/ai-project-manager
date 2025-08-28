from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, validator


class IntakeRequest(BaseModel):
    summary: str = Field(..., min_length=10, description="User-provided high-level project summary")


class IntakeResponse(BaseModel):
    project_id: int
    clarifying_questions: List[str]


class PlanRequest(BaseModel):
    project_id: int
    answers: Dict[str, str] = Field(..., description="Mapping of question -> user answer")


class TaskModel(BaseModel):
    id: Optional[int] = None
    project_id: Optional[int] = None
    milestone_id: Optional[int] = None
    name: str
    estimate_hours: float = Field(..., gt=0)
    dependencies: List[str] = Field(default_factory=list)


class MilestoneModel(BaseModel):
    id: Optional[int] = None
    project_id: Optional[int] = None
    name: str
    target_date: Optional[datetime] = None


class PlanResponse(BaseModel):
    project_id: int
    milestones: List[MilestoneModel]
    tasks: List[TaskModel]
    total_estimated_hours: float

    @validator("total_estimated_hours", always=True)
    def compute_total(cls, v, values):  # type: ignore[override]
        if v is not None:
            return v
        tasks = values.get("tasks") or []
        return float(sum(t.estimate_hours for t in tasks))


class AvailabilitySlot(BaseModel):
    day: str  # e.g., 'Mon'
    hours: float = Field(..., gt=0)


class SchedulePreviewRequest(BaseModel):
    project_id: int
    tasks: List[TaskModel]
    availability: List[AvailabilitySlot] = Field(
        ..., description="Weekly availability pattern (e.g., [{'day':'Mon','hours':4}])"
    )


class ScheduledTask(BaseModel):
    task_name: str
    start_day_index: int
    end_day_index: int
    allocated_hours: float


class SchedulePreviewResponse(BaseModel):
    project_id: int
    schedule: List[ScheduledTask]
    total_days: int


class ApplyRequest(BaseModel):
    project_id: int
    tasks: List[TaskModel]
    dry_run: bool = True
    confirm: bool = False
    push_todoist: bool = True
    push_calendar: bool = True


class ApplyResponse(BaseModel):
    project_id: int
    actions: List[str]
    dry_run: bool
    confirmed: bool
    external_writes_performed: bool
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
