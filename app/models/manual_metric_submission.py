from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


class ManualMetricReviewStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class ManualMetricSubmission(SQLModel, table=True):
    __tablename__ = "manual_metric_submissions"

    id: Optional[int] = Field(default=None, primary_key=True)
    assignment_id: int = Field(foreign_key="assignments.id", index=True)
    likes: int = Field(default=0, ge=0)
    favorites: int = Field(default=0, ge=0)
    shares: int = Field(default=0, ge=0)
    views: int = Field(default=0, ge=0)
    note: Optional[str] = None
    review_status: ManualMetricReviewStatus = Field(default=ManualMetricReviewStatus.pending, index=True)
    review_reason: Optional[str] = None
    submitted_at: datetime = Field(default_factory=datetime.utcnow)
    reviewed_at: Optional[datetime] = None

    assignment: "Assignment" = Relationship(back_populates="manual_metric_submissions")
