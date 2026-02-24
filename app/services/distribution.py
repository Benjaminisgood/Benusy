from __future__ import annotations

from datetime import datetime
from typing import Type

from sqlmodel import Session, select

from app.models import (
    Assignment,
    AssignmentStatus,
    DouyinAccount,
    ReviewStatus,
    Role,
    SocialPlatform,
    Task,
    User,
    WeiboAccount,
    XiaohongshuAccount,
)
from app.services.activity import log_activity

PlatformModel = Type[DouyinAccount] | Type[XiaohongshuAccount] | Type[WeiboAccount]

_PLATFORM_ALIASES = {
    "douyin": SocialPlatform.douyin,
    "抖音": SocialPlatform.douyin,
    "dy": SocialPlatform.douyin,
    "xiaohongshu": SocialPlatform.xiaohongshu,
    "小红书": SocialPlatform.xiaohongshu,
    "xhs": SocialPlatform.xiaohongshu,
    "weibo": SocialPlatform.weibo,
    "微博": SocialPlatform.weibo,
    "wb": SocialPlatform.weibo,
}


def normalize_platform(platform: str) -> SocialPlatform | None:
    return _PLATFORM_ALIASES.get(platform.strip().lower()) or _PLATFORM_ALIASES.get(platform.strip())


def _resolve_platform_model(platform: SocialPlatform) -> PlatformModel:
    if platform == SocialPlatform.douyin:
        return DouyinAccount
    if platform == SocialPlatform.xiaohongshu:
        return XiaohongshuAccount
    return WeiboAccount


def list_eligible_bloggers(session: Session, task: Task) -> list[User]:
    platform = normalize_platform(task.platform)

    base_users = session.exec(
        select(User)
        .where(User.role == Role.blogger)
        .where(User.is_active.is_(True))
        .where(User.review_status == ReviewStatus.approved)
    ).all()

    if platform is None:
        return sorted(
            base_users,
            key=lambda user: (-user.weight, -user.avg_views, -user.follower_total, user.id or 0),
        )

    model = _resolve_platform_model(platform)
    supported_ids = set(session.exec(select(model.user_id)).all())
    users = [user for user in base_users if user.id in supported_ids]
    return sorted(
        users,
        key=lambda user: (-user.weight, -user.avg_views, -user.follower_total, user.id or 0),
    )


def distribute_task(
    session: Session,
    task: Task,
    *,
    target_user_ids: list[int],
) -> tuple[int, int]:
    created_count = 0
    skipped_existing_count = 0

    for user_id in target_user_ids:
        existing = session.exec(
            select(Assignment)
            .where(Assignment.task_id == task.id)
            .where(Assignment.user_id == user_id)
            .where(Assignment.status != AssignmentStatus.cancelled)
        ).first()
        if existing:
            skipped_existing_count += 1
            continue

        session.add(
            Assignment(
                task_id=task.id,
                user_id=user_id,
                status=AssignmentStatus.accepted,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        created_count += 1
        log_activity(
            session,
            user_id=user_id,
            action_type="task_assigned",
            title="任务已分配",
            detail=f"任务ID: {task.id} / {task.title}",
        )

    return created_count, skipped_existing_count
