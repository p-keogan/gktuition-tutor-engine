"""Snowflake-backed structured log sink.

This module implements the "logs piped to Snowflake ``RAW.QUERY_LOG``" piece
of ADR-003. It exposes:

* :class:`SnowflakeLogSink` — a ``logging.Handler`` that batches structured
  records (any record with a ``query_id`` extra, or with ``sink=True``) and
  flushes them to ``GKTUITION_TUTOR.RAW.QUERY_LOG`` on a timer **or** when
  the in-memory buffer reaches the size threshold, whichever fires first.
* :func:`install_default_sink` — convenience wiring: build a sink from
  ``SNOWFLAKE_LOG_SINK_*`` env vars, register its ``enqueue`` as the
  ``api.services.query_log`` writer, and attach it to the root logger.
* :func:`sink_from_env` — same builder without the global wiring; useful
  for tests that want full control of the lifecycle.

Why a separate sink and not the inline INSERT writer that lives in
``api/main.py`` today?

* The inline writer issues one INSERT per ``/query`` invocation. At any
  serious traffic that quickly becomes a per-query Snowflake roundtrip on
  the **request path** — exactly the latency we want to keep out of student
  experience.
* The sink buffers in memory and flushes asynchronously, so the request
  handler returns the moment the row is enqueued. A flush failure is
  lossy: it logs to stdout as a fallback and drops the batch. The
  trade-off is intentional — observability must never block request
  handling, and Snowflake's resource monitor + Agent 10's L5 kill switch
  remain the load-bearing cost belts. Losing a few log rows on a Snowflake
  hiccup is acceptable; failing a paying student's request because the
  log table was busy is not.

Concurrency model

Each :class:`SnowflakeLogSink` owns one background thread that wakes every
``flush_interval_seconds`` (default 30s), drains the buffer atomically
under a lock, and writes the batch via the injected
:attr:`SnowflakeLogSink.writer` callable. The buffer is also drained
inline by any thread that calls :meth:`SnowflakeLogSink.enqueue` and
observes the buffer at or above ``flush_size`` (default 100) — that path
runs the writer synchronously to give backpressure; the timer thread only
handles the steady-state trickle.

This module never imports the Snowflake driver at import time. The writer
is injected by :func:`install_default_sink` (which lazily imports
``snowflake.connector`` only if env vars are set) or by tests.
"""
from __future__ import annotations

import atexit
import logging
import os
import sys
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# The columns we expect on every QUERY_LOG row. Records that omit any of
# these get them substituted with ``None`` — Snowflake accepts NULLs and the
# table schema (see ``api/sql/query_log_table.sql``) allows it for every
# column except ``query_id``, ``q``, and ``created_at``. Records missing
# those three are dropped with a warning rather than rejected by Snowflake.
_REQUIRED_COLUMNS: tuple[str, ...] = ("query_id", "q", "created_at")
_OPTIONAL_COLUMNS: tuple[str, ...] = (
    "tier",
    "query_type",
    "query_class",
    "model_used",
    "top_slug",
    "top_reranker_score",
    "from_cache",
    "elapsed_ms",
    "cost_estimate_cents",
    "extracted_question",
    "user_id",
    "image_bytes_size",
    "extraction_outcome",
)
_ALL_COLUMNS: tuple[str, ...] = _REQUIRED_COLUMNS + _OPTIONAL_COLUMNS

# Type of the injected DB writer. Receives a list of rows (each a dict
# of column-name -> value) and is expected to persist all of them
# atomically; raising any exception triggers the sink's lossy fallback.
BatchWriter = Callable[[list[dict[str, Any]]], None]


@dataclass(frozen=True)
class SnowflakeLogSinkConfig:
    """Pure-data config snapshot — built once at sink construction time.

    ``flush_interval_seconds`` and ``flush_size`` are the two flush
    triggers; the buffer drains as soon as **either** is met. Setting
    ``flush_size`` to 1 effectively disables coalescing (every record is
    its own flush) — useful for tests that want deterministic flushes.
    """

    table_fqn: str = "GKTUITION_TUTOR.RAW.QUERY_LOG"
    flush_interval_seconds: float = 30.0
    flush_size: int = 100
    # If True, attach the sink to the root logger so any module that emits
    # a record with extras (eg ``logger.info("...", extra={"query_id": ...})``)
    # is captured. Off by default — the typical wiring goes through the
    # api.services.query_log seam, not the logging package.
    attach_to_root_logger: bool = False
    # The level the sink listens at when attached to a logger. INFO is fine
    # for normal use; DEBUG only if you want to capture a lot of noise.
    logger_level: int = logging.INFO


@dataclass
class _SinkStats:
    """Internal counters — exposed via :meth:`SnowflakeLogSink.stats` for ops."""

    enqueued: int = 0
    flushed: int = 0
    dropped_invalid: int = 0
    dropped_on_error: int = 0
    flush_errors: int = 0
    last_flush_unix: float | None = None


class SnowflakeLogSink(logging.Handler):
    """Batched, lossy-on-failure log sink for ``RAW.QUERY_LOG``.

    Use :func:`install_default_sink` for the production wiring. Direct
    construction is for tests:

        sink = SnowflakeLogSink(
            writer=fake_writer,
            config=SnowflakeLogSinkConfig(flush_interval_seconds=60, flush_size=5),
        )
        sink.enqueue({"query_id": "...", "q": "...", "created_at": "..."})
        sink.flush()        # forces a synchronous flush
        sink.close()        # joins the background thread

    The handler implements ``logging.Handler`` so it can also be attached
    to a stdlib logger; in that mode it pulls structured fields off the
    ``LogRecord.__dict__`` and enqueues them. Records without a
    ``query_id`` extra are quietly dropped (we don't want to flood the
    table with arbitrary application logs).
    """

    def __init__(
        self,
        writer: BatchWriter,
        config: SnowflakeLogSinkConfig | None = None,
    ) -> None:
        super().__init__(level=(config or SnowflakeLogSinkConfig()).logger_level)
        self._config = config or SnowflakeLogSinkConfig()
        self.writer = writer
        self._buffer: list[dict[str, Any]] = []
        self._buffer_lock = threading.Lock()
        self._wake = threading.Event()
        # ``logging.Handler`` uses ``self._closed`` as a bool internally
        # (set to True by ``logging.shutdown()`` at interpreter exit). We
        # rename to ``_stopped`` so our shutdown signalling doesn't clash
        # with the parent class's bookkeeping.
        self._stopped = threading.Event()
        self._stats = _SinkStats()
        self._stats_lock = threading.Lock()

        # Daemon thread = process can exit even if the loop is mid-sleep;
        # atexit gives us one last flush attempt on clean shutdown.
        self._thread = threading.Thread(
            target=self._run_loop,
            name="snowflake-log-sink",
            daemon=True,
        )
        self._thread.start()
        atexit.register(self._atexit_flush)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enqueue(self, row: dict[str, Any]) -> None:
        """Add a row to the buffer; flush inline if the size threshold is hit.

        Used by ``api.services.query_log.set_query_log_writer`` via
        :func:`install_default_sink`. Safe to call from any thread.
        """
        normalised = self._normalise(row)
        if normalised is None:
            with self._stats_lock:
                self._stats.dropped_invalid += 1
            logger.warning(
                "snowflake_log_sink: dropping row missing required cols %s: %s",
                _REQUIRED_COLUMNS,
                {k: row.get(k) for k in _REQUIRED_COLUMNS},
            )
            return

        flush_now = False
        with self._buffer_lock:
            self._buffer.append(normalised)
            with self._stats_lock:
                self._stats.enqueued += 1
            if len(self._buffer) >= self._config.flush_size:
                flush_now = True

        if flush_now:
            # Inline drain — gives backpressure to the caller when the sink
            # is hot. We don't await the background thread here because
            # waking it and waiting would defeat the point.
            self._flush_locked_or_inline()

    def emit(self, record: logging.LogRecord) -> None:
        """``logging.Handler`` interface — convert and enqueue."""
        # Pull the structured fields off the record. The convention is that
        # callers attach them via ``extra={...}`` which becomes attributes
        # on the LogRecord.
        if not getattr(record, "query_id", None):
            # No query_id → not for us. Caller should use a separate handler
            # for general app logs.
            return
        row = {col: getattr(record, col, None) for col in _ALL_COLUMNS}
        # Created_at defaults to the record's logging timestamp if the
        # caller didn't override.
        if not row.get("created_at"):
            row["created_at"] = _isoformat(record.created)
        try:
            self.enqueue(row)
        except Exception:
            # Never let a sink error propagate up through the logging
            # framework — that would deadlock the very logger we're using
            # to report errors.
            self.handleError(record)

    def flush(self) -> None:
        """Synchronously drain the buffer. Used by tests + :meth:`close`."""
        self._flush_locked_or_inline()

    def close(self) -> None:
        """Stop the background thread and run one final flush.

        Safe to call multiple times. After ``close()`` the sink continues
        to accept ``enqueue`` calls but will only flush them via direct
        calls (the background loop has exited).
        """
        if self._stopped.is_set():
            return
        self._stopped.set()
        self._wake.set()
        self._thread.join(timeout=self._config.flush_interval_seconds + 5)
        self._flush_locked_or_inline()
        super().close()

    def stats(self) -> _SinkStats:
        """Snapshot of internal counters — useful for /healthz integration."""
        with self._stats_lock:
            # Dataclass is mutable; return a fresh copy so the caller can't
            # accidentally race us.
            return _SinkStats(**self._stats.__dict__)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        """Background flush loop. Wakes every ``flush_interval_seconds``."""
        interval = max(0.1, self._config.flush_interval_seconds)
        while not self._stopped.is_set():
            # ``Event.wait(timeout)`` returns True if the event was set
            # before the timeout — that's our shutdown signal.
            woke_for_shutdown = self._wake.wait(timeout=interval)
            try:
                self._flush_locked_or_inline()
            except Exception:
                # _flush_locked_or_inline never raises in normal flow
                # (it traps writer errors itself); this catch is defensive.
                logger.exception("snowflake_log_sink loop iteration failed")
            self._wake.clear()
            if woke_for_shutdown and self._stopped.is_set():
                return

    def _flush_locked_or_inline(self) -> None:
        """Atomically drain the buffer and call the writer.

        Lossy: if the writer raises, the batch is dropped (after a fallback
        stdout log) and the stats counters are bumped. The buffer is
        cleared **before** the writer is called so that an in-flight error
        doesn't block subsequent enqueues from making progress.
        """
        with self._buffer_lock:
            if not self._buffer:
                return
            batch = self._buffer
            self._buffer = []

        try:
            self.writer(batch)
            with self._stats_lock:
                self._stats.flushed += len(batch)
                self._stats.last_flush_unix = time.time()
        except Exception as exc:
            # Lossy fallback — emit the batch to stdout and increment the
            # error counter. Stdout is the right channel for Fly: machine
            # logs are scraped by Fly's log shipper, so we'll see the dropped
            # rows there. Don't recursively call ``logger`` here because the
            # root logger may be attached to this very handler.
            with self._stats_lock:
                self._stats.flush_errors += 1
                self._stats.dropped_on_error += len(batch)
            try:
                sys.stdout.write(
                    f"[snowflake_log_sink][FALLBACK] writer raised {exc!r}; "
                    f"dropping {len(batch)} rows\n"
                )
                for row in batch:
                    sys.stdout.write(
                        f"[snowflake_log_sink][FALLBACK_ROW] {row}\n"
                    )
                sys.stdout.flush()
            except Exception:
                # If stdout itself is broken there's nothing more we can do.
                pass

    @staticmethod
    def _normalise(row: dict[str, Any]) -> dict[str, Any] | None:
        """Pad the row with NULLs for optional columns; reject if missing PKs.

        Returns ``None`` if any required column is missing or empty.
        """
        for col in _REQUIRED_COLUMNS:
            if not row.get(col):
                return None
        return {col: row.get(col) for col in _ALL_COLUMNS}

    def _atexit_flush(self) -> None:
        """One-shot flush on interpreter shutdown. Best-effort."""
        try:
            self._flush_locked_or_inline()
        except Exception:
            # We're in atexit; nothing useful to log to.
            pass


# ---------------------------------------------------------------------------
# Default sink wiring
# ---------------------------------------------------------------------------


def sink_from_env(
    *,
    writer: BatchWriter | None = None,
) -> SnowflakeLogSink:
    """Build a :class:`SnowflakeLogSink` from ``SNOWFLAKE_LOG_SINK_*`` env vars.

    Env vars (all optional, with the defaults documented in ``fly.toml``):

    * ``SNOWFLAKE_LOG_SINK_TABLE``               (default ``GKTUITION_TUTOR.RAW.QUERY_LOG``)
    * ``SNOWFLAKE_LOG_SINK_FLUSH_INTERVAL_S``    (default ``30``)
    * ``SNOWFLAKE_LOG_SINK_FLUSH_SIZE``          (default ``100``)
    * ``SNOWFLAKE_LOG_SINK_ATTACH_ROOT_LOGGER``  (default ``false``)

    The ``writer`` argument is injected (tests pass a fake). When ``None``,
    :func:`_default_snowflake_writer` is used — that lazily imports the
    Snowflake connector and writes via the orchestrator's existing pool.
    """
    config = SnowflakeLogSinkConfig(
        table_fqn=os.environ.get(
            "SNOWFLAKE_LOG_SINK_TABLE", "GKTUITION_TUTOR.RAW.QUERY_LOG"
        ),
        flush_interval_seconds=_float_env(
            "SNOWFLAKE_LOG_SINK_FLUSH_INTERVAL_S", 30.0
        ),
        flush_size=_int_env("SNOWFLAKE_LOG_SINK_FLUSH_SIZE", 100),
        attach_to_root_logger=_bool_env(
            "SNOWFLAKE_LOG_SINK_ATTACH_ROOT_LOGGER", False
        ),
    )
    db_writer: BatchWriter = writer or _default_snowflake_writer(config.table_fqn)
    return SnowflakeLogSink(writer=db_writer, config=config)


def install_default_sink(
    *,
    writer: BatchWriter | None = None,
) -> SnowflakeLogSink | None:
    """Wire a sink as the query-log writer + (optionally) the root logger.

    Returns the sink, or ``None`` if the sink is disabled (e.g.
    ``SNOWFLAKE_LOG_SINK_ENABLED`` is unset/false). The caller does **not**
    need to hold a reference — the sink installs an ``atexit`` flush.
    """
    if not _bool_env("SNOWFLAKE_LOG_SINK_ENABLED", False):
        logger.info(
            "snowflake_log_sink disabled (SNOWFLAKE_LOG_SINK_ENABLED unset)"
        )
        return None

    sink = sink_from_env(writer=writer)

    # Wire as the query_log writer. The seam accepts either ``dict -> None``
    # or ``dict -> Awaitable[None]``; we use the sync form because enqueue
    # never blocks.
    try:
        from ..services import query_log as query_log_svc

        def _writer_seam(row: dict[str, Any]) -> None:
            sink.enqueue(row)

        query_log_svc.set_query_log_writer(_writer_seam)
    except Exception:
        logger.exception(
            "snowflake_log_sink: failed to register as query_log writer"
        )

    if sink._config.attach_to_root_logger:
        logging.getLogger().addHandler(sink)

    logger.info(
        "snowflake_log_sink installed (table=%s interval=%ss size=%d)",
        sink._config.table_fqn,
        sink._config.flush_interval_seconds,
        sink._config.flush_size,
    )
    return sink


# ---------------------------------------------------------------------------
# Default writer — lazy Snowflake import
# ---------------------------------------------------------------------------


def _default_snowflake_writer(table_fqn: str) -> BatchWriter:
    """Build a batch-INSERT writer using the orchestrator's connection pool.

    Defers the Snowflake connector import until first call so that:

    * import-time of this module stays free of side-effects (good for tests
      that don't have the connector installed);
    * misconfigured environments still let the app boot — the writer fails
      on first batch, which triggers the lossy fallback to stdout, rather
      than crashing the FastAPI lifespan startup.
    """

    placeholders = ", ".join(["%s"] * len(_ALL_COLUMNS))
    cols_sql = ", ".join(_ALL_COLUMNS)
    insert_sql = f"INSERT INTO {table_fqn} ({cols_sql}) VALUES ({placeholders})"

    def _writer(batch: list[dict[str, Any]]) -> None:
        if not batch:
            return
        # Lazy import so tests don't need snowflake-connector-python.
        from ..orchestrator.retriever import _cursor  # type: ignore[attr-defined]

        rows: list[tuple[Any, ...]] = [
            tuple(row.get(c) for c in _ALL_COLUMNS) for row in batch
        ]
        with _cursor() as cs:
            # executemany() does a single bind+multi-row INSERT in one
            # roundtrip on the Snowflake connector.
            cs.executemany(insert_sql, rows)

    return _writer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _isoformat(unix: float) -> str:
    import datetime as _dt

    return _dt.datetime.fromtimestamp(unix, tz=_dt.timezone.utc).isoformat()


def _bool_env(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    val = os.environ.get(name)
    if val is None or val.strip() == "":
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    val = os.environ.get(name)
    if val is None or val.strip() == "":
        return default
    try:
        return float(val)
    except ValueError:
        return default


# Make ``Iterable`` reachable for type-checkers reading this module's API
# without exporting it as part of the public surface above.
_ = Iterable
