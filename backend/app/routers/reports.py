from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.services.consolidation import consolidated_pnl

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/consolidated-pnl")
def consolidated(db: Session = Depends(get_db)):
    """Real-time multi-entity P&L with intercompany eliminations."""
    return consolidated_pnl(db)
