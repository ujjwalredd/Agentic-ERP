"""Event worker: consumes the Redis Stream and runs the Orchestrator per event.

Delivery is at-least-once: a message is acked only after its handler succeeds.
On failure the message stays pending and is retried (reclaimed via XAUTOCLAIM);
after `event_max_deliveries` attempts it is moved to the dead-letter stream so one
poison event never blocks the queue. Agents are idempotent (see base.pending_exists
+ the bank-line "already matched" guard), so a redelivered event is safe.

`entry.posted` events are informational here (consolidation is computed live by the
reports endpoint), so we just log + ack them.
"""
from __future__ import annotations

import logging

from app.agents import graph
from app.config import settings
from app.db.base import SessionLocal, init_db
from app.events import bus
from app.events.types import ENTRY_POSTED

logging.basicConfig(level=logging.INFO, format="%(asctime)s worker %(message)s")
log = logging.getLogger("worker")


def handle(event) -> None:
    """Process one event. Raises on failure so the caller can retry/dead-letter."""
    if event.type == ENTRY_POSTED:
        log.info("entry.posted je=%s -> consolidation recomputes live", event.data)
        return

    db = SessionLocal()
    try:
        ids = graph.run_event(db, event.type, event.data, source_event_id=event.id)
        log.info("event %s (%s) -> proposed actions %s", event.type, event.id, ids)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    try:
        init_db()
    except Exception:  # backend may have seeded first; never block the consumer
        log.exception("init_db failed in worker; continuing to consume")
    log.info("worker up, listening on the event stream")

    for delivery in bus.subscribe():
        try:
            handle(delivery.event)
            bus.ack(delivery.msg_id)
        except Exception as e:
            if delivery.deliveries >= settings.event_max_deliveries:
                log.exception(
                    "event %s failed %d times -> dead-letter",
                    delivery.event.type, delivery.deliveries,
                )
                bus.dead_letter(delivery.msg_id, delivery.event, str(e))
            else:
                # Leave unacked: it will be reclaimed + retried later.
                log.exception(
                    "event %s failed (attempt %d/%d); will retry",
                    delivery.event.type, delivery.deliveries, settings.event_max_deliveries,
                )


if __name__ == "__main__":
    main()
