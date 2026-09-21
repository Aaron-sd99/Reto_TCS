from __future__ import annotations

import logging
import time
from uuid import UUID, uuid4

from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .db import close_pool, open_pool
from .observability import (
    OUTBOX_EVENTS_TOTAL,
    REQUEST_LATENCY,
    TRANSFER_OUTCOMES_TOTAL,
    TRANSFERS_TOTAL,
    configure_logging,
)
from .outbox import OutboxWorker
from .repository import (
    create_transfer,
    get_metric_seed_counts,
    get_operations_summary,
    get_transfer,
    list_accounts,
    list_transfers,
)
from .schemas import HealthResponse, TransferRequest, TransferResponse

configure_logging()
logger = logging.getLogger("transaction-service")
worker = OutboxWorker()

app = FastAPI(
    title="SmartBancs Transaction Service",
    version="1.0.0",
    description="MVP transactional layer designed to integrate safely with Bancs.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8083",
        "http://127.0.0.1:8083",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Idempotency-Key", "X-Correlation-Id"],
)


@app.on_event("startup")
async def startup() -> None:
    open_pool()
    seed_metrics()
    worker.start()


@app.on_event("shutdown")
async def shutdown() -> None:
    await worker.stop()
    close_pool()


@app.middleware("http")
async def observe_requests(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    route = request.scope.get("route")
    route_path = getattr(route, "path", request.url.path)
    REQUEST_LATENCY.labels(
        method=request.method,
        route=route_path,
        status=str(response.status_code),
    ).observe(time.perf_counter() - started)
    return response


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def seed_metrics() -> None:
    counts = get_metric_seed_counts()
    for row in counts["transfers"]:
        TRANSFERS_TOTAL.labels(status=row["status"]).inc(row["count"])
        if row["status"] in {"SETTLED", "REJECTED"}:
            TRANSFER_OUTCOMES_TOTAL.labels(status=row["status"]).inc(row["count"])
    for row in counts["outbox"]:
        OUTBOX_EVENTS_TOTAL.labels(event_type=row["event_type"], result=row["result"]).inc(row["count"])
    logger.info("metrics seeded from persisted transaction data")


@app.post("/v1/transfers", response_model=TransferResponse, status_code=status.HTTP_202_ACCEPTED)
def post_transfer(
    body: TransferRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    correlation_id: str | None = Header(None, alias="X-Correlation-Id"),
) -> TransferResponse:
    if len(idempotency_key.strip()) < 8:
        raise HTTPException(status_code=400, detail="Idempotency-Key must contain at least 8 characters")
    correlation_id = correlation_id or str(uuid4())
    transfer, duplicated = create_transfer(body, idempotency_key.strip(), correlation_id)
    TRANSFERS_TOTAL.labels(status=transfer["status"]).inc()
    logger.info(
        "transfer accepted" if not duplicated else "idempotent transfer replayed",
        extra={
            "correlation_id": transfer["correlation_id"],
            "transfer_id": transfer["id"],
            "status": transfer["status"],
        },
    )
    if not duplicated and transfer["status"] == "REJECTED":
        TRANSFER_OUTCOMES_TOTAL.labels(status="REJECTED").inc()
    return TransferResponse(**transfer)


@app.get("/v1/transfers/{transfer_id}", response_model=TransferResponse)
def get_transfer_status(transfer_id: UUID) -> TransferResponse:
    transfer = get_transfer(transfer_id)
    if transfer is None:
        raise HTTPException(status_code=404, detail="transfer not found")
    return TransferResponse(**transfer)


@app.get("/v1/transfers")
def get_recent_transfers(limit: int = 20) -> list[dict]:
    return list_transfers(limit)


@app.get("/v1/accounts")
def get_accounts() -> list[dict]:
    return list_accounts()


@app.get("/v1/operations/summary")
def get_summary() -> dict:
    return get_operations_summary()
