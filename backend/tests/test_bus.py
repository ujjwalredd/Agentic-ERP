"""Redis Streams bus: publish -> consume -> ack, and dead-letter. Redis-gated."""
import uuid

import pytest

from app.config import settings
from app.events import bus
from app.events.types import Event


def _redis_available() -> bool:
    try:
        bus.client().ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _redis_available(), reason="Redis not reachable; bus tests skipped"
)


@pytest.fixture(autouse=True)
def _isolated_stream(monkeypatch):
    # Use a throwaway stream/group per test so we never touch the real queue.
    suffix = uuid.uuid4().hex[:8]
    monkeypatch.setattr(settings, "event_channel", f"test.events.{suffix}")
    monkeypatch.setattr(settings, "event_group", f"test-group-{suffix}")
    monkeypatch.setattr(settings, "event_dead_letter", f"test.dead.{suffix}")
    yield
    try:
        bus.client().delete(settings.event_channel, settings.event_dead_letter)
    except Exception:
        pass


def test_publish_consume_ack():
    ev = Event(type="bank.line", data={"x": 1})
    bus.publish(ev)
    gen = bus.subscribe()
    delivery = next(gen)
    assert delivery.event.type == "bank.line"
    assert delivery.event.data == {"x": 1}
    assert delivery.deliveries >= 1
    bus.ack(delivery.msg_id)
    # after ack there are no pending entries for this consumer group
    pending = bus.client().xpending(settings.event_channel, settings.event_group)
    assert pending["pending"] == 0


def test_dead_letter_moves_message():
    ev = Event(type="bank.line", data={"poison": True})
    bus.publish(ev)
    delivery = next(bus.subscribe())
    bus.dead_letter(delivery.msg_id, delivery.event, "boom")
    # original acked, dead-letter stream has the message
    pending = bus.client().xpending(settings.event_channel, settings.event_group)
    assert pending["pending"] == 0
    assert bus.client().xlen(settings.event_dead_letter) == 1
