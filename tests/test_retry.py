"""Tests for the bounded retry helper."""


import pytest

from src.utils.retry import retry_transient


class _TransientError(Exception):
    """Simulated transient error."""



class _PermanentError(Exception):
    """Simulated non-recoverable error."""



class TestRetryTransient:
    def test_success_on_first_try(self):
        """No retries when the function succeeds immediately."""
        calls = []

        def ok():
            calls.append(1)
            return "done"

        result = retry_transient(
            ok, attempts=3, base_delay=0, recoverable=lambda e: True
        )
        assert result == "done"
        assert len(calls) == 1

    def test_retries_transient_then_succeeds(self):
        """Retries transient errors and succeeds on attempt 3."""
        attempts = [0]

        def flaky():
            attempts[0] += 1
            if attempts[0] < 3:
                raise _TransientError("not yet")
            return "ok"

        result = retry_transient(
            flaky, attempts=3, base_delay=0, recoverable=lambda e: isinstance(e, _TransientError)
        )
        assert result == "ok"
        assert attempts[0] == 3

    def test_exhausts_retries_raises_last(self):
        """Raises last error after exhausting attempts."""
        with pytest.raises(_TransientError, match="fail-3"):
            retry_transient(
                lambda: (_ for _ in ()).throw(_TransientError("fail-3")),
                attempts=2,
                base_delay=0,
                recoverable=lambda e: True,
            )

    def test_non_recoverable_raises_immediately(self):
        """Non-recoverable errors are never retried."""
        calls = []

        def boom():
            calls.append(1)
            raise _PermanentError("bad key")

        with pytest.raises(_PermanentError):
            retry_transient(
                boom, attempts=5, base_delay=0, recoverable=lambda e: False
            )
        assert len(calls) == 1

    def test_mixed_errors_permanent_stops_retry(self):
        """Transient then permanent — permanent stops immediately."""
        calls = []

        def mixed():
            calls.append(1)
            if len(calls) == 1:
                raise _TransientError("transient")
            raise _PermanentError("permanent")

        def recoverable(e):
            return isinstance(e, _TransientError)

        with pytest.raises(_PermanentError):
            retry_transient(
                mixed, attempts=5, base_delay=0, recoverable=recoverable
            )
        assert len(calls) == 2  # first transient, then permanent

    def test_default_args(self):
        """Works with minimal keyword arguments."""
        result = retry_transient(
            lambda: 42,
            attempts=1,
            recoverable=lambda e: True,
        )
        assert result == 42

    def test_backoff_sleeps_between_retries(self, monkeypatch):
        """Verify sleep is called with exponential backoff."""
        sleeps = []
        monkeypatch.setattr("src.utils.retry.time.sleep", lambda d: sleeps.append(d))

        def always_fail():
            raise _TransientError("boom")

        with pytest.raises(_TransientError):
            retry_transient(
                always_fail,
                attempts=3,
                base_delay=1.0,
                backoff=2.0,
                recoverable=lambda e: True,
            )
        # 2 sleeps (between 3 attempts), values 1.0 and 2.0
        assert sleeps == [pytest.approx(1.0), pytest.approx(2.0)]

    def test_no_sleep_when_single_attempt(self):
        """Zero retries means zero sleeps."""
        sleeps = []
        import src.utils.retry as mod

        original_sleep = mod.time.sleep

        def track_sleep(d):
            sleeps.append(d)

        mod.time.sleep = track_sleep
        try:
            with pytest.raises(_TransientError):
                retry_transient(
                    lambda: (_ for _ in ()).throw(_TransientError("once")),
                    attempts=1,
                    base_delay=1.0,
                    recoverable=lambda e: True,
                )
        finally:
            mod.time.sleep = original_sleep
        assert sleeps == []
