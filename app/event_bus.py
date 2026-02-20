"""Pub/sub event bus for inter-tab communication."""

from __future__ import annotations
from collections import defaultdict
from typing import Any, Callable

from app.logger import get_logger

logger = get_logger(__name__)


class EventBus:
    """Simple publish/subscribe event bus."""

    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)

    def subscribe(self, event: str, callback: Callable) -> None:
        self._subscribers[event].append(callback)

    def unsubscribe(self, event: str, callback: Callable) -> None:
        if callback in self._subscribers[event]:
            self._subscribers[event].remove(callback)

    def publish(self, event: str, **kwargs: Any) -> None:
        for callback in self._subscribers[event]:
            try:
                callback(**kwargs)
            except Exception:
                logger.error("EventBus error in '%s'", event, exc_info=True)


event_bus = EventBus()
