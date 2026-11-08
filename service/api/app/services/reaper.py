"""Lease reaper for claimed, running, and canceling jobs."""

from __future__ import annotations

import logging
import threading

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..db import write_transaction
from ..models import Job, Worker
from ..settings import Settings
from ..timeutils import utcnow_iso
from .events import add_event

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ("claimed", "running", "canceling")


def reap_expired_leases(
    session_factory: sessionmaker[Session],
    settings: Settings,
) -> int:
    """Fail or cancel active jobs whose worker lease has expired."""

    session = session_factory()
    reaped = 0
    try:
        with write_transaction(session):
            now = utcnow_iso()
            expired = list(
                session.scalars(
                    select(Job).where(
                        Job.status.in_(ACTIVE_STATUSES),
                        Job.lease_expires_at.is_not(None),
                        Job.lease_expires_at < now,
                    )
                )
            )
            for job in expired:
                previous_status = job.status
                worker_id = job.worker_id

                if job.cancel_requested:
                    job.status = "canceled"
                    add_event(
                        session,
                        job.id,
                        "canceled",
                        "Cancellation completed after the worker lease expired",
                        {
                            "reason": "lease_expired",
                            "previous_status": previous_status,
                            "worker_id": worker_id,
                        },
                    )
                else:
                    job.status = "failed"
                    job.error_code = "worker_lost"
                    job.error_message = (
                        f"Worker {worker_id!r} lease expired before the job "
                        "finished"
                    )
                    add_event(
                        session,
                        job.id,
                        "failed",
                        "Job failed because the worker lease expired",
                        {
                            "reason": "lease_expired",
                            "previous_status": previous_status,
                            "worker_id": worker_id,
                        },
                    )

                job.completed_at = now
                job.updated_at = now
                job.worker_id = None
                job.run_token = None
                job.lease_expires_at = None

                if worker_id is not None:
                    worker = session.get(Worker, worker_id)
                    if worker is not None and worker.current_job_id == job.id:
                        worker.status = "offline"
                        worker.current_job_id = None
                        worker.last_heartbeat_at = now

                reaped += 1
    finally:
        session.close()

    if reaped:
        logger.info("Reaped %s job(s) with expired worker leases", reaped)
    return reaped


class LeaseReaper:
    """Small background thread that reaps expired leases."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="lease-reaper",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                reap_expired_leases(self._session_factory, self._settings)
            except Exception:  # pragma: no cover - defensive
                logger.exception("Lease reaper iteration failed")
            self._stop.wait(self._settings.reaper_interval_seconds)
