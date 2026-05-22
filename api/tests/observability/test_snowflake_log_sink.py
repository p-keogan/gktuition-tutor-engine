"""Unit tests for the Snowflake-backed batched log sink (Agent 12).

Covers the three verification axes called out in the prompt:

* **buffer flush behaviour** — records accumulate in memory; the buffer
  drains when either the size threshold or the interval timer fires;
  synchronous ``flush()`` always works.
* **error fallback** — when the injected writer raises, the batch is
  dropped (lossy), the error counter ticks, and a stdout fallback row is
  emitted so the data is recoverable from Fly logs.
* **batch coalescing** — many enqueues coalesce into one writer call;
  the ``flush_size`` trigger is honoured.

The tests run the sink against a fake writer that captures call args.
No Snowflake connector is imported.
"""
from __future__ import annotations

import logging
import threading
import time

import pytest

from api.observability.snowflake_log_sink import (
    SnowflakeLogSink,
    SnowflakeLogSinkConfig,
    install_default_sink,
    sink_from_env,
)

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


class FakeWriter:
    """Captures every batch the sink flushes."""

    def __init__(self) -> None:
        self.batches: list[list[dict]] = []
        self.lock = threading.Lock()

    def __call__(self, batch: list[dict]) -> None:
        with self.lock:
            # Defensive copy — the sink owns the batch list, we should not
            # depend on it being immutable for assertions.
            self.batches.append([dict(r) for r in batch])

    @property
    def total_rows(self) -> int:
        return sum(len(b) for b in self.batches)


class RaisingWriter:
    """A writer that raises on call. Used for fallback tests."""

    def __init__(self, exc: Exception | None = None) -> None:
        self.calls = 0
        self.exc = exc or RuntimeError("snowflake unavailable")

    def __call__(self, batch: list[dict]) -> None:
        self.calls += 1
        raise self.exc


def make_row(query_id: str = "q1", q: str = "test") -> dict:
    return {
        "query_id": query_id,
        "q": q,
        "tier": "anonymous",
        "query_type": "text",
        "query_class": "concept",
        "model_used": "cortex.mistral-large2",
        "from_cache": False,
        "elapsed_ms": 42,
        "cost_estimate_cents": 0.10,
        "created_at": "2026-05-22T12:00:00+00:00",
    }


@pytest.fixture(autouse=True)
def _quiet_root_logger() -> None:
    """Avoid the test pytest output getting flooded by sink warnings."""
    root = logging.getLogger()
    prev = root.level
    root.setLevel(logging.CRITICAL)
    yield
    root.setLevel(prev)


# ---------------------------------------------------------------------------
# Buffer / flush behaviour
# ---------------------------------------------------------------------------


def test_enqueue_below_threshold_does_not_flush() -> None:
    """Records below ``flush_size`` stay in the buffer until timer or explicit flush."""
    writer = FakeWriter()
    # Very long interval so the timer doesn't interfere.
    sink = SnowflakeLogSink(
        writer=writer,
        config=SnowflakeLogSinkConfig(flush_interval_seconds=300, flush_size=10),
    )
    try:
        for i in range(5):
            sink.enqueue(make_row(query_id=f"q{i}"))
        time.sleep(0.05)  # let any spurious wake-ups settle
        assert writer.batches == []  # nothing flushed yet
        sink.flush()
        assert writer.total_rows == 5
        assert len(writer.batches) == 1
        assert [r["query_id"] for r in writer.batches[0]] == [f"q{i}" for i in range(5)]
    finally:
        sink.close()


def test_enqueue_at_threshold_flushes_inline() -> None:
    """Once the buffer hits ``flush_size``, the enqueueing thread drains it."""
    writer = FakeWriter()
    sink = SnowflakeLogSink(
        writer=writer,
        config=SnowflakeLogSinkConfig(flush_interval_seconds=300, flush_size=3),
    )
    try:
        for i in range(3):
            sink.enqueue(make_row(query_id=f"q{i}"))
        # No timer dependency — the inline flush should have happened by now.
        assert len(writer.batches) == 1
        assert len(writer.batches[0]) == 3
    finally:
        sink.close()


def test_timer_flushes_after_interval() -> None:
    """The background thread flushes the buffer on the timer too."""
    writer = FakeWriter()
    sink = SnowflakeLogSink(
        writer=writer,
        config=SnowflakeLogSinkConfig(flush_interval_seconds=0.1, flush_size=1000),
    )
    try:
        sink.enqueue(make_row(query_id="q-timer"))
        # Give the timer thread a few wake-cycles to drain.
        deadline = time.time() + 1.5
        while time.time() < deadline and writer.total_rows == 0:
            time.sleep(0.05)
        assert writer.total_rows == 1, "timer thread should have flushed by now"
    finally:
        sink.close()


def test_close_runs_final_flush() -> None:
    """``close()`` drains remaining buffered rows."""
    writer = FakeWriter()
    sink = SnowflakeLogSink(
        writer=writer,
        config=SnowflakeLogSinkConfig(flush_interval_seconds=300, flush_size=100),
    )
    sink.enqueue(make_row("final-1"))
    sink.enqueue(make_row("final-2"))
    sink.close()
    assert writer.total_rows == 2
    assert {r["query_id"] for r in writer.batches[-1]} == {"final-1", "final-2"}


# ---------------------------------------------------------------------------
# Error fallback
# ---------------------------------------------------------------------------


def test_writer_exception_does_not_propagate(capsys) -> None:
    """A raising writer is caught; the sink logs to stdout instead."""
    writer = RaisingWriter()
    sink = SnowflakeLogSink(
        writer=writer,
        config=SnowflakeLogSinkConfig(flush_interval_seconds=300, flush_size=2),
    )
    try:
        # Two enqueues = triggers a flush, which raises internally.
        sink.enqueue(make_row("err-1"))
        sink.enqueue(make_row("err-2"))  # triggers inline flush -> raises
        captured = capsys.readouterr()
        assert "[snowflake_log_sink][FALLBACK]" in captured.out
        assert "err-1" in captured.out and "err-2" in captured.out
        # Stats reflect the drop.
        stats = sink.stats()
        assert stats.flush_errors == 1
        assert stats.dropped_on_error == 2
        assert stats.flushed == 0
    finally:
        sink.close()


def test_writer_exception_clears_buffer() -> None:
    """After a writer failure the buffer is empty — subsequent flushes don't repeat the failed batch."""
    writer = RaisingWriter()
    sink = SnowflakeLogSink(
        writer=writer,
        config=SnowflakeLogSinkConfig(flush_interval_seconds=300, flush_size=1),
    )
    try:
        sink.enqueue(make_row("err-clear-1"))   # raises
        assert writer.calls == 1
        # Another enqueue should attempt another flush (since flush_size=1).
        sink.enqueue(make_row("err-clear-2"))
        assert writer.calls == 2
        # If the buffer hadn't been cleared, the second flush would have
        # tried to write two rows, doubling the drop count.
        stats = sink.stats()
        assert stats.dropped_on_error == 2  # 1 per raised flush, not 1+2=3
    finally:
        sink.close()


def test_dropped_invalid_rows_count_and_warn(caplog) -> None:
    """Rows missing required cols are dropped before they hit the writer."""
    writer = FakeWriter()
    sink = SnowflakeLogSink(
        writer=writer,
        config=SnowflakeLogSinkConfig(flush_interval_seconds=300, flush_size=10),
    )
    try:
        sink.enqueue({"tier": "anonymous"})  # missing query_id, q, created_at
        sink.flush()
        assert writer.total_rows == 0
        assert sink.stats().dropped_invalid == 1
    finally:
        sink.close()


# ---------------------------------------------------------------------------
# Batch coalescing
# ---------------------------------------------------------------------------


def test_many_enqueues_coalesce_into_one_call() -> None:
    """N records ≤ flush_size produce one writer call on explicit flush."""
    writer = FakeWriter()
    sink = SnowflakeLogSink(
        writer=writer,
        config=SnowflakeLogSinkConfig(flush_interval_seconds=300, flush_size=1000),
    )
    try:
        for i in range(50):
            sink.enqueue(make_row(query_id=f"row-{i}"))
        sink.flush()
        # One single batch even though 50 enqueues happened.
        assert len(writer.batches) == 1
        assert len(writer.batches[0]) == 50
        # Order preserved.
        assert writer.batches[0][0]["query_id"] == "row-0"
        assert writer.batches[0][-1]["query_id"] == "row-49"
    finally:
        sink.close()


def test_threaded_enqueue_safe() -> None:
    """Many threads enqueueing concurrently don't lose rows."""
    writer = FakeWriter()
    sink = SnowflakeLogSink(
        writer=writer,
        config=SnowflakeLogSinkConfig(flush_interval_seconds=300, flush_size=10000),
    )
    n_threads = 8
    rows_per_thread = 100

    def producer(thread_id: int) -> None:
        for i in range(rows_per_thread):
            sink.enqueue(make_row(query_id=f"t{thread_id}-{i}"))

    threads = [
        threading.Thread(target=producer, args=(t,)) for t in range(n_threads)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    sink.flush()
    sink.close()
    assert writer.total_rows == n_threads * rows_per_thread


# ---------------------------------------------------------------------------
# logging.Handler interface
# ---------------------------------------------------------------------------


def test_emit_skips_records_without_query_id() -> None:
    """LogRecords without a ``query_id`` extra are silently dropped."""
    writer = FakeWriter()
    sink = SnowflakeLogSink(
        writer=writer,
        config=SnowflakeLogSinkConfig(flush_interval_seconds=300, flush_size=10),
    )
    try:
        record = logging.LogRecord(
            name="x", level=logging.INFO, pathname="x", lineno=1,
            msg="hello", args=None, exc_info=None,
        )
        sink.emit(record)
        sink.flush()
        assert writer.total_rows == 0
    finally:
        sink.close()


def test_emit_with_query_id_enqueues_row() -> None:
    """LogRecord extras flow through to the row payload."""
    writer = FakeWriter()
    sink = SnowflakeLogSink(
        writer=writer,
        config=SnowflakeLogSinkConfig(flush_interval_seconds=300, flush_size=10),
    )
    try:
        record = logging.LogRecord(
            name="x", level=logging.INFO, pathname="x", lineno=1,
            msg="hello", args=None, exc_info=None,
        )
        # Attach structured fields the way `logger.info(..., extra={...})` would.
        record.query_id = "log-q-1"
        record.q = "test"
        record.created_at = "2026-05-22T12:00:00+00:00"
        record.tier = "paying"
        sink.emit(record)
        sink.flush()
        assert writer.total_rows == 1
        row = writer.batches[0][0]
        assert row["query_id"] == "log-q-1"
        assert row["tier"] == "paying"
    finally:
        sink.close()


# ---------------------------------------------------------------------------
# Env wiring
# ---------------------------------------------------------------------------


def test_sink_from_env_reads_overrides(monkeypatch) -> None:
    monkeypatch.setenv("SNOWFLAKE_LOG_SINK_TABLE", "DB.SCHEMA.X")
    monkeypatch.setenv("SNOWFLAKE_LOG_SINK_FLUSH_INTERVAL_S", "7")
    monkeypatch.setenv("SNOWFLAKE_LOG_SINK_FLUSH_SIZE", "42")
    writer = FakeWriter()
    sink = sink_from_env(writer=writer)
    try:
        assert sink._config.table_fqn == "DB.SCHEMA.X"
        assert sink._config.flush_interval_seconds == 7.0
        assert sink._config.flush_size == 42
    finally:
        sink.close()


def test_install_default_sink_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("SNOWFLAKE_LOG_SINK_ENABLED", raising=False)
    assert install_default_sink(writer=FakeWriter()) is None


def test_install_default_sink_wires_query_log_writer(monkeypatch) -> None:
    """When enabled, the sink registers itself as the query_log writer."""
    monkeypatch.setenv("SNOWFLAKE_LOG_SINK_ENABLED", "true")
    monkeypatch.setenv("SNOWFLAKE_LOG_SINK_FLUSH_SIZE", "1000")
    monkeypatch.setenv("SNOWFLAKE_LOG_SINK_FLUSH_INTERVAL_S", "300")
    writer = FakeWriter()
    sink = install_default_sink(writer=writer)
    assert sink is not None
    try:
        # Pull the registered writer back out of the seam and call it.
        from api.services import query_log as query_log_svc

        # The query_log writer accepts a dict (no kwargs) — same shape as
        # what the orchestrator's writer emits.
        query_log_svc._writer({
            "query_id": "seam-1",
            "q": "test",
            "tier": "anonymous",
            "query_type": "text",
            "query_class": "concept",
            "model_used": "cortex.mistral-large2",
            "from_cache": False,
            "elapsed_ms": 1,
            "cost_estimate_cents": 0.0,
            "created_at": "2026-05-22T12:00:00+00:00",
        })
        sink.flush()
        assert writer.total_rows == 1
        assert writer.batches[0][0]["query_id"] == "seam-1"
    finally:
        sink.close()
        # Reset the seam so subsequent tests aren't affected.
        from api.services import query_log as query_log_svc
        query_log_svc._writer = None
