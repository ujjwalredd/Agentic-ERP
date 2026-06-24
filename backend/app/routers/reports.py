from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.security import current_user
from app.services.consolidation import consolidated_pnl

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/consolidated-pnl")
def consolidated(db: Session = Depends(get_db), user: str = Depends(current_user)):
    """Real-time multi-entity P&L with intercompany eliminations."""
    return consolidated_pnl(db)
