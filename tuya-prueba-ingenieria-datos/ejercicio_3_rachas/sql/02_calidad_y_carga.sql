-- =============================================================================
-- 02_calidad_y_carga.sql
-- Depura stg_historia / stg_retiros, registra hallazgos en calidad_log y
-- carga las tablas historia y retiros.
--
-- Reglas aplicadas
--   H1  identificacion / corte_mes / saldo nulos o vacíos        -> DESCARTADO
--   H2  corte_mes no es una fecha válida                         -> DESCARTADO
--   H3  saldo negativo o no numérico                             -> DESCARTADO
--   H4  identificacion con espacios o minúsculas                  -> CORREGIDO
--   H5  corte_mes que no es fin de mes                           -> CORREGIDO (se lleva a fin de mes)
--   H6  filas duplicadas exactas                                 -> DESCARTADO (se deja una)
--   H7  misma llave (cliente, corte) con saldos distintos        -> ALERTA (se conserva el saldo mayor:
--                                                                  criterio conservador de riesgo)
--   R1  retiro con identificacion o fecha inválida               -> DESCARTADO
--   R2  cliente con más de una fecha de retiro                   -> ALERTA (se conserva la más antigua)
--   R3  retiro de un cliente inexistente en historia             -> ALERTA
--   R3b retiro sin historia con identificacion casi igual a una existente -> ALERTA
--   R4  longitud de identificacion distinta a la predominante    -> ALERTA
--   R5  saldos reportados con corte posterior a la fecha retiro  -> ALERTA (la consulta los excluye)
-- =============================================================================

DELETE FROM calidad_log;
DELETE FROM historia;
DELETE FROM retiros;

-- -----------------------------------------------------------------------------
-- Vista normalizada de historia
-- -----------------------------------------------------------------------------
DROP VIEW IF EXISTS v_stg_historia_norm;
CREATE VIEW v_stg_historia_norm AS
SELECT
    s.fila_origen,
    s.identificacion                                         AS identificacion_raw,
    UPPER(TRIM(s.identificacion))                            AS identificacion,
    s.corte_mes                                              AS corte_mes_raw,
    date(s.corte_mes, 'start of month', '+1 month', '-1 day') AS corte_mes,
    s.saldo                                                  AS saldo_raw,
    CASE
        WHEN typeof(s.saldo) IN ('integer', 'real') THEN CAST(ROUND(s.saldo) AS INTEGER)
    END                                                      AS saldo
FROM stg_historia AS s;

-- H1 / H2 / H3 ----------------------------------------------------------------
INSERT INTO calidad_log (tabla, regla, accion, identificacion, detalle)
SELECT
    'historia',
    CASE
        WHEN identificacion IS NULL OR identificacion = '' THEN 'H1_identificacion_nula'
        WHEN corte_mes_raw IS NULL                         THEN 'H1_corte_nulo'
        WHEN corte_mes IS NULL                             THEN 'H2_corte_invalido'
        WHEN saldo_raw IS NULL                             THEN 'H1_saldo_nulo'
        ELSE                                                    'H3_saldo_invalido'
    END,
    'DESCARTADO',
    identificacion,
    'fila=' || fila_origen || ' corte=' || IFNULL(corte_mes_raw, 'NULL')
        || ' saldo=' || IFNULL(saldo_raw, 'NULL')
FROM v_stg_historia_norm
WHERE identificacion IS NULL OR identificacion = ''
   OR corte_mes IS NULL
   OR saldo IS NULL OR saldo < 0;

-- H4 ----------------------------------------------------------------------------
INSERT INTO calidad_log (tabla, regla, accion, identificacion, detalle)
SELECT 'historia', 'H4_identificacion_normalizada', 'CORREGIDO', identificacion,
       'fila=' || fila_origen || ' original="' || identificacion_raw || '"'
FROM v_stg_historia_norm
WHERE identificacion_raw <> identificacion;

-- H5 ----------------------------------------------------------------------------
INSERT INTO calidad_log (tabla, regla, accion, identificacion, detalle)
SELECT 'historia', 'H5_corte_no_fin_de_mes', 'CORREGIDO', identificacion,
       'fila=' || fila_origen || ' ' || corte_mes_raw || ' -> ' || corte_mes
FROM v_stg_historia_norm
WHERE corte_mes IS NOT NULL
  AND date(corte_mes_raw) <> corte_mes;

-- Registros válidos -------------------------------------------------------------
DROP TABLE IF EXISTS tmp_historia_valida;
CREATE TEMP TABLE tmp_historia_valida AS
SELECT fila_origen, identificacion, corte_mes, saldo
FROM v_stg_historia_norm
WHERE identificacion IS NOT NULL AND identificacion <> ''
  AND corte_mes IS NOT NULL
  AND saldo IS NOT NULL AND saldo >= 0;

-- H6 ----------------------------------------------------------------------------
INSERT INTO calidad_log (tabla, regla, accion, identificacion, detalle)
SELECT 'historia', 'H6_duplicado_exacto', 'DESCARTADO', identificacion,
       'corte=' || corte_mes || ' saldo=' || saldo || ' filas=' || filas
FROM (
    SELECT identificacion, corte_mes, saldo,
           COUNT(*)                  AS n_filas,
           GROUP_CONCAT(fila_origen) AS filas
    FROM tmp_historia_valida
    GROUP BY identificacion, corte_mes, saldo
    HAVING COUNT(*) > 1
);

-- H7 ----------------------------------------------------------------------------
INSERT INTO calidad_log (tabla, regla, accion, identificacion, detalle)
SELECT 'historia', 'H7_llave_con_saldos_distintos', 'ALERTA', identificacion,
       'corte=' || corte_mes || ' saldos=' || saldos || ' se conserva=' || saldo_max
FROM (
    SELECT identificacion, corte_mes,
           GROUP_CONCAT(DISTINCT saldo) AS saldos,
           MAX(saldo)                   AS saldo_max
    FROM tmp_historia_valida
    GROUP BY identificacion, corte_mes
    HAVING COUNT(DISTINCT saldo) > 1
);

-- Carga historia ------------------------------------------------------------------
INSERT INTO historia (identificacion, corte_mes, saldo)
SELECT identificacion, corte_mes, MAX(saldo)
FROM tmp_historia_valida
GROUP BY identificacion, corte_mes;

-- -----------------------------------------------------------------------------
-- Retiros
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS tmp_retiros_norm;
CREATE TEMP TABLE tmp_retiros_norm AS
SELECT fila_origen,
       identificacion                 AS identificacion_raw,
       UPPER(TRIM(identificacion))    AS identificacion,
       fecha_retiro                   AS fecha_retiro_raw,
       date(fecha_retiro)             AS fecha_retiro
FROM stg_retiros;

-- R1 ----------------------------------------------------------------------------
INSERT INTO calidad_log (tabla, regla, accion, identificacion, detalle)
SELECT 'retiros', 'R1_registro_invalido', 'DESCARTADO', identificacion,
       'fila=' || fila_origen || ' fecha=' || IFNULL(fecha_retiro_raw, 'NULL')
FROM tmp_retiros_norm
WHERE identificacion IS NULL OR identificacion = '' OR fecha_retiro IS NULL;

-- R2 ----------------------------------------------------------------------------
INSERT INTO calidad_log (tabla, regla, accion, identificacion, detalle)
SELECT 'retiros', 'R2_multiples_fechas_retiro', 'ALERTA', identificacion,
       'fechas=' || GROUP_CONCAT(DISTINCT fecha_retiro) || ' se conserva=' || MIN(fecha_retiro)
FROM tmp_retiros_norm
WHERE fecha_retiro IS NOT NULL AND identificacion <> ''
GROUP BY identificacion
HAVING COUNT(DISTINCT fecha_retiro) > 1;

-- Carga retiros -----------------------------------------------------------------
INSERT INTO retiros (identificacion, fecha_retiro)
SELECT identificacion, MIN(fecha_retiro)
FROM tmp_retiros_norm
WHERE identificacion IS NOT NULL AND identificacion <> '' AND fecha_retiro IS NOT NULL
GROUP BY identificacion;

-- R3 ----------------------------------------------------------------------------
INSERT INTO calidad_log (tabla, regla, accion, identificacion, detalle)
SELECT 'retiros', 'R3_cliente_sin_historia', 'ALERTA', r.identificacion,
       'fecha_retiro=' || r.fecha_retiro || ' (sin efecto en la consulta)'
FROM retiros AS r
WHERE NOT EXISTS (SELECT 1 FROM historia AS h WHERE h.identificacion = r.identificacion);

-- R3b: sugerencia de identificación equivalente (mismo prefijo de 12 y sufijo de 3)
INSERT INTO calidad_log (tabla, regla, accion, identificacion, detalle)
SELECT 'retiros', 'R3b_posible_identificacion_equivalente', 'ALERTA', r.identificacion,
       'candidato=' || h.identificacion || ' (no se corrige automáticamente; requiere validación)'
FROM retiros AS r
JOIN (SELECT DISTINCT identificacion FROM historia) AS h
  ON substr(h.identificacion, 1, 12) = substr(r.identificacion, 1, 12)
 AND substr(h.identificacion, -3)    = substr(r.identificacion, -3)
 AND h.identificacion <> r.identificacion
WHERE NOT EXISTS (SELECT 1 FROM historia AS x WHERE x.identificacion = r.identificacion);

-- R4 ----------------------------------------------------------------------------
INSERT INTO calidad_log (tabla, regla, accion, identificacion, detalle)
SELECT 'retiros', 'R4_longitud_identificacion_atipica', 'ALERTA', r.identificacion,
       'longitud=' || LENGTH(r.identificacion) || ' esperada=' || m.longitud
FROM retiros AS r
CROSS JOIN (
    SELECT LENGTH(identificacion) AS longitud
    FROM historia
    GROUP BY LENGTH(identificacion)
    ORDER BY COUNT(*) DESC
    LIMIT 1
) AS m
WHERE LENGTH(r.identificacion) <> m.longitud;

-- R5 ----------------------------------------------------------------------------
INSERT INTO calidad_log (tabla, regla, accion, identificacion, detalle)
SELECT 'historia', 'R5_saldo_posterior_a_retiro', 'ALERTA', h.identificacion,
       'fecha_retiro=' || r.fecha_retiro || ' cortes_posteriores=' || COUNT(*)
           || ' (' || MIN(h.corte_mes) || ' a ' || MAX(h.corte_mes) || ')'
FROM historia AS h
JOIN retiros  AS r ON r.identificacion = h.identificacion
WHERE h.corte_mes > r.fecha_retiro
GROUP BY h.identificacion, r.fecha_retiro;

DROP VIEW IF EXISTS v_stg_historia_norm;
