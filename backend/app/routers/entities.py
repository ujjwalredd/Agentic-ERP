from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import Entity

router = APIRouter(prefix="/entities", tags=["entities"])


@router.get("")
def list_entities(db: Session = Depends(get_db)):
    return [
        {
            "id": e.id,
            "name": e.name,
            "parent_id": e.parent_id,
            "currency": e.currency,
        }
        for e in db.scalars(select(Entity).order_by(Entity.id))
    ]
