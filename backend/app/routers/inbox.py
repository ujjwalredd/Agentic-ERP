from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import AuditLog, ProposedAction
from app.schemas import AuditLogOut, ProposedActionOut
from app.security import current_user
from app.services import approvals
from app.services.approvals import ApprovalError

router = APIRouter(prefix="/inbox", tags=["inbox"])


@router.get("/actions", response_model=list[ProposedActionOut])
def list_actions(status: str = "pending", db: Session = Depends(get_db)):
    stmt = select(ProposedAction).order_by(ProposedAction.created_at.desc())
    if status != "all":
        stmt = stmt.where(ProposedAction.status == status)
    return list(db.scalars(stmt))


@router.post("/actions/{action_id}/approve", response_model=AuditLogOut)
def approve_action(
    action_id: int,
    db: Session = Depends(get_db),
    user: str = Depends(current_user),
):
    action = db.get(ProposedAction, action_id)
    if not action:
        raise HTTPException(404, "action not found")
    try:
        return approvals.approve(db, action, user)
    except ApprovalError as e:
        raise HTTPException(400, str(e))


@router.post("/actions/{action_id}/reject", response_model=AuditLogOut)
def reject_action(
    action_id: int,
    db: Session = Depends(get_db),
    user: str = Depends(current_user),
):
    action = db.get(ProposedAction, action_id)
    if not action:
        raise HTTPException(404, "action not found")
    try:
        return approvals.reject(db, action, user)
    except ApprovalError as e:
        raise HTTPException(400, str(e))


@router.get("/audit", response_model=list[AuditLogOut])
def audit_log(db: Session = Depends(get_db)):
    return list(db.scalars(select(AuditLog).order_by(AuditLog.timestamp.desc())))
