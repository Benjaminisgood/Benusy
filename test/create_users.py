#!/usr/bin/env python3

import sys
from pathlib import Path

from sqlmodel import Session, select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.security import get_password_hash
from app.db.database import create_db_and_tables, engine
from app.models import (
    DouyinAccount,
    ReviewStatus,
    Role,
    User,
    WeiboAccount,
    XiaohongshuAccount,
)


def _create_admins(session: Session) -> None:
    default_admins = [
        ("yangliwei@admin", "13000000001"),
        ("lingxulong@admin", "13000000002"),
    ]
    created = False
    for account, phone in default_admins:
        existing = session.exec(select(User).where(User.email == account)).first()
        if existing:
            continue
        admin = User(
            email=account,
            phone=phone,
            username=account,
            display_name=account,
            city="N/A",
            category="operations",
            tags="admin",
            hashed_password=get_password_hash("ilovemoney"),
            role=Role.admin,
            review_status=ReviewStatus.approved,
        )
        session.add(admin)
        created = True
    if created:
        session.commit()
    print("Default admins ready: yangliwei@admin / lingxulong@admin (password: ilovemoney)")


def _create_blogger(
    session: Session,
    *,
    email: str,
    phone: str,
    username: str,
    platform: str,
) -> None:
    existing = session.exec(select(User).where(User.email == email)).first()
    if existing:
        print(f"User already exists: {email}")
        return

    blogger = User(
        email=email,
        phone=phone,
        username=username,
        display_name=username,
        city="Shanghai",
        category="general",
        tags="demo",
        hashed_password=get_password_hash("password123"),
        role=Role.blogger,
        review_status=ReviewStatus.approved,
    )
    session.add(blogger)
    session.commit()
    session.refresh(blogger)

    if platform == "douyin":
        session.add(DouyinAccount(user_id=blogger.id, account_name=username, account_id=f"{username}_dy"))
    elif platform == "xiaohongshu":
        session.add(XiaohongshuAccount(user_id=blogger.id, account_name=username, account_id=f"{username}_xhs"))
    else:
        session.add(WeiboAccount(user_id=blogger.id, account_name=username, account_id=f"{username}_wb"))

    session.commit()
    print(f"Created blogger: {email} / password123 ({platform})")


def main() -> int:
    create_db_and_tables()
    with Session(engine) as session:
        _create_admins(session)
        _create_blogger(
            session,
            email="blogger1@example.com",
            phone="13100000001",
            username="blogger1",
            platform="douyin",
        )
        _create_blogger(
            session,
            email="blogger2@example.com",
            phone="13100000002",
            username="blogger2",
            platform="xiaohongshu",
        )
        _create_blogger(
            session,
            email="blogger3@example.com",
            phone="13100000003",
            username="blogger3",
            platform="weibo",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
