#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Any

from sqlmodel import Session, delete, select

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.security import get_password_hash
from app.db.database import engine
from app.models import (
    Assignment,
    AssignmentStatus,
    DouyinAccount,
    ManualMetricReviewStatus,
    ManualMetricSubmission,
    Metric,
    MetricSyncStatus,
    ReviewStatus,
    Role,
    Task,
    TaskStatus,
    User,
    WeiboAccount,
    XiaohongshuAccount,
)


def _build_marker() -> str:
    return datetime.now(UTC).strftime("adminreg_%Y%m%d%H%M%S")


def _write_output(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _as_int_ids(raw_values: list[Any] | None) -> list[int]:
    ids: list[int] = []
    for item in raw_values or []:
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            ids.append(item)
    return ids


def _delete_seed_entities(
    session: Session,
    *,
    user_ids: list[int],
    task_ids: list[int],
    account_ids: list[int],
    assignment_ids: list[int],
    manual_submission_ids: list[int],
) -> None:
    related_assignment_ids = set(assignment_ids)

    if task_ids:
        related_assignment_ids.update(
            _as_int_ids(session.exec(select(Assignment.id).where(Assignment.task_id.in_(task_ids))).all())
        )
    if user_ids:
        related_assignment_ids.update(
            _as_int_ids(session.exec(select(Assignment.id).where(Assignment.user_id.in_(user_ids))).all())
        )

    resolved_assignment_ids = sorted(related_assignment_ids)
    related_manual_ids = set(manual_submission_ids)
    if resolved_assignment_ids:
        related_manual_ids.update(
            _as_int_ids(
                session.exec(
                    select(ManualMetricSubmission.id).where(
                        ManualMetricSubmission.assignment_id.in_(resolved_assignment_ids)
                    )
                ).all()
            )
        )
        session.exec(delete(Metric).where(Metric.assignment_id.in_(resolved_assignment_ids)))

    resolved_manual_ids = sorted(related_manual_ids)
    if resolved_manual_ids:
        session.exec(delete(ManualMetricSubmission).where(ManualMetricSubmission.id.in_(resolved_manual_ids)))

    if resolved_assignment_ids:
        session.exec(delete(Assignment).where(Assignment.id.in_(resolved_assignment_ids)))

    if task_ids:
        session.exec(delete(Task).where(Task.id.in_(task_ids)))

    if account_ids:
        session.exec(delete(DouyinAccount).where(DouyinAccount.id.in_(account_ids)))

    if user_ids:
        session.exec(delete(DouyinAccount).where(DouyinAccount.user_id.in_(user_ids)))
        session.exec(delete(XiaohongshuAccount).where(XiaohongshuAccount.user_id.in_(user_ids)))
        session.exec(delete(WeiboAccount).where(WeiboAccount.user_id.in_(user_ids)))
        session.exec(delete(User).where(User.id.in_(user_ids)))


def _cleanup_stale_seed_rows() -> None:
    with Session(engine) as session:
        stale_user_ids = _as_int_ids(
            session.exec(select(User.id).where(User.email.like("adminreg_%@example.com"))).all()
        )
        stale_task_ids = _as_int_ids(
            session.exec(select(Task.id).where(Task.title.like("[E2E]adminreg_%"))).all()
        )
        stale_account_ids = _as_int_ids(
            session.exec(select(DouyinAccount.id).where(DouyinAccount.account_name.like("adminreg_%"))).all()
        )
        _delete_seed_entities(
            session,
            user_ids=stale_user_ids,
            task_ids=stale_task_ids,
            account_ids=stale_account_ids,
            assignment_ids=[],
            manual_submission_ids=[],
        )
        session.commit()


def _create_seed(path: Path) -> int:
    _cleanup_stale_seed_rows()
    marker = _build_marker()
    pending_email = f"{marker}_pending@example.com"
    eligible_email = f"{marker}_eligible@example.com"

    with Session(engine) as session:
        pending_user = User(
            email=pending_email,
            phone=f"199{marker[-8:]}",
            username=f"{marker}_pending",
            display_name=f"{marker}_pending",
            city="Shenzhen",
            category="lifestyle",
            tags="e2e,pending",
            follower_total=500,
            avg_views=1200,
            hashed_password=get_password_hash("adminreg123"),
            role=Role.blogger,
            review_status=ReviewStatus.pending,
        )
        session.add(pending_user)
        session.commit()
        session.refresh(pending_user)

        eligible_user = User(
            email=eligible_email,
            phone=f"188{marker[-8:]}",
            username=f"{marker}_eligible",
            display_name=f"{marker}_eligible",
            city="Hangzhou",
            category="tech",
            tags="e2e,eligible",
            follower_total=1800,
            avg_views=5000,
            hashed_password=get_password_hash("adminreg123"),
            role=Role.blogger,
            review_status=ReviewStatus.approved,
        )
        session.add(eligible_user)
        session.commit()
        session.refresh(eligible_user)

        eligible_account = DouyinAccount(
            user_id=eligible_user.id,
            account_name=f"{marker}_douyin",
            account_id=f"{marker}_dy_account",
            profile_url=f"https://example.com/{marker}/douyin",
            follower_count=2200,
        )
        session.add(eligible_account)
        session.commit()
        session.refresh(eligible_account)

        distribute_task = Task(
            title=f"[E2E]{marker} 分配任务",
            description="管理员分配流程回归任务",
            platform="douyin",
            base_reward=88.0,
            instructions="用于管理员控制台自动化回归，请勿手工操作。",
            attachments=[],
            status=TaskStatus.published,
        )
        session.add(distribute_task)
        session.commit()
        session.refresh(distribute_task)

        review_task = Task(
            title=f"[E2E]{marker} 作业审核任务",
            description="管理员作业审核回归任务",
            platform="douyin",
            base_reward=66.0,
            instructions="审核 submitted -> in_review -> completed 流程",
            attachments=[],
            status=TaskStatus.published,
        )
        session.add(review_task)
        session.commit()
        session.refresh(review_task)

        review_assignment = Assignment(
            task_id=review_task.id,
            user_id=eligible_user.id,
            status=AssignmentStatus.submitted,
            post_link=f"https://example.com/{marker}/review-post",
            metric_sync_status=MetricSyncStatus.manual_required,
            revenue=0.0,
        )
        session.add(review_assignment)
        session.commit()
        session.refresh(review_assignment)

        manual_task = Task(
            title=f"[E2E]{marker} 手工指标审核任务",
            description="管理员手工指标审核回归任务",
            platform="douyin",
            base_reward=77.0,
            instructions="审核手工补录数据",
            attachments=[],
            status=TaskStatus.published,
        )
        session.add(manual_task)
        session.commit()
        session.refresh(manual_task)

        manual_assignment = Assignment(
            task_id=manual_task.id,
            user_id=eligible_user.id,
            status=AssignmentStatus.in_review,
            post_link=f"https://example.com/{marker}/manual-post",
            metric_sync_status=MetricSyncStatus.manual_pending_review,
            revenue=0.0,
        )
        session.add(manual_assignment)
        session.commit()
        session.refresh(manual_assignment)

        manual_submission = ManualMetricSubmission(
            assignment_id=manual_assignment.id,
            likes=321,
            comments=45,
            shares=12,
            views=4567,
            note=f"{marker} manual metrics seed",
            review_status=ManualMetricReviewStatus.pending,
        )
        session.add(manual_submission)
        session.commit()
        session.refresh(manual_submission)

        payload = {
            "marker": marker,
            "pending_user": {
                "id": pending_user.id,
                "email": pending_user.email,
            },
            "eligible_user": {
                "id": eligible_user.id,
                "email": eligible_user.email,
            },
            "distribution_task": {
                "id": distribute_task.id,
                "title": distribute_task.title,
            },
            "review_assignment": {
                "id": review_assignment.id,
                "task_id": review_task.id,
            },
            "manual_assignment": {
                "id": manual_assignment.id,
                "task_id": manual_task.id,
            },
            "manual_submission": {
                "id": manual_submission.id,
            },
            "cleanup_ids": {
                "users": [pending_user.id, eligible_user.id],
                "douyin_accounts": [eligible_account.id],
                "tasks": [distribute_task.id, review_task.id, manual_task.id],
                "assignments": [review_assignment.id, manual_assignment.id],
                "manual_submissions": [manual_submission.id],
            },
        }

    _write_output(path, payload)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def _cleanup_seed(path: Path) -> int:
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        cleanup_ids = payload.get("cleanup_ids", {})
        with Session(engine) as session:
            _delete_seed_entities(
                session,
                user_ids=_as_int_ids(cleanup_ids.get("users")),
                task_ids=_as_int_ids(cleanup_ids.get("tasks")),
                account_ids=_as_int_ids(cleanup_ids.get("douyin_accounts")),
                assignment_ids=_as_int_ids(cleanup_ids.get("assignments")),
                manual_submission_ids=_as_int_ids(cleanup_ids.get("manual_submissions")),
            )
            session.commit()
    path.unlink(missing_ok=True)
    _cleanup_stale_seed_rows()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed/Cleanup data for admin console Playwright regression.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed_parser = subparsers.add_parser("seed")
    seed_parser.add_argument("--output", required=True, help="Path to seed metadata JSON.")

    cleanup_parser = subparsers.add_parser("cleanup")
    cleanup_parser.add_argument("--input", required=True, help="Path to seed metadata JSON.")

    args = parser.parse_args()

    if args.command == "seed":
        return _create_seed(Path(args.output))
    if args.command == "cleanup":
        return _cleanup_seed(Path(args.input))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
