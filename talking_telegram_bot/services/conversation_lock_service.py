from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator


class ConversationLockService:
    def __init__(self) -> None:
        self._locks: dict[int, asyncio.Lock] = {}

    @asynccontextmanager
    async def lock(self, user_id: int) -> AsyncIterator[None]:
        lock = self._locks.setdefault(user_id, asyncio.Lock())
        async with lock:
            yield

