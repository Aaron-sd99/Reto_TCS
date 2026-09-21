# IA en SmartBancs

## Principio de diseño

La IA no participa en el camino crítico de la transferencia. Una falla, lentitud o despliegue defectuoso del modelo no debe impedir que SmartBancs procese operaciones financieras.

En el MVP, `ai-service` recibe eventos después de que una transferencia es confirmada y genera una recomendación determinística. Esto demuestra el patrón de integración sin introducir costo innecesario de modelos grandes o GPU.

## Flujo de datos

```text
transfer settled
  -> outbox event
  -> AI service
  -> recommendation
  -> ai_recommendations
```

## Ciclo de vida productivo

1. Ingesta de transacciones y eventos curados.
2. Validación de calidad de datos.
3. Generación de features.
4. Entrenamiento.
5. Validación offline.
6. Registro de modelo.
7. Despliegue controlado.
8. Inferencia.
9. Monitoreo de latencia, errores, costo y drift.
10. Reentrenamiento gobernado.

## Data drift

Se monitorean cambios entre entrenamiento y producción:

- monto promedio;
- distribución de categorías;
- frecuencia transaccional;
- horarios de uso;
- segmentos de clientes;
- monedas y tipos de operación.

Si el drift supera umbrales acordados, se genera alerta y se evalúa reentrenamiento. No se recomienda reentrenamiento automático sin validación, porque el dominio financiero exige control y trazabilidad.

## Costo de IA

Para este caso, la estrategia inicial es CPU-first. La métrica de decisión no debe ser “usar IA avanzada”, sino costo por mil recomendaciones, latencia, exactitud útil para negocio y consumo de recursos.

Un LLM no es necesario para el MVP. En producción se justificaría solo si el caso de uso requiere comprensión de texto, explicación avanzada o interacción conversacional con controles de seguridad.
