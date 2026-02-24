from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


class PayoutMethod(str, Enum):
    bank_card = "bank_card"
    alipay = "alipay"
    wechat_pay = "wechat_pay"
    paypal = "paypal"
    other = "other"


class PayoutInfo(SQLModel, table=True):
    __tablename__ = "payout_infos"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True, sa_column_kwargs={"unique": True})
    payout_method: PayoutMethod = Field(default=PayoutMethod.bank_card)
    account_name: str
    account_no: str
    account_qr_url: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    user: "User" = Relationship(back_populates="payout_info")
