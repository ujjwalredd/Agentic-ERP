"""Thin Redis pub/sub wrapper used as the event broker."""
from __future__ import annotations

import json
import logging
from collections.abc import Iterator

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


def publish(event: Event) -> None:
    """Best-effort emit. A broker outage must never roll back a committed ledger
    action, so connection errors are logged rather than raised."""
    try:
        client().publish(settings.event_channel, json.dumps(event.to_dict()))
    except redis.RedisError:
        log.warning("event %s not published (broker unavailable)", event.type)


def subscribe() -> Iterator[Event]:
    """Blocking generator yielding events off the channel. Used by the worker."""
    pubsub = client().pubsub()
    pubsub.subscribe(settings.event_channel)
    for message in pubsub.listen():
        if message.get("type") != "message":
            continue
        try:
            yield Event.from_dict(json.loads(message["data"]))
        except (json.JSONDecodeError, KeyError):
            continue
