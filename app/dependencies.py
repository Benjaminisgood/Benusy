from typing import Annotated, Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session, select

from app.core.config import settings
from app.core.security import decode_access_token
from app.db.database import get_session
from app.models import ReviewStatus, Role, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_v1_prefix}/auth/token")


def get_db() -> Generator[Session, None, None]:
    yield from get_session()


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
    except ValueError:
        raise credentials_exception

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    user = db.exec(select(User).where(User.id == int(user_id))).first()
    if not user:
        raise credentials_exception
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")
    return current_user


async def get_current_approved_blogger(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    if current_user.role != Role.blogger:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Blogger role required")
    if current_user.review_status != ReviewStatus.approved:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account not approved")
    return current_user


async def get_current_active_admin_user(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    if current_user.role != Role.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough privileges")
    return current_user
