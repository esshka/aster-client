"""
Performance monitoring and statistics for Aster client.

Tracks request metrics, health status, and performance indicators.
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from collections import defaultdict, deque


@dataclass(frozen=True)
class RequestMetrics:
    """Metrics for a single request."""
    endpoint: str
    method: str
    status_code: int
    duration_ms: float
    timestamp: float


@dataclass
class Statistics:
    """Client performance statistics."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_duration_ms: float = 0.0
    avg_duration_ms: float = 0.0
    min_duration_ms: float = float("inf")
    max_duration_ms: float = 0.0

    def update(self, metrics: RequestMetrics) -> None:
        """Update statistics with new request metrics."""
        self.total_requests += 1
        self.total_duration_ms += metrics.duration_ms
        self.avg_duration_ms = self.total_duration_ms / self.total_requests
        self.min_duration_ms = min(self.min_duration_ms, metrics.duration_ms)
        self.max_duration_ms = max(self.max_duration_ms, metrics.duration_ms)

        if 200 <= metrics.status_code < 400:
            self.successful_requests += 1
        else:
            self.failed_requests += 1


class PerformanceMonitor:
    """Monitors client performance and tracks metrics."""

    def __init__(self, max_history: int = 1000):
        """Initialize performance monitor."""
        self._max_history = max_history
        self._statistics = Statistics()
        self._request_history: deque[RequestMetrics] = deque(maxlen=max_history)
        self._endpoint_stats: Dict[str, List[RequestMetrics]] = defaultdict(list)
        self._start_time = time.time()

    def record_request(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        """Record metrics for a completed request."""
        metrics = RequestMetrics(
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            duration_ms=duration_ms,
            timestamp=time.time(),
        )

        # Update global statistics
        self._statistics.update(metrics)

        # Add to history
        self._request_history.append(metrics)

        # Update endpoint-specific stats
        endpoint_key = f"{method} {endpoint}"
        self._endpoint_stats[endpoint_key].append(metrics)

        # Limit endpoint history
        if len(self._endpoint_stats[endpoint_key]) > self._max_history:
            self._endpoint_stats[endpoint_key] = self._endpoint_stats[endpoint_key][-self._max_history:]

    @property
    def statistics(self) -> Statistics:
        """Get current statistics snapshot."""
        return self._statistics

    @property
    def uptime_seconds(self) -> float:
        """Get client uptime in seconds."""
        return time.time() - self._start_time

    def get_endpoint_stats(self, endpoint: str, method: str) -> Dict[str, float]:
        """Get statistics for a specific endpoint."""
        endpoint_key = f"{method} {endpoint}"
        requests = self._endpoint_stats[endpoint_key]

        if not requests:
            return {
                "count": 0,
                "avg_duration_ms": 0.0,
                "min_duration_ms": 0.0,
                "max_duration_ms": 0.0,
                "success_rate": 0.0,
            }

        durations = [r.duration_ms for r in requests]
        successful = sum(1 for r in requests if 200 <= r.status_code < 400)

        return {
            "count": len(requests),
            "avg_duration_ms": sum(durations) / len(durations),
            "min_duration_ms": min(durations),
            "max_duration_ms": max(durations),
            "success_rate": successful / len(requests),
        }

    def get_recent_requests(self, count: int = 10) -> List[RequestMetrics]:
        """Get most recent requests."""
        return list(self._request_history)[-count:]

    def get_error_rate(self, window_seconds: float = 60.0) -> float:
        """Get error rate for the recent time window."""
        cutoff_time = time.time() - window_seconds
        recent_requests = [
            r for r in self._request_history
            if r.timestamp >= cutoff_time
        ]

        if not recent_requests:
            return 0.0

        failed_count = sum(1 for r in recent_requests if r.status_code >= 400)
        return failed_count / len(recent_requests)

    def reset(self) -> None:
        """Reset all statistics and history."""
        self._statistics = Statistics()
        self._request_history.clear()
        self._endpoint_stats.clear()
        self._start_time = time.time()