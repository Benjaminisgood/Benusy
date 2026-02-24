from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import or_
from sqlmodel import Session, select

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash, verify_password
from app.dependencies import get_db
from app.models import (
    DouyinAccount,
    ReviewStatus,
    Role,
    User,
    WeiboAccount,
    XiaohongshuAccount,
)
from app.schemas.auth import Token
from app.schemas.user import UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


def _create_platform_accounts(db: Session, user_id: int, user_in: UserCreate) -> None:
    for account in user_in.douyin_accounts:
        db.add(
            DouyinAccount(
                user_id=user_id,
                account_name=account.account_name,
                account_id=account.account_id,
                profile_url=account.profile_url,
                follower_count=account.follower_count,
            )
        )
    for account in user_in.xiaohongshu_accounts:
        db.add(
            XiaohongshuAccount(
                user_id=user_id,
                account_name=account.account_name,
                account_id=account.account_id,
                profile_url=account.profile_url,
                follower_count=account.follower_count,
            )
        )
    for account in user_in.weibo_accounts:
        db.add(
            WeiboAccount(
                user_id=user_id,
                account_name=account.account_name,
                account_id=account.account_id,
                profile_url=account.profile_url,
                follower_count=account.follower_count,
            )
        )


def _has_any_platform_account(user_in: UserCreate) -> bool:
    return bool(user_in.douyin_accounts or user_in.xiaohongshu_accounts or user_in.weibo_accounts)


def _ensure_relations_loaded(user: User) -> None:
    _ = user.douyin_accounts
    _ = user.xiaohongshu_accounts
    _ = user.weibo_accounts


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register_user(user_in: UserCreate, db: Session = Depends(get_db)) -> User:
    if not _has_any_platform_account(user_in):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one social platform account is required",
        )

    existing_email = db.exec(select(User).where(User.email == user_in.email)).first()
    if existing_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    if user_in.phone:
        existing_phone = db.exec(select(User).where(User.phone == user_in.phone)).first()
        if existing_phone:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Phone already registered")

    user = User(
        email=user_in.email,
        phone=user_in.phone,
        username=user_in.username,
        display_name=user_in.display_name,
        real_name=user_in.real_name,
        id_no=user_in.id_no,
        city=user_in.city,
        category=user_in.category,
        tags=",".join(user_in.tags),
        follower_total=user_in.follower_total,
        avg_views=user_in.avg_views,
        hashed_password=get_password_hash(user_in.password),
        is_active=True,
        review_status=ReviewStatus.pending,
        role=Role.blogger,
        updated_at=datetime.utcnow(),
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    _create_platform_accounts(db, user.id, user_in)
    db.commit()
    db.refresh(user)
    _ensure_relations_loaded(user)
    return user


@router.post("/token", response_model=Token)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    remember_me: bool = Form(default=False),
    db: Session = Depends(get_db),
) -> Token:
    user = db.exec(
        select(User).where(
            or_(
                User.email == form_data.username,
                User.phone == form_data.username,
                User.username == form_data.username,
            )
        )
    ).first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")

    if user.role == Role.blogger and user.review_status != ReviewStatus.approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account review status: {user.review_status.value}",
        )

    expires_delta = None
    if remember_me:
        expires_delta = timedelta(days=settings.remember_me_access_token_expire_days)

    access_token = create_access_token(
        data={"sub": str(user.id), "role": user.role.value},
        expires_delta=expires_delta,
    )
    return Token(access_token=access_token, token_type="bearer")
