from __future__ import annotations

import argparse
import os
import signal
import sys
from typing import Any

from rq import Queue, Worker

from trustdesk.core.config import settings
from trustdesk.core.logging import configure_logging, get_logger
from trustdesk.core.redis import get_redis_client
from trustdesk.worker.reconciliation import reconcile_stale_evaluations

logger = get_logger(__name__)


def run_worker_daemon(burst: bool = False, worker_name: str | None = None) -> None:
    """Run the TrustDesk RQ background worker daemon.

    1. Executes pre-flight reconciliation to detect and recover orphaned/interrupted runs.
    2. Connects to the configured Redis queue.
    3. Handles graceful shutdown on SIGINT / SIGTERM.
    4. Executes jobs outside the HTTP request lifecycle.
    """
    configure_logging()
    pid = os.getpid()
    name = worker_name or f"trustdesk-worker-{pid}"

    logger.info("Starting TrustDesk RQ worker '%s' (PID=%d, burst=%s)", name, pid, burst)

    # 1. Startup reconciliation sweep
    try:
        reconciled = reconcile_stale_evaluations()
        if reconciled:
            logger.info("Startup reconciliation recovered %d stale evaluation run(s)", len(reconciled))
    except Exception as exc:
        logger.warning("Startup reconciliation check encountered error: %s", exc)

    # 2. Initialize Redis client and queue
    redis_conn = get_redis_client()
    queue = Queue(settings.rq_queue_name, connection=redis_conn)

    # 3. Initialize RQ Worker
    worker = Worker([queue], connection=redis_conn, name=name)

    def _handle_signal(signum: int, frame: Any) -> None:
        signame = signal.Signals(signum).name
        logger.info("Received termination signal %s; shutting down worker gracefully...", signame)
        # In RQ, request_stop() signals the worker to exit after finishing the current job
        worker.request_stop(signum, frame)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logger.info("Listening for background jobs on queue '%s'...", settings.rq_queue_name)

    # 4. Process jobs
    try:
        worker.work(burst=burst)
    except Exception as exc:
        logger.critical("Worker encountered fatal crash: %s", exc, exc_info=True)
        sys.exit(1)

    logger.info("TrustDesk worker '%s' stopped cleanly.", name)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m trustdesk.worker.worker",
        description="TrustDesk RQ Background Task Worker Daemon",
    )
    parser.add_argument(
        "--burst",
        action="store_true",
        default=False,
        help="Run in burst mode: process all currently queued jobs and exit",
    )
    parser.add_argument(
        "--reconcile",
        action="store_true",
        default=False,
        help="Run operational reconciliation sweep for stale evaluations and exit without consuming jobs",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Custom worker name identifier",
    )

    args = parser.parse_args()

    if args.reconcile:
        configure_logging()
        logger.info("Running standalone evaluation failure reconciliation sweep...")
        try:
            reconciled = reconcile_stale_evaluations()
            msg = f"Reconciliation sweep completed: {len(reconciled)} run(s) reconciled."
            logger.info(msg)
            print(msg)
        except Exception as exc:
            logger.warning("Reconciliation sweep encountered error: %s", exc)
            print(f"Reconciliation sweep encountered error: {exc}", file=sys.stderr)
        sys.exit(0)

    run_worker_daemon(burst=args.burst, worker_name=args.name)


if __name__ == "__main__":
    main()

