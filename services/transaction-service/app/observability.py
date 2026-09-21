import json
import logging
import time
from typing import Any

from prometheus_client import Counter, Histogram


REQUEST_LATENCY = Histogram(
    "smartbancs_request_latency_seconds",
    "HTTP request latency by route and method.",
    ["method", "route", "status"],
)

TRANSFERS_TOTAL = Counter(
    "smartbancs_transfers_total",
    "Transfers received by final immediate status.",
    ["status"],
)

TRANSFER_OUTCOMES_TOTAL = Counter(
    "smartbancs_transfer_outcomes_total",
    "Transfers by final business outcome.",
    ["status"],
)

OUTBOX_EVENTS_TOTAL = Counter(
    "smartbancs_outbox_events_total",
    "Outbox events processed by result.",
    ["event_type", "result"],
)

CORE_LATENCY = Histogram(
    "smartbancs_core_latency_seconds",
    "Latency observed when calling Bancs through the adapter.",
    ["result"],
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("correlation_id", "transfer_id", "event_id", "status"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
