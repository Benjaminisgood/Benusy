from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class SettlementRecord(SQLModel, table=True):
    __tablename__ = "settlement_records"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    admin_id: int = Field(foreign_key="users.id", index=True)
    amount: float = Field(default=0.0, gt=0)
    note: Optional[str] = None
    paid_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
