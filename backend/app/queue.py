from typing import Final

# Windows has no 'fork'; RQ uses get_context('fork'). Patch before importing rq.
import sys
if sys.platform == "win32":
    import multiprocessing
    _orig = multiprocessing.get_context
    multiprocessing.get_context = lambda method=None: _orig("spawn" if method == "fork" else method)

import redis
from rq import Queue

from app.config import REDIS_URL, WORKFLOW_QUEUE_NAME
from app.db import SessionLocal


def get_redis_connection() -> redis.Redis:
    return redis.from_url(REDIS_URL)


def get_workflow_queue() -> Queue:
    return Queue(WORKFLOW_QUEUE_NAME, connection=get_redis_connection())


__all__ = ["get_redis_connection", "get_workflow_queue", "WORKFLOW_QUEUE_NAME", "SessionLocal"]

