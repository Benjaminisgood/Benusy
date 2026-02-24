from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel

from app.models import TaskStatus


class TaskCreate(SQLModel):
    title: str
    description: str
    platform: str
    base_reward: float = Field(ge=0)
    instructions: str
    attachments: list[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.draft


class TaskUpdate(SQLModel):
    title: Optional[str] = None
    description: Optional[str] = None
    platform: Optional[str] = None
    base_reward: Optional[float] = Field(default=None, ge=0)
    instructions: Optional[str] = None
    attachments: Optional[list[str]] = None
    status: Optional[TaskStatus] = None


class TaskRead(SQLModel):
    id: int
    title: str
    description: str
    platform: str
    base_reward: float
    instructions: str
    attachments: list[str] = Field(default_factory=list)
    status: TaskStatus
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
