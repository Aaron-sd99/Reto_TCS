# Costos y Escalabilidad

## Enfoque

La arquitectura evita gastar en componentes que no resuelven una restricción real. No se incluye Redis, GPU, bases distribuidas o service mesh como requisito inicial. Cada componente debe justificar su costo por resiliencia, rendimiento, seguridad u operación.

## Principales drivers

- TPS pico y TPS promedio.
- Duración de los picos.
- Escrituras por transferencia.
- Retención de eventos.
- Volumen de logs y trazas.
- Alta disponibilidad.
- Recuperación ante desastre.
- Operación administrada vs self-managed.
- Conectividad con Bancs.
- Costo de inferencia de IA.

## Base de datos

Una transferencia genera al menos:

- una fila en `transfers`;
- dos filas en `ledger_entries`;
- un evento en `outbox_events`;
- actualizaciones de saldos de proyección.

A 10 000 TPS, el volumen de escritura exige pruebas de carga reales. PostgreSQL es una decisión inicial razonable por ACID, madurez y costo operativo, pero la capacidad se valida con benchmarks. Antes de introducir una base distribuida conviene optimizar índices, pool, particionamiento, hardware y réplicas de lectura.

## Mensajería

Kafka o una alternativa compatible se justifica en producción si se requiere replay, desacoplamiento y múltiples consumidores. En el MVP se implementa el patrón outbox sobre PostgreSQL para demostrar confiabilidad sin obligar al evaluador a levantar un cluster pesado.

Para producción:

- retención caliente corta, por ejemplo 24 a 72 horas;
- archivo histórico en object storage;
- consumidores idempotentes;
- DLQ para eventos no procesables.

## Observabilidad

Los logs pueden ser más costosos que la aplicación. La estrategia recomendada:

- logs estructurados;
- sin `DEBUG` permanente en producción;
- retención diferenciada por criticidad;
- trazas completas para errores y solicitudes lentas;
- muestreo para tráfico normal;
- métricas agregadas para tendencias.

## AWS

AWS puede aportar valor si el banco ya opera una plataforma madura. Equivalencias posibles:

- EKS o ECS para servicios.
- RDS o Aurora PostgreSQL.
- MSK para Kafka.
- S3 para históricos.
- Secrets Manager y KMS.
- CloudWatch, OpenSearch o plataforma observabilidad corporativa.

No se propone AWS por apariencia. Si Bancs está en datacenter, mover todo a nube pública puede agregar latencia, egress, Direct Connect, superficie de seguridad y dependencia operativa. Una alternativa híbrida razonable es dejar el adapter cerca de Bancs y alojar servicios escalables donde tenga mejor costo total.

## Decisiones de ahorro

- Docker Compose para MVP.
- PostgreSQL antes que base distribuida.
- Outbox local en el MVP.
- IA mock/ligera en CPU.
- Sin Redis como fuente de verdad financiera.
- Retención corta de eventos operacionales.
- Logs y trazas con políticas de retención.
- Escalamiento horizontal solo en servicios stateless.
- Backpressure para no convertir SmartBancs en un ataque interno contra Bancs.
