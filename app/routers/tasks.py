from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.dependencies import get_current_approved_blogger, get_db
from app.models import Assignment, AssignmentStatus, Task, TaskStatus, User
from app.schemas.assignment import AssignmentRead
from app.schemas.task import TaskRead
from app.services.activity import log_activity

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _ensure_assignment_relations_loaded(assignment: Assignment) -> None:
    _ = assignment.task
    _ = assignment.metrics
    _ = assignment.manual_metric_submissions


@router.get("/", response_model=list[TaskRead])
def list_tasks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_approved_blogger),
) -> list[Task]:
    del current_user
    return db.exec(
        select(Task)
        .where(Task.status == TaskStatus.published)
        .order_by(Task.created_at.desc())
    ).all()


@router.get("/{task_id}", response_model=TaskRead)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_approved_blogger),
) -> Task:
    del current_user
    task = db.get(Task, task_id)
    if not task or task.status != TaskStatus.published:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.post("/{task_id}/accept", response_model=AssignmentRead, status_code=status.HTTP_201_CREATED)
def accept_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_approved_blogger),
) -> Assignment:
    task = db.get(Task, task_id)
    if not task or task.status != TaskStatus.published:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    existing = db.exec(
        select(Assignment)
        .where(Assignment.task_id == task_id)
        .where(Assignment.user_id == current_user.id)
        .where(Assignment.status != AssignmentStatus.cancelled)
    ).first()
    if existing:
        _ensure_assignment_relations_loaded(existing)
        return existing

    assignment = Assignment(
        task_id=task_id,
        user_id=current_user.id,
        status=AssignmentStatus.accepted,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(assignment)
    log_activity(
        db,
        user_id=current_user.id,
        action_type="task_accept",
        title="接受任务",
        detail=f"任务ID: {task.id} / {task.title}",
    )
    db.commit()
    db.refresh(assignment)
    _ensure_assignment_relations_loaded(assignment)
    return assignment
