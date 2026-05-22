"""Observability seams — structured logging sinks, traces.

The Snowflake log sink (``snowflake_log_sink``) is the implementation of the
"logs piped to Snowflake ``RAW.QUERY_LOG``" line in ADR-003 — it batches
structured query-log entries and flushes them to the warehouse on a timer
(or a record-count threshold, whichever fires first), without ever
blocking a request.
"""
from __future__ import annotations

from .snowflake_log_sink import (
    SnowflakeLogSink,
    SnowflakeLogSinkConfig,
    install_default_sink,
    sink_from_env,
)

__all__ = [
    "SnowflakeLogSink",
    "SnowflakeLogSinkConfig",
    "install_default_sink",
    "sink_from_env",
]
