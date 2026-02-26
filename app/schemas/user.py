from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import field_validator
from sqlmodel import Field, SQLModel

from app.models import AssignmentStatus, MetricSyncStatus, PayoutMethod, ReviewStatus, Role


class PlatformAccountCreate(SQLModel):
    account_name: str
    account_id: str
    profile_url: Optional[str] = None
    follower_count: int = Field(default=0, ge=0)


class PlatformAccountRead(PlatformAccountCreate):
    id: int


class SocialAccountRead(SQLModel):
    id: int
    platform: str
    account_name: str
    account_id: str
    profile_url: Optional[str] = None
    follower_count: int


class UserCreate(SQLModel):
    email: str
    phone: Optional[str] = None
    username: str
    password: str
    display_name: Optional[str] = None
    real_name: Optional[str] = None
    id_no: Optional[str] = None
    city: Optional[str] = None
    category: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    follower_total: int = Field(default=0, ge=0)
    avg_views: int = Field(default=0, ge=0)
    douyin_accounts: list[PlatformAccountCreate] = Field(default_factory=list)
    xiaohongshu_accounts: list[PlatformAccountCreate] = Field(default_factory=list)
    weibo_accounts: list[PlatformAccountCreate] = Field(default_factory=list)

    @field_validator("password")
    @classmethod
    def validate_password_length(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must contain at least 8 characters")
        return value


class UserProfileUpdate(SQLModel):
    display_name: Optional[str] = None
    real_name: Optional[str] = None
    id_no: Optional[str] = None
    city: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    follower_total: Optional[int] = Field(default=None, ge=0)
    avg_views: Optional[int] = Field(default=None, ge=0)


class UserPasswordUpdate(SQLModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("New password must contain at least 8 characters")
        return value


class UserRead(SQLModel):
    id: int
    email: str
    phone: Optional[str] = None
    username: str
    display_name: Optional[str] = None
    real_name: Optional[str] = None
    id_no: Optional[str] = None
    city: Optional[str] = None
    category: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    follower_total: int
    avg_views: int
    is_active: bool
    review_status: ReviewStatus
    review_reason: Optional[str] = None
    role: Role
    weight: float
    created_at: datetime
    updated_at: datetime
    douyin_accounts: list[PlatformAccountRead] = Field(default_factory=list)
    xiaohongshu_accounts: list[PlatformAccountRead] = Field(default_factory=list)
    weibo_accounts: list[PlatformAccountRead] = Field(default_factory=list)

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            if not value.strip():
                return []
            return [tag.strip() for tag in value.split(",") if tag.strip()]
        return []


class UserReviewUpdate(SQLModel):
    review_status: ReviewStatus
    review_reason: Optional[str] = None


class UserWeightUpdate(SQLModel):
    weight: float = Field(gt=0)


class PlatformAccountCreateRequest(PlatformAccountCreate):
    pass


class PlatformAccountUpdateRequest(SQLModel):
    account_name: Optional[str] = None
    account_id: Optional[str] = None
    profile_url: Optional[str] = None
    follower_count: Optional[int] = Field(default=None, ge=0)


class PayoutInfoUpsert(SQLModel):
    payout_method: PayoutMethod = Field(default=PayoutMethod.bank_card)
    bank_description: Optional[str] = None
    wechat_id: Optional[str] = None
    wechat_phone: Optional[str] = None
    wechat_qr_url: Optional[str] = None
    alipay_phone: Optional[str] = None
    alipay_account_name: Optional[str] = None
    alipay_qr_url: Optional[str] = None
    note: Optional[str] = None


class PayoutInfoRead(PayoutInfoUpsert):
    account_name: Optional[str] = None
    account_no: Optional[str] = None
    account_qr_url: Optional[str] = None
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime


class PayoutQrUploadRead(SQLModel):
    method: PayoutMethod
    object_key: str
    url: str


class UserActivityRead(SQLModel):
    id: int
    action_type: str
    title: str
    detail: Optional[str] = None
    created_at: datetime


class AdminUserReviewSummaryRead(SQLModel):
    total: int
    pending: int
    under_review: int
    approved: int
    rejected: int


class AdminUserAssignmentStatsRead(SQLModel):
    total: int
    accepted: int
    in_review: int
    completed: int
    rejected: int
    cancelled: int
    total_revenue: float
    last_assignment_at: Optional[datetime] = None


class AdminUserAssignmentSnapshotRead(SQLModel):
    assignment_id: int
    task_id: int
    task_title: str
    status: AssignmentStatus
    metric_sync_status: MetricSyncStatus
    revenue: float
    post_link: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_synced_at: Optional[datetime] = None


class AdminUserDetailRead(SQLModel):
    user: UserRead
    payout_info: Optional[PayoutInfoRead] = None
    assignment_stats: Optional[AdminUserAssignmentStatsRead] = None
    recent_assignments: list[AdminUserAssignmentSnapshotRead] = Field(default_factory=list)
    recent_activities: list[UserActivityRead] = Field(default_factory=list)
