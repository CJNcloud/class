from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Header, Query
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Group, GroupMember, GroupJoinRequest, User, Report
from ..schemas import GroupMemberCreate, GroupMemberOut, GroupJoinRequestCreate, GroupJoinRequestOut


router = APIRouter(prefix="/groups", tags=["group-members"])


def require_admin(x_admin_token: str | None = Header(default=None)):
    if x_admin_token != "dev-admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")


@router.post("/{group_id}/join-requests", response_model=GroupJoinRequestOut, status_code=status.HTTP_201_CREATED)
def submit_join_request(group_id: int, payload: GroupJoinRequestCreate, db: Session = Depends(get_db)):
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="群不存在")
    if group.audit_state != "审核通过":
        raise HTTPException(status_code=400, detail="群未审核通过，暂无法申请加入")
    ex_req = db.scalar(select(GroupJoinRequest).where(and_(GroupJoinRequest.group_id == group_id, GroupJoinRequest.user_id == payload.user_id, GroupJoinRequest.audit_state == "未审核")))
    if ex_req:
        raise HTTPException(status_code=400, detail="已有待审核申请")
    ex_member = db.scalar(select(GroupMember).where(and_(GroupMember.group_id == group_id, GroupMember.user_id == payload.user_id)))
    if ex_member:
        raise HTTPException(status_code=400, detail="已在群中")
    req = GroupJoinRequest(
        group_id=group_id,
        user_id=payload.user_id,
        nickname=None,
        avatar_url=None,
        reason=payload.reason,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    
    # 获取用户信息，如果 nickname 为 null，使用用户的 username 作为默认昵称
    user = db.get(User, payload.user_id)
    default_nickname = user.username if user else None
    
    return GroupJoinRequestOut(
        id=req.id,
        group_id=req.group_id,
        user_id=req.user_id,
        nickname=req.nickname if req.nickname is not None else default_nickname,
        avatar_url=req.avatar_url,
        created_at=req.created_at,
        audit_state=req.audit_state,
        reason=req.reason,
    )


@router.get("/{group_id}/members", response_model=List[GroupMemberOut])
def list_members(group_id: int, db: Session = Depends(get_db)):
    """
    获取群成员列表
    
    - 返回指定群的所有成员
    - 如果成员的 nickname 为 null，会使用用户的 username 作为默认值
    - 包含每个成员被管理员通过的举报次数
    """
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="群不存在")
    members = db.scalars(select(GroupMember).where(GroupMember.group_id == group_id).order_by(GroupMember.id)).all()
    
    # 批量查询所有相关用户信息，如果 nickname 为 null，使用用户的 username
    user_ids = list(set([member.user_id for member in members]))  # 去重
    user_dict = {}
    if user_ids:
        users = db.scalars(select(User).where(User.id.in_(user_ids))).all()
        user_dict = {user.id: user.username for user in users}
    
    # 批量查询所有成员被审核通过的举报次数
    report_counts = {}
    if user_ids:
        # 查询 reported_user_id 在 user_ids 中且 audit_state 为 "审核通过" 的举报数量
        report_stats = db.execute(
            select(Report.reported_user_id, func.count(Report.id).label("count"))
            .where(
                and_(
                    Report.reported_user_id.in_(user_ids),
                    Report.audit_state == "审核通过"
                )
            )
            .group_by(Report.reported_user_id)
        ).all()
        report_counts = {user_id: count for user_id, count in report_stats}
    
    # 构建返回结果，如果 nickname 为 null，使用用户的 username
    result = []
    for member in members:
        # 通过 user_id 获取用户的 username（作为默认 nickname）
        user_username = user_dict.get(member.user_id)
        if user_username is None:
            # 如果批量查询中没有，直接查询单个用户
            user = db.get(User, member.user_id)
            user_username = user.username if user else None
        
        # nickname: 优先使用 member.nickname，如果为 None 或空字符串则使用用户的 username
        final_nickname = member.nickname if member.nickname else user_username
        
        # 获取该成员被审核通过的举报次数
        approved_report_count = report_counts.get(member.user_id, 0)
        
        result.append(GroupMemberOut(
            id=member.id,
            group_id=member.group_id,
            user_id=member.user_id,
            nickname=final_nickname,
            avatar_url=member.avatar_url,
            is_group_admin=member.is_group_admin,
            joined_at=member.joined_at,
            approved_report_count=approved_report_count,
        ))
    
    return result


def is_owner(group, x_user_id: int | None) -> bool:
    return x_user_id is not None and x_user_id == group.created_by_user_id


@router.post("/join-requests/{request_id}/audit", response_model=GroupMemberOut)
def audit_join_request(
    request_id: int,
    action: str = Query(..., pattern="^(approve|reject)$"),
    db: Session = Depends(get_db),
    x_user_id: int | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
):
    req = db.get(GroupJoinRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="申请不存在")
    group = db.get(Group, req.group_id)
    if not group:
        raise HTTPException(status_code=404, detail="群不存在")
    if not (is_owner(group, x_user_id) or x_admin_token == "dev-admin"):
        raise HTTPException(status_code=403, detail="无权审核")
    if action == "reject":
        req.audit_state = "审核未通过"
        db.add(req)
        db.commit()
        raise HTTPException(status_code=400, detail="入群申请被驳回")

    # approve
    current_count = db.scalar(select(func.count()).select_from(GroupMember).where(GroupMember.group_id == req.group_id))
    if current_count >= group.member_limit:
        raise HTTPException(status_code=400, detail="群人数已达上限")
    ex_member = db.scalar(select(GroupMember).where(and_(GroupMember.group_id == req.group_id, GroupMember.user_id == req.user_id)))
    if ex_member:
        raise HTTPException(status_code=400, detail="已在群中")
    
    # 获取用户信息，如果 nickname 为 null，使用用户的 username 作为默认昵称
    user = db.get(User, req.user_id)
    default_nickname = user.username if user else None
    member_nickname = req.nickname if req.nickname is not None else default_nickname
    
    gm = GroupMember(
        group_id=req.group_id,
        user_id=req.user_id,
        nickname=member_nickname,
        avatar_url=req.avatar_url,
        is_group_admin=False,
    )
    req.audit_state = "审核通过"
    db.add_all([gm, req])
    db.commit()
    db.refresh(gm)
    
    # 查询该用户被审核通过的举报次数
    approved_report_count = db.scalar(
        select(func.count(Report.id))
        .where(
            and_(
                Report.reported_user_id == req.user_id,
                Report.audit_state == "审核通过"
            )
        )
    ) or 0
    
    # 构建返回结果
    final_nickname = gm.nickname if gm.nickname else (user.username if user else None)
    return GroupMemberOut(
        id=gm.id,
        group_id=gm.group_id,
        user_id=gm.user_id,
        nickname=final_nickname,
        avatar_url=gm.avatar_url,
        is_group_admin=gm.is_group_admin,
        joined_at=gm.joined_at,
        approved_report_count=approved_report_count,
    )


@router.get("/{group_id}/join-requests", response_model=List[GroupJoinRequestOut])
def list_join_requests(
    group_id: int,
    state: str = Query("未审核"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    x_user_id: int | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
):
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="群不存在")
    if not (is_owner(group, x_user_id) or x_admin_token == "dev-admin"):
        raise HTTPException(status_code=403, detail="无权查看")
    stmt = (
        select(GroupJoinRequest)
        .where(GroupJoinRequest.group_id == group_id)
        .where(GroupJoinRequest.audit_state == state)
        .order_by(GroupJoinRequest.id)
        .offset(skip)
        .limit(limit)
    )
    rows = db.scalars(stmt).all()
    
    # 批量查询所有相关用户信息，通过 user_id 获取 username
    user_ids = list(set([row.user_id for row in rows]))  # 去重
    user_dict = {}
    if user_ids:
        users = db.scalars(select(User).where(User.id.in_(user_ids))).all()
        # 构建 user_id -> username 的映射
        user_dict = {user.id: user.username for user in users}
    
    # 构建返回结果，如果 nickname 或 avatar_url 为 null，使用用户信息填充
    result = []
    for row in rows:
        # 通过 user_id 获取用户的 username（作为默认 nickname）
        user_username = user_dict.get(row.user_id)
        if user_username is None:
            # 如果批量查询中没有，直接查询单个用户
            user = db.get(User, row.user_id)
            user_username = user.username if user else None
        
        # nickname: 优先使用 row.nickname，如果为 None 或空字符串则使用用户的 username
        final_nickname = row.nickname if row.nickname else user_username
        
        # avatar_url: 如果为 null，保持 null（User 表中没有头像字段，或者可以设置默认值）
        final_avatar_url = row.avatar_url
        
        result.append(GroupJoinRequestOut(
            id=row.id,
            group_id=row.group_id,
            user_id=row.user_id,
            nickname=final_nickname,
            avatar_url=final_avatar_url,
            created_at=row.created_at,
            audit_state=row.audit_state,
            reason=row.reason,
        ))
    
    return result


@router.post("/{group_id}/members/{user_id}/admin", response_model=GroupMemberOut)
def set_member_admin(group_id: int, user_id: int, is_admin: bool, db: Session = Depends(get_db), _: None = Depends(require_admin)):
    gm = db.scalar(
        select(GroupMember).where(and_(GroupMember.group_id == group_id, GroupMember.user_id == user_id))
    )
    if not gm:
        raise HTTPException(status_code=404, detail="成员不存在")
    gm.is_group_admin = is_admin
    db.add(gm)
    db.commit()
    db.refresh(gm)
    
    # 获取用户信息，用于 nickname 默认值
    user = db.get(User, user_id)
    final_nickname = gm.nickname if gm.nickname else (user.username if user else None)
    
    # 查询该用户被审核通过的举报次数
    approved_report_count = db.scalar(
        select(func.count(Report.id))
        .where(
            and_(
                Report.reported_user_id == user_id,
                Report.audit_state == "审核通过"
            )
        )
    ) or 0
    
    # 构建返回结果
    return GroupMemberOut(
        id=gm.id,
        group_id=gm.group_id,
        user_id=gm.user_id,
        nickname=final_nickname,
        avatar_url=gm.avatar_url,
        is_group_admin=gm.is_group_admin,
        joined_at=gm.joined_at,
        approved_report_count=approved_report_count,
    )


@router.delete("/{group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(group_id: int, user_id: int, db: Session = Depends(get_db), x_user_id: int | None = Header(default=None), x_admin_token: str | None = Header(default=None)):
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="群不存在")
    # 权限：群主可以踢出除自己外的成员；管理员可以移除任意成员；本人可以退出
    is_admin = x_admin_token == "dev-admin"
    if not (is_admin or (x_user_id == group.created_by_user_id) or (x_user_id == user_id)):
        raise HTTPException(status_code=403, detail="无权移除")
    gm = db.scalar(select(GroupMember).where(and_(GroupMember.group_id == group_id, GroupMember.user_id == user_id)))
    if not gm:
        raise HTTPException(status_code=404, detail="成员不存在")
    # 群主不能通过此接口移除自己（包括管理员也不能直接移除群主），需要先转让群主身份
    if user_id == group.created_by_user_id:
        raise HTTPException(status_code=400, detail="群主退出请使用转让或携带新群主参数")
    db.delete(gm)
    db.commit()
    return None


@router.post("/{group_id}/transfer")
def transfer_ownership(group_id: int, to_user_id: int, db: Session = Depends(get_db), x_user_id: int | None = Header(default=None)):
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="群不存在")
    if x_user_id != group.created_by_user_id:
        raise HTTPException(status_code=403, detail="仅群主可转让")
    target = db.scalar(select(GroupMember).where(and_(GroupMember.group_id == group_id, GroupMember.user_id == to_user_id)))
    if not target:
        raise HTTPException(status_code=404, detail="目标用户不在群内")
    prev_member = db.scalar(select(GroupMember).where(and_(GroupMember.group_id == group_id, GroupMember.user_id == group.created_by_user_id)))
    if prev_member:
        prev_member.is_group_admin = False
        db.add(prev_member)
    target.is_group_admin = True
    group.created_by_user_id = to_user_id
    db.add(group)
    db.commit()
    return {"message": "已转让群主"}


@router.delete("/{group_id}/members/me")
def quit_group_self(group_id: int, db: Session = Depends(get_db), x_user_id: int | None = Header(default=None), new_owner_user_id: int | None = Query(default=None)):
    if x_user_id is None:
        raise HTTPException(status_code=401, detail="缺少用户标识 X-User-Id")
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="群不存在")
    gm = db.scalar(select(GroupMember).where(and_(GroupMember.group_id == group_id, GroupMember.user_id == x_user_id)))
    if not gm:
        raise HTTPException(status_code=404, detail="不在群内")
    if x_user_id == group.created_by_user_id:
        if not new_owner_user_id:
            raise HTTPException(status_code=400, detail="群主退出需指定新群主 new_owner_user_id")
        target = db.scalar(select(GroupMember).where(and_(GroupMember.group_id == group_id, GroupMember.user_id == new_owner_user_id)))
        if not target:
            raise HTTPException(status_code=404, detail="新群主不在群内")
        group.created_by_user_id = new_owner_user_id
        db.add(group)
    db.delete(gm)
    db.commit()
    return None


@router.get("/{group_id}/members/search", response_model=List[GroupMemberOut])
def search_members(group_id: int, q: str, db: Session = Depends(get_db)):
    """
    按昵称或用户名搜索群成员
    
    - 搜索范围包括：成员的 nickname 和用户的 username
    - 使用模糊匹配（LIKE %q%）
    - 包含每个成员被管理员通过的举报次数
    """
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="群不存在")
    
    # 使用 JOIN 查询，同时搜索 GroupMember.nickname 和 User.username
    stmt = (
        select(GroupMember, User)
        .join(User, GroupMember.user_id == User.id)
        .where(GroupMember.group_id == group_id)
        .where(
            or_(
                GroupMember.nickname.like(f"%{q}%"),
                User.username.like(f"%{q}%")
            )
        )
    )
    results = db.execute(stmt).all()
    
    # 获取搜索结果的用户ID列表，用于批量查询举报次数
    user_ids = [member.user_id for member, user in results]
    report_counts = {}
    if user_ids:
        # 查询 reported_user_id 在 user_ids 中且 audit_state 为 "审核通过" 的举报数量
        report_stats = db.execute(
            select(Report.reported_user_id, func.count(Report.id).label("count"))
            .where(
                and_(
                    Report.reported_user_id.in_(user_ids),
                    Report.audit_state == "审核通过"
                )
            )
            .group_by(Report.reported_user_id)
        ).all()
        report_counts = {user_id: count for user_id, count in report_stats}
    
    # 构建返回结果，如果 nickname 为 null，使用用户的 username
    member_list = []
    for member, user in results:
        # nickname: 优先使用 member.nickname，如果为 None 或空字符串则使用用户的 username
        final_nickname = member.nickname if member.nickname else user.username
        
        # 获取该成员被审核通过的举报次数
        approved_report_count = report_counts.get(member.user_id, 0)
        
        member_list.append(GroupMemberOut(
            id=member.id,
            group_id=member.group_id,
            user_id=member.user_id,
            nickname=final_nickname,
            avatar_url=member.avatar_url,
            is_group_admin=member.is_group_admin,
            joined_at=member.joined_at,
            approved_report_count=approved_report_count,
        ))
    
    return member_list

