# In-process pub/sub for chat events (single backend instance). Swap `publish` for Redis/change streams later.
import asyncio
from collections import defaultdict


class Hub:
    def __init__(self):
        self.conns = defaultdict(set)

    def add(self, uid, ws):
        self.conns[uid].add(ws)

    def remove(self, uid, ws):
        self.conns[uid].discard(ws)
        if not self.conns[uid]:
            self.conns.pop(uid, None)

    def online(self, uid) -> bool:
        return bool(self.conns.get(uid))

    async def publish(self, user_ids, event: dict, exclude=None):
        targets = [(u, ws) for u in set(user_ids or []) if u and u != exclude for ws in list(self.conns.get(u, ()))]

        async def send(u, ws):
            try:
                await ws.send_json(event)
            except Exception:
                self.remove(u, ws)
        if targets:
            await asyncio.gather(*(send(u, ws) for u, ws in targets))


hub = Hub()
