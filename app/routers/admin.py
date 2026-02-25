from __future__ import annotations

from datetime import datetime
import logging

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlmodel import Session, select

from app.dependencies import get_current_active_admin_user, get_db
from app.models import (
    Assignment,
    AssignmentStatus,
    ManualMetricReviewStatus,
    ManualMetricSubmission,
    MetricSyncStatus,
    PayoutInfo,
    PlatformMetricConfig,
    ReviewStatus,
    Role,
    Task,
    TaskStatus,
    User,
    UserActivityLog,
)
from app.schemas.assignment import (
    AssignmentRead,
    AssignmentReject,
    ManualMetricReview,
    ManualMetricSubmissionRead,
)
from app.schemas.dashboard import (
    AdminAssignmentStatsRead,
    AdminDashboardRead,
    AdminRevenueStatsRead,
    AdminReviewQueueStatsRead,
    AdminTaskStatsRead,
    DashboardActivityRead,
    DashboardMetricFormulaRead,
)
from app.schemas.platform_config import (
    PlatformMetricConfigRead,
    PlatformMetricConfigUpsert,
)
from app.schemas.task import (
    EligibleBloggerRead,
    TaskAttachmentUploadRead,
    TaskCreate,
    TaskDistributeRequest,
    TaskDistributeResult,
    TaskRead,
    TaskUpdate,
)
from app.schemas.user import (
    AdminUserAssignmentSnapshotRead,
    AdminUserAssignmentStatsRead,
    AdminUserDetailRead,
    AdminUserReviewSummaryRead,
    UserRead,
    UserReviewUpdate,
    UserWeightUpdate,
)
from app.services.activity import log_activity
from app.services.distribution import distribute_task, list_eligible_bloggers, normalize_platform
from app.services.oss import OSSConfigError, upload_task_attachment
from app.services.sync import apply_manual_metric

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)

ADMIN_FORMULAS = [
    DashboardMetricFormulaRead(
        key="pending_users",
        label="待审核用户",
        definition="统计口径: role=blogger 且 review_status in [pending, under_review] 的用户总数",
    ),
    DashboardMetricFormulaRead(
        key="pending_assignment_reviews",
        label="待审任务作业",
        definition="统计口径: status in [submitted, in_review] 的任务分配总数",
    ),
    DashboardMetricFormulaRead(
        key="pending_manual_metric_reviews",
        label="待审手工指标",
        definition="统计口径: review_status=pending 的手工补录记录总数",
    ),
    DashboardMetricFormulaRead(
        key="total_revenue",
        label="平台累计收益",
        definition=(
            "统计口径: assignments.revenue 累加；"
            "单条 revenue = base_reward + engagement_score * platform_coef * user.weight"
        ),
    ),
]


def _ensure_user_relations_loaded(user: User) -> None:
    _ = user.douyin_accounts
    _ = user.xiaohongshu_accounts
    _ = user.weibo_accounts


def _ensure_assignment_relations_loaded(assignment: Assignment) -> None:
    _ = assignment.task
    _ = assignment.metrics
    _ = assignment.manual_metric_submissions


def _to_admin_activity(assignment: Assignment) -> DashboardActivityRead:
    task = assignment.task
    user = assignment.user
    return DashboardActivityRead(
        assignment_id=assignment.id,
        task_id=assignment.task_id,
        task_title=task.title if task else "未命名任务",
        status=assignment.status,
        created_at=assignment.created_at,
        user_id=assignment.user_id,
        user_name=(user.display_name or user.username) if user else None,
    )


def _normalize_attachment_urls(urls: list[str] | None) -> list[str]:
    if not urls:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for raw in urls:
        value = (raw or "").strip()
        if not value:
            continue
        if not (value.startswith("http://") or value.startswith("https://")):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Attachment URL must start with http:// or https://: {value}",
            )
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


@router.get("/dashboard", response_model=AdminDashboardRead)
def get_admin_dashboard(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_active_admin_user),
) -> AdminDashboardRead:
    del current_admin

    tasks = db.exec(select(Task)).all()
    assignments = db.exec(select(Assignment).order_by(Assignment.created_at.desc())).all()
    blogger_users = db.exec(select(User).where(User.role == Role.blogger)).all()
    pending_manual_metrics = db.exec(
        select(ManualMetricSubmission).where(
            ManualMetricSubmission.review_status == ManualMetricReviewStatus.pending
        )
    ).all()

    task_stats = AdminTaskStatsRead(
        total=len(tasks),
        draft=sum(1 for task in tasks if task.status == TaskStatus.draft),
        published=sum(1 for task in tasks if task.status == TaskStatus.published),
        cancelled=sum(1 for task in tasks if task.status == TaskStatus.cancelled),
    )

    assignment_stats = AdminAssignmentStatsRead(
        total=len(assignments),
        accepted=sum(1 for item in assignments if item.status == AssignmentStatus.accepted),
        submitted=sum(1 for item in assignments if item.status == AssignmentStatus.submitted),
        in_review=sum(1 for item in assignments if item.status == AssignmentStatus.in_review),
        completed=sum(1 for item in assignments if item.status == AssignmentStatus.completed),
        rejected=sum(1 for item in assignments if item.status == AssignmentStatus.rejected),
        cancelled=sum(1 for item in assignments if item.status == AssignmentStatus.cancelled),
    )

    review_queue = AdminReviewQueueStatsRead(
        pending_users=sum(1 for user in blogger_users if user.review_status == ReviewStatus.pending),
        under_review_users=sum(1 for user in blogger_users if user.review_status == ReviewStatus.under_review),
        pending_assignment_reviews=assignment_stats.submitted + assignment_stats.in_review,
        pending_manual_metric_reviews=len(pending_manual_metrics),
    )

    revenue = AdminRevenueStatsRead(
        total_revenue=round(sum(float(item.revenue or 0.0) for item in assignments), 2),
        completed_revenue=round(
            sum(float(item.revenue or 0.0) for item in assignments if item.status == AssignmentStatus.completed),
            2,
        ),
    )

    recent_activities = [_to_admin_activity(item) for item in assignments[:12]]

    return AdminDashboardRead(
        generated_at=datetime.utcnow(),
        task_stats=task_stats,
        assignment_stats=assignment_stats,
        review_queue=review_queue,
        revenue=revenue,
        recent_activities=recent_activities,
        formulas=ADMIN_FORMULAS,
    )


@router.get("/users", response_model=list[UserRead])
def list_users(
    role: Role | None = Query(default=None),
    review_status: ReviewStatus | None = Query(default=None),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_active_admin_user),
) -> list[User]:
    del current_admin
    statement = select(User).order_by(User.created_at.desc())
    if role is not None:
        statement = statement.where(User.role == role)
    if review_status is not None:
        statement = statement.where(User.review_status == review_status)

    users = db.exec(statement).all()
    for user in users:
        _ensure_user_relations_loaded(user)
    return users


@router.get("/users/review-summary", response_model=AdminUserReviewSummaryRead)
def get_user_review_summary(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_active_admin_user),
) -> AdminUserReviewSummaryRead:
    del current_admin

    bloggers = db.exec(select(User).where(User.role == Role.blogger)).all()
    return AdminUserReviewSummaryRead(
        total=len(bloggers),
        pending=sum(1 for user in bloggers if user.review_status == ReviewStatus.pending),
        under_review=sum(1 for user in bloggers if user.review_status == ReviewStatus.under_review),
        approved=sum(1 for user in bloggers if user.review_status == ReviewStatus.approved),
        rejected=sum(1 for user in bloggers if user.review_status == ReviewStatus.rejected),
    )


@router.get("/users/{user_id}/detail", response_model=AdminUserDetailRead)
def get_user_detail(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_active_admin_user),
) -> AdminUserDetailRead:
    del current_admin
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    _ensure_user_relations_loaded(user)

    payout_info = db.exec(select(PayoutInfo).where(PayoutInfo.user_id == user_id)).first()
    activities = db.exec(
        select(UserActivityLog)
        .where(UserActivityLog.user_id == user_id)
        .order_by(UserActivityLog.created_at.desc())
        .limit(20)
    ).all()

    assignments = db.exec(
        select(Assignment)
        .where(Assignment.user_id == user_id)
        .order_by(Assignment.created_at.desc())
    ).all()
    for assignment in assignments:
        _ensure_assignment_relations_loaded(assignment)

    assignment_stats = AdminUserAssignmentStatsRead(
        total=len(assignments),
        accepted=sum(1 for item in assignments if item.status == AssignmentStatus.accepted),
        submitted=sum(1 for item in assignments if item.status == AssignmentStatus.submitted),
        in_review=sum(1 for item in assignments if item.status == AssignmentStatus.in_review),
        completed=sum(1 for item in assignments if item.status == AssignmentStatus.completed),
        rejected=sum(1 for item in assignments if item.status == AssignmentStatus.rejected),
        cancelled=sum(1 for item in assignments if item.status == AssignmentStatus.cancelled),
        total_revenue=round(sum(float(item.revenue or 0.0) for item in assignments), 2),
        last_assignment_at=assignments[0].created_at if assignments else None,
    )

    recent_assignments = [
        AdminUserAssignmentSnapshotRead(
            assignment_id=assignment.id or 0,
            task_id=assignment.task_id,
            task_title=assignment.task.title if assignment.task else f"任务#{assignment.task_id}",
            status=assignment.status,
            metric_sync_status=assignment.metric_sync_status,
            revenue=float(assignment.revenue or 0.0),
            post_link=assignment.post_link,
            created_at=assignment.created_at,
            updated_at=assignment.updated_at,
            last_synced_at=assignment.last_synced_at,
        )
        for assignment in assignments[:12]
    ]

    return AdminUserDetailRead(
        user=user,
        payout_info=payout_info,
        assignment_stats=assignment_stats,
        recent_assignments=recent_assignments,
        recent_activities=activities,
    )


@router.patch("/users/{user_id}/review", response_model=UserRead)
def review_user(
    user_id: int,
    payload: UserReviewUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_active_admin_user),
) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user.role != Role.blogger:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only blogger accounts can be reviewed",
        )

    if user.review_status == ReviewStatus.pending and payload.review_status != ReviewStatus.under_review:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pending users must move to under_review first",
        )
    if user.review_status == ReviewStatus.under_review and payload.review_status not in {
        ReviewStatus.approved,
        ReviewStatus.rejected,
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Under-review users can only be approved or rejected",
        )
    if user.review_status == ReviewStatus.approved and payload.review_status != ReviewStatus.approved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Approved users cannot be moved to another review state",
        )
    if user.review_status == ReviewStatus.rejected and payload.review_status != ReviewStatus.under_review:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rejected users must return to under_review before a new decision",
        )

    if payload.review_status == ReviewStatus.rejected and not payload.review_reason:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="review_reason is required when rejecting",
        )

    previous_status = user.review_status
    user.review_status = payload.review_status
    user.review_reason = payload.review_reason
    user.reviewed_at = datetime.utcnow()
    user.updated_at = datetime.utcnow()
    db.add(user)
    log_activity(
        db,
        user_id=user.id,
        action_type="admin_user_review",
        title="管理员更新审核状态",
        detail=(
            f"操作人ID: {current_admin.id}; 状态: {previous_status.value} -> {payload.review_status.value}; "
            f"原因: {payload.review_reason or '-'}"
        ),
    )
    db.commit()
    db.refresh(user)
    _ensure_user_relations_loaded(user)
    return user


@router.patch("/users/{user_id}/weight", response_model=UserRead)
def update_user_weight(
    user_id: int,
    payload: UserWeightUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_active_admin_user),
) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    previous_weight = float(user.weight)
    user.weight = payload.weight
    user.updated_at = datetime.utcnow()
    db.add(user)
    log_activity(
        db,
        user_id=user.id,
        action_type="admin_weight_update",
        title="管理员更新运营权重",
        detail=f"操作人ID: {current_admin.id}; 权重: {previous_weight:.2f} -> {payload.weight:.2f}",
    )
    db.commit()
    db.refresh(user)
    _ensure_user_relations_loaded(user)
    return user


@router.get("/tasks", response_model=list[TaskRead])
def list_tasks(
    status_filter: TaskStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_active_admin_user),
) -> list[Task]:
    del current_admin
    statement = select(Task).order_by(Task.created_at.desc())
    if status_filter is not None:
        statement = statement.where(Task.status == status_filter)
    return db.exec(statement).all()


@router.post("/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_active_admin_user),
) -> Task:
    del current_admin
    task = Task(
        title=payload.title,
        description=payload.description,
        platform=payload.platform,
        base_reward=payload.base_reward,
        instructions=payload.instructions,
        attachments=_normalize_attachment_urls(payload.attachments),
        status=payload.status,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.post(
    "/tasks/attachments/upload",
    response_model=TaskAttachmentUploadRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_task_attachment_file(
    file: UploadFile = File(...),
    current_admin: User = Depends(get_current_active_admin_user),
) -> TaskAttachmentUploadRead:
    del current_admin
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")

    try:
        url, object_key = upload_task_attachment(file)
    except OSSConfigError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    except Exception as exc:
        logger.exception("OSS attachment upload failed for filename=%s", file.filename)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"上传附件到 OSS 失败: {exc}",
        )
    finally:
        await file.close()

    return TaskAttachmentUploadRead(filename=file.filename, object_key=object_key, url=url)


@router.patch("/tasks/{task_id}", response_model=TaskRead)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_active_admin_user),
) -> Task:
    del current_admin
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    updates = payload.model_dump(exclude_unset=True)
    if "attachments" in updates:
        updates["attachments"] = _normalize_attachment_urls(updates["attachments"])
    for field_name, value in updates.items():
        setattr(task, field_name, value)
    task.updated_at = datetime.utcnow()

    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.post("/tasks/{task_id}/publish", response_model=TaskRead)
def publish_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_active_admin_user),
) -> Task:
    del current_admin
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    task.status = TaskStatus.published
    task.updated_at = datetime.utcnow()
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.post("/tasks/{task_id}/cancel", response_model=TaskRead)
def cancel_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_active_admin_user),
) -> Task:
    del current_admin
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    task.status = TaskStatus.cancelled
    task.updated_at = datetime.utcnow()
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.get("/tasks/{task_id}/eligible-bloggers", response_model=list[EligibleBloggerRead])
def list_task_eligible_bloggers(
    task_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_active_admin_user),
) -> list[EligibleBloggerRead]:
    del current_admin
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if task.status != TaskStatus.published:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only published tasks can be distributed",
        )

    platform = normalize_platform(task.platform)
    platform_value = platform.value if platform is not None else task.platform
    bloggers = list_eligible_bloggers(db, task)[:limit]
    return [
        EligibleBloggerRead(
            user_id=user.id,
            username=user.username,
            display_name=user.display_name,
            follower_total=user.follower_total,
            avg_views=user.avg_views,
            weight=user.weight,
            platform=platform_value,
        )
        for user in bloggers
        if user.id is not None
    ]


@router.post("/tasks/{task_id}/distribute", response_model=TaskDistributeResult)
def distribute_task_to_bloggers(
    task_id: int,
    payload: TaskDistributeRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_active_admin_user),
) -> TaskDistributeResult:
    del current_admin
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if task.status != TaskStatus.published:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only published tasks can be distributed",
        )

    eligible = list_eligible_bloggers(db, task)
    eligible_ids = {user.id for user in eligible if user.id is not None}

    if payload.user_ids:
        seen: set[int] = set()
        target_user_ids: list[int] = []
        for user_id in payload.user_ids:
            if user_id in seen:
                continue
            seen.add(user_id)
            target_user_ids.append(user_id)

        invalid = [user_id for user_id in target_user_ids if user_id not in eligible_ids]
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Users not eligible for task platform: {invalid}",
            )
    else:
        target_user_ids = [user.id for user in eligible[: payload.limit] if user.id is not None]

    if not target_user_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No eligible bloggers found")

    created_count, skipped_existing_count = distribute_task(
        db,
        task,
        target_user_ids=target_user_ids,
    )
    db.commit()
    return TaskDistributeResult(
        task_id=task.id,
        created_count=created_count,
        skipped_existing_count=skipped_existing_count,
        target_user_ids=target_user_ids,
    )


@router.get("/assignments", response_model=list[AssignmentRead])
def list_assignments(
    status_filter: AssignmentStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_active_admin_user),
) -> list[Assignment]:
    del current_admin
    statement = select(Assignment).order_by(Assignment.created_at.desc())
    if status_filter is not None:
        statement = statement.where(Assignment.status == status_filter)

    assignments = db.exec(statement).all()
    for assignment in assignments:
        _ensure_assignment_relations_loaded(assignment)
    return assignments


@router.post("/assignments/{assignment_id}/start-review", response_model=AssignmentRead)
def start_assignment_review(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_active_admin_user),
) -> Assignment:
    del current_admin
    assignment = db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")

    if assignment.status != AssignmentStatus.submitted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Assignment is not submitted")

    assignment.status = AssignmentStatus.in_review
    assignment.updated_at = datetime.utcnow()
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    _ensure_assignment_relations_loaded(assignment)
    return assignment


@router.post("/assignments/{assignment_id}/approve", response_model=AssignmentRead)
def approve_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_active_admin_user),
) -> Assignment:
    del current_admin
    assignment = db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")

    if assignment.status not in {AssignmentStatus.submitted, AssignmentStatus.in_review}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only submitted or in_review assignments can be approved",
        )

    assignment.status = AssignmentStatus.completed
    assignment.reject_reason = None
    assignment.updated_at = datetime.utcnow()
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    _ensure_assignment_relations_loaded(assignment)
    return assignment


@router.post("/assignments/{assignment_id}/reject", response_model=AssignmentRead)
def reject_assignment(
    assignment_id: int,
    payload: AssignmentReject,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_active_admin_user),
) -> Assignment:
    del current_admin
    assignment = db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")

    if assignment.status not in {AssignmentStatus.submitted, AssignmentStatus.in_review}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only submitted or in_review assignments can be rejected",
        )

    assignment.status = AssignmentStatus.rejected
    assignment.reject_reason = payload.reason
    assignment.updated_at = datetime.utcnow()
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    _ensure_assignment_relations_loaded(assignment)
    return assignment


@router.get("/manual-metrics/pending", response_model=list[ManualMetricSubmissionRead])
def list_pending_manual_metrics(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_active_admin_user),
) -> list[ManualMetricSubmission]:
    del current_admin
    return db.exec(
        select(ManualMetricSubmission).where(
            ManualMetricSubmission.review_status == ManualMetricReviewStatus.pending
        )
    ).all()


@router.post("/manual-metrics/{submission_id}/review", response_model=ManualMetricSubmissionRead)
def review_manual_metric_submission(
    submission_id: int,
    payload: ManualMetricReview,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_active_admin_user),
) -> ManualMetricSubmission:
    del current_admin
    submission = db.get(ManualMetricSubmission, submission_id)
    if not submission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manual submission not found")

    if submission.review_status != ManualMetricReviewStatus.pending:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Submission already reviewed")

    assignment = db.get(Assignment, submission.assignment_id)
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")

    submission.reviewed_at = datetime.utcnow()
    submission.review_reason = payload.review_reason

    if payload.approved:
        submission.review_status = ManualMetricReviewStatus.approved
        apply_manual_metric(
            db,
            assignment,
            likes=submission.likes,
            comments=submission.comments,
            shares=submission.shares,
            views=submission.views,
        )
        if assignment.status == AssignmentStatus.submitted:
            assignment.status = AssignmentStatus.in_review
    else:
        submission.review_status = ManualMetricReviewStatus.rejected
        assignment.metric_sync_status = MetricSyncStatus.manual_rejected
        assignment.last_sync_error = payload.review_reason or "Manual metrics rejected"
        assignment.updated_at = datetime.utcnow()

    db.add(assignment)
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return submission


@router.get("/platform-configs", response_model=list[PlatformMetricConfigRead])
def list_platform_configs(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_active_admin_user),
) -> list[PlatformMetricConfig]:
    del current_admin
    return db.exec(select(PlatformMetricConfig)).all()


@router.put("/platform-configs/{platform}", response_model=PlatformMetricConfigRead)
def upsert_platform_config(
    platform: str,
    payload: PlatformMetricConfigUpsert,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_active_admin_user),
) -> PlatformMetricConfig:
    del current_admin
    config = db.exec(select(PlatformMetricConfig).where(PlatformMetricConfig.platform == platform)).first()

    if config is None:
        config = PlatformMetricConfig(platform=platform)

    config.platform_coef = payload.platform_coef
    config.like_weight = payload.like_weight
    config.comment_weight = payload.comment_weight
    config.share_weight = payload.share_weight
    config.view_weight = payload.view_weight
    config.updated_at = datetime.utcnow()

    db.add(config)
    db.commit()
    db.refresh(config)
    return config
