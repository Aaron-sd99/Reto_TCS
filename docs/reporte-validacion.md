# Reporte de Validación

Fecha de validación: 2026-09-20

## Resumen

El MVP fue ejecutado con Docker Compose y validado contra los requisitos prácticos del reto. La prueba principal simuló 10 000 transferencias reales enviadas al endpoint `POST /v1/transfers`, con idempotency keys únicas y concurrencia local.

La prueba valida el comportamiento funcional del MVP. No debe interpretarse como una certificación de 10 000 TPS en producción, porque esa capacidad depende de infraestructura, tuning de base de datos, capacidad real de Bancs, red, hardware, retención de logs, configuración de pools y pruebas formales de performance.

## Ambiente

- Sistema local Windows con Docker Desktop.
- Docker Compose.
- PostgreSQL 16.
- Transaction Service FastAPI.
- Bancs Adapter FastAPI.
- AI Service FastAPI.
- Prometheus.

## Comandos ejecutados

```bash
docker compose down -v
docker compose up --build -d
python -m unittest discover -s tests
python -m compileall services etl tests
python tests/load_10000_transfers.py --requests 10000 --concurrency 100 --amount 0.01
```

## Resultado de la carga

```json
{
  "requests": 10000,
  "concurrency": 100,
  "elapsed_seconds": 66.701,
  "throughput_requests_per_second": 149.92,
  "successful_http_202": 10000,
  "failed": 0,
  "transfer_statuses": {
    "PENDING_CORE": 10000
  },
  "latency_ms": {
    "min": 33.63,
    "mean": 663.15,
    "p50": 525.42,
    "p95": 1427.53,
    "p99": 2146.03,
    "max": 4370.11
  }
}
```

La respuesta inicial del endpoint fue no bloqueante y aceptó el 100% de solicitudes. El p95 quedó por debajo de 2 segundos en este entorno local. El p99 superó 2 segundos, lo cual se documenta como límite del ambiente local y no como objetivo productivo.

## Estado final en base de datos

```text
transfers:
  SETTLED = 10000

outbox_events:
  PUBLISHED = 20000

ledger_entries:
  20000

ai_recommendations:
  10000
```

Interpretación:

- Cada transferencia generó dos entradas de ledger.
- Cada transferencia generó un evento hacia Bancs y un evento hacia IA.
- Todas las transferencias aceptadas terminaron liquidadas.
- Todas las recomendaciones de IA fueron generadas fuera del camino crítico.

## Métricas observadas

```text
smartbancs_outbox_events_total{event_type="TRANSFER_REQUESTED",result="published"} 10000
smartbancs_outbox_events_total{event_type="AI_RECOMMENDATION_REQUESTED",result="published"} 10000
smartbancs_core_latency_seconds_count{result="200"} 10000
bancs_postings_total{status="SETTLED"} 10000
ai_recommendations_total{type="SAVINGS_NUDGE"} 10000
```

## Validaciones funcionales adicionales

- Healthchecks de los tres servicios respondieron `{"status":"ok"}`.
- Idempotencia: repetir la misma clave devolvió el mismo `transfer_id` y no duplicó saldos.
- Fondos insuficientes: la transferencia quedó `REJECTED`, sin ledger ni outbox.
- Concurrencia: dos débitos simultáneos sobre una cuenta con fondos insuficientes para ambos dejaron una transferencia `SETTLED` y otra `REJECTED`, sin saldo negativo.
- Prometheus detectó los tres targets como `up`.

## Conclusión

El MVP cumple el objetivo práctico del reto: expone un microservicio transaccional, interactúa con base de datos, controla concurrencia, evita duplicidad por idempotencia, integra un adapter para Bancs, usa un flujo asíncrono para IA, registra métricas y deja evidencia observable de extremo a extremo.

Para producción, la validación debe extenderse con pruebas de carga formales, datos realistas, tuning de PostgreSQL, capacidad real del canal de Bancs, SLO acordados con negocio y pruebas de resiliencia.
