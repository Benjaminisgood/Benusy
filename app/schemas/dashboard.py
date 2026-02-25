from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from app.models import AssignmentStatus


class DashboardMetricFormulaRead(SQLModel):
    key: str
    label: str
    definition: str


class DashboardActivityRead(SQLModel):
    assignment_id: int
    task_id: int | None = None
    task_title: str
    status: AssignmentStatus
    created_at: datetime
    user_id: int | None = None
    user_name: str | None = None


class BloggerDashboardStatsRead(SQLModel):
    available_tasks: int
    in_progress_assignments: int
    completed_assignments: int
    total_revenue: float
    accepted_assignments: int
    submitted_assignments: int
    in_review_assignments: int
    rejected_assignments: int
    cancelled_assignments: int


class BloggerDashboardRead(SQLModel):
    generated_at: datetime
    stats: BloggerDashboardStatsRead
    recent_activities: list[DashboardActivityRead] = Field(default_factory=list)
    formulas: list[DashboardMetricFormulaRead] = Field(default_factory=list)


class AdminTaskStatsRead(SQLModel):
    total: int
    draft: int
    published: int
    cancelled: int


class AdminAssignmentStatsRead(SQLModel):
    total: int
    accepted: int
    submitted: int
    in_review: int
    completed: int
    rejected: int
    cancelled: int


class AdminReviewQueueStatsRead(SQLModel):
    pending_users: int
    under_review_users: int
    pending_assignment_reviews: int
    pending_manual_metric_reviews: int


class AdminRevenueStatsRead(SQLModel):
    total_revenue: float
    completed_revenue: float


class AdminDashboardRead(SQLModel):
    generated_at: datetime
    task_stats: AdminTaskStatsRead
    assignment_stats: AdminAssignmentStatsRead
    review_queue: AdminReviewQueueStatsRead
    revenue: AdminRevenueStatsRead
    recent_activities: list[DashboardActivityRead] = Field(default_factory=list)
    formulas: list[DashboardMetricFormulaRead] = Field(default_factory=list)
