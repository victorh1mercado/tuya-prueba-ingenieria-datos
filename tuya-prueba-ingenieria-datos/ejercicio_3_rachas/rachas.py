"""Construye la base SQLite desde rachas.xlsx y ejecuta la consulta de rachas.

Uso:
    python rachas.py --fecha-base 2024-12-31 --n 3
    python rachas.py --fecha-base 2024-06-15 --n 4 --salida output/rachas_2024-06.csv
    python rachas.py --solo-consulta --fecha-base 2023-12-31 --n 2   # reutiliza la BD
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook

BASE_DIR = Path(__file__).resolve().parent
SQL_DIR = BASE_DIR / "sql"
DEFAULT_EXCEL = BASE_DIR / "data" / "rachas.xlsx"
DEFAULT_DB = BASE_DIR / "output" / "rachas.db"

HOJAS = {
    "historia": ("stg_historia", ["identificacion", "corte_mes", "saldo"]),
    "retiros": ("stg_retiros", ["identificacion", "fecha_retiro"]),
}


def _a_texto_fecha(valor):
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    return None if valor is None else str(valor).strip()


def leer_hoja(ruta_excel: Path, hoja: str, columnas: list[str]) -> list[tuple]:
    libro = load_workbook(ruta_excel, read_only=True, data_only=True)
    try:
        filas = libro[hoja].iter_rows(values_only=True)
        encabezado = [str(c).strip().lower() if c is not None else "" for c in next(filas)]
        faltantes = [c for c in columnas if c not in encabezado]
        if faltantes:
            raise ValueError(f"Hoja '{hoja}' sin columnas requeridas: {faltantes}")
        indices = [encabezado.index(c) for c in columnas]
        registros = []
        for numero, fila in enumerate(filas, start=2):
            if fila is None or all(v is None for v in fila):
                continue
            valores = [fila[i] if i < len(fila) else None for i in indices]
            valores = [
                _a_texto_fecha(v) if col in ("corte_mes", "fecha_retiro") else v
                for col, v in zip(columnas, valores)
            ]
            registros.append((numero, *valores))
        return registros
    finally:
        libro.close()


def ejecutar_script(conexion: sqlite3.Connection, nombre: str) -> None:
    conexion.executescript((SQL_DIR / nombre).read_text(encoding="utf-8"))


def construir_base(conexion: sqlite3.Connection, ruta_excel: Path) -> None:
    ejecutar_script(conexion, "01_esquema.sql")
    for hoja, (tabla, columnas) in HOJAS.items():
        registros = leer_hoja(ruta_excel, hoja, columnas)
        marcadores = ", ".join("?" * (len(columnas) + 1))
        conexion.executemany(
            f"INSERT INTO {tabla} (fila_origen, {', '.join(columnas)}) VALUES ({marcadores})",
            registros,
        )
    ejecutar_script(conexion, "02_calidad_y_carga.sql")
    conexion.commit()


def fijar_parametros(conexion: sqlite3.Connection, fecha_base: str, n: int) -> None:
    conexion.execute(
        "UPDATE parametros SET fecha_base = ?, n = ? WHERE id = 1", (fecha_base, n)
    )
    conexion.commit()


def consultar_rachas(conexion: sqlite3.Connection) -> tuple[list[str], list[tuple]]:
    cursor = conexion.execute((SQL_DIR / "03_rachas.sql").read_text(encoding="utf-8"))
    return [d[0] for d in cursor.description], cursor.fetchall()


def resumen_calidad(conexion: sqlite3.Connection) -> list[tuple]:
    return conexion.execute(
        """
        SELECT regla, accion, COUNT(*) AS casos
        FROM calidad_log
        GROUP BY regla, accion
        ORDER BY regla
        """
    ).fetchall()


def _fecha_valida(texto: str) -> str:
    try:
        return date.fromisoformat(texto).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("fecha_base debe tener formato YYYY-MM-DD") from exc


def _entero_positivo(texto: str) -> int:
    valor = int(texto)
    if valor < 1:
        raise argparse.ArgumentTypeError("n debe ser >= 1")
    return valor


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--excel", type=Path, default=DEFAULT_EXCEL)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--fecha-base", type=_fecha_valida, required=True)
    parser.add_argument("--n", type=_entero_positivo, required=True)
    parser.add_argument("--salida", type=Path, help="CSV de salida (opcional)")
    parser.add_argument("--solo-consulta", action="store_true", help="No reconstruye la base")
    args = parser.parse_args(argv)

    args.db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(args.db) as conexion:
        if not args.solo_consulta:
            construir_base(conexion, args.excel)
            print("Hallazgos de calidad:")
            for regla, accion, casos in resumen_calidad(conexion):
                print(f"  {regla:<40} {accion:<11} {casos}")

        fijar_parametros(conexion, args.fecha_base, args.n)
        columnas, filas = consultar_rachas(conexion)

    print(f"\nfecha_base={args.fecha_base}  n={args.n}  clientes={len(filas)}")
    print(" | ".join(columnas))
    for fila in filas[:15]:
        print(" | ".join(str(v) for v in fila))
    if len(filas) > 15:
        print(f"... ({len(filas) - 15} filas más)")

    if args.salida:
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        with args.salida.open("w", newline="", encoding="utf-8") as archivo:
            escritor = csv.writer(archivo)
            escritor.writerow(columnas)
            escritor.writerows(filas)
        print(f"\nResultado guardado en {args.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
