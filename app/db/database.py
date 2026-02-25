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


def _ensure_tasks_accept_limit_column() -> None:
    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as conn:
        table_exists = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'"
        ).first()
        if table_exists is None:
            return

        columns = conn.exec_driver_sql("PRAGMA table_info(tasks)").all()
        has_accept_limit = any(row[1] == "accept_limit" for row in columns)
        if not has_accept_limit:
            conn.exec_driver_sql("ALTER TABLE tasks ADD COLUMN accept_limit INTEGER")


def _ensure_payout_infos_columns() -> None:
    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as conn:
        table_exists = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='payout_infos'"
        ).first()
        if table_exists is None:
            return

        columns = conn.exec_driver_sql("PRAGMA table_info(payout_infos)").all()
        existing = {row[1] for row in columns}
        target_columns: dict[str, str] = {
            "bank_description": "TEXT",
            "wechat_id": "TEXT",
            "wechat_phone": "TEXT",
            "wechat_qr_url": "TEXT",
            "alipay_phone": "TEXT",
            "alipay_account_name": "TEXT",
            "alipay_qr_url": "TEXT",
        }

        for column_name, column_type in target_columns.items():
            if column_name in existing:
                continue
            conn.exec_driver_sql(
                f"ALTER TABLE payout_infos ADD COLUMN {column_name} {column_type}"
            )


def create_db_and_tables() -> None:
    # Ensure all SQLModel table classes are imported before metadata.create_all.
    import app.models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    _ensure_tasks_attachments_column()
    _ensure_tasks_accept_limit_column()
    _ensure_payout_infos_columns()


def drop_db_and_tables() -> None:
    SQLModel.metadata.drop_all(engine)


def rebuild_db() -> None:
    drop_db_and_tables()
    create_db_and_tables()


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
