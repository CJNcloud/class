import logging
import secrets
import string
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import (
    UserCreate, UserOut, UserUpdate, UserLogin, UserResetPassword, 
    UserLoginResponse, UserLoginInfo, AdminChangePassword, 
    ForgotPassword, ForgotPasswordResponse
)
from ..security import hash_password, verify_password


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["users"])


@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    logger.info(f"创建用户请求: username={payload.username}, phone={payload.phone}, email={payload.email}")
    # Check uniqueness
    existing_username = db.scalar(select(User).where(User.username == payload.username))
    if existing_username:
        logger.warning(f"创建用户失败: 用户名已存在 username={payload.username}")
        raise HTTPException(status_code=400, detail="用户名已存在")
    
    existing_phone = db.scalar(select(User).where(User.phone == payload.phone))
    if existing_phone:
        logger.warning(f"创建用户失败: 手机号已存在 phone={payload.phone}")
        raise HTTPException(status_code=400, detail="手机号已存在")
    
    existing_email = db.scalar(select(User).where(User.email == payload.email))
    if existing_email:
        logger.warning(f"创建用户失败: 邮箱已存在 email={payload.email}")
        raise HTTPException(status_code=400, detail="邮箱已存在")

    user = User(
        username=payload.username,
        phone=payload.phone,
        email=payload.email,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info(f"用户创建成功: id={user.id}, username={user.username}, phone={user.phone}, email={user.email}")
    return user


@router.get("/", response_model=List[UserOut])
def list_users(
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    q: Optional[str] = Query(None, description="按用户名模糊搜索"),
):
    logger.info(f"查询用户列表: skip={skip}, limit={limit}, q={q}")
    stmt = select(User).order_by(User.id).offset(skip).limit(limit)
    if q:
        stmt = select(User).where(User.username.like(f"%{q}%")).order_by(User.id).offset(skip).limit(limit)
    users = db.scalars(stmt).all()
    logger.info(f"查询用户列表成功: 返回 {len(users)} 个用户")
    return users


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: Session = Depends(get_db)):
    logger.info(f"查询用户: user_id={user_id}")
    user = db.get(User, user_id)
    if not user:
        logger.warning(f"查询用户失败: 用户不存在 user_id={user_id}")
        raise HTTPException(status_code=404, detail="用户不存在")
    logger.info(f"查询用户成功: user_id={user_id}, username={user.username}")
    return user


@router.put("/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db)):
    logger.info(f"更新用户请求: user_id={user_id}, fields={[k for k, v in payload.model_dump().items() if v is not None]}")
    user = db.get(User, user_id)
    if not user:
        logger.warning(f"更新用户失败: 用户不存在 user_id={user_id}")
        raise HTTPException(status_code=404, detail="用户不存在")

    # 更新用户名
    if payload.username is not None:
        if payload.username != user.username:
            existing_username = db.scalar(select(User).where((User.username == payload.username) & (User.id != user_id)))
            if existing_username:
                logger.warning(f"更新用户失败: 用户名已存在 username={payload.username}")
                raise HTTPException(status_code=400, detail="用户名已存在")
            user.username = payload.username
            logger.info(f"更新用户名: user_id={user_id}, new_username={payload.username}")

    # 更新手机号
    if payload.phone is not None:
        if payload.phone != user.phone:
            existing_phone = db.scalar(select(User).where((User.phone == payload.phone) & (User.id != user_id)))
            if existing_phone:
                logger.warning(f"更新用户失败: 手机号已存在 phone={payload.phone}")
                raise HTTPException(status_code=400, detail="手机号已存在")
            user.phone = payload.phone
            logger.info(f"更新手机号: user_id={user_id}, new_phone={payload.phone}")

    # 更新邮箱
    if payload.email is not None:
        if payload.email != user.email:
            existing_email = db.scalar(select(User).where((User.email == payload.email) & (User.id != user_id)))
            if existing_email:
                logger.warning(f"更新用户失败: 邮箱已存在 email={payload.email}")
                raise HTTPException(status_code=400, detail="邮箱已存在")
            user.email = payload.email
            logger.info(f"更新邮箱: user_id={user_id}, new_email={payload.email}")

    # 更新密码
    if payload.password:
        user.hashed_password = hash_password(payload.password)
        logger.info(f"更新用户密码: user_id={user_id}")

    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info(f"用户更新成功: user_id={user_id}, username={user.username}, phone={user.phone}, email={user.email}")
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: Session = Depends(get_db)):
    logger.info(f"删除用户请求: user_id={user_id}")
    user = db.get(User, user_id)
    if not user:
        logger.warning(f"删除用户失败: 用户不存在 user_id={user_id}")
        raise HTTPException(status_code=404, detail="用户不存在")
    username = user.username
    
    # 级联删除所有关联数据
    try:
        # 1. 删除用户发送的聊天消息
        from ..models import ChatMessage
        chat_messages = db.query(ChatMessage).filter(ChatMessage.user_id == user_id).all()
        for msg in chat_messages:
            db.delete(msg)
        logger.info(f"删除用户聊天消息: user_id={user_id}, count={len(chat_messages)}")
        
        # 2. 删除用户相关的举报记录
        from ..models import Report
        reports = db.query(Report).filter(
            (Report.user_id == user_id) | (Report.reported_user_id == user_id)
        ).all()
        for report in reports:
            db.delete(report)
        logger.info(f"删除用户举报记录: user_id={user_id}, count={len(reports)}")
        
        # 3. 删除用户的入群申请
        from ..models import GroupJoinRequest
        join_requests = db.query(GroupJoinRequest).filter(GroupJoinRequest.user_id == user_id).all()
        for req in join_requests:
            db.delete(req)
        logger.info(f"删除用户入群申请: user_id={user_id}, count={len(join_requests)}")
        
        # 4. 删除用户的建群申请
        from ..models import GroupCreateRequest
        create_requests = db.query(GroupCreateRequest).filter(GroupCreateRequest.created_by_user_id == user_id).all()
        for req in create_requests:
            db.delete(req)
        logger.info(f"删除用户建群申请: user_id={user_id}, count={len(create_requests)}")
        
        # 5. 删除用户的群更新申请
        from ..models import GroupUpdateRequest
        update_requests = db.query(GroupUpdateRequest).filter(GroupUpdateRequest.requested_by_user_id == user_id).all()
        for req in update_requests:
            db.delete(req)
        logger.info(f"删除用户群更新申请: user_id={user_id}, count={len(update_requests)}")
        
        # 6. 删除用户的群成员身份
        from ..models import GroupMember
        group_members = db.query(GroupMember).filter(GroupMember.user_id == user_id).all()
        for member in group_members:
            db.delete(member)
        logger.info(f"删除用户群成员身份: user_id={user_id}, count={len(group_members)}")
        
        # 7. 删除用户创建的群组
        from ..models import Group
        groups = db.query(Group).filter(Group.created_by_user_id == user_id).all()
        for group in groups:
            # 删除该群组的所有聊天消息
            group_messages = db.query(ChatMessage).filter(ChatMessage.group_id == group.id).all()
            for msg in group_messages:
                db.delete(msg)
            # 删除该群组的所有成员
            group_members = db.query(GroupMember).filter(GroupMember.group_id == group.id).all()
            for member in group_members:
                db.delete(member)
            # 删除该群组的所有入群申请
            group_join_requests = db.query(GroupJoinRequest).filter(GroupJoinRequest.group_id == group.id).all()
            for req in group_join_requests:
                db.delete(req)
            # 删除该群组
            db.delete(group)
        logger.info(f"删除用户创建的群组: user_id={user_id}, count={len(groups)}")
        
        # 最后删除用户
        db.delete(user)
        db.commit()
        logger.info(f"用户删除成功: user_id={user_id}, username={username}")
    except Exception as e:
        db.rollback()
        logger.error(f"删除用户失败: user_id={user_id}, error={str(e)}")
        raise HTTPException(status_code=500, detail=f"删除用户失败: {str(e)}")
    
    return None


@router.post("/login", response_model=UserLoginResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    logger.info(f"用户登录请求: login_identifier={payload.login_identifier}")
    # 支持通过用户名、邮箱或手机号登录
    user = db.scalar(
        select(User).where(
            (User.username == payload.login_identifier) |
            (User.email == payload.login_identifier) |
            (User.phone == payload.login_identifier)
        )
    )
    if not user or not verify_password(payload.password, user.hashed_password):
        logger.warning(f"用户登录失败: 登录标识或密码错误 login_identifier={payload.login_identifier}")
        raise HTTPException(status_code=400, detail="登录标识或密码错误")
    logger.info(f"用户登录成功: user_id={user.id}, username={user.username}, role={user.role}")
    return {
        "message": "登录成功",
        "user": UserLoginInfo(id=user.id, username=user.username, role=user.role),
        "role": user.role
    }


@router.post("/reset-password")
def reset_password(payload: UserResetPassword, db: Session = Depends(get_db)):
    """
    重置密码接口 - 通过用户名、手机号或邮箱找回密码
    用于找回密码场景，用户不知道自己的用户ID
    """
    logger.info(f"重置密码请求: identifier={payload.identifier}")
    # 通过用户名、手机号或邮箱查找用户
    user = db.scalar(
        select(User).where(
            (User.username == payload.identifier) |
            (User.phone == payload.identifier) |
            (User.email == payload.identifier)
        )
    )
    if not user:
        logger.warning(f"重置密码失败: 未找到用户 identifier={payload.identifier}")
        raise HTTPException(status_code=404, detail="未找到该用户名、手机号或邮箱对应的用户")
    
    # 更新密码
    user.hashed_password = hash_password(payload.new_password)
    db.add(user)
    db.commit()
    logger.info(f"密码重置成功: user_id={user.id}, username={user.username}, identifier={payload.identifier}")
    return {"message": "密码重置成功", "user_id": user.id, "username": user.username}


def require_admin(x_admin_token: str | None = Header(default=None)):
    if x_admin_token != "dev-admin":
        logger.warning(f"管理员权限验证失败: token={x_admin_token}")
        raise HTTPException(status_code=403, detail="需要管理员权限")
    logger.debug("管理员权限验证成功")


@router.post("/{user_id}/role", response_model=UserOut)
def change_role(
    user_id: int,
    role: str = Query(..., pattern="^(admin|user)$"),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    logger.info(f"修改用户角色请求: user_id={user_id}, new_role={role}")
    user = db.get(User, user_id)
    if not user:
        logger.warning(f"修改用户角色失败: 用户不存在 user_id={user_id}")
        raise HTTPException(status_code=404, detail="用户不存在")
    old_role = user.role
    user.role = role
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info(f"用户角色修改成功: user_id={user_id}, username={user.username}, old_role={old_role}, new_role={role}")
    return user


@router.post("/{user_id}/change-password", response_model=UserOut)
def admin_change_password(
    user_id: int,
    payload: AdminChangePassword,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """
    管理员修改用户密码接口
    需要管理员权限（通过 X-Admin-Token 头验证）
    """
    logger.info(f"管理员修改用户密码请求: user_id={user_id}")
    user = db.get(User, user_id)
    if not user:
        logger.warning(f"管理员修改用户密码失败: 用户不存在 user_id={user_id}")
        raise HTTPException(status_code=404, detail="用户不存在")
    
    # 更新密码
    user.hashed_password = hash_password(payload.new_password)
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info(f"管理员修改用户密码成功: user_id={user_id}, username={user.username}")
    return user


