-- =============================================================================
-- 01_esquema.sql
-- Modelo de datos del ejercicio de rachas (SQLite >= 3.25, requiere funciones
-- de ventana). Las fechas se almacenan como TEXT ISO-8601 (YYYY-MM-DD).
--
-- Capas:
--   stg_*      : datos crudos tal como llegan del Excel (sin restricciones).
--   historia / retiros : datos depurados, con llaves y restricciones.
--   dim_nivel  : catálogo de niveles de deuda (parametrizable).
--   parametros : fecha_base y n con los que se ejecuta la consulta.
--   calidad_log: bitácora de hallazgos de calidad de datos.
-- =============================================================================

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS stg_historia;
DROP TABLE IF EXISTS stg_retiros;
DROP TABLE IF EXISTS historia;
DROP TABLE IF EXISTS retiros;
DROP TABLE IF EXISTS dim_nivel;
DROP TABLE IF EXISTS parametros;
DROP TABLE IF EXISTS calidad_log;

-- ---------------------------------------------------------------------------
-- Staging (crudo)
-- ---------------------------------------------------------------------------
CREATE TABLE stg_historia (
    fila_origen     INTEGER PRIMARY KEY,   -- número de fila en el Excel
    identificacion  TEXT,
    corte_mes       TEXT,
    saldo           NUMERIC
);

CREATE TABLE stg_retiros (
    fila_origen     INTEGER PRIMARY KEY,
    identificacion  TEXT,
    fecha_retiro    TEXT
);

-- ---------------------------------------------------------------------------
-- Datos depurados
-- ---------------------------------------------------------------------------
CREATE TABLE historia (
    identificacion  TEXT    NOT NULL,
    corte_mes       TEXT    NOT NULL
        CHECK (corte_mes = date(corte_mes, 'start of month', '+1 month', '-1 day')),
    saldo           INTEGER NOT NULL CHECK (saldo >= 0),
    PRIMARY KEY (identificacion, corte_mes)
);

CREATE TABLE retiros (
    identificacion  TEXT NOT NULL PRIMARY KEY,
    fecha_retiro    TEXT NOT NULL CHECK (fecha_retiro = date(fecha_retiro))
);

-- ---------------------------------------------------------------------------
-- Catálogo de niveles: rango semiabierto [saldo_min, saldo_max)
-- ---------------------------------------------------------------------------
CREATE TABLE dim_nivel (
    nivel       TEXT    NOT NULL PRIMARY KEY,
    saldo_min   INTEGER NOT NULL,
    saldo_max   INTEGER              -- NULL = sin límite superior
);

INSERT INTO dim_nivel (nivel, saldo_min, saldo_max) VALUES
    ('N0',         0,   300000),
    ('N1',    300000,  1000000),
    ('N2',   1000000,  3000000),
    ('N3',   3000000,  5000000),
    ('N4',   5000000,     NULL);

-- ---------------------------------------------------------------------------
-- Parámetros de ejecución (una sola fila)
-- ---------------------------------------------------------------------------
CREATE TABLE parametros (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    fecha_base  TEXT    NOT NULL CHECK (fecha_base = date(fecha_base)),
    n           INTEGER NOT NULL CHECK (n >= 1)
);

INSERT INTO parametros (id, fecha_base, n) VALUES (1, '2024-12-31', 3);

-- ---------------------------------------------------------------------------
-- Bitácora de calidad
-- ---------------------------------------------------------------------------
CREATE TABLE calidad_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tabla           TEXT NOT NULL,
    regla           TEXT NOT NULL,
    accion          TEXT NOT NULL,       -- DESCARTADO | CORREGIDO | ALERTA
    identificacion  TEXT,
    detalle         TEXT,
    registrado_en   TEXT NOT NULL DEFAULT (datetime('now'))
);
