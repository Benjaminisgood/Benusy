from sqlmodel import Session

from app.models import UserActivityLog


def log_activity(
    session: Session,
    *,
    user_id: int,
    action_type: str,
    title: str,
    detail: str | None = None,
) -> None:
    session.add(
        UserActivityLog(
            user_id=user_id,
            action_type=action_type,
            title=title,
            detail=detail,
        )
    )
