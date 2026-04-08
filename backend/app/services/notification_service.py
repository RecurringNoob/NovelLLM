"""
app/services/notification_service.py — WebSocket badge notifications.

Sends pending_bible_update count badges to connected clients via Redis Pub/Sub.
In Phase 6, Hocuspocus will relay these over WebSocket.
For Phase 2, we publish to a Redis channel that any connected client can subscribe to.
"""
from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis_client import get_redis_pool
from app.models.bible import PendingBibleUpdate

logger = logging.getLogger("notelm.notifications")

CHANNEL_PREFIX = "notelm:project:"


async def notify_pending_badge(db: AsyncSession, project_id: uuid.UUID) -> None:
    """
    Count pending bible updates and publish a badge event to Redis.

    Payload:
        { "type": "pending_bible_updates", "project_id": "<uuid>", "count": <int> }

    Phase 6: Hocuspocus subscribes to this channel and relays over WebSocket.
    """
    result = await db.execute(
        select(func.count()).where(
            PendingBibleUpdate.project_id == project_id,
            PendingBibleUpdate.status == "pending",
        )
    )
    count = result.scalar_one()

    try:
        redis = get_redis_pool()
        channel = f"{CHANNEL_PREFIX}{project_id}:notifications"
        payload = json.dumps({
            "type": "pending_bible_updates",
            "project_id": str(project_id),
            "count": count,
        })
        await redis.publish(channel, payload)
        logger.debug("Badge published | project=%s count=%d", project_id, count)
    except Exception as exc:
        # Non-fatal — Redis down degrades badge notifications, not core data
        logger.warning("Badge publish failed (Redis down?): %s", exc)
