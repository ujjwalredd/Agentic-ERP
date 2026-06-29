"""Redis Streams event broker.

Streams give us a durable, at-least-once work queue (unlike pub/sub, which drops
events when no consumer is listening and fans every message out to every worker).
A single consumer group (`event_group`) lets multiple worker replicas share the
load; messages stay in the pending-entries list until explicitly acked, so a
worker crash never loses an event.
"""
from __future__ import annotations

import json
import logging
import socket
from collections.abc import Iterator
from typing import NamedTuple

import redis

from app.config import settings
from app.events.types import Event

log = logging.getLogger("events")
_client: redis.Redis | None = None


def client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client


def consumer_name() -> str:
    return settings.event_consumer or socket.gethostname() or "worker"


class Delivery(NamedTuple):
    """One stream message handed to the worker. `msg_id` + `deliveries` let the
    worker ack on success or dead-letter after too many failed attempts."""

    msg_id: str
    event: Event
    deliveries: int


def publish(event: Event) -> None:
    """Best-effort emit. A broker outage must never roll back a committed ledger
    action, so connection errors are logged rather than raised."""
    try:
        client().xadd(settings.event_channel, {"payload": json.dumps(event.to_dict())})
    except redis.RedisError:
        log.warning("event %s not published (broker unavailable)", event.type)


def ensure_group() -> None:
    """Create the consumer group (idempotent). MKSTREAM so it works before any
    event has been published."""
    try:
        client().xgroup_create(
            settings.event_channel, settings.event_group, id="0", mkstream=True
        )
    except redis.ResponseError as e:
        if "BUSYGROUP" not in str(e):  # group already exists -> fine
            raise


def _to_event(fields: dict) -> Event | None:
    try:
        return Event.from_dict(json.loads(fields["payload"]))
    except (json.JSONDecodeError, KeyError):
        return None


def _delivery_count(msg_id: str) -> int:
    """How many times this message has been delivered (1 on first read)."""
    try:
        pending = client().xpending_range(
            settings.event_channel, settings.event_group,
            min=msg_id, max=msg_id, count=1,
        )
        if pending:
            return int(pending[0]["times_delivered"])
    except redis.RedisError:
        pass
    return 1


def subscribe() -> Iterator[Delivery]:
    """Blocking generator yielding undelivered + reclaimed events for this group.

    Each iteration first reclaims messages other consumers left unacked too long
    (crash recovery via XAUTOCLAIM), then blocks for new messages (XREADGROUP).
    """
    ensure_group()
    c = client()
    me = consumer_name()
    log.info("consuming stream=%s group=%s as=%s", settings.event_channel, settings.event_group, me)

    while True:
        # 1. Reclaim stale pending messages from dead/slow consumers.
        try:
            _, claimed, _ = c.xautoclaim(
                settings.event_channel, settings.event_group, me,
                min_idle_time=settings.event_reclaim_idle_ms, start_id="0", count=10,
            )
        except redis.RedisError:
            claimed = []
        for msg_id, fields in claimed:
            if not fields:  # message was already deleted/dead-lettered
                continue
            ev = _to_event(fields)
            if ev is None:
                c.xack(settings.event_channel, settings.event_group, msg_id)
                continue
            yield Delivery(msg_id, ev, _delivery_count(msg_id))

        # 2. Read new messages (block up to 5s, then loop to re-check reclaims).
        try:
            resp = c.xreadgroup(
                settings.event_group, me,
                {settings.event_channel: ">"}, count=10, block=5000,
            )
        except redis.RedisError as e:
            log.warning("xreadgroup failed: %s", e)
            continue
        for _stream, messages in resp or []:
            for msg_id, fields in messages:
                ev = _to_event(fields)
                if ev is None:
                    c.xack(settings.event_channel, settings.event_group, msg_id)
                    continue
                yield Delivery(msg_id, ev, _delivery_count(msg_id))


def ack(msg_id: str) -> None:
    try:
        client().xack(settings.event_channel, settings.event_group, msg_id)
    except redis.RedisError:
        log.warning("ack failed for %s", msg_id)


def dead_letter(msg_id: str, event: Event, error: str) -> None:
    """Move a repeatedly-failing message to the dead-letter stream and ack the
    original so it stops being redelivered."""
    try:
        client().xadd(
            settings.event_dead_letter,
            {"payload": json.dumps(event.to_dict()), "error": error[:500], "orig_id": msg_id},
        )
    except redis.RedisError:
        log.warning("could not write %s to dead-letter stream", msg_id)
    ack(msg_id)
