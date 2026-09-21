# Operación Observabilidad e Incidente Simulado

## Observabilidad del MVP

Cada servicio expone `/metrics` para Prometheus y registra eventos en JSON. Las trazas completas pueden incorporarse con OpenTelemetry en producción; el MVP ya conserva `correlation_id` y `transfer_id` para seguir una transacción entre componentes.

Métricas principales:

- `smartbancs_transfers_total`: transferencias recibidas por estado.
- `smartbancs_request_latency_seconds`: latencia HTTP por ruta.
- `smartbancs_core_latency_seconds`: latencia de llamadas al adapter de Bancs.
- `smartbancs_outbox_events_total`: eventos procesados por resultado.
- `bancs_postings_total`: postings aceptados o rechazados por el mock de Bancs.
- `bancs_inflight_requests`: solicitudes concurrentes hacia Bancs.
- `ai_recommendations_total`: recomendaciones generadas.

Logs críticos:

- recepción de transferencia;
- replay por idempotencia;
- errores de outbox;
- llamadas a Bancs;
- generación de recomendación de IA.

No deben registrarse PIN, contraseñas, tokens, CVV ni números de cuenta completos.

## Incidente simulado

Escenario: pico transaccional de quincena, transferencias sin completar, latencia alta, timeouts de conexión a base de datos y posibles deadlocks.

## Detección

Alertas iniciales:

- p95 o p99 de `POST /v1/transfers` por encima del SLO;
- aumento de transferencias `PENDING_CORE` o `PENDING_RECONCILIATION`;
- pool de base saturado;
- lock waits elevados;
- deadlocks en PostgreSQL;
- backlog de outbox;
- latencia alta en Bancs adapter.

## Contención inmediata

1. Activar o endurecer rate limiting en canales no críticos.
2. Pausar jobs no esenciales de analítica, reportes o reprocesos.
3. Reducir temporalmente concurrencia de workers que presionen la base.
4. Revisar sesiones bloqueantes y finalizar únicamente las que estén identificadas como causa del bloqueo.
5. Mantener abierto el circuito hacia Bancs si la degradación proviene del core o su enlace.
6. Priorizar consultas de transferencia sobre consultas masivas de lectura.

La primera respuesta no debe ser “agregar más pods”, porque más instancias pueden aumentar la presión sobre la base y agravar los deadlocks.

## Diagnóstico

Preguntas operativas:

- qué query concentra el mayor tiempo total;
- qué transacción bloquea a otras;
- qué tablas tienen mayor lock wait;
- si el pool espera conexiones o si el cuello está dentro de PostgreSQL;
- si el adapter está saturando Bancs;
- si el outbox acumula eventos por falla de downstream;
- si el problema afecta todas las transferencias o solo una ruta.

Consultas típicas de diagnóstico:

```sql
SELECT pid, state, wait_event_type, wait_event, query
FROM pg_stat_activity
WHERE datname = 'smartbancs';

SELECT deadlocks, conflicts, temp_files
FROM pg_stat_database
WHERE datname = 'smartbancs';
```

## Solución permanente

- mantener locks en orden determinístico;
- acortar transacciones que retengan locks;
- revisar índices de `transfers`, `ledger_entries` y `outbox_events`;
- dimensionar pool de conexiones según capacidad real de PostgreSQL;
- separar tráfico transaccional de procesos analíticos;
- mantener outbox con lotes controlados;
- hacer pruebas de carga con escenarios de transferencias cruzadas;
- incorporar OpenTelemetry distribuido para diagnóstico visual.

## Post mortem

Estructura propuesta:

1. Resumen ejecutivo.
2. Línea de tiempo.
3. Impacto en clientes y negocio.
4. Servicios afectados.
5. Causa raíz.
6. Factores contribuyentes.
7. Qué funcionó.
8. Qué no funcionó.
9. Acciones correctivas.
10. Acciones preventivas.
11. Owner y fecha compromiso.

El post mortem debe ser sin culpa individual. El objetivo es mejorar código, infraestructura, monitoreo y procedimientos.
