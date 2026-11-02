"""Pruebas de la consulta de rachas.

1. Casos sintéticos con resultado esperado conocido.
2. Contraste de la consulta SQL contra una implementación de referencia
   en Python puro sobre los datos reales, para varias fechas base y valores de n.

Ejecutar:  python -m unittest discover -s tests -v   (desde ejercicio_3_rachas)
"""

import calendar
import sqlite3
import sys
import unittest
from collections import defaultdict
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

import rachas  # noqa: E402

NIVELES = [("N0", 0, 300_000), ("N1", 300_000, 1_000_000), ("N2", 1_000_000, 3_000_000),
           ("N3", 3_000_000, 5_000_000), ("N4", 5_000_000, None)]


def fin_de_mes(anio, mes):
    return date(anio, mes, calendar.monthrange(anio, mes)[1])


def siguiente_fin_de_mes(d):
    anio, mes = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return fin_de_mes(anio, mes)


def nivel_de(saldo):
    for nombre, minimo, maximo in NIVELES:
        if saldo >= minimo and (maximo is None or saldo < maximo):
            return nombre
    raise ValueError(saldo)


def rachas_referencia(historia, retiros, fecha_base, n):
    """historia: {(id, date): saldo}; retiros: {id: date}. Implementación iterativa."""
    vigente = {k: v for k, v in historia.items() if k[1] <= fecha_base}
    if not vigente:
        return []
    ultimo_fin = fin_de_mes(fecha_base.year, fecha_base.month)
    if ultimo_fin > fecha_base:
        ultimo_fin = date.fromordinal(fecha_base.replace(day=1).toordinal() - 1)
    ultimo = min(max(k[1] for k in vigente), ultimo_fin)

    primeros = defaultdict(lambda: date.max)
    for (cid, corte) in vigente:
        primeros[cid] = min(primeros[cid], corte)

    resultado = []
    for cid, primero in primeros.items():
        mes, mejor, actual = primero, None, None
        while mes <= ultimo:
            if cid in retiros and mes > retiros[cid]:
                break
            nivel = nivel_de(vigente.get((cid, mes), 0))
            if actual and actual[0] == nivel:
                actual = (nivel, actual[1] + 1, mes)
            else:
                actual = (nivel, 1, mes)
            if actual[1] >= n and (mejor is None or actual[1] > mejor[1]
                                   or (actual[1] == mejor[1] and actual[2] > mejor[2])):
                mejor = actual
            mes = siguiente_fin_de_mes(mes)
        if mejor:
            resultado.append((cid, mejor[1], mejor[2].isoformat(), mejor[0]))
    return sorted(resultado)


class BaseSintetica(unittest.TestCase):
    def setUp(self):
        self.cx = sqlite3.connect(":memory:")
        rachas.ejecutar_script(self.cx, "01_esquema.sql")

    def tearDown(self):
        self.cx.close()

    def cargar(self, historia, retiros=()):
        self.cx.executemany(
            "INSERT INTO stg_historia (fila_origen, identificacion, corte_mes, saldo) VALUES (?,?,?,?)",
            [(i, *f) for i, f in enumerate(historia, start=2)])
        self.cx.executemany(
            "INSERT INTO stg_retiros (fila_origen, identificacion, fecha_retiro) VALUES (?,?,?)",
            [(i, *f) for i, f in enumerate(retiros, start=2)])
        rachas.ejecutar_script(self.cx, "02_calidad_y_carga.sql")

    def consultar(self, fecha_base, n):
        rachas.fijar_parametros(self.cx, fecha_base, n)
        return rachas.consultar_rachas(self.cx)[1]


class CasosSinteticos(BaseSintetica):
    def test_mes_faltante_se_imputa_como_n0(self):
        self.cargar([("A", "2024-01-31", 100), ("A", "2024-04-30", 100)])
        self.assertEqual(self.consultar("2024-04-30", 4), [("A", 4, "2024-04-30", "N0")])

    def test_limites_de_nivel_son_semiabiertos(self):
        self.cargar([("A", "2024-01-31", 299_999), ("A", "2024-02-29", 300_000),
                     ("A", "2024-03-31", 999_999), ("A", "2024-04-30", 5_000_000)])
        self.assertEqual(self.consultar("2024-04-30", 2), [("A", 2, "2024-03-31", "N1")])

    def test_desempate_por_racha_mas_larga_y_luego_mas_reciente(self):
        self.cargar([("A", "2024-01-31", 6e6), ("A", "2024-02-29", 6e6),
                     ("A", "2024-03-31", 2e6), ("A", "2024-04-30", 2e6),
                     ("A", "2024-05-31", 6e6)])
        self.assertEqual(self.consultar("2024-05-31", 2), [("A", 2, "2024-04-30", "N2")])
        self.assertEqual(self.consultar("2024-05-31", 1), [("A", 2, "2024-04-30", "N2")])

    def test_retiro_corta_la_grilla_y_los_saldos_reportados(self):
        self.cargar([("A", "2024-01-31", 4e6), ("A", "2024-02-29", 4e6),
                     ("A", "2024-03-31", 4e6), ("A", "2024-04-30", 4e6)],
                    [("A", "2024-03-15")])
        self.assertEqual(self.consultar("2024-04-30", 1), [("A", 2, "2024-02-29", "N3")])

    def test_retiro_posterior_a_fecha_base_no_aplica(self):
        self.cargar([("A", "2024-01-31", 4e6), ("A", "2024-02-29", 4e6)], [("A", "2024-12-01")])
        self.assertEqual(self.consultar("2024-02-29", 2), [("A", 2, "2024-02-29", "N3")])

    def test_fecha_base_a_mitad_de_mes_ignora_corte_futuro(self):
        self.cargar([("A", "2024-01-31", 1e6), ("A", "2024-02-29", 1e6), ("A", "2024-03-31", 1e6)])
        self.assertEqual(self.consultar("2024-03-15", 1), [("A", 2, "2024-02-29", "N2")])

    def test_cliente_que_aparece_despues_de_fecha_base_no_se_reporta(self):
        self.cargar([("A", "2024-01-31", 1e6), ("B", "2024-06-30", 1e6)])
        self.assertEqual([r[0] for r in self.consultar("2024-03-31", 1)], ["A"])

    def test_racha_menor_a_n_no_se_reporta(self):
        self.cargar([("A", "2024-01-31", 1e6), ("A", "2024-02-29", 6e6)])
        self.assertEqual(self.consultar("2024-02-29", 2), [])

    def test_calidad_duplicados_y_normalizacion(self):
        self.cargar([(" a ", "2024-01-15", 100), ("A", "2024-01-31", 100), ("A", "2024-01-31", 900_000),
                     ("B", None, 5), ("C", "2024-01-31", -1)])
        reglas = {r[0] for r in self.cx.execute("SELECT regla FROM calidad_log")}
        self.assertTrue({"H1_corte_nulo", "H3_saldo_invalido", "H4_identificacion_normalizada",
                         "H5_corte_no_fin_de_mes", "H6_duplicado_exacto",
                         "H7_llave_con_saldos_distintos"} <= reglas)
        self.assertEqual(self.cx.execute("SELECT * FROM historia").fetchall(), [("A", "2024-01-31", 900_000)])


class ContraReferencia(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cx = sqlite3.connect(":memory:")
        rachas.construir_base(cls.cx, rachas.DEFAULT_EXCEL)
        cls.historia = {(i, date.fromisoformat(c)): s
                        for i, c, s in cls.cx.execute("SELECT * FROM historia")}
        cls.retiros = {i: date.fromisoformat(f) for i, f in cls.cx.execute("SELECT * FROM retiros")}

    @classmethod
    def tearDownClass(cls):
        cls.cx.close()

    def test_sql_coincide_con_referencia(self):
        fechas = ["2023-01-31", "2023-06-15", "2023-12-31", "2024-03-31",
                  "2024-07-20", "2024-12-31", "2026-10-24"]
        for fecha in fechas:
            for n in (1, 2, 3, 4, 6):
                with self.subTest(fecha_base=fecha, n=n):
                    rachas.fijar_parametros(self.cx, fecha, n)
                    sql = rachas.consultar_rachas(self.cx)[1]
                    ref = rachas_referencia(self.historia, self.retiros, date.fromisoformat(fecha), n)
                    self.assertEqual(sql, ref)


if __name__ == "__main__":
    unittest.main()
