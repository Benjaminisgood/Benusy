import asyncio

from sqlmodel import Session, select

from app.core.config import settings
from app.db.database import engine
from app.models import Assignment, AssignmentStatus
from app.services.sync import sync_assignment_metrics_once


async def metrics_update_loop(stop_event: asyncio.Event) -> None:
    interval = settings.metrics_update_interval_seconds
    if interval <= 0:
        return

    try:
        while not stop_event.is_set():
            with Session(engine) as session:
                assignments = session.exec(
                    select(Assignment).where(
                        Assignment.status.in_([
                            AssignmentStatus.submitted,
                            AssignmentStatus.in_review,
                        ])
                    )
                ).all()

                for assignment in assignments:
                    await sync_assignment_metrics_once(session, assignment)

                session.commit()

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue
    except asyncio.CancelledError:
        return
