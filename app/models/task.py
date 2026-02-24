from datetime import datetime
from enum import Enum
from typing import List, Optional

from sqlalchemy import Column, JSON
from sqlmodel import Field, Relationship, SQLModel


class TaskStatus(str, Enum):
    draft = "draft"
    published = "published"
    cancelled = "cancelled"


class Task(SQLModel, table=True):
    __tablename__ = "tasks"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    description: str
    platform: str = Field(index=True)
    base_reward: float = Field(default=0.0, ge=0)
    instructions: str
    attachments: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    status: TaskStatus = Field(default=TaskStatus.draft, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    assignments: List["Assignment"] = Relationship(back_populates="task")
