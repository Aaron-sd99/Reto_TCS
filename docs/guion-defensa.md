# Guion de Defensa de 3 Minutos

## Mensaje central

SmartBancs no reemplaza ni sobrecarga Bancs. La solución crea una capa transaccional desacoplada que absorbe concurrencia, protege el core bancario, publica eventos durables y deja la IA fuera del flujo financiero principal.

La demo se presenta desde una consola operativa, no solo desde Swagger. Ahí se puede crear una transferencia, ver saldos de proyección, actividad reciente, outbox, recomendaciones IA y el flujo de infraestructura que conecta canales digitales con Bancs.

## Minuto 1 arquitectura

El principal riesgo del reto es Bancs: es robusto, pero no debe recibir consultas masivas directas. Por eso propuse un `transaction-service` que recibe transferencias, controla idempotencia y concurrencia, y una capa `bancs-adapter` que funciona como anti-corruption layer. Si Bancs se integra por API, MQ, archivo, socket o mecanismo propietario, ese detalle queda encapsulado en el adapter.

Bancs se mantiene como system of record financiero. SmartBancs mantiene proyecciones y ledger técnico para operación, auditoría y conciliación.

## Minuto 2 garantías técnicas

El MVP usa PostgreSQL por ACID, constraints, locking e índices. Cada transferencia usa `Idempotency-Key` para evitar dobles débitos por reintentos. Para concurrencia se bloquean las cuentas con `SELECT FOR UPDATE` y en orden determinístico, reduciendo condiciones de carrera y deadlocks.

El patrón outbox evita perder eventos entre base de datos y consumidores. Primero se confirma la transacción local y el evento en el mismo commit; después el worker publica hacia Bancs e IA. Si Bancs confirma, la transferencia queda `SETTLED`; si hay timeout ambiguo, queda `PENDING_RECONCILIATION`.

## Minuto 3 operación IA y costos

La IA no está en el camino crítico. Consume eventos después del settlement y puede fallar sin detener transferencias. La observabilidad expone métricas de volumen, latencia, errores, outbox, Bancs e IA, además de logs con `correlation_id`.

En costos, no propuse tecnología innecesaria. El MVP usa Docker Compose y PostgreSQL; para producción se puede ir a Kubernetes, PostgreSQL HA, Kafka/MSK y AWS solo si la plataforma del banco lo justifica. La estrategia protege el recurso caro y crítico: Bancs.

La validación local envió 10 000 transferencias reales al API, todas aceptadas y posteriormente liquidadas, con 20 000 eventos outbox publicados y 10 000 recomendaciones generadas.
