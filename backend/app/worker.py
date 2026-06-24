"""Event worker: consumes the bus and runs the Orchestrator graph per event.

`entry.posted` events are informational here (consolidation is computed live by
the reports endpoint), so we just log them. All ingress events are routed through
the LangGraph supervisor which wakes the right specialist agent.
"""
from __future__ import annotations

import logging

from app.agents import graph
from app.db.base import SessionLocal, init_db
from app.events import bus
from app.events.types import ENTRY_POSTED

logging.basicConfig(level=logging.INFO, format="%(asctime)s worker %(message)s")
log = logging.getLogger("worker")


def handle(event) -> None:
    if event.type == ENTRY_POSTED:
        log.info("entry.posted je=%s -> consolidation recomputes live", event.data)
        return

    db = SessionLocal()
    try:
        ids = graph.run_event(db, event.type, event.data, source_event_id=event.id)
        log.info("event %s (%s) -> proposed actions %s", event.type, event.id, ids)
    except Exception:  # never let one bad event kill the worker
        log.exception("error handling event %s", event.type)
        db.rollback()
    finally:
        db.close()


def main() -> None:
    try:
        init_db()
    except Exception:  # backend may have seeded first; never block the consumer
        log.exception("init_db failed in worker; continuing to consume")
    log.info("worker up, listening on the event bus")
    for event in bus.subscribe():
        handle(event)


if __name__ == "__main__":
    main()
