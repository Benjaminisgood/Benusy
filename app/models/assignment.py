from datetime import datetime
from enum import Enum
from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel


class AssignmentStatus(str, Enum):
    accepted = "accepted"
    submitted = "submitted"
    in_review = "in_review"
    rejected = "rejected"
    completed = "completed"
    cancelled = "cancelled"


class MetricSyncStatus(str, Enum):
    normal = "normal"
    manual_required = "manual_required"
    manual_pending_review = "manual_pending_review"
    manual_approved = "manual_approved"
    manual_rejected = "manual_rejected"


class Assignment(SQLModel, table=True):
    __tablename__ = "assignments"

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="tasks.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    status: AssignmentStatus = Field(default=AssignmentStatus.accepted, index=True)
    post_link: Optional[str] = None
    reject_reason: Optional[str] = None
    metric_sync_status: MetricSyncStatus = Field(default=MetricSyncStatus.normal, index=True)
    last_sync_error: Optional[str] = None
    revenue: float = Field(default=0.0, ge=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_synced_at: Optional[datetime] = None

    task: "Task" = Relationship(back_populates="assignments")
    user: "User" = Relationship(back_populates="assignments")
    metrics: List["Metric"] = Relationship(back_populates="assignment")
    manual_metric_submissions: List["ManualMetricSubmission"] = Relationship(back_populates="assignment")
