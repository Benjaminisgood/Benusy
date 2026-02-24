from enum import Enum
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


class SocialPlatform(str, Enum):
    douyin = "douyin"
    xiaohongshu = "xiaohongshu"
    weibo = "weibo"


class SocialAccountBase(SQLModel):
    account_name: str
    account_id: str = Field(index=True)
    profile_url: Optional[str] = None
    follower_count: int = Field(default=0, ge=0)


class DouyinAccount(SocialAccountBase, table=True):
    __tablename__ = "douyin_accounts"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    sec_uid: Optional[str] = None

    user: "User" = Relationship(back_populates="douyin_accounts")


class XiaohongshuAccount(SocialAccountBase, table=True):
    __tablename__ = "xiaohongshu_accounts"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    xhs_user_id: Optional[str] = None

    user: "User" = Relationship(back_populates="xiaohongshu_accounts")


class WeiboAccount(SocialAccountBase, table=True):
    __tablename__ = "weibo_accounts"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    weibo_uid: Optional[str] = None

    user: "User" = Relationship(back_populates="weibo_accounts")
