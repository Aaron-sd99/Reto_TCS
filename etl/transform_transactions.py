from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path


DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%b %d %Y", "%Y/%m/%d")


@dataclass
class TransformResult:
    valid: list[dict[str, str]]
    rejected: list[dict[str, str]]


def normalize_amount(value: str) -> str:
    value = value.strip().replace(",", ".")
    amount = Decimal(value)
    if amount <= 0:
        raise ValueError("amount must be positive")
    return f"{amount.quantize(Decimal('0.01'))}"


def normalize_date(value: str) -> str:
    raw = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError("invalid transaction_date")


def transform(rows: list[dict[str, str]]) -> TransformResult:
    valid: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    for row in rows:
        try:
            transaction_id = row.get("transaction_id", "").strip()
            if not transaction_id or transaction_id in seen_ids:
                raise ValueError("missing or duplicated transaction_id")
            seen_ids.add(transaction_id)

            customer_id = row.get("customer_id", "").strip()
            if not customer_id:
                raise ValueError("missing customer_id")

            curated = {
                "transaction_id": transaction_id,
                "customer_id": customer_id,
                "source_account": row.get("source_account", "").strip(),
                "destination_account": row.get("destination_account", "").strip(),
                "amount": normalize_amount(row.get("amount", "")),
                "currency": row.get("currency", "").strip().upper(),
                "transaction_date": normalize_date(row.get("transaction_date", "")),
                "category": row.get("category", "").strip().upper() or "UNKNOWN",
            }
            if curated["currency"] not in {"USD", "EUR"}:
                raise ValueError("unsupported currency")
            valid.append(curated)
        except (InvalidOperation, ValueError) as exc:
            bad = dict(row)
            bad["rejection_reason"] = str(exc)
            rejected.append(bad)

    return TransformResult(valid=valid, rejected=rejected)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean raw transactions for analytics and AI consumption.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--rejected", required=True, type=Path)
    args = parser.parse_args()

    result = transform(read_csv(args.input))
    valid_fields = [
        "transaction_id",
        "customer_id",
        "source_account",
        "destination_account",
        "amount",
        "currency",
        "transaction_date",
        "category",
    ]
    rejected_fields = valid_fields + ["rejection_reason"]
    write_csv(args.output, result.valid, valid_fields)
    write_csv(args.rejected, result.rejected, rejected_fields)
    print(f"valid={len(result.valid)} rejected={len(result.rejected)}")


if __name__ == "__main__":
    main()
