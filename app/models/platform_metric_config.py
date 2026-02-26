from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class PlatformMetricConfig(SQLModel, table=True):
    __tablename__ = "platform_metric_configs"

    id: Optional[int] = Field(default=None, primary_key=True)
    platform: str = Field(index=True, sa_column_kwargs={"unique": True})
    platform_coef: float = Field(default=1.0, gt=0)
    like_weight: float = Field(default=1.0, ge=0)
    favorite_weight: float = Field(default=2.0, ge=0)
    share_weight: float = Field(default=3.0, ge=0)
    view_weight: float = Field(default=0.01, ge=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
