"""Real ingress: external systems POST bank lines / invoices here.

Each webhook persists the raw record and emits an event for the worker. (The
Simulate panel replays seed data through the same event types.)
"""
import datetime as dt
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import BankTransaction, Bill
from app.events import bus
from app.events.types import Event, BANK_LINE, INVOICE_RECEIVED
from app.security import require_role

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

controller = require_role("controller")


class BankLineIn(BaseModel):
    entity_id: int
    amount: float
    description: str
    date: str | None = None


class InvoiceIn(BaseModel):
    entity_id: int
    vendor: str
    amount: float
    due_date: str | None = None
    lines: dict = {}


@router.post("/bank")
def bank_webhook(
    body: BankLineIn,
    db: Session = Depends(get_db),
    user: str = Depends(controller),
):
    bt = BankTransaction(
        entity_id=body.entity_id,
        amount=Decimal(str(body.amount)),
        description=body.description,
        date=dt.date.fromisoformat(body.date) if body.date else dt.date.today(),
    )
    db.add(bt)
    db.commit()
    ev = Event(
        type=BANK_LINE,
        data={
            "bank_transaction_id": bt.id,
            "entity_id": bt.entity_id,
            "description": bt.description,
            "amount": float(bt.amount),
            "date": bt.date.isoformat(),
        },
    )
    bus.publish(ev)
    return {"bank_transaction_id": bt.id, "event_id": ev.id}


@router.post("/invoice")
def invoice_webhook(
    body: InvoiceIn,
    db: Session = Depends(get_db),
    user: str = Depends(controller),
):
    bill = Bill(
        entity_id=body.entity_id,
        vendor=body.vendor,
        amount=Decimal(str(body.amount)),
        due_date=dt.date.fromisoformat(body.due_date) if body.due_date else dt.date.today(),
        lines=body.lines,
    )
    db.add(bill)
    db.commit()
    ev = Event(
        type=INVOICE_RECEIVED,
        data={
            "bill_id": bill.id,
            "entity_id": bill.entity_id,
            "vendor": bill.vendor,
            "amount": float(bill.amount),
            "lines": bill.lines,
        },
    )
    bus.publish(ev)
    return {"bill_id": bill.id, "event_id": ev.id}
