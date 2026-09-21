from __future__ import annotations

import asyncio
import logging
import time
from uuid import UUID

import httpx

from .config import settings
from .observability import CORE_LATENCY, OUTBOX_EVENTS_TOTAL, TRANSFER_OUTCOMES_TOTAL
from .repository import (
    claim_outbox_events,
    mark_event_pending,
    mark_event_published,
    mark_pending_reconciliation,
    reject_transfer,
    save_ai_recommendation,
    settle_transfer,
)

logger = logging.getLogger("transaction-service.outbox")


class OutboxWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stopped = asyncio.Event()
        self._semaphore = asyncio.Semaphore(settings.outbox_max_concurrency)

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopped.set()
        if self._task:
            await self._task

    async def _run(self) -> None:
        async with httpx.AsyncClient() as client:
            while not self._stopped.is_set():
                events = await asyncio.to_thread(claim_outbox_events, settings.outbox_batch_size)
                if events:
                    await asyncio.gather(*(self._handle_event_with_limit(client, event) for event in events))
                    continue
                await asyncio.sleep(settings.outbox_poll_seconds)

    async def _handle_event_with_limit(self, client: httpx.AsyncClient, event: dict) -> None:
        async with self._semaphore:
            await self._handle_event(client, event)

    async def _handle_event(self, client: httpx.AsyncClient, event: dict) -> None:
        event_id = event["id"]
        event_type = event["event_type"]
        payload = event["payload"]
        try:
            if event_type == "TRANSFER_REQUESTED":
                await self._send_to_bancs(client, event_id, payload)
            elif event_type == "AI_RECOMMENDATION_REQUESTED":
                await self._send_to_ai(client, event_id, payload)
            else:
                raise ValueError(f"unsupported event type: {event_type}")
            OUTBOX_EVENTS_TOTAL.labels(event_type=event_type, result="published").inc()
        except Exception as exc:
            logger.warning(
                "outbox event failed",
                extra={"event_id": str(event_id), "status": "retry"},
                exc_info=True,
            )
            await asyncio.to_thread(mark_event_pending, event_id, str(exc))
            OUTBOX_EVENTS_TOTAL.labels(event_type=event_type, result="failed").inc()

    async def _send_to_bancs(self, client: httpx.AsyncClient, event_id: UUID, payload: dict) -> None:
        started = time.perf_counter()
        transfer_id = UUID(payload["transfer_id"])
        try:
            response = await client.post(
                f"{settings.bancs_adapter_url}/core/transfers",
                json=payload,
                timeout=settings.core_timeout_seconds,
                headers={"X-Correlation-Id": payload["correlation_id"]},
            )
        except httpx.TimeoutException:
            CORE_LATENCY.labels(result="timeout").observe(time.perf_counter() - started)
            await asyncio.to_thread(mark_pending_reconciliation, transfer_id, "BANCS_TIMEOUT_AMBIGUOUS")
            await asyncio.to_thread(mark_event_published, event_id)
            return

        CORE_LATENCY.labels(result=str(response.status_code)).observe(time.perf_counter() - started)
        if response.status_code == 200:
            body = response.json()
            if body["status"] == "SETTLED":
                await asyncio.to_thread(settle_transfer, transfer_id, body["core_reference"])
                TRANSFER_OUTCOMES_TOTAL.labels(status="SETTLED").inc()
            else:
                await asyncio.to_thread(reject_transfer, transfer_id, body.get("rejection_reason", "BANCS_REJECTED"))
                TRANSFER_OUTCOMES_TOTAL.labels(status="REJECTED").inc()
            await asyncio.to_thread(mark_event_published, event_id)
            return

        if response.status_code == 409:
            body = response.json()
            await asyncio.to_thread(reject_transfer, transfer_id, body.get("detail", "BANCS_REJECTED"))
            TRANSFER_OUTCOMES_TOTAL.labels(status="REJECTED").inc()
            await asyncio.to_thread(mark_event_published, event_id)
            return

        raise RuntimeError(f"Bancs adapter returned {response.status_code}: {response.text[:250]}")

    async def _send_to_ai(self, client: httpx.AsyncClient, event_id: UUID, payload: dict) -> None:
        response = await client.post(
            f"{settings.ai_service_url}/v1/recommendations",
            json=payload,
            timeout=1.0,
            headers={"X-Correlation-Id": payload["correlation_id"]},
        )
        response.raise_for_status()
        await asyncio.to_thread(save_ai_recommendation, payload, response.json())
        await asyncio.to_thread(mark_event_published, event_id)
