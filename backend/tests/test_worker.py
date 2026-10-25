from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.worker import _retry_delay, _run_configured_loop


class FakeStop:
    def __init__(self) -> None:
        self.stopped = False
        self.waits: list[float] = []

    def is_set(self) -> bool:
        return self.stopped

    def wait(self, delay: float) -> bool:
        self.waits.append(delay)
        if len(self.waits) >= 2:
            self.stopped = True
        return self.stopped


class FakeContext:
    def __enter__(self):
        return object()

    def __exit__(self, *_args):
        return None


def test_worker_recovers_after_transient_database_failure() -> None:
    calls = 0
    processed = 0

    def session_factory():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise SQLAlchemyError("temporary database outage")
        return FakeContext()

    def processor(_db, _client, _settings):
        nonlocal processed
        processed += 1
        return False

    stop = FakeStop()
    settings = Settings(extraction_poll_interval_seconds=1)
    _run_configured_loop(settings, stop, object(), session_factory, processor)

    assert calls == 2
    assert processed == 1
    assert stop.waits == [1.0, 1.0]


def test_database_backoff_is_bounded() -> None:
    assert _retry_delay(1, 0.1) == 1.0
    assert _retry_delay(3, 2) == 8
    assert _retry_delay(100, 2) == 30.0
