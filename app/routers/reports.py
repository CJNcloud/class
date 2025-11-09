from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Report
from ..schemas import ReportCreate, ReportOut


router = APIRouter(prefix="/reports", tags=["reports"])


def require_admin(x_admin_token: str | None = Header(default=None)):
    if x_admin_token != "dev-admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")


@router.post("/", response_model=ReportOut)
def submit_report(payload: ReportCreate, db: Session = Depends(get_db)):
    report = Report(
        user_id=payload.user_id,
        report_content=payload.report_content,
        reported_user_id=payload.reported_user_id,
        group_id=payload.group_id,
        chat_message_id=payload.chat_message_id,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


@router.get("/my", response_model=List[ReportOut])
def list_my_reports(
    x_user_id: int = Header(..., alias="X-User-Id"),
    state: str | None = Query(default=None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """用户查看自己提交的举报列表"""
    stmt = select(Report).where(Report.user_id == x_user_id)
    if state:
        stmt = stmt.where(Report.audit_state == state)
    stmt = stmt.order_by(Report.id.desc()).offset(skip).limit(limit)
    rows = db.scalars(stmt).all()
    return rows


@router.get("/", response_model=List[ReportOut])
def list_all_reports(
    state: str | None = Query(default=None, description="按审核状态筛选"),
    reported_user_id: int | None = Query(default=None, description="按被举报用户ID筛选"),
    group_id: int | None = Query(default=None, description="按群ID筛选"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    """管理员查看所有举报列表（支持多维度筛选）"""
    stmt = select(Report)
    if state:
        stmt = stmt.where(Report.audit_state == state)
    if reported_user_id:
        stmt = stmt.where(Report.reported_user_id == reported_user_id)
    if group_id:
        stmt = stmt.where(Report.group_id == group_id)
    stmt = stmt.order_by(Report.id.desc()).offset(skip).limit(limit)
    rows = db.scalars(stmt).all()
    return rows


@router.post("/{report_id}/audit")
def audit_report(
    report_id: int,
    action: str = Query(..., pattern="^(approve|reject)$"),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    r = db.get(Report, report_id)
    if not r:
        raise HTTPException(status_code=404, detail="举报不存在")
    r.audit_state = "审核通过" if action == "approve" else "审核未通过"
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"message": "已更新举报审核状态", "report": r}


@router.delete("/{report_id}")
def delete_my_report(
    report_id: int,
    x_user_id: int = Header(..., alias="X-User-Id"),
    db: Session = Depends(get_db),
):
    """用户删除自己提交的举报（需 Header: X-User-Id）"""
    r = db.get(Report, report_id)
    if not r:
        raise HTTPException(status_code=404, detail="举报不存在")
    if r.user_id != x_user_id:
        raise HTTPException(status_code=403, detail="无权删除此举报")
    db.delete(r)
    db.commit()
    return {"message": "已删除"}


