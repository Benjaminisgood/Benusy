from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel

from app.models import TaskStatus


class TaskCreate(SQLModel):
    title: str
    description: str
    platform: str
    base_reward: float = Field(ge=0)
    accept_limit: Optional[int] = Field(default=None, ge=1)
    instructions: str
    attachments: list[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.draft


class TaskUpdate(SQLModel):
    title: Optional[str] = None
    description: Optional[str] = None
    platform: Optional[str] = None
    base_reward: Optional[float] = Field(default=None, ge=0)
    accept_limit: Optional[int] = Field(default=None, ge=1)
    instructions: Optional[str] = None
    attachments: Optional[list[str]] = None
    status: Optional[TaskStatus] = None


class TaskRead(SQLModel):
    id: int
    title: str
    description: str
    platform: str
    base_reward: float
    accept_limit: Optional[int] = None
    instructions: str
    attachments: list[str] = Field(default_factory=list)
    status: TaskStatus
    accepted_count: Optional[int] = None
    remaining_slots: Optional[int] = None
    is_full: bool = False
    created_at: datetime
    updated_at: datetime


class EligibleBloggerRead(SQLModel):
    user_id: int
    username: str
    display_name: Optional[str] = None
    follower_total: int
    avg_views: int
    weight: float
    platform: str


class EligibleBloggerSummaryRead(SQLModel):
    task_id: int
    platform: str
    eligible_count: int
    preview_limit: int
    preview_bloggers: list[EligibleBloggerRead] = Field(default_factory=list)


class TaskEligibleEstimateRead(SQLModel):
    platform: str
    eligible_count: int
    preview_limit: int
    input_accept_limit: Optional[int] = None
    estimated_accept_count: int
    saturation_rate: float = 0.0
    saturation_label: str = ""
    recommended_scale_min: int = 0
    recommended_scale_max: int = 0
    preview_bloggers: list[EligibleBloggerRead] = Field(default_factory=list)


class TaskDistributeRequest(SQLModel):
    user_ids: list[int] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=500)


class TaskDistributeResult(SQLModel):
    task_id: int
    created_count: int
    skipped_existing_count: int
    target_user_ids: list[int]


class TaskAttachmentUploadRead(SQLModel):
    filename: str
    object_key: str
    url: str
