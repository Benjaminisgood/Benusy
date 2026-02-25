from __future__ import annotations

from datetime import datetime
import logging
from typing import Type

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlmodel import Session, select

from app.core.security import get_password_hash, verify_password
from app.dependencies import get_current_active_user, get_db
from app.models import (
    DouyinAccount,
    PayoutInfo,
    PayoutMethod,
    SocialPlatform,
    User,
    UserActivityLog,
    WeiboAccount,
    XiaohongshuAccount,
)
from app.schemas.user import (
    PayoutInfoRead,
    PayoutQrUploadRead,
    PayoutInfoUpsert,
    PlatformAccountCreateRequest,
    PlatformAccountRead,
    PlatformAccountUpdateRequest,
    SocialAccountRead,
    UserActivityRead,
    UserPasswordUpdate,
    UserProfileUpdate,
    UserRead,
)
from app.services.activity import log_activity
from app.services.oss import OSSConfigError, upload_payout_qr_code

router = APIRouter(prefix="/users", tags=["users"])
logger = logging.getLogger(__name__)


PlatformModel = Type[DouyinAccount] | Type[XiaohongshuAccount] | Type[WeiboAccount]


def _ensure_relations_loaded(user: User) -> None:
    _ = user.douyin_accounts
    _ = user.xiaohongshu_accounts
    _ = user.weibo_accounts
    _ = user.payout_info


def _resolve_platform_model(platform: SocialPlatform) -> PlatformModel:
    if platform == SocialPlatform.douyin:
        return DouyinAccount
    if platform == SocialPlatform.xiaohongshu:
        return XiaohongshuAccount
    return WeiboAccount


def _platform_label(platform: SocialPlatform) -> str:
    if platform == SocialPlatform.douyin:
        return "抖音"
    if platform == SocialPlatform.xiaohongshu:
        return "小红书"
    return "微博"


def _all_user_accounts(db: Session, user_id: int) -> list[SocialAccountRead]:
    accounts: list[SocialAccountRead] = []

    for account in db.exec(select(DouyinAccount).where(DouyinAccount.user_id == user_id)).all():
        accounts.append(
            SocialAccountRead(
                id=account.id,
                platform=SocialPlatform.douyin.value,
                account_name=account.account_name,
                account_id=account.account_id,
                profile_url=account.profile_url,
                follower_count=account.follower_count,
            )
        )

    for account in db.exec(select(XiaohongshuAccount).where(XiaohongshuAccount.user_id == user_id)).all():
        accounts.append(
            SocialAccountRead(
                id=account.id,
                platform=SocialPlatform.xiaohongshu.value,
                account_name=account.account_name,
                account_id=account.account_id,
                profile_url=account.profile_url,
                follower_count=account.follower_count,
            )
        )

    for account in db.exec(select(WeiboAccount).where(WeiboAccount.user_id == user_id)).all():
        accounts.append(
            SocialAccountRead(
                id=account.id,
                platform=SocialPlatform.weibo.value,
                account_name=account.account_name,
                account_id=account.account_id,
                profile_url=account.profile_url,
                follower_count=account.follower_count,
            )
        )

    return accounts


def _legacy_payout_fields(payload: PayoutInfoUpsert) -> dict[str, str | None]:
    if payload.payout_method == PayoutMethod.wechat_pay:
        return {
            "account_name": payload.wechat_id or "",
            "account_no": payload.wechat_phone or "",
            "account_qr_url": payload.wechat_qr_url,
        }
    if payload.payout_method == PayoutMethod.alipay:
        return {
            "account_name": payload.alipay_account_name or "",
            "account_no": payload.alipay_phone or "",
            "account_qr_url": payload.alipay_qr_url,
        }
    return {
        "account_name": "",
        "account_no": "",
        "account_qr_url": None,
    }


@router.get("/me", response_model=UserRead)
def read_current_user(current_user: User = Depends(get_current_active_user)) -> User:
    _ensure_relations_loaded(current_user)
    return current_user


@router.patch("/me/profile", response_model=UserRead)
def update_current_user_profile(
    payload: UserProfileUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> User:
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        _ensure_relations_loaded(current_user)
        return current_user

    for field_name, value in updates.items():
        if field_name == "tags" and value is not None:
            setattr(current_user, field_name, ",".join([tag.strip() for tag in value if tag.strip()]))
        else:
            setattr(current_user, field_name, value)

    current_user.updated_at = datetime.utcnow()
    db.add(current_user)
    log_activity(
        db,
        user_id=current_user.id,
        action_type="profile_update",
        title="更新个人资料",
        detail="更新了基础资料信息",
    )
    db.commit()
    db.refresh(current_user)
    _ensure_relations_loaded(current_user)
    return current_user


@router.post(
    "/me/accounts/{platform}",
    response_model=PlatformAccountRead,
    status_code=status.HTTP_201_CREATED,
)
def add_platform_account(
    platform: SocialPlatform,
    payload: PlatformAccountCreateRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> PlatformAccountRead:
    model = _resolve_platform_model(platform)
    existing = db.exec(
        select(model)
        .where(model.user_id == current_user.id)
        .where(model.account_id == payload.account_id)
    ).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account already linked")

    account = model(
        user_id=current_user.id,
        account_name=payload.account_name,
        account_id=payload.account_id,
        profile_url=payload.profile_url,
        follower_count=payload.follower_count,
    )
    db.add(account)

    current_user.updated_at = datetime.utcnow()
    db.add(current_user)
    log_activity(
        db,
        user_id=current_user.id,
        action_type="social_add",
        title=f"新增{_platform_label(platform)}账号",
        detail=f"账号ID: {payload.account_id}",
    )
    db.commit()
    db.refresh(account)
    return PlatformAccountRead.model_validate(account)


@router.patch("/me/accounts/{platform}/{account_id}", response_model=PlatformAccountRead)
def update_platform_account(
    platform: SocialPlatform,
    account_id: int,
    payload: PlatformAccountUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> PlatformAccountRead:
    model = _resolve_platform_model(platform)
    account = db.exec(
        select(model)
        .where(model.id == account_id)
        .where(model.user_id == current_user.id)
    ).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return PlatformAccountRead.model_validate(account)

    if "account_id" in updates:
        duplicate = db.exec(
            select(model)
            .where(model.user_id == current_user.id)
            .where(model.account_id == updates["account_id"])
            .where(model.id != account_id)
        ).first()
        if duplicate:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account ID already exists")

    for field_name, value in updates.items():
        setattr(account, field_name, value)

    current_user.updated_at = datetime.utcnow()
    db.add(account)
    db.add(current_user)
    log_activity(
        db,
        user_id=current_user.id,
        action_type="social_update",
        title=f"更新{_platform_label(platform)}账号",
        detail=f"账号ID: {account.account_id}",
    )
    db.commit()
    db.refresh(account)
    return PlatformAccountRead.model_validate(account)


@router.delete("/me/accounts/{platform}/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_platform_account(
    platform: SocialPlatform,
    account_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> None:
    model = _resolve_platform_model(platform)
    account = db.exec(
        select(model)
        .where(model.id == account_id)
        .where(model.user_id == current_user.id)
    ).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    total_accounts = len(_all_user_accounts(db, current_user.id))
    if total_accounts <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one social account must remain",
        )

    deleted_account_id = account.account_id
    db.delete(account)
    current_user.updated_at = datetime.utcnow()
    db.add(current_user)
    log_activity(
        db,
        user_id=current_user.id,
        action_type="social_delete",
        title=f"删除{_platform_label(platform)}账号",
        detail=f"账号ID: {deleted_account_id}",
    )
    db.commit()


@router.get("/me/social-accounts", response_model=list[SocialAccountRead])
def list_my_social_accounts(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> list[SocialAccountRead]:
    return _all_user_accounts(db, current_user.id)


@router.post("/me/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: UserPasswordUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> None:
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

    if verify_password(payload.new_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password must be different")

    current_user.hashed_password = get_password_hash(payload.new_password)
    current_user.updated_at = datetime.utcnow()
    db.add(current_user)
    log_activity(
        db,
        user_id=current_user.id,
        action_type="password_change",
        title="修改账号密码",
        detail="密码已更新",
    )
    db.commit()


@router.get("/me/payout-info", response_model=PayoutInfoRead | None)
def get_my_payout_info(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> PayoutInfo | None:
    return db.exec(select(PayoutInfo).where(PayoutInfo.user_id == current_user.id)).first()


@router.put("/me/payout-info", response_model=PayoutInfoRead)
def upsert_my_payout_info(
    payload: PayoutInfoUpsert,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> PayoutInfo:
    updates = payload.model_dump()
    updates.update(_legacy_payout_fields(payload))
    payout = db.exec(select(PayoutInfo).where(PayoutInfo.user_id == current_user.id)).first()
    if payout is None:
        payout = PayoutInfo(user_id=current_user.id, **updates)
    else:
        for field_name, value in updates.items():
            setattr(payout, field_name, value)
        payout.updated_at = datetime.utcnow()

    db.add(payout)
    log_activity(
        db,
        user_id=current_user.id,
        action_type="payout_update",
        title="更新收款信息",
        detail=f"收款方式: {payload.payout_method.value}",
    )
    db.commit()
    db.refresh(payout)
    return payout


@router.post(
    "/me/payout-info/qrcode",
    response_model=PayoutQrUploadRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_my_payout_qr_code(
    method: PayoutMethod = Query(..., description="仅支持 wechat_pay 或 alipay"),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
) -> PayoutQrUploadRead:
    if method not in {PayoutMethod.wechat_pay, PayoutMethod.alipay}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅微信或支付宝支持上传收款码",
        )
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")

    try:
        url, object_key = upload_payout_qr_code(
            file=file,
            user_id=current_user.id,
            method=method.value,
        )
    except OSSConfigError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    except Exception as exc:
        logger.exception("upload payout qrcode failed user_id=%s filename=%s", current_user.id, file.filename)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"上传收款码到 OSS 失败: {exc}",
        )
    finally:
        await file.close()

    return PayoutQrUploadRead(method=method, object_key=object_key, url=url)


@router.get("/me/history", response_model=list[UserActivityRead])
def list_my_history(
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> list[UserActivityLog]:
    return db.exec(
        select(UserActivityLog)
        .where(UserActivityLog.user_id == current_user.id)
        .order_by(UserActivityLog.created_at.desc())
        .limit(limit)
    ).all()
