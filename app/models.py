from datetime import datetime, timezone, timedelta
import enum
from sqlalchemy import String, Integer, DateTime, Text, ForeignKey, Enum as SAEnum, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base

# 中国时区 (UTC+8)
CHINA_TZ = timezone(timedelta(hours=8))

def get_china_time():
    """获取中国时区的当前时间"""
    return datetime.now(CHINA_TZ).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_china_time, nullable=False)
    role: Mapped[str] = mapped_column(SAEnum("admin", "user", name="user_role"), nullable=False, default="user", server_default="user")


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column("GroupID", Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column("GroupName", String(100), nullable=False, index=True)
    group_type: Mapped[str | None] = mapped_column("GroupType", String(50), nullable=True)
    note: Mapped[str | None] = mapped_column("GroupNote", String(255), nullable=True)
    announce_limit: Mapped[int] = mapped_column("GroupAnnounceLimit", Integer, nullable=False, default=0, server_default="0")
    member_limit: Mapped[int] = mapped_column("GroupMemberLimit", Integer, nullable=False, default=200, server_default="200")
    announce: Mapped[str | None] = mapped_column("GroupAnnounce", Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column("GroupAvatar", String(255), nullable=True)
    created_by_user_id: Mapped[int] = mapped_column("UserID", Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column("CreateTime", DateTime, default=get_china_time, nullable=False)
    pin: Mapped[str] = mapped_column("GroupPin", SAEnum("未置顶", "已置顶", name="group_pin_state"), nullable=False, default="未置顶", server_default="未置顶")
    audit_state: Mapped[str] = mapped_column(
        "GroupAuditState",
        SAEnum("未审核", "审核未通过", "审核通过", name="group_audit_state"),
        nullable=False,
        default="未审核",
        server_default="未审核",
    )


class GroupMember(Base):
    __tablename__ = "group_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column("GroupID", Integer, ForeignKey("groups.GroupID"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column("GroupMemberID", Integer, ForeignKey("users.id"), index=True, nullable=False)
    nickname: Mapped[str | None] = mapped_column("GroupMemberName", String(50), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column("GroupMemberAvatar", String(255), nullable=True)
    is_group_admin: Mapped[bool] = mapped_column("WhetherGroupAd", Boolean, nullable=False, default=False, server_default="0")
    joined_at: Mapped[datetime] = mapped_column("JoinGroupTime", DateTime, default=get_china_time, nullable=False)
    pin: Mapped[str] = mapped_column("GroupPin", SAEnum("未置顶", "已置顶", name="group_member_pin"), nullable=False, default="未置顶", server_default="未置顶")


class GroupUpdateRequest(Base):
    __tablename__ = "group_update_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("groups.GroupID"), index=True, nullable=False)
    requested_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    group_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    announce_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    announce: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    member_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_china_time, nullable=False)
    audit_state: Mapped[str] = mapped_column(
        SAEnum("未审核", "审核未通过", "审核通过", name="group_update_audit_state"),
        nullable=False,
        default="未审核",
        server_default="未审核",
    )


class GroupCreateRequest(Base):
    __tablename__ = "group_create_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    group_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    announce_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    announce: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    member_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=200, server_default="200")
    created_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_china_time, nullable=False)
    audit_state: Mapped[str] = mapped_column(
        SAEnum("未审核", "审核未通过", "审核通过", name="group_create_audit_state"),
        nullable=False,
        default="未审核",
        server_default="未审核",
    )


class GroupJoinRequest(Base):
    __tablename__ = "group_join_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("groups.GroupID"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(50), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_china_time, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    audit_state: Mapped[str] = mapped_column(
        SAEnum("未审核", "审核未通过", "审核通过", name="group_join_audit_state"),
        nullable=False,
        default="未审核",
        server_default="未审核",
    )


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column("ReportNo", Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column("UserID", Integer, ForeignKey("users.id"), index=True, nullable=False)
    report_content: Mapped[str] = mapped_column("ReportContent", Text, nullable=False)
    # Optional targets
    reported_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    group_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("groups.GroupID"), nullable=True)
    chat_message_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("chat_messages.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=get_china_time, nullable=False)
    audit_state: Mapped[str] = mapped_column(
        "AuditState",
        SAEnum("未审核", "审核通过", "审核未通过", name="report_audit_state"),
        nullable=False,
        default="未审核",
        server_default="未审核",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_no: Mapped[int] = mapped_column("ChatNo", Integer, index=True, nullable=False)
    group_id: Mapped[int] = mapped_column("GroupID", Integer, ForeignKey("groups.GroupID"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column("UserID", Integer, ForeignKey("users.id"), index=True, nullable=False)
    sender_name: Mapped[str | None] = mapped_column("GroupMemberName", String(50), nullable=True)
    content: Mapped[str] = mapped_column("ChatContent", Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column("ChatSendTime", DateTime, default=get_china_time, nullable=False)

