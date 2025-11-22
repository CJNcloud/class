from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, model_validator


class UserBase(BaseModel):
    username: str = Field(min_length=3, max_length=50)


class UserCreate(UserBase):
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    phone: str = Field(..., min_length=1, max_length=20, description="手机号")
    email: str = Field(..., min_length=1, max_length=100, description="邮箱")
    password: str = Field(..., min_length=6, max_length=128, description="密码")


class UserUpdate(BaseModel):
    username: Optional[str] = Field(default=None, min_length=3, max_length=50, description="用户名")
    phone: Optional[str] = Field(default=None, min_length=1, max_length=20, description="手机号")
    email: Optional[str] = Field(default=None, min_length=1, max_length=100, description="邮箱")
    password: Optional[str] = Field(default=None, min_length=6, max_length=128, description="密码")
    
    @model_validator(mode='before')
    @classmethod
    def convert_empty_strings_to_none(cls, data):
        """将空字符串转换为 None，以便跳过验证"""
        if isinstance(data, dict):
            return {k: None if v == "" else v for k, v in data.items()}
        return data


class UserOut(BaseModel):
    id: int
    username: str
    phone: str
    email: str
    created_at: datetime
    role: str

    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    login_identifier: Optional[str] = Field(default=None, description="登录标识：可以是用户名、邮箱或手机号")
    username: Optional[str] = Field(default=None, description="用户名（兼容字段，等同于login_identifier）")
    password: str
    
    @model_validator(mode='after')
    def validate_identifier(self):
        # 如果提供了username但没有login_identifier，则使用username
        if self.username and not self.login_identifier:
            self.login_identifier = self.username
        # 如果两个都没提供，抛出错误
        if not self.login_identifier:
            raise ValueError("必须提供 login_identifier 或 username")
        return self


class UserResetPassword(BaseModel):
    identifier: str = Field(..., description="用户标识：用户名、手机号或邮箱")
    new_password: str = Field(..., min_length=6, max_length=128, description="新密码")


class AdminChangePassword(BaseModel):
    """管理员修改用户密码的请求"""
    new_password: str = Field(..., min_length=6, max_length=128, description="新密码")


class ForgotPassword(BaseModel):
    """用户找回密码的请求"""
    identifier: str = Field(..., description="用户标识：用户名、手机号或邮箱")


class ForgotPasswordResponse(BaseModel):
    """用户找回密码的响应"""
    message: str = Field(..., description="响应消息")
    new_password: str = Field(..., description="新生成的随机5位密码")
    user_id: int = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")


class UserLoginInfo(BaseModel):
    id: int = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")
    role: str = Field(..., description="用户角色")


class UserLoginResponse(BaseModel):
    message: str = Field(..., description="响应消息")
    user: UserLoginInfo = Field(..., description="用户信息")
    role: str = Field(..., description="用户角色：admin 或 user，用于前端权限控制和页面跳转")


# Group schemas
class GroupBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    group_type: Optional[str] = Field(default=None, max_length=50)
    note: Optional[str] = Field(default=None, max_length=255)
    announce_limit: int = 0
    announce: Optional[str] = None
    avatar_url: Optional[str] = Field(default=None, max_length=255)
    member_limit: int = 200


class GroupCreateRequestCreate(GroupBase):
    created_by_user_id: int


class GroupUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    group_type: Optional[str] = Field(default=None, max_length=50)
    note: Optional[str] = Field(default=None, max_length=255)
    announce_limit: Optional[int] = None
    announce: Optional[str] = None
    avatar_url: Optional[str] = Field(default=None, max_length=255)
    pin: Optional[str] = Field(default=None)
    member_limit: Optional[int] = None


class GroupOut(BaseModel):
    id: int
    name: str
    group_type: Optional[str]
    note: Optional[str]
    announce_limit: int
    member_limit: int
    announce: Optional[str]
    avatar_url: Optional[str]
    created_by_user_id: int
    created_at: datetime
    pin: str
    audit_state: str
    approved_report_count: int = Field(default=0, description="被管理员通过的举报次数（违规次数）")

    class Config:
        from_attributes = True


class UserGroupOut(BaseModel):
    """用户自己的群聊列表返回格式，包含用户级别的置顶状态"""
    id: int
    name: str
    group_type: Optional[str]
    note: Optional[str]
    announce_limit: int
    member_limit: int
    announce: Optional[str]
    avatar_url: Optional[str]
    created_by_user_id: int
    created_at: datetime
    pin: str  # 用户级别的置顶状态（来自GroupMember表）
    audit_state: str
    approved_report_count: int = Field(default=0, description="被管理员通过的举报次数（违规次数）")

    class Config:
        from_attributes = True


class GroupAuditAction(BaseModel):
    action: str = Field(pattern="^(approve|reject)$")


class GroupPinRequest(BaseModel):
    is_pinned: bool = Field(..., description="是否置顶：true=置顶, false=取消置顶")


class GroupUpdateRequestCreate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    group_type: Optional[str] = Field(default=None, max_length=50)
    note: Optional[str] = Field(default=None, max_length=255)
    announce_limit: Optional[int] = None
    announce: Optional[str] = None
    avatar_url: Optional[str] = Field(default=None, max_length=255)
    member_limit: Optional[int] = None


class GroupUpdateRequestOut(BaseModel):
    id: int
    group_id: int
    requested_by_user_id: int
    name: Optional[str] = None
    group_type: Optional[str] = None
    note: Optional[str] = None
    announce_limit: Optional[int] = None
    announce: Optional[str] = None
    avatar_url: Optional[str] = None
    member_limit: Optional[int] = None
    created_at: datetime
    audit_state: str

    class Config:
        from_attributes = True


class GroupCreateRequestOut(BaseModel):
    id: int
    name: str
    group_type: Optional[str]
    note: Optional[str]
    announce_limit: int
    announce: Optional[str]
    avatar_url: Optional[str]
    member_limit: int
    created_by_user_id: int
    created_at: datetime
    audit_state: str

    class Config:
        from_attributes = True


# Group member schemas
class GroupMemberBase(BaseModel):
    user_id: int
    nickname: Optional[str] = Field(default=None, max_length=50)
    avatar_url: Optional[str] = Field(default=None, max_length=255)


class GroupMemberCreate(GroupMemberBase):
    pass


class GroupMemberOut(BaseModel):
    id: int
    group_id: int
    user_id: int
    nickname: Optional[str]
    avatar_url: Optional[str]
    is_group_admin: bool
    joined_at: datetime
    approved_report_count: int = Field(default=0, description="被管理员通过的举报次数")

    class Config:
        from_attributes = True


class GroupJoinRequestCreate(BaseModel):
    user_id: int
    reason: str = Field(..., max_length=255)


class GroupJoinRequestOut(BaseModel):
    id: int
    group_id: int
    user_id: int
    nickname: Optional[str]
    avatar_url: Optional[str]
    created_at: datetime
    audit_state: str
    reason: Optional[str]

    class Config:
        from_attributes = True


# Report schemas
class ReportCreate(BaseModel):
    user_id: int
    report_content: str = Field(..., min_length=1)
    reported_user_id: Optional[int] = None
    group_id: Optional[int] = None
    chat_message_id: Optional[int] = None


class ReportOut(BaseModel):
    id: int
    user_id: int
    report_content: str
    reported_user_id: Optional[int]
    group_id: Optional[int]
    chat_message_id: Optional[int]
    created_at: datetime
    audit_state: str

    class Config:
        from_attributes = True


# Chat message schemas
class ChatCreate(BaseModel):
    chat_no: Optional[int] = None
    user_id: int
    sender_name: Optional[str] = Field(default=None, max_length=50)
    content: str = Field(..., min_length=1)


class ChatOut(BaseModel):
    id: int
    chat_no: int
    group_id: int
    user_id: int
    sender_name: Optional[str]
    content: str
    sent_at: datetime

    class Config:
        from_attributes = True

