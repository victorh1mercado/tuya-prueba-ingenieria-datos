-- =============================================================================
-- 03_rachas.sql
-- Racha seleccionada por cliente, "parado" en parametros.fecha_base y
-- filtrando rachas con longitud >= parametros.n.
--
-- Para cambiar los parámetros:
--   UPDATE parametros SET fecha_base = '2024-06-15', n = 4 WHERE id = 1;
--
-- Supuestos
--   * Solo se usa información con corte_mes <= fecha_base.
--   * El último mes evaluable es el menor entre: el último fin de mes <= fecha_base
--     y el último corte cargado en la base (no se inventan meses sin reporte global).
--   * Un cliente existe desde su primer corte <= fecha_base; los meses faltantes
--     posteriores se imputan con saldo 0 (N0).
--   * Si el cliente tiene retiro, se excluyen los cortes con corte_mes > fecha_retiro
--     (tanto imputados como reportados).
--   * Desempate: racha más larga y, después, la de fecha_fin más reciente.
-- =============================================================================

WITH RECURSIVE
params AS (
    SELECT fecha_base, n
    FROM parametros
    WHERE id = 1
),

historia_vigente AS (
    SELECT h.identificacion, h.corte_mes, h.saldo
    FROM historia AS h
    CROSS JOIN params AS p
    WHERE h.corte_mes <= p.fecha_base
),

limites AS (
    SELECT
        MIN(hv.corte_mes) AS primer_corte,
        MIN(
            MAX(hv.corte_mes),
            date(p.fecha_base, '+1 day', 'start of month', '-1 day')
        )                 AS ultimo_corte
    FROM historia_vigente AS hv
    CROSS JOIN params AS p
),

calendario (corte_mes) AS (
    SELECT primer_corte
    FROM limites
    WHERE primer_corte IS NOT NULL
    UNION ALL
    SELECT date(c.corte_mes, '+1 day', '+1 month', '-1 day')
    FROM calendario AS c
    CROSS JOIN limites AS l
    WHERE c.corte_mes < l.ultimo_corte
),

clientes AS (
    SELECT
        hv.identificacion,
        MIN(hv.corte_mes) AS primer_corte,
        r.fecha_retiro
    FROM historia_vigente AS hv
    LEFT JOIN retiros AS r
           ON r.identificacion = hv.identificacion
    GROUP BY hv.identificacion, r.fecha_retiro
),

-- Grilla continua cliente x mes, con imputación de N0 y corte por retiro
saldos_mes AS (
    SELECT
        cl.identificacion,
        ca.corte_mes,
        COALESCE(hv.saldo, 0) AS saldo
    FROM clientes AS cl
    JOIN calendario AS ca
      ON ca.corte_mes >= cl.primer_corte
     AND (cl.fecha_retiro IS NULL OR ca.corte_mes <= cl.fecha_retiro)
    LEFT JOIN historia_vigente AS hv
           ON hv.identificacion = cl.identificacion
          AND hv.corte_mes      = ca.corte_mes
),

niveles AS (
    SELECT
        s.identificacion,
        s.corte_mes,
        d.nivel,
        CAST(strftime('%Y', s.corte_mes) AS INTEGER) * 12
            + CAST(strftime('%m', s.corte_mes) AS INTEGER) AS mes_idx
    FROM saldos_mes AS s
    JOIN dim_nivel AS d
      ON s.saldo >= d.saldo_min
     AND (d.saldo_max IS NULL OR s.saldo < d.saldo_max)
),

-- Gaps & islands: meses consecutivos en el mismo nivel comparten grupo
islas AS (
    SELECT
        identificacion,
        corte_mes,
        nivel,
        mes_idx - ROW_NUMBER() OVER (
            PARTITION BY identificacion, nivel
            ORDER BY corte_mes
        ) AS grupo
    FROM niveles
),

rachas AS (
    SELECT
        identificacion,
        nivel,
        COUNT(*)       AS racha,
        MIN(corte_mes) AS fecha_inicio,
        MAX(corte_mes) AS fecha_fin
    FROM islas
    GROUP BY identificacion, nivel, grupo
),

rachas_ranking AS (
    SELECT
        r.*,
        ROW_NUMBER() OVER (
            PARTITION BY r.identificacion
            ORDER BY r.racha DESC, r.fecha_fin DESC
        ) AS orden
    FROM rachas AS r
    CROSS JOIN params AS p
    WHERE r.racha >= p.n
)

SELECT
    identificacion,
    racha,
    fecha_fin,
    nivel
FROM rachas_ranking
WHERE orden = 1
ORDER BY identificacion;
