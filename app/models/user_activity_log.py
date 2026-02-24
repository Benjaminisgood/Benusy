from datetime import datetime
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


class UserActivityLog(SQLModel, table=True):
    __tablename__ = "user_activity_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    action_type: str = Field(index=True)
    title: str
    detail: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    user: "User" = Relationship(back_populates="activity_logs")
