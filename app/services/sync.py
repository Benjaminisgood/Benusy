from __future__ import annotations

from datetime import datetime

from sqlmodel import Session

from app.models import Assignment, Metric, MetricSource, MetricSyncStatus
from app.services.metrics import fetch_metrics
from app.services.revenue import (
    calculate_engagement_score,
    calculate_revenue,
    get_revenue_config,
)


async def sync_assignment_metrics_once(session: Session, assignment: Assignment) -> tuple[bool, str | None]:
    if not assignment.post_link:
        assignment.metric_sync_status = MetricSyncStatus.manual_required
        assignment.last_sync_error = "Post link is missing"
        assignment.updated_at = datetime.utcnow()
        return False, assignment.last_sync_error

    try:
        metrics_data = await fetch_metrics(assignment.post_link)
    except Exception as exc:
        assignment.metric_sync_status = MetricSyncStatus.manual_required
        assignment.last_sync_error = str(exc)
        assignment.updated_at = datetime.utcnow()
        return False, assignment.last_sync_error

    metric = Metric(
        assignment_id=assignment.id,
        likes=int(metrics_data.get("likes", 0)),
        comments=int(metrics_data.get("comments", 0)),
        shares=int(metrics_data.get("shares", 0)),
        views=int(metrics_data.get("views", 0)),
        source=MetricSource.auto,
    )
    session.add(metric)

    task = assignment.task
    user = assignment.user
    if task is None or user is None:
        assignment.metric_sync_status = MetricSyncStatus.manual_required
        assignment.last_sync_error = "Task or user context missing"
        assignment.updated_at = datetime.utcnow()
        return False, assignment.last_sync_error

    config = get_revenue_config(session, task.platform)
    engagement_score = calculate_engagement_score(metric, config)

    assignment.revenue = calculate_revenue(
        base_reward=task.base_reward,
        user_weight=user.weight,
        engagement_score=engagement_score,
        platform_coef=config.platform_coef,
    )
    assignment.metric_sync_status = MetricSyncStatus.normal
    assignment.last_sync_error = None
    assignment.last_synced_at = datetime.utcnow()
    assignment.updated_at = datetime.utcnow()
    return True, None


def apply_manual_metric(
    session: Session,
    assignment: Assignment,
    *,
    likes: int,
    comments: int,
    shares: int,
    views: int,
) -> Metric:
    metric = Metric(
        assignment_id=assignment.id,
        likes=likes,
        comments=comments,
        shares=shares,
        views=views,
        source=MetricSource.manual,
    )
    session.add(metric)

    task = assignment.task
    user = assignment.user
    config = get_revenue_config(session, task.platform if task else "default")
    engagement_score = calculate_engagement_score(metric, config)

    base_reward = task.base_reward if task else 0.0
    user_weight = user.weight if user else 1.0

    assignment.revenue = calculate_revenue(
        base_reward=base_reward,
        user_weight=user_weight,
        engagement_score=engagement_score,
        platform_coef=config.platform_coef,
    )
    assignment.metric_sync_status = MetricSyncStatus.manual_approved
    assignment.last_sync_error = None
    assignment.last_synced_at = datetime.utcnow()
    assignment.updated_at = datetime.utcnow()
    return metric
