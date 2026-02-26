from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.dependencies import get_current_approved_blogger, get_db
from app.models import Assignment, AssignmentStatus, MetricSyncStatus, Task, TaskStatus, User
from app.schemas.dashboard import (
    BloggerDashboardRead,
    BloggerDashboardStatsRead,
    DashboardActivityRead,
    DashboardMetricFormulaRead,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


BLOGGER_FORMULAS = [
    DashboardMetricFormulaRead(
        key="available_tasks",
        label="可用任务",
        definition="统计口径: status=published 的任务总数",
    ),
    DashboardMetricFormulaRead(
        key="in_progress_assignments",
        label="进行中任务",
        definition="统计口径: 当前用户 status in [accepted, in_review] 的分配数",
    ),
    DashboardMetricFormulaRead(
        key="completed_assignments",
        label="已完成任务",
        definition="统计口径: 当前用户 status=completed 的分配数",
    ),
    DashboardMetricFormulaRead(
        key="total_revenue",
        label="累计收益",
        definition=(
            "统计口径: 当前用户 metric_sync_status=manual_approved 的分配 revenue 累加；"
            "自动同步仅作预采集，手工审核通过后计入结算收益"
        ),
    ),
]


def _to_activity_row(assignment: Assignment) -> DashboardActivityRead:
    task = assignment.task
    return DashboardActivityRead(
        assignment_id=assignment.id,
        task_id=assignment.task_id,
        task_title=task.title if task else "未命名任务",
        status=assignment.status,
        created_at=assignment.created_at,
    )


def _is_revenue_verified(assignment: Assignment) -> bool:
    return assignment.metric_sync_status == MetricSyncStatus.manual_approved


@router.get("/blogger", response_model=BloggerDashboardRead)
def get_blogger_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_approved_blogger),
) -> BloggerDashboardRead:
    assignments = db.exec(
        select(Assignment)
        .where(Assignment.user_id == current_user.id)
        .order_by(Assignment.created_at.desc())
    ).all()
    available_tasks = db.exec(select(Task).where(Task.status == TaskStatus.published)).all()

    accepted_count = 0
    in_review_count = 0
    completed_count = 0
    rejected_count = 0
    cancelled_count = 0
    total_revenue = 0.0

    for assignment in assignments:
        if _is_revenue_verified(assignment):
            total_revenue += float(assignment.revenue or 0.0)
        if assignment.status == AssignmentStatus.accepted:
            accepted_count += 1
        elif assignment.status == AssignmentStatus.in_review:
            in_review_count += 1
        elif assignment.status == AssignmentStatus.completed:
            completed_count += 1
        elif assignment.status == AssignmentStatus.rejected:
            rejected_count += 1
        elif assignment.status == AssignmentStatus.cancelled:
            cancelled_count += 1

    in_progress_count = accepted_count + in_review_count
    recent_activities = [_to_activity_row(item) for item in assignments[:10]]

    return BloggerDashboardRead(
        generated_at=datetime.utcnow(),
        stats=BloggerDashboardStatsRead(
            available_tasks=len(available_tasks),
            in_progress_assignments=in_progress_count,
            completed_assignments=completed_count,
            total_revenue=round(total_revenue, 2),
            accepted_assignments=accepted_count,
            in_review_assignments=in_review_count,
            rejected_assignments=rejected_count,
            cancelled_assignments=cancelled_count,
        ),
        recent_activities=recent_activities,
        formulas=BLOGGER_FORMULAS,
    )
