# Prueba técnica — Ingeniería de Datos Tuya

Autor: Victor

| # | Ejercicio | Tipo | Carpeta |
|---|---|---|---|
| 1 | Dataset confiable de teléfonos de clientes con CI/CD | Conceptual + normalizador de referencia | [`ejercicio_1_dataset_telefonos`](ejercicio_1_dataset_telefonos/README.md) |
| 2 | Veeduría de calidad, trazabilidad y KPIs de teléfonos | Conceptual | [`ejercicio_2_kpis_calidad`](ejercicio_2_kpis_calidad/README.md) |
| 3 | Rachas de nivel de deuda | SQL (SQLite) + Python | [`ejercicio_3_rachas`](ejercicio_3_rachas/README.md) |
| 4 | Imágenes de HTML a base64 | Python (solo librería estándar, POO) | [`ejercicio_4_html_base64`](ejercicio_4_html_base64/README.md) |

## Requisitos

- Python 3.10 o superior.
- `openpyxl` únicamente para leer el Excel del ejercicio 3 (`pip install -r ejercicio_3_rachas/requirements.txt`).
- Los ejercicios 1 y 4 no tienen dependencias externas.

## Ejecución rápida

```bash
# Ejercicio 1: pruebas del normalizador
cd ejercicio_1_dataset_telefonos && python -m unittest discover -s tests && cd ..

# Ejercicio 3: construir la BD y consultar rachas
cd ejercicio_3_rachas
pip install -r requirements.txt
python rachas.py --fecha-base 2024-12-31 --n 3 --salida output/rachas.csv
python -m unittest discover -s tests -v
cd ..

# Ejercicio 4: procesar HTML
cd ejercicio_4_html_base64
python -m html_base64 examples/sitio --report reporte.json
python -m unittest discover -s tests -v
```

## Resumen del desarrollo

### 1. Dataset de teléfonos
Arquitectura medallion (Bronze → Silver → Gold) con contratos de datos, normalización a E.164 según el plan de numeración colombiano, cuarentena de inválidos, golden record con puntaje de confiabilidad, historial SCD2 y cumplimiento de Habeas Data. El CI/CD valida cada Pull Request (lint, pruebas unitarias, contratos, build efímero, pruebas de datos y *data diff*) y despliega con aprobación y patrón Write-Audit-Publish. Incluye un normalizador funcional con pruebas.

### 2. KPIs y veeduría
Observatorio de calidad: catálogo de reglas, resultados por ejecución, linaje a nivel de tabla, columna y registro, capa semántica de KPIs (cobertura, validez, sospechosos, frescura, contactabilidad, calidad por fuente), tablero Power BI por audiencia y alertas con gestión de incidentes.

### 3. Rachas
Carga Excel → staging → tablas depuradas con 13 reglas de calidad registradas en `calidad_log`. La consulta, parametrizada por `fecha_base` y `n`, construye una grilla continua cliente × mes (imputando N0 y respetando retiros) y resuelve las rachas con *gaps & islands* y funciones de ventana. Se validó contra una implementación de referencia independiente en 35 combinaciones de parámetros. Hallazgos en los datos: un duplicado exacto, una llave con dos saldos distintos, un retiro con identificación mal digitada y dos clientes con saldos reportados después de su retiro.

### 4. HTML a base64
Paquete `html_base64` con CLI, diseñado con principios SOLID: descubrimiento de archivos y directorios recursivo, ubicación de `<img>` con `html.parser` (ignora comentarios y scripts), fuentes de imagen intercambiables (local, `file://`, data URI y http opcional), detección de MIME por firma binaria y reemplazo no destructivo que genera un archivo nuevo. Devuelve `{success: {}, fail: {}}` agrupado por archivo.

## Integración continua

`.github/workflows/ci.yml` ejecuta las pruebas de los ejercicios 1, 3 y 4 en Python 3.10 y 3.12 en cada push y Pull Request.
