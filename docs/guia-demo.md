# Guía de Demo

## Objetivo de la demo

Mostrar en pocos minutos que SmartBancs no es una aplicación aislada, sino una capa transaccional integrable con Bancs, con control de concurrencia, idempotencia, observabilidad e IA fuera del camino crítico.

## Preparar ambiente

```bash
docker compose down -v
docker compose up --build -d
docker compose ps
```

Abrir:

- http://localhost:8083
- http://localhost:8080/docs
- http://localhost:8081/docs
- http://localhost:8082/docs
- http://localhost:9090

## Demo 1 consola operativa

Abrir `http://localhost:8083`.

Mostrar:

- resumen operativo de transferencias, outbox, recomendaciones de IA y ledger;
- saldos de proyección por cuenta;
- actividad reciente con `correlation_id`;
- diagrama de flujo ejecutable: canal digital, `transaction-service`, PostgreSQL, outbox, `bancs-adapter`, Bancs simulado e IA.

Crear una transferencia desde el formulario:

- origen: `ACC-1001`;
- destino: `ACC-1002` o `ACC-2001`;
- monto bajo, por ejemplo `1.23`;
- cliente: `CUS-001`.

Esperado:

- la transferencia aparece en actividad reciente;
- el contador de transferencias aumenta;
- el outbox publica dos eventos adicionales;
- se generan dos asientos de ledger;
- aparece una nueva recomendación de IA;
- los saldos se actualizan sin entrar directamente a Bancs.

## Demo 2 transferencia normal por API

```bash
curl -X POST http://localhost:8080/v1/transfers ^
  -H "Content-Type: application/json" ^
  -H "Idempotency-Key: demo-001" ^
  -H "X-Correlation-Id: corr-demo-001" ^
  -d "{\"source_account\":\"ACC-1001\",\"destination_account\":\"ACC-2001\",\"amount\":\"125.50\",\"currency\":\"USD\",\"customer_id\":\"CUS-001\"}"
```

Esperado:

- respuesta inicial `PENDING_CORE`;
- luego `SETTLED` al consultar el `transfer_id`;
- ledger con débito y crédito;
- outbox publicada;
- recomendación en `ai_recommendations`.

## Demo 3 idempotencia

Repetir el mismo comando con el mismo `Idempotency-Key`.

Esperado:

- mismo `transfer_id`;
- una sola transferencia en base;
- saldos sin doble débito.

## Demo 4 concurrencia

Usar dos requests simultáneos debitando la misma cuenta con fondos insuficientes para ambas. El resultado esperado es una transferencia aceptada y otra rechazada, sin saldo negativo.

## Demo 5 carga

```bash
python tests/load_10000_transfers.py --requests 10000 --concurrency 100 --amount 0.01
```

Validar:

```bash
docker compose exec -T postgres psql -U smartbancs -d smartbancs -c "SELECT status, COUNT(*) FROM transfers GROUP BY status;"
docker compose exec -T postgres psql -U smartbancs -d smartbancs -c "SELECT status, COUNT(*) FROM outbox_events GROUP BY status;"
docker compose exec -T postgres psql -U smartbancs -d smartbancs -c "SELECT COUNT(*) FROM ai_recommendations;"
```

Después abrir la consola en `http://localhost:8083` y presionar **Actualizar** para mostrar el impacto de la carga en un tablero legible.

## Demo 6 observabilidad

Revisar:

- `smartbancs_transfers_total`
- `smartbancs_outbox_events_total`
- `smartbancs_core_latency_seconds_count`
- `bancs_postings_total`
- `ai_recommendations_total`

En Prometheus:

```text
up
smartbancs_outbox_events_total
bancs_postings_total
ai_recommendations_total
```
