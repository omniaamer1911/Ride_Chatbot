"""In-process asyncio pub/sub for trip updates keyed by user external_id."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue[str]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def subscribe(self, user_external_id: str) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=256)
        async with self._lock:
            self._queues[user_external_id].append(q)
        return q

    async def unsubscribe(self, user_external_id: str, q: asyncio.Queue[str]) -> None:
        async with self._lock:
            subs = self._queues.get(user_external_id, [])
            if q in subs:
                subs.remove(q)
            if not subs:
                self._queues.pop(user_external_id, None)

    async def publish(self, user_external_id: str, event: dict[str, Any]) -> None:
        payload = json.dumps(event, ensure_ascii=False)
        async with self._lock:
            queues = list(self._queues.get(user_external_id, []))
        for q in queues:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    _ = q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    pass
