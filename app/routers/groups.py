from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status, Header
from sqlalchemy import select, func, case, and_, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Group, GroupMember, ChatMessage, GroupUpdateRequest, GroupCreateRequest, Report
from ..schemas import GroupCreateRequestCreate, GroupCreateRequestOut, GroupOut, GroupUpdate, GroupUpdateRequestCreate, GroupUpdateRequestOut, UserGroupOut, GroupPinRequest


router = APIRouter(prefix="/groups", tags=["groups"])


def require_admin(x_admin_token: str | None = Header(default=None)):
    if x_admin_token != "dev-admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")


def get_current_user_id(x_user_id: Optional[int] = Header(default=None)) -> Optional[int]:
    return x_user_id


@router.post("/", response_model=GroupCreateRequestOut, status_code=status.HTTP_201_CREATED)
def create_group_request(payload: GroupCreateRequestCreate, db: Session = Depends(get_db)):
    req = GroupCreateRequest(
        name=payload.name,
        group_type=payload.group_type,
        note=payload.note,
        announce_limit=payload.announce_limit,
        member_limit=payload.member_limit,
        announce=payload.announce,
        avatar_url=payload.avatar_url,
        created_by_user_id=payload.created_by_user_id,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


@router.get("/", response_model=List[GroupOut])
def list_groups(
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    audit_state: Optional[str] = Query(None, description="按审核状态过滤"),
    q: Optional[str] = Query(None, description="按群名模糊搜索"),
):
    stmt = select(Group)
    if audit_state:
        stmt = stmt.where(Group.audit_state == audit_state)
    if q:
        stmt = stmt.where(Group.name.like(f"%{q}%"))
    stmt = stmt.order_by(Group.id).offset(skip).limit(limit)
    groups = db.scalars(stmt).all()
    
    # 批量查询所有群组被审核通过的举报次数
    group_ids = [group.id for group in groups]
    report_counts = {}
    if group_ids:
        # 查询 group_id 在 group_ids 中且 audit_state 为 "审核通过" 的举报数量
        report_stats = db.execute(
            select(Report.group_id, func.count(Report.id).label("count"))
            .where(
                and_(
                    Report.group_id.in_(group_ids),
                    Report.audit_state == "审核通过"
                )
            )
            .group_by(Report.group_id)
        ).all()
        report_counts = {group_id: count for group_id, count in report_stats}
    
    # 构建返回结果
    result = []
    for group in groups:
        approved_report_count = report_counts.get(group.id, 0)
        result.append(GroupOut(
            id=group.id,
            name=group.name,
            group_type=group.group_type,
            note=group.note,
            announce_limit=group.announce_limit,
            member_limit=group.member_limit,
            announce=group.announce,
            avatar_url=group.avatar_url,
            created_by_user_id=group.created_by_user_id,
            created_at=group.created_at,
            pin=group.pin,
            audit_state=group.audit_state,
            approved_report_count=approved_report_count,
        ))
    
    return result


@router.get("/create-requests", response_model=List[GroupCreateRequestOut])
def list_group_create_requests(
    audit_state: Optional[str] = Query("未审核", description="按审核状态过滤：未审核、审核通过、审核未通过"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    q: Optional[str] = Query(None, description="按群名模糊搜索"),
    db: Session = Depends(get_db),
):
    """
    查看建群请求列表
    
    - 默认显示待审核的请求（audit_state=未审核）
    - 支持按审核状态过滤
    - 支持按群名搜索
    - 支持分页
    """
    stmt = select(GroupCreateRequest)
    if audit_state:
        stmt = stmt.where(GroupCreateRequest.audit_state == audit_state)
    if q:
        stmt = stmt.where(GroupCreateRequest.name.like(f"%{q}%"))
    stmt = stmt.order_by(GroupCreateRequest.created_at.desc()).offset(skip).limit(limit)
    requests = db.scalars(stmt).all()
    return requests


@router.post("/create-requests/{request_id}/audit")
def audit_group_create_request(
    request_id: int,
    action: str = Query(..., pattern="^(approve|reject)$"),
    db: Session = Depends(get_db),
):
    req = db.get(GroupCreateRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="建群请求不存在")
    
    if action == "reject":
        # 驳回后直接删除请求
        db.delete(req)
        db.commit()
        return {"message": "建群请求已驳回并删除", "request_id": request_id}

    # approve: create group
    # 审核通过后才创建 Group 并分配 group_id
    group = Group(
        name=req.name,
        group_type=req.group_type,
        note=req.note,
        announce_limit=req.announce_limit,
        member_limit=req.member_limit,
        announce=req.announce,
        avatar_url=req.avatar_url,
        created_by_user_id=req.created_by_user_id,
        audit_state="审核通过",
    )
    db.add(group)
    req.audit_state = "审核通过"
    db.add(req)
    
    # 先提交 Group 和 Request 的更改，以获取 group.id
    db.commit()
    db.refresh(group)
    
    # 验证 group.id 是否已正确赋值
    if group.id is None:
        raise HTTPException(status_code=500, detail="创建群失败：无法获取群ID")
    
    # 自动将群主添加到 GroupMember 表中，这样群主也能使用置顶等功能
    group_member = GroupMember(
        group_id=group.id,
        user_id=req.created_by_user_id,
        nickname=None,
        avatar_url=None,
        is_group_admin=True,  # 群主默认是管理员
    )
    db.add(group_member)
    db.commit()
    db.refresh(group_member)
    
    # 新建的群，举报次数应该为 0
    # 构建返回结果
    return GroupOut(
        id=group.id,
        name=group.name,
        group_type=group.group_type,
        note=group.note,
        announce_limit=group.announce_limit,
        member_limit=group.member_limit,
        announce=group.announce,
        avatar_url=group.avatar_url,
        created_by_user_id=group.created_by_user_id,
        created_at=group.created_at,
        pin=group.pin,
        audit_state=group.audit_state,
        approved_report_count=0,  # 新建的群，违规次数为 0
    )


@router.get("/update-requests", response_model=List[GroupUpdateRequestOut])
def list_group_update_requests(
    audit_state: Optional[str] = Query("未审核", description="按审核状态过滤：未审核、审核通过、审核未通过"),
    group_id: Optional[int] = Query(None, description="按群ID过滤"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """
    管理员查看群信息修改请求列表
    
    - 需要 Header: X-Admin-Token: dev-admin
    - 默认显示待审核的请求（audit_state=未审核）
    - 支持按审核状态过滤
    - 支持按群ID过滤
    - 支持分页
    - 如果请求中的字段为 null，会从原始群信息中获取该字段的值
    """
    stmt = select(GroupUpdateRequest)
    if audit_state:
        stmt = stmt.where(GroupUpdateRequest.audit_state == audit_state)
    if group_id:
        stmt = stmt.where(GroupUpdateRequest.group_id == group_id)
    stmt = stmt.order_by(GroupUpdateRequest.created_at.desc()).offset(skip).limit(limit)
    requests = db.scalars(stmt).all()
    
    # 处理每个请求，将 null 字段替换为原始群信息的值
    result = []
    for req in requests:
        # 获取原始群信息
        group = db.get(Group, req.group_id)
        if group:
            # 创建请求数据的副本
            req_dict = {
                "id": req.id,
                "group_id": req.group_id,
                "requested_by_user_id": req.requested_by_user_id,
                "name": req.name if req.name is not None else group.name,
                "group_type": req.group_type if req.group_type is not None else group.group_type,
                "note": req.note if req.note is not None else group.note,
                "announce_limit": req.announce_limit if req.announce_limit is not None else group.announce_limit,
                "announce": req.announce if req.announce is not None else group.announce,
                "avatar_url": req.avatar_url if req.avatar_url is not None else group.avatar_url,
                "member_limit": req.member_limit if req.member_limit is not None else group.member_limit,
                "created_at": req.created_at,
                "audit_state": req.audit_state,
            }
            result.append(GroupUpdateRequestOut(**req_dict))
        else:
            # 如果群不存在，直接返回原始请求
            result.append(req)
    
    return result


@router.get("/my", response_model=List[UserGroupOut])
def get_my_groups(
    x_user_id: int = Header(..., alias="X-User-Id", description="用户ID"),
    db: Session = Depends(get_db),
):
    """
    获取用户自己的群聊列表，包括是否置顶
    
    - 需要 Header: X-User-Id
    - 返回用户所在的所有群聊，包含用户级别的置顶状态
    - 群主也会自动添加到 GroupMember 表中，所以统一通过 GroupMember 查询
    - 按置顶状态和创建时间排序（置顶的在前）
    - 一次性返回所有数据，不做分页限制
    - 只返回审核通过的群
    """
    # 由于群主也会自动添加到 GroupMember 表中，所以统一查询用户作为成员的群
    # 使用 case 语句确保"已置顶"排在前面
    pin_order = case(
        (GroupMember.pin == "已置顶", 0),
        else_=1
    )
    
    stmt = (
        select(Group, GroupMember.pin)
        .join(GroupMember, Group.id == GroupMember.group_id)
        .where(GroupMember.user_id == x_user_id)
        .where(Group.audit_state == "审核通过")  # 只返回审核通过的群
        .order_by(
            # 置顶的在前（pin_order=0），然后按创建时间倒序
            pin_order.asc(),
            Group.created_at.desc()
        )
    )
    
    results = db.execute(stmt).all()
    
    # 批量查询所有群组被审核通过的举报次数
    group_ids = [group.id for group, pin in results]
    report_counts = {}
    if group_ids:
        # 查询 group_id 在 group_ids 中且 audit_state 为 "审核通过" 的举报数量
        report_stats = db.execute(
            select(Report.group_id, func.count(Report.id).label("count"))
            .where(
                and_(
                    Report.group_id.in_(group_ids),
                    Report.audit_state == "审核通过"
                )
            )
            .group_by(Report.group_id)
        ).all()
        report_counts = {group_id: count for group_id, count in report_stats}
    
    # 构建返回结果
    groups = []
    for group, pin in results:
        # 获取该群组被审核通过的举报次数
        approved_report_count = report_counts.get(group.id, 0)
        
        group_dict = {
            "id": group.id,
            "name": group.name,
            "group_type": group.group_type,
            "note": group.note,
            "announce_limit": group.announce_limit,
            "member_limit": group.member_limit,
            "announce": group.announce,
            "avatar_url": group.avatar_url,
            "created_by_user_id": group.created_by_user_id,
            "created_at": group.created_at,
            "pin": pin if pin else "未置顶",  # 使用GroupMember的pin字段
            "audit_state": group.audit_state,
            "approved_report_count": approved_report_count,
        }
        groups.append(UserGroupOut(**group_dict))
    
    return groups


@router.post("/update-requests/{request_id}/audit")
def audit_group_update_request(
    request_id: int,
    action: str = Query(..., pattern="^(approve|reject)$"),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    req = db.get(GroupUpdateRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="修改请求不存在")
    group = db.get(Group, req.group_id)
    if not group:
        raise HTTPException(status_code=404, detail="群不存在")
    
    if action == "reject":
        # 驳回后直接删除请求
        db.delete(req)
        db.commit()
        return {"message": "修改请求已驳回并删除", "request_id": request_id, "group_id": req.group_id}

    # approve: apply changes
    if req.name is not None:
        group.name = req.name
    if req.group_type is not None:
        group.group_type = req.group_type
    if req.note is not None:
        group.note = req.note
    if req.announce_limit is not None:
        group.announce_limit = req.announce_limit
    if req.announce is not None:
        group.announce = req.announce
    if req.avatar_url is not None:
        group.avatar_url = req.avatar_url
    if getattr(req, 'member_limit', None) is not None:
        group.member_limit = req.member_limit  # type: ignore[attr-defined]

    req.audit_state = "审核通过"
    db.add_all([group, req])
    db.commit()
    db.refresh(group)
    
    # 查询该群组被审核通过的举报次数
    approved_report_count = db.scalar(
        select(func.count(Report.id))
        .where(
            and_(
                Report.group_id == group.id,
                Report.audit_state == "审核通过"
            )
        )
    ) or 0
    
    # 构建返回结果
    return GroupOut(
        id=group.id,
        name=group.name,
        group_type=group.group_type,
        note=group.note,
        announce_limit=group.announce_limit,
        member_limit=group.member_limit,
        announce=group.announce,
        avatar_url=group.avatar_url,
        created_by_user_id=group.created_by_user_id,
        created_at=group.created_at,
        pin=group.pin,
        audit_state=group.audit_state,
        approved_report_count=approved_report_count,
    )


@router.get("/{group_id}", response_model=GroupOut)
def get_group(group_id: int, db: Session = Depends(get_db)):
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="群不存在")
    
    # 查询该群组被审核通过的举报次数
    approved_report_count = db.scalar(
        select(func.count(Report.id))
        .where(
            and_(
                Report.group_id == group_id,
                Report.audit_state == "审核通过"
            )
        )
    ) or 0
    
    # 构建返回结果
    return GroupOut(
        id=group.id,
        name=group.name,
        group_type=group.group_type,
        note=group.note,
        announce_limit=group.announce_limit,
        member_limit=group.member_limit,
        announce=group.announce,
        avatar_url=group.avatar_url,
        created_by_user_id=group.created_by_user_id,
        created_at=group.created_at,
        pin=group.pin,
        audit_state=group.audit_state,
        approved_report_count=approved_report_count,
    )


@router.post("/{group_id}/pin", status_code=status.HTTP_200_OK)
def pin_group(
    group_id: int,
    payload: GroupPinRequest,
    db: Session = Depends(get_db),
    x_user_id: Optional[int] = Header(default=None, alias="X-User-Id"),
):
    """
    置顶/取消置顶群聊（用户个人设置）
    
    - 需要 Header: X-User-Id
    - 请求体: {"is_pinned": true} 或 {"is_pinned": false}
    - is_pinned: true=置顶, false=取消置顶
    - 只有群成员才能置顶该群
    """
    if x_user_id is None:
        raise HTTPException(status_code=401, detail="缺少用户标识 X-User-Id")
    
    # 检查群是否存在
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="群不存在")
    
    # 检查用户是否是群成员
    from ..models import GroupMember
    member = db.scalar(
        select(GroupMember).where(
            (GroupMember.group_id == group_id) & (GroupMember.user_id == x_user_id)
        )
    )
    if not member:
        raise HTTPException(status_code=403, detail="您不是该群成员，无法置顶")
    
    # 更新置顶状态
    member.pin = "已置顶" if payload.is_pinned else "未置顶"
    db.add(member)
    db.commit()
    db.refresh(member)
    
    return {
        "message": "置顶成功" if payload.is_pinned else "取消置顶成功",
        "group_id": group_id,
        "pin": member.pin
    }


@router.post("/{group_id}/update-requests", response_model=GroupUpdateRequestOut)
def create_group_update_request(
    group_id: int,
    payload: GroupUpdateRequestCreate,
    db: Session = Depends(get_db),
    x_user_id: Optional[int] = Header(default=None, alias="X-User-Id"),
):
    """
    提交群信息修改请求
    
    - 需要 Header: X-User-Id
    - 仅群主可以提交修改请求
    - 如果已有待审核的修改请求，会覆盖更新，而不是创建新请求
    """
    if x_user_id is None:
        raise HTTPException(status_code=401, detail="缺少用户标识 X-User-Id，请提供 Header: X-User-Id")
    
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="群不存在")
    
    # 确保类型一致，进行比较
    if int(x_user_id) != int(group.created_by_user_id):
        raise HTTPException(status_code=403, detail="仅群主可提交修改请求")
    
    # 检查是否已有待审核的修改请求
    existing_req = db.scalar(
        select(GroupUpdateRequest).where(
            (GroupUpdateRequest.group_id == group_id) &
            (GroupUpdateRequest.audit_state == "未审核")
        )
    )
    
    if existing_req:
        # 更新现有请求，覆盖之前的修改内容
        if payload.name is not None:
            existing_req.name = payload.name
        if payload.group_type is not None:
            existing_req.group_type = payload.group_type
        if payload.note is not None:
            existing_req.note = payload.note
        if payload.announce_limit is not None:
            existing_req.announce_limit = payload.announce_limit
        if payload.announce is not None:
            existing_req.announce = payload.announce
        if payload.avatar_url is not None:
            existing_req.avatar_url = payload.avatar_url
        if payload.member_limit is not None:
            existing_req.member_limit = payload.member_limit        
        # 更新请求时间
        from datetime import datetime, timezone, timedelta
        CHINA_TZ = timezone(timedelta(hours=8))
        existing_req.created_at = datetime.now(CHINA_TZ).replace(tzinfo=None)
        
        db.add(existing_req)
        db.commit()
        db.refresh(existing_req)
        return existing_req
    else:
        # 创建新请求
        req = GroupUpdateRequest(
            group_id=group_id,
            requested_by_user_id=x_user_id,
            name=payload.name,
            group_type=payload.group_type,
            note=payload.note,
            announce_limit=payload.announce_limit,
            announce=payload.announce,
            avatar_url=payload.avatar_url,
            member_limit=payload.member_limit,
        )
        db.add(req)
        db.commit()
        db.refresh(req)
        return req


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def dissolve_group(
    group_id: int,
    db: Session = Depends(get_db),
    x_user_id: Optional[int] = Header(default=None, alias="X-User-Id"),
    x_admin_token: Optional[str] = Header(default=None),
):
    """
    解散群聊
    
    - 群主可以通过提供 X-User-Id Header 解散自己的群
    - 管理员可以通过提供 X-Admin-Token: dev-admin Header 解散任何群
    """
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="群不存在")
    
    is_admin = x_admin_token == "dev-admin"
    
    # 如果不是管理员，必须提供用户ID且必须是群主
    if not is_admin:
        if x_user_id is None:
            raise HTTPException(status_code=401, detail="缺少用户标识 X-User-Id，请提供 Header: X-User-Id")
        
        # 检查用户是否是群成员（可选，但可以提供更好的错误提示）
        from ..models import GroupMember
        member = db.scalar(
            select(GroupMember).where(
                (GroupMember.group_id == group_id) & (GroupMember.user_id == x_user_id)
            )
        )
        
        # 检查是否是群主
        if int(x_user_id) != int(group.created_by_user_id):
            if member is None:
                raise HTTPException(status_code=403, detail="您不是该群成员，无法解散")
            else:
                raise HTTPException(status_code=403, detail="无权解散该群，仅群主或管理员可以解散")
    
    # 级联删除所有与群组相关的数据
    try:
        # 1. 删除群组成员
        db.execute(
            GroupMember.__table__.delete().where(GroupMember.group_id == group_id)
        )
        
        # 2. 删除群组聊天消息
        db.execute(
            ChatMessage.__table__.delete().where(ChatMessage.group_id == group_id)
        )
        
        # 3. 删除群组入群申请
        from ..models import GroupJoinRequest
        db.execute(
            GroupJoinRequest.__table__.delete().where(GroupJoinRequest.group_id == group_id)
        )
        
        # 4. 删除群组更新申请
        from ..models import GroupUpdateRequest
        db.execute(
            GroupUpdateRequest.__table__.delete().where(GroupUpdateRequest.group_id == group_id)
        )
        
        # 5. 删除与群组相关的举报记录
        from ..models import Report
        db.execute(
            Report.__table__.delete().where(Report.group_id == group_id)
        )
        
        # 6. 最后删除群组本身
        db.delete(group)
        db.commit()
        return None
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"解散群聊失败: {str(e)}")

