"""Interfaz de línea de comandos.

Ejemplos:
    python -m html_base64 examples/sitio
    python -m html_base64 a.html b.html --suffix _embebido
    python -m html_base64 sitio1 sitio2 --output-dir salida --report reporte.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .processor import DEFAULT_SUFFIX, build_processor


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="html_base64",
        description="Embebe en base64 las imágenes <img> de archivos HTML, generando archivos nuevos.",
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("paths", nargs="+", help="Archivos HTML y/o directorios (se recorren subdirectorios)")
    destino = parser.add_mutually_exclusive_group()
    destino.add_argument("--suffix", default=DEFAULT_SUFFIX, help=f"Sufijo del archivo nuevo (default: {DEFAULT_SUFFIX})")
    destino.add_argument("--output-dir", type=Path, help="Carpeta de salida que replica la estructura de entrada")
    parser.add_argument("--allow-remote", action="store_true", help="Descargar imágenes http(s)")
    parser.add_argument("--max-bytes", type=int, default=None, help="Tamaño máximo por imagen")
    parser.add_argument("--report", type=Path, help="Guardar el reporte JSON en este archivo")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s")

    processor = build_processor(
        args.paths,
        output_dir=args.output_dir,
        suffix=args.suffix,
        allow_remote=args.allow_remote,
        max_bytes=args.max_bytes,
    )
    report = processor.process(args.paths)
    payload = json.dumps(report.to_dict(), indent=2, ensure_ascii=False)

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
    print(payload)
    print(f"\nImágenes exitosas: {report.total_success} | fallidas: {report.total_fail}", file=sys.stderr)
    return 0 if report.total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
