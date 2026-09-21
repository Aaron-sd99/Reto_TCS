from __future__ import annotations

from decimal import Decimal
import asyncio
import json
import logging
import os
import time

from fastapi import FastAPI, Header, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel, Field


MODEL_VERSION = os.getenv("MODEL_VERSION", "mock-risk-advisor-local")
ARTIFICIAL_DELAY_MS = int(os.getenv("ARTIFICIAL_DELAY_MS", "50"))
DATABASE_URL = os.getenv("DATABASE_URL")

RECOMMENDATIONS_TOTAL = Counter("ai_recommendations_total", "AI recommendations generated.", ["type"])
AI_LATENCY = Histogram("ai_recommendation_latency_seconds", "AI recommendation generation latency.", ["type"])


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
logger = logging.getLogger("ai-service")

app = FastAPI(
    title="SmartBancs AI Service",
    version="1.0.0",
    description="Functional asynchronous AI mock for financial recommendations.",
)


class RecommendationRequest(BaseModel):
    transfer_id: str
    customer_id: str
    amount: Decimal = Field(gt=0)
    currency: str
    source_account: str
    destination_account: str
    correlation_id: str


class RecommendationResponse(BaseModel):
    recommendation_type: str
    message: str
    model_version: str


@app.on_event("startup")
def startup() -> None:
    seed_metrics()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def seed_metrics() -> None:
    if not DATABASE_URL:
        return
    try:
        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
            rows = conn.execute(
                """
                SELECT recommendation_type AS type, COUNT(*)::int AS count
                FROM ai_recommendations
                GROUP BY recommendation_type
                """
            ).fetchall()
        for row in rows:
            RECOMMENDATIONS_TOTAL.labels(type=row["type"]).inc(row["count"])
        logger.info("metrics seeded from persisted AI recommendations")
    except Exception as exc:
        logger.warning("could not seed AI metrics", extra={"correlation_id": None, "error": str(exc)})


@app.post("/v1/recommendations", response_model=RecommendationResponse)
async def generate_recommendation(
    body: RecommendationRequest,
    correlation_id: str | None = Header(None, alias="X-Correlation-Id"),
) -> RecommendationResponse:
    started = time.perf_counter()
    if ARTIFICIAL_DELAY_MS:
        await asyncio.sleep(ARTIFICIAL_DELAY_MS / 1000)

    amount = Decimal(body.amount)
    if amount >= Decimal("500.00"):
        recommendation_type = "CASH_FLOW_ALERT"
        message = "Transferencia alta detectada. Revisa que el flujo de caja del mes cubra obligaciones próximas."
    else:
        recommendation_type = "SAVINGS_NUDGE"
        message = "Operacion registrada. Considera separar un porcentaje fijo para ahorro automatico."

    RECOMMENDATIONS_TOTAL.labels(type=recommendation_type).inc()
    AI_LATENCY.labels(type=recommendation_type).observe(time.perf_counter() - started)
    logger.info("recommendation generated", extra={"correlation_id": correlation_id or body.correlation_id})
    return RecommendationResponse(
        recommendation_type=recommendation_type,
        message=message,
        model_version=MODEL_VERSION,
    )
