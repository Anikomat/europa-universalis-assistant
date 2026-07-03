"""
轻量异步 EventBus — 线程内发布订阅
"""
import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)

EventName = str
Handler = Callable[[Any], Awaitable[None]]


class EventBus:
    """线程内异步事件总线"""

    def __init__(self):
        self._handlers: dict[EventName, list[Handler]] = defaultdict(list)

    def subscribe(self, event: EventName, handler: Handler):
        self._handlers[event].append(handler)
        name = getattr(handler, "__name__", str(handler))
        logger.debug(f"订阅事件: {event} -> {name}")

    def unsubscribe(self, event: EventName, handler: Handler):
        """移除指定 handler；找不到则静默忽略"""
        handlers = self._handlers.get(event)
        if not handlers:
            return
        try:
            handlers.remove(handler)
            name = getattr(handler, "__name__", str(handler))
            logger.debug(f"取消订阅: {event} -> {name}")
        except ValueError:
            pass

    async def publish(self, event: EventName, data: Any = None):
        handlers = self._handlers.get(event, [])
        if not handlers:
            return
        logger.debug(f"发布事件: {event}, handlers={len(handlers)}")
        await asyncio.gather(*(h(data) for h in handlers))
