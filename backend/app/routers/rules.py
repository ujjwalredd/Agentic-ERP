from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import Rule
from app.schemas import RuleIn, RuleOut
from app.security import current_user, require_role
from app.services import rules as rules_svc

router = APIRouter(prefix="/rules", tags=["rules"])

controller = require_role("controller")


@router.get("", response_model=list[RuleOut])
def list_rules(db: Session = Depends(get_db), user: str = Depends(current_user)):
    return list(db.scalars(select(Rule).order_by(Rule.created_at.desc())))


@router.post("", response_model=RuleOut)
def create_rule(body: RuleIn, db: Session = Depends(get_db), user: str = Depends(controller)):
    rule = rules_svc.upsert(
        db,
        entity_id=body.entity_id,
        pattern=body.pattern,
        account_code=body.account_code,
        match_type=body.match_type,
        auto_approve=body.auto_approve,
        min_confidence=body.min_confidence,
        source="manual",
        created_by=user,
    )
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db), user: str = Depends(controller)):
    rule = db.get(Rule, rule_id)
    if not rule:
        raise HTTPException(404, "rule not found")
    db.delete(rule)
    db.commit()
    return {"deleted": rule_id}
