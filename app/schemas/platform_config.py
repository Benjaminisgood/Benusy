from datetime import datetime

from sqlmodel import Field, SQLModel


class PlatformMetricConfigUpsert(SQLModel):
    platform_coef: float = Field(default=1.0, gt=0)
    like_weight: float = Field(default=1.0, ge=0)
    comment_weight: float = Field(default=2.0, ge=0)
    share_weight: float = Field(default=3.0, ge=0)
    view_weight: float = Field(default=0.01, ge=0)


class PlatformMetricConfigRead(PlatformMetricConfigUpsert):
    id: int
    platform: str
    created_at: datetime
    updated_at: datetime
