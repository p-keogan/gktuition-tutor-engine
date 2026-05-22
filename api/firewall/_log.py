"""Shared structured-logging helper.

Every firewall layer emits one log line per request via :func:`event`. The
shape is deliberately flat (no nested objects) so the line is grep-able and
can be parsed by Fly.io's log shipper without a custom decoder.

The shape::

    firewall_event layer=L2 outcome=blocked tier=anonymous ip=… reason=subnet_cap
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("gktuition.firewall")


def event(layer: str, outcome: str, **fields: Any) -> None:
    """Emit one structured firewall event line.

    ``layer`` is one of L1..L6. ``outcome`` is short (one of
    ``ok``, ``blocked``, ``cache_hit``, ``cache_miss``, ``trip``, ``recover``,
    ``cap_fired`` etc.). Extra fields are key=value-joined.
    """
    parts = [f"layer={layer}", f"outcome={outcome}"]
    for k, v in fields.items():
        if v is None:
            continue
        # Quote strings that contain spaces so the line stays grep-friendly.
        s = str(v)
        if " " in s or "=" in s:
            s = '"' + s.replace('"', '\\"') + '"'
        parts.append(f"{k}={s}")
    logger.info("firewall_event " + " ".join(parts))
