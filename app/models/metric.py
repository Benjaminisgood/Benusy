from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


class MetricSource(str, Enum):
    auto = "auto"
    manual = "manual"


class Metric(SQLModel, table=True):
    __tablename__ = "metrics"

    id: Optional[int] = Field(default=None, primary_key=True)
    assignment_id: int = Field(foreign_key="assignments.id", index=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    likes: int = Field(default=0, ge=0)
    favorites: int = Field(default=0, ge=0)
    shares: int = Field(default=0, ge=0)
    views: int = Field(default=0, ge=0)
    source: MetricSource = Field(default=MetricSource.auto, index=True)

    assignment: "Assignment" = Relationship(back_populates="metrics")
