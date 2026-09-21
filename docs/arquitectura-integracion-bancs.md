# Arquitectura de SmartBancs

## Tesis de la solución

SmartBancs no reemplaza a Bancs ni lo expone a la carga completa de los canales digitales. La solución se plantea como una capa transaccional desacoplada que absorbe concurrencia, protege el core, mantiene un modelo operacional propio y publica eventos para capacidades no críticas como IA, analítica y observabilidad.

Bancs permanece como sistema financiero de registro. SmartBancs mantiene una proyección local y un ledger técnico para auditoría, conciliación, idempotencia y control de concurrencia del MVP.

## Componentes

- `transaction-service`: recibe transferencias, valida idempotencia, bloquea cuentas en orden determinístico, registra ledger y genera eventos outbox.
- `bancs-adapter`: anti-corruption layer. Traduce el modelo canónico de SmartBancs al contrato real de Bancs. En el MVP usa un mock con reglas transaccionales y límites de concurrencia.
- `ai-service`: servicio independiente que genera recomendaciones a partir de eventos de transferencia ya procesados.
- `PostgreSQL`: almacena transferencias, saldos de proyección, ledger, outbox, recomendaciones y tablas simuladas de Bancs.
- `Prometheus`: recolecta métricas de volumen, latencia, errores, llamadas a Bancs e IA.

## Flujo de transferencia

1. El cliente envía `POST /v1/transfers` con `Idempotency-Key` y `X-Correlation-Id`.
2. `transaction-service` inserta la transferencia con restricción única sobre la clave de idempotencia.
3. La base bloquea las cuentas afectadas con `SELECT ... FOR UPDATE` y siempre en orden por `account_id`.
4. Si la cuenta no existe, no está activa, la moneda no coincide o no hay fondos suficientes, la operación queda `REJECTED`.
5. Si pasa la validación, SmartBancs reserva el movimiento en su proyección, registra dos entradas de ledger y crea un evento `TRANSFER_REQUESTED` en la outbox dentro de la misma transacción ACID.
6. El worker de outbox llama al `bancs-adapter`.
7. Si Bancs confirma, la transferencia pasa a `SETTLED` y se publica `AI_RECOMMENDATION_REQUESTED`.
8. Si Bancs rechaza, SmartBancs compensa la reserva local y marca la transferencia como `REJECTED`.
9. Si ocurre un timeout ambiguo, la transferencia queda `PENDING_RECONCILIATION`.
10. La IA consume el evento después del settlement, por lo que no bloquea la transferencia.

## Integración con Bancs

El reto no especifica si Bancs se integra mediante API, MQ, archivos, socket, procedimientos, CDC o un protocolo propietario. Por eso el diseño evita acoplar el dominio de SmartBancs a un contrato inventado.

El `bancs-adapter` es la frontera de integración. En producción debe encapsular:

- mapeo entre modelo canónico y modelo Bancs;
- idempotencia por `core_reference`;
- rate limiting;
- bulkheads;
- circuit breaker;
- timeouts;
- backpressure;
- conciliación de estados ambiguos;
- masking de datos sensibles;
- trazabilidad con `correlation_id`.

Si Bancs soporta idempotencia transaccional, el adapter puede hacer retries seguros. Si no la soporta, un timeout no se trata como fallo definitivo: se marca `PENDING_RECONCILIATION` y se consulta posteriormente el estado por referencia de negocio o referencia del core.

## Saldos y consistencia

SmartBancs puede mantener saldos de consulta y ledger técnico, pero Bancs conserva la autoridad financiera. La proyección local reduce consultas directas al core y permite responder consultas frecuentes sin degradar Bancs.

Para operaciones financieras sensibles, la autorización final depende del contrato real con Bancs. El MVP reserva localmente para demostrar concurrencia y consistencia, y confirma contra el adapter para simular el posting del core.

## Outbox transaccional

La outbox evita el fallo clásico de guardar una transacción y perder el evento si el proceso cae antes de publicarlo. En el MVP se inserta `outbox_events` dentro del mismo commit que la transferencia y el ledger. Un worker posterior procesa eventos pendientes.

La entrega se asume at-least-once. Los consumidores deben ser idempotentes; por eso existe la tabla `processed_messages` como parte del modelo recomendado.

## Concurrencia

La regla crítica es bloquear recursos compartidos dentro de la transacción y en orden determinístico. Si dos transferencias intentan debitar la misma cuenta, una verá el saldo actualizado por la otra y no podrá sobregirar.

Para prevenir deadlocks en transferencias cruzadas, el orden de lock no depende de la dirección de la transferencia:

```text
lock min(account_id)
lock max(account_id)
```

Esta decisión responde directamente al incidente simulado del reto.

## Seguridad

El MVP deja la estructura preparada para controles productivos:

- TLS externo y mTLS interno;
- OAuth2/OIDC en el gateway;
- RBAC por operación;
- secretos fuera del repositorio;
- cifrado en tránsito y reposo;
- auditoría de operaciones financieras;
- segmentación de red;
- masking de cuentas y datos sensibles;
- Bancs inaccesible desde Internet.

## Producción

Docker Compose no es producción. La versión productiva debería ejecutarse en la plataforma corporativa existente, por ejemplo Kubernetes u OpenShift, con PostgreSQL HA, Kafka o equivalente, observabilidad centralizada, secretos gestionados y conectividad privada hacia Bancs.

AWS puede ser una buena opción si el banco ya tiene landing zone, gobierno de seguridad, Direct Connect, IAM, observabilidad y FinOps maduros. Si Bancs está on-premise, el adapter debe mantenerse cerca del core para reducir latencia y proteger la integración.
