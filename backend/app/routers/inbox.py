from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import AuditLog, ProposedAction
from app.schemas import AuditLogOut, EditRequest, ProposedActionOut, RejectRequest
from app.security import current_user, require_role
from app.services import approvals
from app.services.approvals import ApprovalError

router = APIRouter(prefix="/inbox", tags=["inbox"])

# Write actions require a controller; reads accept any authenticated principal.
controller = require_role("controller")


@router.get("/actions", response_model=list[ProposedActionOut])
def list_actions(
    status: str = "pending",
    db: Session = Depends(get_db),
    user: str = Depends(current_user),
):
    stmt = select(ProposedAction).order_by(ProposedAction.created_at.desc())
    if status != "all":
        stmt = stmt.where(ProposedAction.status == status)
    return list(db.scalars(stmt))


@router.post("/actions/{action_id}/approve", response_model=AuditLogOut)
def approve_action(
    action_id: int,
    db: Session = Depends(get_db),
    user: str = Depends(controller),
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
    body: RejectRequest | None = None,
    db: Session = Depends(get_db),
    user: str = Depends(controller),
):
    action = db.get(ProposedAction, action_id)
    if not action:
        raise HTTPException(404, "action not found")
    try:
        return approvals.reject(db, action, user, reason=(body.reason if body else ""))
    except ApprovalError as e:
        raise HTTPException(400, str(e))


@router.post("/actions/{action_id}/edit", response_model=AuditLogOut)
def edit_action(
    action_id: int,
    body: EditRequest,
    db: Session = Depends(get_db),
    user: str = Depends(controller),
):
    """Correct a draft (re-categorize), optionally codify it as a rule, then approve."""
    action = db.get(ProposedAction, action_id)
    if not action:
        raise HTTPException(404, "action not found")
    try:
        return approvals.apply_edit(
            db,
            action,
            user,
            account_code=body.account_code,
            reason=body.reason,
            create_rule=body.create_rule,
            auto_approve=body.auto_approve,
        )
    except ApprovalError as e:
        raise HTTPException(400, str(e))


@router.get("/audit", response_model=list[AuditLogOut])
def audit_log(db: Session = Depends(get_db), user: str = Depends(current_user)):
    return list(db.scalars(select(AuditLog).order_by(AuditLog.timestamp.desc())))
