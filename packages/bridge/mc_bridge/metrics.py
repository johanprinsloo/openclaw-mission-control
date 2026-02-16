"""
Metrics collection and Prometheus-compatible exposition.

Tracks bridge health counters and gauges for monitoring.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any


class MetricsCollector:
    """
    Simple metrics collector with Prometheus text format export.

    Tracks counters and gauges for bridge operations.
    """

    def __init__(self) -> None:
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = {}
        self._start_time = time.time()

    def inc(self, name: str, value: int = 1) -> None:
        """Increment a counter."""
        self._counters[f"bridge_{name}"] += value

    def set_gauge(self, name: str, value: float) -> None:
        """Set a gauge value."""
        self._gauges[f"bridge_{name}"] = value

    def get(self, name: str) -> int | float:
        """Get a metric value."""
        full = f"bridge_{name}"
        if full in self._gauges:
            return self._gauges[full]
        return self._counters.get(full, 0)

    def to_prometheus(self) -> str:
        """Export all metrics in Prometheus text format."""
        lines = []
        for name, value in sorted(self._counters.items()):
            lines.append(f"# TYPE {name} counter")
            lines.append(f"{name} {value}")
        for name, value in sorted(self._gauges.items()):
            lines.append(f"# TYPE {name} gauge")
            lines.append(f"{name} {value}")
        # Uptime gauge
        uptime = time.time() - self._start_time
        lines.append("# TYPE bridge_uptime_seconds gauge")
        lines.append(f"bridge_uptime_seconds {uptime:.1f}")
        return "\n".join(lines) + "\n"

    def to_dict(self) -> dict[str, Any]:
        """Export metrics as a dictionary."""
        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "uptime_seconds": time.time() - self._start_time,
        }
