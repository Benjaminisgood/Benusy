from typing import Iterator

from sqlmodel import SQLModel, Session, create_engine

from app.core.config import settings

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.database_url, echo=settings.debug, connect_args=connect_args)


def _ensure_tasks_attachments_column() -> None:
    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as conn:
        table_exists = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'"
        ).first()
        if table_exists is None:
            return

        columns = conn.exec_driver_sql("PRAGMA table_info(tasks)").all()
        has_attachments = any(row[1] == "attachments" for row in columns)
        if not has_attachments:
            conn.exec_driver_sql(
                "ALTER TABLE tasks ADD COLUMN attachments TEXT NOT NULL DEFAULT '[]'"
            )


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)
    _ensure_tasks_attachments_column()


def drop_db_and_tables() -> None:
    SQLModel.metadata.drop_all(engine)


def rebuild_db() -> None:
    drop_db_and_tables()
    create_db_and_tables()


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
