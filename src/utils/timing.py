"""Per-request latency instrumentation.

Provides a lightweight accumulator that times the major phases of a proxy
request (provisioning, completion, tool execution, persistence) and emits a
single structured log line. Phases may be entered multiple times; their
durations accumulate. See specs/005-reduce-api-latency/data-model.md.
"""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from typing import Dict, Iterator, Optional

from src.utils.logger import logger

# Canonical phase keys reported in every breakdown.
_PHASES = ("provision_ms", "completion_ms", "tool_ms", "persist_ms")


class RequestTiming:
    """Accumulates per-phase timings for one proxy request."""

    def __init__(self) -> None:
        self._start = time.monotonic()
        self._phases: Dict[str, float] = {name: 0.0 for name in _PHASES}
        self.round_trips = 0

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        """Time a block and accumulate its duration into ``name``."""
        start = time.monotonic()
        try:
            yield
        finally:
            self._phases[name] = self._phases.get(name, 0.0) + (time.monotonic() - start) * 1000.0

    def add_round_trips(self, n: int = 1) -> None:
        self.round_trips += n

    def emit(self, **extra: object) -> Dict[str, object]:
        """Log one structured timing line and return the breakdown dict."""
        total_ms = int((time.monotonic() - self._start) * 1000.0)
        data: Dict[str, object] = {name: int(self._phases.get(name, 0.0)) for name in _PHASES}
        data["total_ms"] = total_ms
        data["round_trips"] = self.round_trips
        data.update(extra)
        logger.info("request_timing %s", json.dumps(data, ensure_ascii=False))
        return data
