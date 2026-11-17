"""Shared state for claims, audits, promises and the memory log.

Vercel runs each request in a fresh function, so in-process dicts don't survive between calls.
With Upstash Redis keys set (add Upstash from the Vercel Marketplace), state lives there. Without
them, a process-local dict is used: fine for `uvicorn` on a laptop, not for a deployed demo.
Cognee is the agent's memory; this store is just the app's bookkeeping.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from .config import Settings

_LOCAL: dict[str, Any] = {}


class Store:
    def __init__(self, settings: Settings):
        self.s = settings
        self.kind = "redis" if settings.redis_enabled else "memory"

    async def _cmd(self, *args: Any) -> Any:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                self.s.redis_url,
                headers={"Authorization": f"Bearer {self.s.redis_token}"},
                json=[str(a) for a in args],
            )
            resp.raise_for_status()
            return resp.json().get("result")

    async def get(self, key: str) -> Any:
        if self.kind == "memory":
            return _LOCAL.get(key)
        raw = await self._cmd("GET", f"clawback:{key}")
        return json.loads(raw) if raw else None

    async def set(self, key: str, value: Any) -> None:
        if self.kind == "memory":
            _LOCAL[key] = value
            return
        await self._cmd("SET", f"clawback:{key}", json.dumps(value, default=str))

    async def delete(self, key: str) -> None:
        if self.kind == "memory":
            _LOCAL.pop(key, None)
            return
        await self._cmd("DEL", f"clawback:{key}")

    async def push(self, key: str, value: Any, cap: int = 200) -> None:
        """Prepend to a capped list (newest first)."""
        if self.kind == "memory":
            items = _LOCAL.setdefault(key, [])
            items.insert(0, value)
            del items[cap:]
            return
        await self._cmd("LPUSH", f"clawback:{key}", json.dumps(value, default=str))
        await self._cmd("LTRIM", f"clawback:{key}", 0, cap - 1)

    async def list(self, key: str, limit: int = 100) -> list[Any]:
        if self.kind == "memory":
            return list(_LOCAL.get(key, []))[:limit]
        raw = await self._cmd("LRANGE", f"clawback:{key}", 0, limit - 1) or []
        return [json.loads(r) for r in raw]

    async def reset(self) -> None:
        """Wipes the app's bookkeeping (not Cognee). Used by POST /api/py/reset before a demo run."""
        if self.kind == "memory":
            _LOCAL.clear()
            return
        keys = await self._cmd("KEYS", "clawback:*") or []
        for k in keys:
            await self._cmd("DEL", k)
