from __future__ import annotations

from decimal import Decimal
import json
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from .db import pool
from .domain import ordered_account_locks
from .schemas import TransferRequest, TransferStatus


def _transfer_from_row(row: dict[str, Any]) -> dict[str, Any]:
    row = dict(row)
    for key in ("id",):
        row[key] = str(row[key])
    row["amount"] = Decimal(row["amount"])
    row["created_at"] = row["created_at"].isoformat()
    row["updated_at"] = row["updated_at"].isoformat()
    return row


def create_transfer(request: TransferRequest, idempotency_key: str, correlation_id: str) -> tuple[dict[str, Any], bool]:
    transfer_id = uuid4()
    with pool.connection() as conn:
        with conn.transaction():
            inserted = conn.execute(
                """
                INSERT INTO transfers (
                    id, idempotency_key, source_account, destination_account, amount,
                    currency, customer_id, status, correlation_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (idempotency_key) DO NOTHING
                RETURNING *
                """,
                (
                    transfer_id,
                    idempotency_key,
                    request.source_account,
                    request.destination_account,
                    request.amount,
                    request.currency,
                    request.customer_id,
                    TransferStatus.RECEIVED,
                    correlation_id,
                ),
            ).fetchone()

            if inserted is None:
                existing = conn.execute(
                    "SELECT * FROM transfers WHERE idempotency_key = %s",
                    (idempotency_key,),
                ).fetchone()
                return _transfer_from_row(existing), True

            accounts = conn.execute(
                """
                SELECT account_id, currency, available_balance, status
                FROM accounts
                WHERE account_id = ANY(%s)
                ORDER BY account_id
                FOR UPDATE
                """,
                (ordered_account_locks(request.source_account, request.destination_account),),
            ).fetchall()
            by_id = {row["account_id"]: row for row in accounts}
            rejection_reason = _validate_accounts(request, by_id)

            if rejection_reason:
                row = conn.execute(
                    """
                    UPDATE transfers
                    SET status = %s, rejection_reason = %s, updated_at = now()
                    WHERE id = %s
                    RETURNING *
                    """,
                    (TransferStatus.REJECTED, rejection_reason, transfer_id),
                ).fetchone()
                return _transfer_from_row(row), False

            conn.execute(
                """
                UPDATE accounts
                SET available_balance = available_balance - %s, updated_at = now()
                WHERE account_id = %s
                """,
                (request.amount, request.source_account),
            )
            conn.execute(
                """
                UPDATE accounts
                SET available_balance = available_balance + %s, updated_at = now()
                WHERE account_id = %s
                """,
                (request.amount, request.destination_account),
            )
            conn.execute(
                """
                INSERT INTO ledger_entries (transfer_id, account_id, entry_type, amount, currency)
                VALUES (%s, %s, 'DEBIT_RESERVED', %s, %s),
                       (%s, %s, 'CREDIT_RESERVED', %s, %s)
                """,
                (
                    transfer_id,
                    request.source_account,
                    request.amount,
                    request.currency,
                    transfer_id,
                    request.destination_account,
                    request.amount,
                    request.currency,
                ),
            )

            payload = {
                "transfer_id": str(transfer_id),
                "core_reference": str(transfer_id),
                "source_account": request.source_account,
                "destination_account": request.destination_account,
                "amount": str(request.amount),
                "currency": request.currency,
                "customer_id": request.customer_id,
                "correlation_id": correlation_id,
            }
            conn.execute(
                """
                INSERT INTO outbox_events (id, aggregate_id, event_type, payload)
                VALUES (%s, %s, 'TRANSFER_REQUESTED', %s)
                """,
                (uuid4(), transfer_id, Jsonb(payload)),
            )

            row = conn.execute(
                """
                UPDATE transfers
                SET status = %s, core_reference = %s, updated_at = now()
                WHERE id = %s
                RETURNING *
                """,
                (TransferStatus.PENDING_CORE, str(transfer_id), transfer_id),
            ).fetchone()
            return _transfer_from_row(row), False


def _validate_accounts(request: TransferRequest, accounts: dict[str, dict[str, Any]]) -> str | None:
    source = accounts.get(request.source_account)
    destination = accounts.get(request.destination_account)
    if source is None:
        return "SOURCE_ACCOUNT_NOT_FOUND"
    if destination is None:
        return "DESTINATION_ACCOUNT_NOT_FOUND"
    if source["status"] != "ACTIVE" or destination["status"] != "ACTIVE":
        return "ACCOUNT_NOT_ACTIVE"
    if source["currency"] != request.currency or destination["currency"] != request.currency:
        return "CURRENCY_MISMATCH"
    if source["available_balance"] < request.amount:
        return "INSUFFICIENT_FUNDS"
    return None


def get_transfer(transfer_id: UUID) -> dict[str, Any] | None:
    with pool.connection() as conn:
        row = conn.execute("SELECT * FROM transfers WHERE id = %s", (transfer_id,)).fetchone()
        return _transfer_from_row(row) if row else None


def list_transfers(limit: int = 20) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 100))
    with pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM transfers
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return [_transfer_from_row(row) for row in rows]


def list_accounts() -> list[dict[str, Any]]:
    with pool.connection() as conn:
        rows = conn.execute(
            """
            SELECT account_id, customer_id, currency, available_balance, status, updated_at
            FROM accounts
            ORDER BY account_id
            """
        ).fetchall()
        accounts = []
        for row in rows:
            item = dict(row)
            item["available_balance"] = str(item["available_balance"])
            item["updated_at"] = item["updated_at"].isoformat()
            accounts.append(item)
        return accounts


def get_operations_summary() -> dict[str, Any]:
    with pool.connection() as conn:
        transfer_counts = conn.execute(
            "SELECT status, COUNT(*)::int AS count FROM transfers GROUP BY status ORDER BY status"
        ).fetchall()
        outbox_counts = conn.execute(
            "SELECT status, COUNT(*)::int AS count FROM outbox_events GROUP BY status ORDER BY status"
        ).fetchall()
        recommendation_count = conn.execute("SELECT COUNT(*)::int AS count FROM ai_recommendations").fetchone()["count"]
        ledger_count = conn.execute("SELECT COUNT(*)::int AS count FROM ledger_entries").fetchone()["count"]
        total_balance = conn.execute(
            "SELECT COALESCE(SUM(available_balance), 0) AS amount FROM accounts"
        ).fetchone()["amount"]
        latest_recommendation = conn.execute(
            """
            SELECT recommendation_type, message, model_version, generated_at
            FROM ai_recommendations
            ORDER BY generated_at DESC
            LIMIT 1
            """
        ).fetchone()
        return {
            "transfers": {row["status"]: row["count"] for row in transfer_counts},
            "outbox": {row["status"]: row["count"] for row in outbox_counts},
            "ledger_entries": ledger_count,
            "ai_recommendations": recommendation_count,
            "total_projected_balance": str(total_balance),
            "latest_recommendation": {
                "recommendation_type": latest_recommendation["recommendation_type"],
                "message": latest_recommendation["message"],
                "model_version": latest_recommendation["model_version"],
                "generated_at": latest_recommendation["generated_at"].isoformat(),
            }
            if latest_recommendation
            else None,
          }


def get_metric_seed_counts() -> dict[str, list[dict[str, Any]]]:
    with pool.connection() as conn:
        transfers = conn.execute(
            "SELECT status, COUNT(*)::int AS count FROM transfers GROUP BY status"
        ).fetchall()
        outbox = conn.execute(
            """
            SELECT event_type, LOWER(status) AS result, COUNT(*)::int AS count
            FROM outbox_events
            GROUP BY event_type, status
            """
        ).fetchall()
        return {
            "transfers": [dict(row) for row in transfers],
            "outbox": [dict(row) for row in outbox],
        }


def claim_outbox_events(limit: int = 10) -> list[dict[str, Any]]:
    with pool.connection() as conn:
        with conn.transaction():
            rows = conn.execute(
                """
                SELECT id, aggregate_id, event_type, payload, attempts
                FROM outbox_events
                WHERE status = 'PENDING'
                ORDER BY created_at
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                (limit,),
            ).fetchall()
            for row in rows:
                conn.execute(
                    "UPDATE outbox_events SET status = 'IN_PROGRESS', attempts = attempts + 1 WHERE id = %s",
                    (row["id"],),
                )
            return [dict(row) for row in rows]


def mark_event_published(event_id: UUID) -> None:
    with pool.connection() as conn:
        conn.execute(
            "UPDATE outbox_events SET status = 'PUBLISHED', published_at = now(), last_error = NULL WHERE id = %s",
            (event_id,),
        )


def mark_event_pending(event_id: UUID, error: str) -> None:
    with pool.connection() as conn:
        conn.execute(
            """
            UPDATE outbox_events
            SET status = CASE WHEN attempts >= 5 THEN 'FAILED' ELSE 'PENDING' END,
                last_error = %s
            WHERE id = %s
            """,
            (error[:1000], event_id),
        )


def settle_transfer(transfer_id: UUID, core_reference: str) -> None:
    with pool.connection() as conn:
        with conn.transaction():
            conn.execute(
                """
                UPDATE transfers
                SET status = %s, core_reference = %s, rejection_reason = NULL, updated_at = now()
                WHERE id = %s
                """,
                (TransferStatus.SETTLED, core_reference, transfer_id),
            )
            transfer = conn.execute("SELECT * FROM transfers WHERE id = %s", (transfer_id,)).fetchone()
            payload = {
                "transfer_id": str(transfer_id),
                "customer_id": transfer["customer_id"],
                "amount": str(transfer["amount"]),
                "currency": transfer["currency"],
                "source_account": transfer["source_account"],
                "destination_account": transfer["destination_account"],
                "correlation_id": transfer["correlation_id"],
            }
            conn.execute(
                """
                INSERT INTO outbox_events (id, aggregate_id, event_type, payload)
                VALUES (%s, %s, 'AI_RECOMMENDATION_REQUESTED', %s)
                """,
                (uuid4(), transfer_id, Jsonb(payload)),
            )


def reject_transfer(transfer_id: UUID, reason: str) -> None:
    with pool.connection() as conn:
        with conn.transaction():
            transfer = conn.execute(
                "SELECT * FROM transfers WHERE id = %s FOR UPDATE",
                (transfer_id,),
            ).fetchone()
            if not transfer or transfer["status"] == TransferStatus.REJECTED:
                return
            if transfer["status"] in (TransferStatus.PENDING_CORE, TransferStatus.PENDING_RECONCILIATION):
                conn.execute(
                    """
                    UPDATE accounts
                    SET available_balance = available_balance + %s, updated_at = now()
                    WHERE account_id = %s
                    """,
                    (transfer["amount"], transfer["source_account"]),
                )
                conn.execute(
                    """
                    UPDATE accounts
                    SET available_balance = available_balance - %s, updated_at = now()
                    WHERE account_id = %s
                    """,
                    (transfer["amount"], transfer["destination_account"]),
                )
                conn.execute(
                    """
                    INSERT INTO ledger_entries (transfer_id, account_id, entry_type, amount, currency)
                    VALUES (%s, %s, 'DEBIT_COMPENSATED', %s, %s),
                           (%s, %s, 'CREDIT_COMPENSATED', %s, %s)
                    """,
                    (
                        transfer_id,
                        transfer["source_account"],
                        transfer["amount"],
                        transfer["currency"],
                        transfer_id,
                        transfer["destination_account"],
                        transfer["amount"],
                        transfer["currency"],
                    ),
                )
            conn.execute(
                """
                UPDATE transfers
                SET status = %s, rejection_reason = %s, updated_at = now()
                WHERE id = %s
                """,
                (TransferStatus.REJECTED, reason, transfer_id),
            )


def mark_pending_reconciliation(transfer_id: UUID, reason: str) -> None:
    with pool.connection() as conn:
        conn.execute(
            """
            UPDATE transfers
            SET status = %s, rejection_reason = %s, updated_at = now()
            WHERE id = %s AND status = %s
            """,
            (TransferStatus.PENDING_RECONCILIATION, reason, transfer_id, TransferStatus.PENDING_CORE),
        )


def save_ai_recommendation(payload: dict[str, Any], response: dict[str, Any]) -> None:
    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO ai_recommendations (
                id, transfer_id, customer_id, recommendation_type, message, model_version
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                uuid4(),
                UUID(payload["transfer_id"]),
                payload["customer_id"],
                response["recommendation_type"],
                response["message"],
                response["model_version"],
            ),
        )
