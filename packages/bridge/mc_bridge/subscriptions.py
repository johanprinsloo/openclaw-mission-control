"""
Subscription management for agent topic filtering.

Tracks which topics/channels an agent is subscribed to.
Supports dynamic subscribe/unsubscribe via bridge commands.
"""

from __future__ import annotations

import structlog

log = structlog.get_logger()


class SubscriptionManager:
    """Manages topic subscriptions for an agent."""

    def __init__(self) -> None:
        self._topics: set[str] = set()

    def subscribe(self, topic: str) -> None:
        self._topics.add(topic)
        log.info("subscriptions.added", topic=topic)

    def unsubscribe(self, topic: str) -> None:
        self._topics.discard(topic)
        log.info("subscriptions.removed", topic=topic)

    def is_subscribed(self, topic: str) -> bool:
        # If no topics set, accept all (auto-subscribe mode)
        if not self._topics:
            return True
        return topic in self._topics

    def list_topics(self) -> list[str]:
        return sorted(self._topics)

    def set_topics(self, topics: list[str]) -> None:
        self._topics = set(topics)
