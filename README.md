# SmartBancs MVP

SmartBancs es un MVP bancario diseñado para integrarse con Bancs, el core transaccional del banco, sin convertir la nueva plataforma en un core paralelo ni saturar el sistema legado con consultas directas.

La solución incluye:

- `transaction-service`: API REST principal para registrar transferencias, aplicar idempotencia, controlar concurrencia, mantener un ledger técnico y publicar eventos mediante outbox transaccional.
- `bancs-adapter`: capa anticorrupción que simula la integración con Bancs. En producción encapsula el mecanismo real disponible por el core: API, MQ, archivos, socket, servicios propietarios u otro contrato.
- `ai-service`: mock funcional de IA, consumido de forma asíncrona y fuera del camino crítico de la transferencia.
- `PostgreSQL`: base transaccional del MVP, con DDL/DML, saldos de proyección, ledger, outbox, recomendaciones y tablas simuladas del core.
- `ETL`: script Python que limpia datos transaccionales crudos y genera un dataset curado para analítica o IA.
- `Prometheus`: métricas básicas de volumen, errores y latencia.
- `frontend`: consola operativa para demostrar el flujo completo sin depender solo de Swagger o comandos curl.

## Prerrequisitos

- Docker 29+
- Docker Compose

## Ejecutar

```bash
docker compose up --build
```

Servicios:

- Operations Console: http://localhost:8083
- Transaction Service: http://localhost:8080/docs
- Bancs Adapter: http://localhost:8081/docs
- AI Service: http://localhost:8082/docs
- Prometheus: http://localhost:9090

La consola muestra el resumen operativo, saldos de proyección, últimas transferencias, flujo de infraestructura y un formulario real para crear nuevas transferencias contra el `transaction-service`.

## Datos de prueba

Al iniciar con `docker compose down -v` y luego `docker compose up --build`, la base queda cargada con cuentas de ejemplo:

- `ACC-1001` a `ACC-2001`: transferencia exitosa estándar en USD.
- `ACC-3001` a `ACC-2001`: transferencia exitosa con saldo alto.
- `ACC-3002` a `ACC-2001`: caso de fondos insuficientes si el monto supera `5.00`.
- `ACC-4001` a `ACC-2001`: caso de moneda incompatible si se intenta enviar en USD.
- `ACC-9001` a `ACC-2001`: caso de cuenta inactiva.

## Probar una transferencia

```bash
curl -X POST http://localhost:8080/v1/transfers ^
  -H "Content-Type: application/json" ^
  -H "Idempotency-Key: demo-001" ^
  -H "X-Correlation-Id: corr-demo-001" ^
  -d "{\"source_account\":\"ACC-1001\",\"destination_account\":\"ACC-2001\",\"amount\":\"125.50\",\"currency\":\"USD\",\"customer_id\":\"CUS-001\"}"
```

Consultar el estado:

```bash
curl http://localhost:8080/v1/transfers/{transfer_id}
```

Repetir el mismo `Idempotency-Key` devuelve la misma transferencia y no mueve dinero dos veces.

## Ejecutar ETL

```bash
python etl/transform_transactions.py --input etl/input/raw_transactions.csv --output etl/output/curated_transactions.csv --rejected etl/output/rejected_transactions.csv
```

## Pruebas

```bash
python -m unittest discover -s tests
```

Las pruebas cubren idempotencia pura y orden determinístico de locks, que son dos puntos críticos del reto.

## Simular 10 000 transferencias

Con el stack levantado:

```bash
python tests/load_10000_transfers.py --requests 10000 --concurrency 100 --amount 0.01
```

La prueba envía claves de idempotencia únicas, mide latencias del endpoint y permite validar en base de datos cuántas transferencias fueron aceptadas, liquidadas por Bancs y consumidas por IA.

## Detener

```bash
docker compose down -v
```

## Documentación de defensa

- [Informe técnico final](Informe/Informe%20Técnico_Aarón%20Yumancela___.pdf)
- [Arquitectura e integración con Bancs](docs/arquitectura-integracion-bancs.md)
- [Operación, observabilidad e incidente simulado](docs/operacion-observabilidad-incidente.md)
- [IA y ciclo de vida del modelo](docs/ia-ciclo-vida-modelo.md)
- [Costos y estrategia de escalabilidad](docs/costos-escalabilidad.md)
- [Valor de negocio](docs/valor-negocio.md)
- [Reporte de validación](docs/reporte-validacion.md)
- [Guía de demo](docs/guia-demo.md)
- [Guion de defensa](docs/guion-defensa.md)
- [Declaración de uso de IA](docs/declaracion-uso-ia.md)
