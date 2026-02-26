from __future__ import annotations

from datetime import datetime
import logging
from math import ceil

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func
from sqlmodel import Session, select

from app.dependencies import get_current_active_admin_user, get_db
from app.models import (
    Assignment,
    AssignmentStatus,
    ManualMetricReviewStatus,
    ManualMetricSubmission,
    MetricSyncStatus,
    PayoutInfo,
    PayoutMethod,
    PlatformMetricConfig,
    ReviewStatus,
    Role,
    SettlementRecord,
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
from app.schemas.settlement import (
    AdminSettlementOverviewRead,
    AdminSettlementUserDetailRead,
    AdminSettlementUserSummaryRead,
    SettlementAssignmentRecordRead,
    SettlementRecordCreate,
    SettlementRecordRead,
)
from app.schemas.task import (
    EligibleBloggerRead,
    EligibleBloggerSummaryRead,
    TaskAttachmentUploadRead,
    TaskCreate,
    TaskDistributeRequest,
    TaskDistributeResult,
    TaskEligibleEstimateRead,
    TaskRead,
    TaskUpdate,
)
from app.schemas.user import (
    AdminUserDetailRead,
    AdminUserReviewSummaryRead,
    UserRead,
    UserReviewUpdate,
    UserWeightUpdate,
)
from app.services.activity import log_activity
from app.services.distribution import list_eligible_bloggers, normalize_platform
from app.services.oss import OSSConfigError, upload_task_attachment
from app.services.sync import apply_manual_metric

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)

ADMIN_FORMULAS = [
    DashboardMetricFormulaRead(
        key="pending_users",
        label="待审核达人",
        definition="统计口径: role=blogger 且 review_status in [pending, under_review] 的达人总数",
    ),
    DashboardMetricFormulaRead(
        key="pending_assignment_reviews",
        label="待审任务作业",
        definition="统计口径: status=in_review 的任务分配总数",
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
            "统计口径: 仅统计 metric_sync_status=manual_approved 的 assignments.revenue；"
            "自动同步仅作预采集，手工审核通过后才计入结算收益"
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


def _is_revenue_verified(assignment: Assignment) -> bool:
    return assignment.metric_sync_status == MetricSyncStatus.manual_approved


def _has_valid_payout_info(payout_info: PayoutInfo | None) -> bool:
    if payout_info is None:
        return False

    method = payout_info.payout_method.value
    if method == "bank_card":
        return True
    if method == "wechat_pay":
        return bool(
            (payout_info.wechat_id or "").strip()
            and (payout_info.wechat_phone or "").strip()
            and (payout_info.wechat_qr_url or "").strip()
        )
    if method == "alipay":
        return bool(
            (payout_info.alipay_phone or "").strip()
            and (payout_info.alipay_account_name or "").strip()
            and (payout_info.alipay_qr_url or "").strip()
        )

    # Fallback for historical generic payout fields.
    return bool((payout_info.account_no or "").strip())


def _settlement_status(total_revenue: float, total_settled: float) -> str:
    pending = round(max(total_revenue - total_settled, 0.0), 2)
    if pending <= 0 and total_settled > 0:
        return "paid_off"
    if pending > 0 and total_settled > 0:
        return "partially_paid"
    if pending > 0:
        return "pending"
    return "no_revenue"


def _build_settlement_summary(
    *,
    user: User,
    payout_info: PayoutInfo | None,
    total_revenue: float,
    total_settled: float,
    last_paid_at: datetime | None,
) -> AdminSettlementUserSummaryRead:
    user_id = user.id or 0
    pending = round(max(total_revenue - total_settled, 0.0), 2)
    display_name = (user.display_name or "").strip() or user.username
    return AdminSettlementUserSummaryRead(
        user_id=user_id,
        display_name=display_name,
        username=user.username,
        phone=user.phone,
        city=user.city,
        review_status=user.review_status.value,
        preferred_method=payout_info.payout_method if payout_info else PayoutMethod.bank_card,
        has_valid_payout_info=_has_valid_payout_info(payout_info),
        total_revenue=round(float(total_revenue), 2),
        total_settled=round(float(total_settled), 2),
        pending_settlement=pending,
        settlement_status=_settlement_status(total_revenue, total_settled),
        last_paid_at=last_paid_at,
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


def _estimate_recommended_scale(eligible_count: int) -> tuple[int, int]:
    if eligible_count <= 0:
        return 0, 0
    if eligible_count < 30:
        low = max(1, ceil(eligible_count * 0.5))
        high = eligible_count
        return low, high
    if eligible_count <= 120:
        low = max(12, ceil(eligible_count * 0.4))
        high = min(eligible_count, max(low, ceil(eligible_count * 0.7)))
        return low, high
    low = max(30, ceil(eligible_count * 0.25))
    high = min(eligible_count, max(low, ceil(eligible_count * 0.5)))
    return low, high


def _estimate_saturation_label(saturation_rate: float, eligible_count: int) -> str:
    if eligible_count <= 0:
        return "暂无供给"
    if saturation_rate < 0.3:
        return "偏低（覆盖不足）"
    if saturation_rate <= 0.65:
        return "健康（供给充足）"
    if saturation_rate <= 0.85:
        return "偏高（建议留余量）"
    return "高饱和（建议分批放量）"


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
        in_review=sum(1 for item in assignments if item.status == AssignmentStatus.in_review),
        completed=sum(1 for item in assignments if item.status == AssignmentStatus.completed),
        rejected=sum(1 for item in assignments if item.status == AssignmentStatus.rejected),
        cancelled=sum(1 for item in assignments if item.status == AssignmentStatus.cancelled),
    )

    review_queue = AdminReviewQueueStatsRead(
        pending_users=sum(1 for user in blogger_users if user.review_status == ReviewStatus.pending),
        under_review_users=sum(1 for user in blogger_users if user.review_status == ReviewStatus.under_review),
        pending_assignment_reviews=assignment_stats.in_review,
        pending_manual_metric_reviews=len(pending_manual_metrics),
    )

    revenue = AdminRevenueStatsRead(
        total_revenue=round(
            sum(float(item.revenue or 0.0) for item in assignments if _is_revenue_verified(item)),
            2,
        ),
        completed_revenue=round(
            sum(
                float(item.revenue or 0.0)
                for item in assignments
                if item.status == AssignmentStatus.completed and _is_revenue_verified(item)
            ),
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
    activities = db.exec(
        select(UserActivityLog)
        .where(UserActivityLog.user_id == user_id)
        .order_by(UserActivityLog.created_at.desc())
        .limit(20)
    ).all()

    return AdminUserDetailRead(
        user=user,
        recent_activities=activities,
    )


@router.get("/settlements/summary", response_model=AdminSettlementOverviewRead)
def get_settlement_summary(
    keyword: str | None = Query(default=None),
    status_filter: str = Query(default="all", alias="status"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_active_admin_user),
) -> AdminSettlementOverviewRead:
    del current_admin

    bloggers = db.exec(
        select(User)
        .where(User.role == Role.blogger)
        .order_by(User.created_at.desc())
    ).all()

    normalized_keyword = (keyword or "").strip().lower()
    if normalized_keyword:
        bloggers = [
            user
            for user in bloggers
            if normalized_keyword in " ".join(
                [
                    (user.display_name or ""),
                    user.username,
                    (user.phone or ""),
                    (user.email or ""),
                    (user.city or ""),
                    (user.category or ""),
                ]
            ).lower()
        ]

    user_ids = [user.id for user in bloggers if user.id is not None]
    payout_map: dict[int, PayoutInfo] = {}
    if user_ids:
        payouts = db.exec(select(PayoutInfo).where(PayoutInfo.user_id.in_(user_ids))).all()
        payout_map = {item.user_id: item for item in payouts}

    revenue_map: dict[int, float] = {}
    if user_ids:
        revenue_rows = db.exec(
            select(
                Assignment.user_id,
                func.coalesce(func.sum(Assignment.revenue), 0.0),
            )
            .where(Assignment.user_id.in_(user_ids))
            .where(Assignment.status == AssignmentStatus.completed)
            .where(Assignment.metric_sync_status == MetricSyncStatus.manual_approved)
            .group_by(Assignment.user_id)
        ).all()
        revenue_map = {int(user_id): float(total or 0.0) for user_id, total in revenue_rows}

    settled_map: dict[int, tuple[float, datetime | None]] = {}
    if user_ids:
        settled_rows = db.exec(
            select(
                SettlementRecord.user_id,
                func.coalesce(func.sum(SettlementRecord.amount), 0.0),
                func.max(SettlementRecord.paid_at),
            )
            .where(SettlementRecord.user_id.in_(user_ids))
            .group_by(SettlementRecord.user_id)
        ).all()
        settled_map = {
            int(user_id): (float(total_amount or 0.0), last_paid_at)
            for user_id, total_amount, last_paid_at in settled_rows
        }

    summaries = []
    for user in bloggers:
        user_id = user.id or 0
        total_revenue = revenue_map.get(user_id, 0.0)
        total_settled, last_paid_at = settled_map.get(user_id, (0.0, None))
        summaries.append(
            _build_settlement_summary(
                user=user,
                payout_info=payout_map.get(user_id),
                total_revenue=total_revenue,
                total_settled=total_settled,
                last_paid_at=last_paid_at,
            )
        )

    if status_filter != "all":
        summaries = [item for item in summaries if item.settlement_status == status_filter]

    summaries.sort(
        key=lambda item: (
            -item.pending_settlement,
            -item.total_revenue,
            item.user_id,
        )
    )

    total_revenue = round(sum(item.total_revenue for item in summaries), 2)
    total_settled = round(sum(item.total_settled for item in summaries), 2)
    total_pending = round(sum(item.pending_settlement for item in summaries), 2)
    pending_blogger_count = sum(1 for item in summaries if item.pending_settlement > 0)

    return AdminSettlementOverviewRead(
        generated_at=datetime.utcnow(),
        blogger_count=len(summaries),
        total_revenue=total_revenue,
        total_settled=total_settled,
        total_pending=total_pending,
        pending_blogger_count=pending_blogger_count,
        users=summaries,
    )


@router.get("/settlements/{user_id}", response_model=AdminSettlementUserDetailRead)
def get_settlement_user_detail(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_active_admin_user),
) -> AdminSettlementUserDetailRead:
    del current_admin
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.role != Role.blogger:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only blogger is supported")

    _ensure_user_relations_loaded(user)
    payout_info = db.exec(select(PayoutInfo).where(PayoutInfo.user_id == user_id)).first()

    revenue_total = db.exec(
        select(func.coalesce(func.sum(Assignment.revenue), 0.0))
        .where(Assignment.user_id == user_id)
        .where(Assignment.status == AssignmentStatus.completed)
        .where(Assignment.metric_sync_status == MetricSyncStatus.manual_approved)
    ).one()
    settled_row = db.exec(
        select(
            func.coalesce(func.sum(SettlementRecord.amount), 0.0),
            func.max(SettlementRecord.paid_at),
        ).where(SettlementRecord.user_id == user_id)
    ).one()
    total_settled = float(settled_row[0] or 0.0)
    last_paid_at = settled_row[1]

    summary = _build_settlement_summary(
        user=user,
        payout_info=payout_info,
        total_revenue=float(revenue_total or 0.0),
        total_settled=total_settled,
        last_paid_at=last_paid_at,
    )

    records = db.exec(
        select(SettlementRecord)
        .where(SettlementRecord.user_id == user_id)
        .order_by(SettlementRecord.paid_at.desc())
        .limit(100)
    ).all()
    completed_assignments = db.exec(
        select(Assignment)
        .where(Assignment.user_id == user_id)
        .where(Assignment.status == AssignmentStatus.completed)
        .order_by(Assignment.updated_at.desc())
        .limit(50)
    ).all()
    for assignment in completed_assignments:
        _ = assignment.task

    completed_records = [
        SettlementAssignmentRecordRead(
            assignment_id=assignment.id or 0,
            task_id=assignment.task_id,
            task_title=assignment.task.title if assignment.task else "未命名任务",
            platform=assignment.task.platform if assignment.task else "unknown",
            status=assignment.status,
            metric_sync_status=assignment.metric_sync_status,
            revenue=round(float(assignment.revenue or 0.0), 2),
            post_link=assignment.post_link,
            completed_at=assignment.updated_at,
        )
        for assignment in completed_assignments
    ]
    activities = db.exec(
        select(UserActivityLog)
        .where(UserActivityLog.user_id == user_id)
        .order_by(UserActivityLog.created_at.desc())
        .limit(20)
    ).all()

    return AdminSettlementUserDetailRead(
        user=user,
        payout_info=payout_info,
        summary=summary,
        recent_completed_assignments=completed_records,
        recent_records=records,
        recent_activities=activities,
    )


@router.post(
    "/settlements/{user_id}/records",
    response_model=SettlementRecordRead,
    status_code=status.HTTP_201_CREATED,
)
def create_settlement_record(
    user_id: int,
    payload: SettlementRecordCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_active_admin_user),
) -> SettlementRecord:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.role != Role.blogger:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only blogger is supported")
    if current_admin.id is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid admin identity")

    revenue_total = db.exec(
        select(func.coalesce(func.sum(Assignment.revenue), 0.0))
        .where(Assignment.user_id == user_id)
        .where(Assignment.status == AssignmentStatus.completed)
        .where(Assignment.metric_sync_status == MetricSyncStatus.manual_approved)
    ).one()
    settled_total = db.exec(
        select(func.coalesce(func.sum(SettlementRecord.amount), 0.0)).where(SettlementRecord.user_id == user_id)
    ).one()
    pending = round(max(float(revenue_total or 0.0) - float(settled_total or 0.0), 0.0), 2)
    if pending <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前无待结款金额")

    amount = round(float(payload.amount), 2)
    if amount <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="amount must be > 0")
    if amount > pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"放款金额不能超过待结款金额 {pending:.2f}",
        )

    record = SettlementRecord(
        user_id=user_id,
        admin_id=current_admin.id,
        amount=amount,
        note=payload.note,
        paid_at=datetime.utcnow(),
    )
    db.add(record)
    log_activity(
        db,
        user_id=user_id,
        action_type="admin_settlement_paid",
        title="管理员登记放款",
        detail=f"操作人ID: {current_admin.id}; 放款金额: {amount:.2f}; 备注: {payload.note or '-'}",
    )
    db.commit()
    db.refresh(record)
    return record


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
    if user.review_status == ReviewStatus.approved and payload.review_status not in {
        ReviewStatus.under_review,
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Approved users can only return to under_review",
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
    user.review_reason = payload.review_reason if payload.review_status == ReviewStatus.rejected else None
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
) -> list[TaskRead]:
    del current_admin
    statement = select(Task).order_by(Task.created_at.desc())
    if status_filter is not None:
        statement = statement.where(Task.status == status_filter)
    tasks = db.exec(statement).all()
    task_ids = [task.id for task in tasks if task.id is not None]
    count_map = _count_active_assignments_map(db, task_ids)
    return [_to_task_read(task, count_map.get(task.id or 0, 0)) for task in tasks]


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
        accept_limit=payload.accept_limit,
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


@router.get("/tasks/eligible-bloggers-estimate", response_model=TaskEligibleEstimateRead)
def estimate_task_eligible_bloggers(
    platform: str = Query(default="douyin"),
    accept_limit: int | None = Query(default=None, ge=1, le=50000),
    preview_limit: int = Query(default=12, ge=1, le=200),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_active_admin_user),
) -> TaskEligibleEstimateRead:
    del current_admin
    normalized_platform = normalize_platform(platform)
    if normalized_platform is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported platform. Supported values: douyin, xiaohongshu, weibo",
        )

    task_for_estimate = Task(
        title="实时预估",
        description="",
        platform=normalized_platform.value,
        base_reward=0.0,
        instructions="",
        attachments=[],
        status=TaskStatus.draft,
    )
    eligible = list_eligible_bloggers(db, task_for_estimate)
    preview_users = eligible[:preview_limit]
    preview_bloggers = [
        EligibleBloggerRead(
            user_id=user.id,
            username=user.username,
            display_name=user.display_name,
            follower_total=user.follower_total,
            avg_views=user.avg_views,
            weight=user.weight,
            platform=normalized_platform.value,
        )
        for user in preview_users
        if user.id is not None
    ]

    eligible_count = len(eligible)
    estimated_accept_count = min(eligible_count, accept_limit) if accept_limit is not None else eligible_count
    saturation_rate = (estimated_accept_count / eligible_count) if eligible_count > 0 else 0.0
    recommended_scale_min, recommended_scale_max = _estimate_recommended_scale(eligible_count)
    saturation_label = _estimate_saturation_label(saturation_rate, eligible_count)
    return TaskEligibleEstimateRead(
        platform=normalized_platform.value,
        eligible_count=eligible_count,
        preview_limit=preview_limit,
        input_accept_limit=accept_limit,
        estimated_accept_count=estimated_accept_count,
        saturation_rate=round(saturation_rate, 4),
        saturation_label=saturation_label,
        recommended_scale_min=recommended_scale_min,
        recommended_scale_max=recommended_scale_max,
        preview_bloggers=preview_bloggers,
    )


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
            detail="Only published tasks can be queried",
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


@router.get("/tasks/{task_id}/eligible-bloggers-summary", response_model=EligibleBloggerSummaryRead)
def get_task_eligible_bloggers_summary(
    task_id: int,
    preview_limit: int = Query(default=20, ge=1, le=500),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_active_admin_user),
) -> EligibleBloggerSummaryRead:
    del current_admin
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if task.status != TaskStatus.published:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only published tasks can be queried",
        )

    platform = normalize_platform(task.platform)
    platform_value = platform.value if platform is not None else task.platform
    eligible = list_eligible_bloggers(db, task)
    preview_users = eligible[:preview_limit]
    preview_bloggers = [
        EligibleBloggerRead(
            user_id=user.id,
            username=user.username,
            display_name=user.display_name,
            follower_total=user.follower_total,
            avg_views=user.avg_views,
            weight=user.weight,
            platform=platform_value,
        )
        for user in preview_users
        if user.id is not None
    ]
    return EligibleBloggerSummaryRead(
        task_id=task.id or 0,
        platform=platform_value,
        eligible_count=len(eligible),
        preview_limit=preview_limit,
        preview_bloggers=preview_bloggers,
    )


@router.post("/tasks/{task_id}/distribute", response_model=TaskDistributeResult)
def distribute_task_to_bloggers(
    task_id: int,
    payload: TaskDistributeRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_active_admin_user),
) -> TaskDistributeResult:
    del current_admin
    del payload
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Task distribution is disabled. Bloggers should accept published tasks themselves.",
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

    if assignment.status != AssignmentStatus.in_review:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only in_review assignments can be approved",
        )
    if assignment.metric_sync_status != MetricSyncStatus.manual_approved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Manual metrics must be approved before assignment approval",
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

    if assignment.status != AssignmentStatus.in_review:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only in_review assignments can be rejected",
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
            favorites=submission.favorites,
            shares=submission.shares,
            views=submission.views,
        )
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
    config.favorite_weight = payload.favorite_weight
    config.share_weight = payload.share_weight
    config.view_weight = payload.view_weight
    config.updated_at = datetime.utcnow()

    db.add(config)
    db.commit()
    db.refresh(config)
    return config
