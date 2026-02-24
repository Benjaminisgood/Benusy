from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlmodel import Session, select

from app.db.database import engine
from app.dependencies import get_current_approved_blogger, get_db
from app.models import (
    Assignment,
    AssignmentStatus,
    ManualMetricSubmission,
    ManualMetricReviewStatus,
    MetricSyncStatus,
    User,
)
from app.schemas.assignment import (
    AssignmentRead,
    AssignmentSubmit,
    ManualMetricSubmissionRead,
    ManualMetricSubmit,
)
from app.services.activity import log_activity
from app.services.sync import sync_assignment_metrics_once

router = APIRouter(prefix="/assignments", tags=["assignments"])


def _ensure_assignment_relations_loaded(assignment: Assignment) -> None:
    _ = assignment.task
    _ = assignment.metrics
    _ = assignment.manual_metric_submissions


@router.get("/me", response_model=list[AssignmentRead])
def list_user_assignments(
    current_user: User = Depends(get_current_approved_blogger),
    db: Session = Depends(get_db),
) -> list[Assignment]:
    assignments = db.exec(
        select(Assignment)
        .where(Assignment.user_id == current_user.id)
        .order_by(Assignment.created_at.desc())
    ).all()
    for assignment in assignments:
        _ensure_assignment_relations_loaded(assignment)
    return assignments


@router.post("/{assignment_id}/submit", response_model=AssignmentRead)
def submit_assignment(
    assignment_id: int,
    submission: AssignmentSubmit,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_approved_blogger),
    db: Session = Depends(get_db),
) -> Assignment:
    assignment = db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    if assignment.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your assignment")

    if assignment.status not in {AssignmentStatus.accepted, AssignmentStatus.rejected}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only accepted or rejected assignments can be submitted",
        )

    assignment.post_link = submission.post_link
    assignment.status = AssignmentStatus.submitted
    assignment.reject_reason = None
    assignment.updated_at = datetime.utcnow()
    db.add(assignment)
    log_activity(
        db,
        user_id=current_user.id,
        action_type="assignment_submit",
        title="提交任务内容",
        detail=f"任务分配ID: {assignment.id}",
    )
    db.commit()
    db.refresh(assignment)

    background_tasks.add_task(_sync_once_task, assignment.id)

    _ensure_assignment_relations_loaded(assignment)
    return assignment


@router.post(
    "/{assignment_id}/manual-metrics",
    response_model=ManualMetricSubmissionRead,
    status_code=status.HTTP_201_CREATED,
)
def submit_manual_metrics(
    assignment_id: int,
    payload: ManualMetricSubmit,
    current_user: User = Depends(get_current_approved_blogger),
    db: Session = Depends(get_db),
) -> ManualMetricSubmission:
    assignment = db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    if assignment.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your assignment")

    if assignment.metric_sync_status not in {
        MetricSyncStatus.manual_required,
        MetricSyncStatus.manual_rejected,
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Manual metric input is not required for this assignment",
        )

    submission = ManualMetricSubmission(
        assignment_id=assignment.id,
        likes=payload.likes,
        comments=payload.comments,
        shares=payload.shares,
        views=payload.views,
        note=payload.note,
        review_status=ManualMetricReviewStatus.pending,
    )
    db.add(submission)

    assignment.metric_sync_status = MetricSyncStatus.manual_pending_review
    assignment.updated_at = datetime.utcnow()
    db.add(assignment)
    log_activity(
        db,
        user_id=current_user.id,
        action_type="manual_metrics_submit",
        title="提交手工数据",
        detail=f"任务分配ID: {assignment.id}",
    )

    db.commit()
    db.refresh(submission)
    return submission


def _sync_once_task(assignment_id: int) -> None:
    with Session(engine) as session:
        assignment = session.get(Assignment, assignment_id)
        if not assignment:
            return
        try:
            asyncio.run(sync_assignment_metrics_once(session, assignment))
        except Exception:
            assignment.metric_sync_status = MetricSyncStatus.manual_required
            assignment.last_sync_error = "Background sync failed"
            assignment.updated_at = datetime.utcnow()
            session.add(assignment)
        session.commit()
