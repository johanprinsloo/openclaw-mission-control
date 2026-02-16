"""Tests for metrics collection."""

from mc_bridge.metrics import MetricsCollector


def test_counter_increment():
    m = MetricsCollector()
    m.inc("messages_inbound_total")
    m.inc("messages_inbound_total")
    assert m.get("messages_inbound_total") == 2


def test_gauge_set():
    m = MetricsCollector()
    m.set_gauge("sse_connections_active", 3)
    assert m.get("sse_connections_active") == 3


def test_prometheus_format():
    m = MetricsCollector()
    m.inc("messages_inbound_total", 5)
    m.set_gauge("sse_connections_active", 2)
    text = m.to_prometheus()
    assert "bridge_messages_inbound_total 5" in text
    assert "bridge_sse_connections_active 2" in text
    assert "bridge_uptime_seconds" in text
