from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status, Header, WebSocket, WebSocketDisconnect
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Group, GroupMember, ChatMessage
from ..schemas import ChatCreate, ChatOut
from ..websocket_manager import ws_manager


router = APIRouter(prefix="/groups/{group_id}/chats", tags=["chats"])


def get_current_user_id(x_user_id: int | None = Header(default=None, alias="X-User-Id")) -> int:
    if x_user_id is None:
        raise HTTPException(status_code=401, detail="缺少用户标识 X-User-Id")
    return x_user_id


@router.post("/", response_model=ChatOut, status_code=status.HTTP_201_CREATED)
async def send_message(group_id: int, payload: ChatCreate, db: Session = Depends(get_db)):
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="群不存在")
    if group.audit_state != "审核通过":
        raise HTTPException(status_code=400, detail="群未审核通过，暂无法发送消息")

    member = db.scalar(
        select(GroupMember).where(GroupMember.group_id == group_id, GroupMember.user_id == payload.user_id)
    )
    if not member:
        raise HTTPException(status_code=403, detail="非群成员，不能发送消息")

    # auto-generate chat_no if not provided (per group increasing)
    chat_no = payload.chat_no
    if chat_no is None:
        max_no = db.scalar(select(func.max(ChatMessage.chat_no)).where(ChatMessage.group_id == group_id))
        chat_no = (max_no or 0) + 1

    message = ChatMessage(
        chat_no=chat_no,
        group_id=group_id,
        user_id=payload.user_id,
        sender_name=payload.sender_name or member.nickname,
        content=payload.content,
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    # broadcast via WS
    await ws_manager.broadcast_json(group_id, {
        "event": "message",
        "data": {
            "id": message.id,
            "chat_no": message.chat_no,
            "group_id": message.group_id,
            "user_id": message.user_id,
            "sender_name": message.sender_name,
            "content": message.content,
            "sent_at": message.sent_at.isoformat(),
        }
    })

    return message


@router.get("/", response_model=List[ChatOut])
def list_messages(
    group_id: int,
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    min_chat_no: Optional[int] = Query(None),
    q: Optional[str] = Query(None, description="按内容关键字搜索"),
    x_user_id: int = Depends(get_current_user_id),
):
    """
    获取群聊消息列表（支持关键字搜索）
    
    - 需要 Header: X-User-Id（必须是群成员或群主才能查看）
    - 支持关键字搜索：使用参数 `q` 进行模糊匹配
    - 支持分页：使用 `skip` 和 `limit` 参数
    - 支持按消息序号筛选：使用 `min_chat_no` 参数
    """
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="群不存在")
    
    # 权限验证：必须是群成员或群主才能查看群聊记录
    member = db.scalar(
        select(GroupMember).where(
            GroupMember.group_id == group_id,
            GroupMember.user_id == x_user_id
        )
    )
    if not member and x_user_id != group.created_by_user_id:
        raise HTTPException(status_code=403, detail="非群成员，无法查看群聊记录")
    
    stmt = select(ChatMessage).where(ChatMessage.group_id == group_id)
    if min_chat_no is not None:
        stmt = stmt.where(ChatMessage.chat_no >= min_chat_no)
    if q:
        stmt = stmt.where(ChatMessage.content.like(f"%{q}%"))
    stmt = stmt.order_by(ChatMessage.id).offset(skip).limit(limit)
    messages = db.scalars(stmt).all()
    return messages


@router.delete("/{message_id}")
async def retract_message(
    group_id: int,
    message_id: int,
    db: Session = Depends(get_db),
    x_user_id: int = Depends(get_current_user_id),
):
    group = db.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="群不存在")
    message = db.get(ChatMessage, message_id)
    if not message or message.group_id != group_id:
        raise HTTPException(status_code=404, detail="消息不存在")

    # 权限与时间窗口：
    # - 发送者：2 分钟内可撤回
    # - 群主（group.created_by_user_id）：可随时撤回
    from datetime import datetime, timedelta, timezone
    CHINA_TZ = timezone(timedelta(hours=8))
    now = datetime.now(CHINA_TZ).replace(tzinfo=None)

    if x_user_id == group.created_by_user_id:
        allowed = True
    elif x_user_id == message.user_id and (now - message.sent_at) <= timedelta(minutes=2):
        allowed = True
    else:
        allowed = False

    if not allowed:
        raise HTTPException(status_code=403, detail="无权限或超出可撤回时间")

    db.delete(message)
    db.commit()

    # 广播撤回事件
    await ws_manager.broadcast_json(group_id, {
        "event": "retracted",
        "data": {"message_id": message_id}
    })

    return {"message": "已撤回"}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, group_id: int):
    await ws_manager.connect(group_id, websocket)
    try:
        while True:
            # 目前仅作为服务端推送通道；如果要支持客户端发消息，可在此处理
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(group_id, websocket)

