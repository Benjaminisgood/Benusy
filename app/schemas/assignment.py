from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel

from app.models import (
    AssignmentStatus,
    ManualMetricReviewStatus,
    MetricSyncStatus,
)
from app.schemas.metric import MetricRead
from app.schemas.task import TaskRead


class ManualMetricSubmit(SQLModel):
    likes: int = Field(default=0, ge=0)
    comments: int = Field(default=0, ge=0)
    shares: int = Field(default=0, ge=0)
    views: int = Field(default=0, ge=0)
    note: Optional[str] = None


class ManualMetricReview(SQLModel):
    approved: bool
    review_reason: Optional[str] = None


class ManualMetricSubmissionRead(SQLModel):
    id: int
    likes: int
    comments: int
    shares: int
    views: int
    note: Optional[str] = None
    review_status: ManualMetricReviewStatus
    review_reason: Optional[str] = None
    submitted_at: datetime
    reviewed_at: Optional[datetime] = None


class AssignmentSubmit(SQLModel):
    post_link: str


class AssignmentReject(SQLModel):
    reason: str


class AssignmentRead(SQLModel):
    id: int
    status: AssignmentStatus
    post_link: Optional[str] = None
    reject_reason: Optional[str] = None
    metric_sync_status: MetricSyncStatus
    last_sync_error: Optional[str] = None
    revenue: float
    created_at: datetime
    updated_at: datetime
    last_synced_at: Optional[datetime] = None
    task: TaskRead
    metrics: list[MetricRead] = Field(default_factory=list)
    manual_metric_submissions: list[ManualMetricSubmissionRead] = Field(default_factory=list)
