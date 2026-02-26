from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel

from app.models import AssignmentStatus, MetricSyncStatus, PayoutMethod
from app.schemas.user import PayoutInfoRead, UserActivityRead, UserRead


class SettlementRecordCreate(SQLModel):
    amount: float = Field(gt=0)
    note: Optional[str] = None


class SettlementRecordRead(SQLModel):
    id: int
    user_id: int
    admin_id: int
    amount: float
    note: Optional[str] = None
    paid_at: datetime
    created_at: datetime


class AdminSettlementUserSummaryRead(SQLModel):
    user_id: int
    display_name: str
    username: str
    phone: Optional[str] = None
    city: Optional[str] = None
    review_status: str
    preferred_method: PayoutMethod
    has_valid_payout_info: bool
    total_revenue: float
    total_settled: float
    pending_settlement: float
    settlement_status: str
    last_paid_at: Optional[datetime] = None


class AdminSettlementOverviewRead(SQLModel):
    generated_at: datetime
    blogger_count: int
    total_revenue: float
    total_settled: float
    total_pending: float
    pending_blogger_count: int
    users: list[AdminSettlementUserSummaryRead] = Field(default_factory=list)


class SettlementAssignmentRecordRead(SQLModel):
    assignment_id: int
    task_id: int
    task_title: str
    platform: str
    status: AssignmentStatus
    metric_sync_status: MetricSyncStatus
    revenue: float
    post_link: Optional[str] = None
    completed_at: datetime


class AdminSettlementUserDetailRead(SQLModel):
    user: UserRead
    payout_info: Optional[PayoutInfoRead] = None
    summary: AdminSettlementUserSummaryRead
    recent_completed_assignments: list[SettlementAssignmentRecordRead] = Field(default_factory=list)
    recent_records: list[SettlementRecordRead] = Field(default_factory=list)
    recent_activities: list[UserActivityRead] = Field(default_factory=list)
