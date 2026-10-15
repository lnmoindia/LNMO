# Chat event pub/sub. Local sockets get events immediately; every event is also written to Mongo `rt_events`
# so sockets held by OTHER backend processes/replicas (production may run several) receive it within ~150 ms.
import asyncio
import logging
import os
import uuid
from collections import defaultdict
from datetime import datetime, timezone

log = logging.getLogger("lnmo.realtime")
NODE = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
POLL_S = 0.15
SEND_TIMEOUT_S = 5


class Hub:
    def __init__(self):
        self.conns = defaultdict(set)
        self.db = None
        self._task = None
        self._last = None

    def add(self, uid, ws):
        self.conns[uid].add(ws)

    def remove(self, uid, ws):
        self.conns[uid].discard(ws)
        if not self.conns[uid]:
            self.conns.pop(uid, None)

    def online(self, uid) -> bool:
        return bool(self.conns.get(uid))

    async def _local(self, user_ids, event, exclude=None):
        targets = [(u, ws) for u in set(user_ids or []) if u and u != exclude for ws in list(self.conns.get(u, ()))]

        async def send(u, ws):
            try:
                await asyncio.wait_for(ws.send_json(event), SEND_TIMEOUT_S)
            except Exception:
                self.remove(u, ws)
        if targets:
            await asyncio.gather(*(send(u, ws) for u, ws in targets))

    async def publish(self, user_ids, event: dict, exclude=None):
        ids = [u for u in set(user_ids or []) if u]
        await self._local(ids, event, exclude)
        if self.db is not None and ids:
            try:
                await self.db.rt_events.insert_one({"node": NODE, "users": ids, "exclude": exclude, "event": event,
                                                    "at": datetime.now(timezone.utc)})
            except Exception:
                log.exception("rt_events insert failed")

    async def start(self, db):
        """Begin relaying events published by other processes (idempotent)."""
        self.db = db
        if self._task:
            return
        try:
            await db.rt_events.create_index("at", expireAfterSeconds=120)
        except Exception:
            log.warning("rt_events TTL index not created")
        last = await db.rt_events.find_one({}, sort=[("_id", -1)], projection={"_id": 1})
        self._last = last["_id"] if last else None
        self._task = asyncio.get_event_loop().create_task(self._relay())

    async def _relay(self):
        while True:
            try:
                q = {"_id": {"$gt": self._last}} if self._last else {}
                async for d in self.db.rt_events.find(q).sort("_id", 1).limit(500):
                    self._last = d["_id"]
                    if d.get("node") != NODE and any(u in self.conns for u in d.get("users") or []):
                        await self._local(d["users"], d["event"], d.get("exclude"))
            except Exception:
                log.exception("rt_events relay error")
                await asyncio.sleep(1)
            await asyncio.sleep(POLL_S)


hub = Hub()
