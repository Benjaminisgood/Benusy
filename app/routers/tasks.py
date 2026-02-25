from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
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


def _count_active_assignments_map(db: Session, task_ids: list[int]) -> dict[int, int]:
    if not task_ids:
        return {}

    rows = db.exec(
        select(Assignment.task_id, func.count(Assignment.id))
        .where(Assignment.task_id.in_(task_ids))
        .where(Assignment.status != AssignmentStatus.cancelled)
        .group_by(Assignment.task_id)
    ).all()
    return {int(task_id): int(count) for task_id, count in rows}


def _count_active_assignments(db: Session, task_id: int) -> int:
    count = db.exec(
        select(func.count(Assignment.id))
        .where(Assignment.task_id == task_id)
        .where(Assignment.status != AssignmentStatus.cancelled)
    ).one()
    return int(count or 0)


def _to_task_read(task: Task, accepted_count: int) -> TaskRead:
    remaining_slots = None
    is_full = False
    if task.accept_limit is not None:
        remaining_slots = max(task.accept_limit - accepted_count, 0)
        is_full = remaining_slots == 0

    return TaskRead(
        id=task.id or 0,
        title=task.title,
        description=task.description,
        platform=task.platform,
        base_reward=task.base_reward,
        accept_limit=task.accept_limit,
        instructions=task.instructions,
        attachments=list(task.attachments or []),
        status=task.status,
        accepted_count=accepted_count,
        remaining_slots=remaining_slots,
        is_full=is_full,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.get("/", response_model=list[TaskRead])
def list_tasks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_approved_blogger),
) -> list[TaskRead]:
    del current_user
    tasks = db.exec(
        select(Task)
        .where(Task.status == TaskStatus.published)
        .order_by(Task.created_at.desc())
    ).all()
    task_ids = [task.id for task in tasks if task.id is not None]
    count_map = _count_active_assignments_map(db, task_ids)
    return [_to_task_read(task, count_map.get(task.id or 0, 0)) for task in tasks]


@router.get("/{task_id}", response_model=TaskRead)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_approved_blogger),
) -> TaskRead:
    del current_user
    task = db.get(Task, task_id)
    if not task or task.status != TaskStatus.published:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return _to_task_read(task, _count_active_assignments(db, task_id))


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

    current_active = _count_active_assignments(db, task_id)
    if task.accept_limit is not None and current_active >= task.accept_limit:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Task acceptance limit reached",
        )

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
