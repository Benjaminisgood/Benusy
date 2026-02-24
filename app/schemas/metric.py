from datetime import datetime

from sqlmodel import SQLModel

from app.models import MetricSource


class MetricRead(SQLModel):
    id: int
    timestamp: datetime
    likes: int
    comments: int
    shares: int
    views: int
    source: MetricSource
