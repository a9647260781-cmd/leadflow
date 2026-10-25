import logging
import signal
import threading

from sqlalchemy.exc import SQLAlchemyError

from .config import get_settings
from .database import SessionLocal
from .extraction import YandexExtractionClient
from .extraction_jobs import mark_unconfigured_jobs, process_one

logger = logging.getLogger("leadflow.extraction_worker")


def _retry_delay(failures: int, poll_interval: float) -> float:
    return min(30.0, max(1.0, poll_interval) * (2 ** min(max(failures - 1, 0), 5)))


def _run_configured_loop(
    settings, stop, client, session_factory=SessionLocal, processor=process_one
):
    failures = 0
    while not stop.is_set():
        try:
            with session_factory() as db:
                worked = processor(db, client, settings)
        except SQLAlchemyError:
            failures += 1
            logger.warning("Extraction worker database unavailable; retrying")
            stop.wait(_retry_delay(failures, settings.extraction_poll_interval_seconds))
            continue
        failures = 0
        if not worked:
            stop.wait(settings.extraction_poll_interval_seconds)


def _reconcile_disabled(settings, stop, session_factory=SessionLocal) -> None:
    failures = 0
    while not stop.is_set():
        try:
            with session_factory() as db:
                changed = mark_unconfigured_jobs(db)
        except SQLAlchemyError:
            failures += 1
            logger.warning("Extraction worker database unavailable; retrying")
            stop.wait(_retry_delay(failures, settings.extraction_poll_interval_seconds))
            continue
        if changed:
            logger.warning("Marked unfinished extraction jobs not_configured")
        return


def run() -> None:
    settings = get_settings()
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())

    if not settings.ai_configured:
        logger.warning("AI extraction is not configured; reconciling unfinished jobs")
        _reconcile_disabled(settings, stop)
        while not stop.wait(settings.extraction_poll_interval_seconds):
            pass
        return

    client = YandexExtractionClient(settings)
    try:
        _run_configured_loop(settings, stop, client)
    finally:
        client.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
