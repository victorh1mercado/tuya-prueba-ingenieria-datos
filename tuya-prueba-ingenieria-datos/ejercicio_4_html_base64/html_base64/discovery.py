"""Descubrimiento de archivos HTML a partir de archivos y/o directorios."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path


class HtmlFileCollector:
    """Expande una lista de rutas (archivos o directorios, recursivo) en archivos HTML únicos."""

    def __init__(
        self,
        extensions: Iterable[str] = (".html", ".htm"),
        exclude_suffix: str | None = None,
        exclude_dirs: Iterable[Path] = (),
    ) -> None:
        self._extensions = {e.lower() for e in extensions}
        self._exclude_suffix = exclude_suffix
        self._exclude_dirs = [Path(d).resolve() for d in exclude_dirs]

    def collect(self, paths: Iterable[str | Path]) -> tuple[list[Path], list[tuple[Path, str]]]:
        """Devuelve (archivos_html, rutas_invalidas[(ruta, motivo)])."""
        found: dict[Path, None] = {}
        invalid: list[tuple[Path, str]] = []
        for raw in paths:
            path = Path(raw).expanduser()
            if path.is_dir():
                for html in self._walk(path):
                    found.setdefault(html.resolve(), None)
            elif path.is_file():
                if self._is_html(path):
                    found.setdefault(path.resolve(), None)
                else:
                    invalid.append((path, "no es un archivo HTML"))
            else:
                invalid.append((path, "la ruta no existe"))
        return list(found), invalid

    def _walk(self, directory: Path) -> Iterator[Path]:
        for candidate in sorted(directory.rglob("*")):
            if candidate.is_file() and self._is_html(candidate) and not self._is_generated(candidate):
                yield candidate

    def _is_html(self, path: Path) -> bool:
        return path.suffix.lower() in self._extensions

    def _is_generated(self, path: Path) -> bool:
        """Evita reprocesar archivos generados en ejecuciones anteriores."""
        if self._exclude_suffix and path.stem.endswith(self._exclude_suffix):
            return True
        resolved = path.resolve()
        return any(resolved.is_relative_to(d) for d in self._exclude_dirs)
