from __future__ import annotations

import asyncio
from decimal import Decimal
import json
import logging
import os
import time
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field


DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://smartbancs:smartbancs@localhost:5432/smartbancs")
MAX_INFLIGHT = int(os.getenv("BANCS_MAX_INFLIGHT", "25"))
ARTIFICIAL_DELAY_MS = int(os.getenv("BANCS_ARTIFICIAL_DELAY_MS", "80"))

pool = ConnectionPool(conninfo=DATABASE_URL, kwargs={"row_factory": dict_row}, min_size=1, max_size=8, open=False)
semaphore = asyncio.Semaphore(MAX_INFLIGHT)

POSTINGS_TOTAL = Counter("bancs_postings_total", "Bancs postings by status.", ["status"])
POSTING_LATENCY = Histogram("bancs_posting_latency_seconds", "Bancs simulated posting latency.", ["status"])
INFLIGHT = Gauge("bancs_inflight_requests", "Requests currently being processed by the Bancs adapter.")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "correlation_id": getattr(record, "correlation_id", None),
            },
            ensure_ascii=False,
        )


handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
logger = logging.getLogger("bancs-adapter")

app = FastAPI(
    title="Bancs Adapter",
    version="1.0.0",
    description="Anti-corruption layer that protects Bancs and simulates core posting for the MVP.",
)


class CoreTransferRequest(BaseModel):
    transfer_id: str
    core_reference: str
    source_account: str
    destination_account: str
    amount: Decimal = Field(gt=0, decimal_places=2)
    currency: str = Field(min_length=3, max_length=3)
    customer_id: str
    correlation_id: str


@app.on_event("startup")
def startup() -> None:
    pool.open(wait=True)
    seed_metrics()


@app.on_event("shutdown")
def shutdown() -> None:
    pool.close()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def seed_metrics() -> None:
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*)::int AS count FROM bancs_postings GROUP BY status"
        ).fetchall()
    for row in rows:
        POSTINGS_TOTAL.labels(status=row["status"]).inc(row["count"])
    logger.info("metrics seeded from persisted core postings")


@app.post("/core/transfers")
async def post_core_transfer(
    body: CoreTransferRequest,
    correlation_id: str | None = Header(None, alias="X-Correlation-Id"),
) -> dict[str, Any]:
    started = time.perf_counter()
    async with semaphore:
        INFLIGHT.inc()
        try:
            if ARTIFICIAL_DELAY_MS:
                await asyncio.sleep(ARTIFICIAL_DELAY_MS / 1000)
            result = await asyncio.to_thread(_post_core_transfer, body)
            POSTINGS_TOTAL.labels(status=result["status"]).inc()
            POSTING_LATENCY.labels(status=result["status"]).observe(time.perf_counter() - started)
            logger.info(
                "core posting processed",
                extra={"correlation_id": correlation_id or body.correlation_id},
            )
            return result
        finally:
            INFLIGHT.dec()


@app.get("/core/transfers/{core_reference}")
def get_core_transfer(core_reference: str) -> dict[str, Any]:
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT * FROM bancs_postings WHERE core_reference = %s",
            (core_reference,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="core posting not found")
        return dict(row)


def _post_core_transfer(body: CoreTransferRequest) -> dict[str, Any]:
    with pool.connection() as conn:
        with conn.transaction():
            existing = conn.execute(
                "SELECT * FROM bancs_postings WHERE core_reference = %s",
                (body.core_reference,),
            ).fetchone()
            if existing:
                return dict(existing)

            rows = conn.execute(
                """
                SELECT account_id, currency, available_balance, status
                FROM bancs_accounts
                WHERE account_id = ANY(%s)
                ORDER BY account_id
                FOR UPDATE
                """,
                (sorted([body.source_account, body.destination_account]),),
            ).fetchall()
            accounts = {row["account_id"]: row for row in rows}
            rejection = _validate(body, accounts)
            if rejection:
                conn.execute(
                    """
                    INSERT INTO bancs_postings (
                        core_reference, source_account, destination_account,
                        amount, currency, status, rejection_reason
                    )
                    VALUES (%s, %s, %s, %s, %s, 'REJECTED', %s)
                    """,
                    (
                        body.core_reference,
                        body.source_account,
                        body.destination_account,
                        body.amount,
                        body.currency,
                        rejection,
                    ),
                )
                return {
                    "core_reference": body.core_reference,
                    "status": "REJECTED",
                    "rejection_reason": rejection,
                }

            conn.execute(
                "UPDATE bancs_accounts SET available_balance = available_balance - %s, updated_at = now() WHERE account_id = %s",
                (body.amount, body.source_account),
            )
            conn.execute(
                "UPDATE bancs_accounts SET available_balance = available_balance + %s, updated_at = now() WHERE account_id = %s",
                (body.amount, body.destination_account),
            )
            conn.execute(
                """
                INSERT INTO bancs_postings (
                    core_reference, source_account, destination_account,
                    amount, currency, status
                )
                VALUES (%s, %s, %s, %s, %s, 'SETTLED')
                """,
                (
                    body.core_reference,
                    body.source_account,
                    body.destination_account,
                    body.amount,
                    body.currency,
                ),
            )
            return {
                "core_reference": body.core_reference,
                "status": "SETTLED",
                "rejection_reason": None,
            }


def _validate(body: CoreTransferRequest, accounts: dict[str, dict[str, Any]]) -> str | None:
    source = accounts.get(body.source_account)
    destination = accounts.get(body.destination_account)
    if source is None:
        return "BANCS_SOURCE_ACCOUNT_NOT_FOUND"
    if destination is None:
        return "BANCS_DESTINATION_ACCOUNT_NOT_FOUND"
    if source["status"] != "ACTIVE" or destination["status"] != "ACTIVE":
        return "BANCS_ACCOUNT_NOT_ACTIVE"
    if source["currency"] != body.currency or destination["currency"] != body.currency:
        return "BANCS_CURRENCY_MISMATCH"
    if source["available_balance"] < body.amount:
        return "BANCS_INSUFFICIENT_FUNDS"
    return None
