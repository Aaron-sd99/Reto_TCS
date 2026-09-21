from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass


@dataclass(frozen=True)
class Result:
    status_code: int
    latency_ms: float
    transfer_status: str
    error: str | None = None


def post_transfer(base_url: str, sequence: int, amount: str) -> Result:
    payload = {
        "source_account": "ACC-1001",
        "destination_account": "ACC-2001",
        "amount": amount,
        "currency": "USD",
        "customer_id": "CUS-001",
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/v1/transfers",
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Idempotency-Key": f"load-10000-{sequence:05d}",
            "X-Correlation-Id": f"load-10000-{sequence:05d}",
        },
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = json.loads(response.read().decode("utf-8"))
            elapsed = (time.perf_counter() - started) * 1000
            return Result(response.status, elapsed, body.get("status", "UNKNOWN"))
    except urllib.error.HTTPError as exc:
        elapsed = (time.perf_counter() - started) * 1000
        return Result(exc.code, elapsed, "HTTP_ERROR", exc.read().decode("utf-8", errors="replace")[:250])
    except Exception as exc:
        elapsed = (time.perf_counter() - started) * 1000
        return Result(0, elapsed, "CLIENT_ERROR", str(exc))


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    index = int(round((pct / 100) * (len(values) - 1)))
    return sorted(values)[index]


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit many transfer requests to the SmartBancs API.")
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--requests", type=int, default=10_000)
    parser.add_argument("--concurrency", type=int, default=100)
    parser.add_argument("--amount", default="0.01")
    args = parser.parse_args()

    started = time.perf_counter()
    results: list[Result] = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(post_transfer, args.base_url, item, args.amount) for item in range(args.requests)]
        for index, future in enumerate(as_completed(futures), 1):
            results.append(future.result())
            if index % 1000 == 0:
                print(f"submitted={index}")

    elapsed = time.perf_counter() - started
    latencies = [result.latency_ms for result in results]
    successful = [result for result in results if result.status_code == 202]
    failed = [result for result in results if result.status_code != 202]
    by_status: dict[str, int] = {}
    for result in results:
        by_status[result.transfer_status] = by_status.get(result.transfer_status, 0) + 1

    print(json.dumps(
        {
            "requests": args.requests,
            "concurrency": args.concurrency,
            "elapsed_seconds": round(elapsed, 3),
            "throughput_requests_per_second": round(len(results) / elapsed, 2),
            "successful_http_202": len(successful),
            "failed": len(failed),
            "transfer_statuses": by_status,
            "latency_ms": {
                "min": round(min(latencies), 2) if latencies else 0,
                "mean": round(statistics.mean(latencies), 2) if latencies else 0,
                "p50": round(percentile(latencies, 50), 2),
                "p95": round(percentile(latencies, 95), 2),
                "p99": round(percentile(latencies, 99), 2),
                "max": round(max(latencies), 2) if latencies else 0,
            },
            "sample_errors": [result.error for result in failed[:5]],
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
