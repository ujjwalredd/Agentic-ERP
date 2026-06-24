"""Demo driver: fire events onto the bus so the worker wakes the agents.

The frontend Simulate panel calls these. Each kind maps seed data to an Event.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import BankTransaction, Bill, Entity, Invoice
from app.events import bus
from app.events.types import (
    Event,
    AR_OVERDUE,
    BANK_LINE,
    CLOSE_TRIGGER,
    INTERCOMPANY,
    INVOICE_RECEIVED,
)
from app.schemas import SimulateRequest
from app.security import current_user

router = APIRouter(prefix="/simulate", tags=["simulate"])


@router.post("")
def simulate(
    body: SimulateRequest,
    db: Session = Depends(get_db),
    user: str = Depends(current_user),
):
    fired: list[dict] = []

    if body.kind == "bank_feed":
        # Fire every still-unmatched, non-intercompany bank line.
        lines = db.scalars(
            select(BankTransaction).where(
                BankTransaction.status == "unmatched",
                ~BankTransaction.description.ilike("%intercompany%"),
            )
        )
        for bt in lines:
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
            fired.append({"type": ev.type, "id": ev.id, "desc": bt.description})

    elif body.kind == "intercompany":
        bt = db.scalar(
            select(BankTransaction).where(
                BankTransaction.description.ilike("%intercompany%"),
                BankTransaction.status == "unmatched",
            )
        )
        if bt:
            ev = Event(
                type=INTERCOMPANY,
                data={
                    "bank_transaction_id": bt.id,
                    "entity_id": bt.entity_id,
                    "description": bt.description,
                    "amount": float(bt.amount),
                },
            )
            bus.publish(ev)
            fired.append({"type": ev.type, "id": ev.id, "desc": bt.description})

    elif body.kind == "bill":
        bill = db.scalar(select(Bill).where(Bill.status == "staged"))
        if bill:
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
            fired.append({"type": ev.type, "id": ev.id, "desc": bill.vendor})

    elif body.kind == "invoice":  # AR overdue
        inv = db.scalar(select(Invoice).where(Invoice.status == "overdue"))
        if inv:
            ev = Event(
                type=AR_OVERDUE,
                data={
                    "invoice_id": inv.id,
                    "entity_id": inv.entity_id,
                    "customer": inv.customer,
                    "amount": float(inv.amount),
                    "due_date": inv.due_date.isoformat(),
                },
            )
            bus.publish(ev)
            fired.append({"type": ev.type, "id": ev.id, "desc": inv.customer})

    elif body.kind == "close":
        for ent in db.scalars(select(Entity)):
            ev = Event(type=CLOSE_TRIGGER, data={"entity_id": ent.id, "entity": ent.name})
            bus.publish(ev)
            fired.append({"type": ev.type, "id": ev.id, "desc": ent.name})

    return {"fired": fired, "count": len(fired)}
