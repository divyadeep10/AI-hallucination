# Windows has no os.fork(); RQ's Worker uses fork_work_horse -> os.fork().
# Patch multiprocessing.get_context so 'fork' -> 'spawn' (for rq.scheduler import),
# and use SimpleWorker on Windows so jobs run in-process (no fork).
import sys

if sys.platform == "win32":
    import multiprocessing
    _orig_get_context = multiprocessing.get_context
    def _get_context(method=None):
        if method == "fork":
            method = "spawn"
        return _orig_get_context(method)
    multiprocessing.get_context = _get_context

from rq import Queue, Worker, SimpleWorker

from app.queue import WORKFLOW_QUEUE_NAME, get_redis_connection


def main() -> None:
    """
    Entry point for the RQ worker process.

    This worker listens on the workflow queue and executes enqueued agents
    such as the PlannerAgent introduced in Phase 2.

    On Windows, uses SimpleWorker (no os.fork); on Unix uses Worker.
    """
    connection = get_redis_connection()
    queue = Queue(WORKFLOW_QUEUE_NAME, connection=connection)
    worker_class = SimpleWorker if sys.platform == "win32" else Worker
    worker = worker_class(queues=[queue], connection=connection)
    worker.work()


if __name__ == "__main__":
    main()

