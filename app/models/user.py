from datetime import datetime
from enum import Enum
from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel

from app.core.config import settings


class Role(str, Enum):
    admin = "admin"
    blogger = "blogger"


class ReviewStatus(str, Enum):
    pending = "pending"
    under_review = "under_review"
    approved = "approved"
    rejected = "rejected"


class UserBase(SQLModel):
    email: str = Field(index=True, sa_column_kwargs={"unique": True})
    phone: Optional[str] = Field(default=None, index=True, sa_column_kwargs={"unique": True})
    username: str = Field(index=True)
    display_name: Optional[str] = None
    real_name: Optional[str] = None
    id_no: Optional[str] = None
    city: Optional[str] = None
    category: Optional[str] = None
    tags: str = Field(default="")
    follower_total: int = Field(default=0, ge=0)
    avg_views: int = Field(default=0, ge=0)


class User(UserBase, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    hashed_password: str
    is_active: bool = Field(default=True, index=True)
    review_status: ReviewStatus = Field(default=ReviewStatus.pending, index=True)
    review_reason: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    role: Role = Field(default=Role.blogger, index=True)
    weight: float = Field(default_factory=lambda: settings.default_user_weight, gt=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    douyin_accounts: List["DouyinAccount"] = Relationship(back_populates="user")
    xiaohongshu_accounts: List["XiaohongshuAccount"] = Relationship(back_populates="user")
    weibo_accounts: List["WeiboAccount"] = Relationship(back_populates="user")
    assignments: List["Assignment"] = Relationship(back_populates="user")
    payout_info: Optional["PayoutInfo"] = Relationship(back_populates="user")
    activity_logs: List["UserActivityLog"] = Relationship(back_populates="user")

    @property
    def is_approved(self) -> bool:
        return self.review_status == ReviewStatus.approved


class UserPublic(UserBase):
    id: int
    is_active: bool
    review_status: ReviewStatus
    review_reason: Optional[str] = None
    role: Role
    weight: float
    created_at: datetime
    updated_at: datetime
