"""Modelos de datos del procesamiento."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ImgTag:
    """Etiqueta <img> localizada dentro del texto HTML."""

    start: int
    end: int
    raw: str
    src: str | None


@dataclass(frozen=True)
class LoadedImage:
    content: bytes
    mime_type: str


class ImageProcessingError(Exception):
    """Error controlado al cargar o codificar una imagen."""


@dataclass
class ProcessingReport:
    """Resultado agregado: imágenes exitosas y fallidas por archivo HTML."""

    success: dict[str, list[dict]] = field(default_factory=dict)
    fail: dict[str, list[dict]] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)

    def add_success(self, html: Path, src: str, mime_type: str, size: int) -> None:
        self.success.setdefault(str(html), []).append(
            {"src": src, "mime_type": mime_type, "size_bytes": size}
        )

    def add_fail(self, html: Path, src: str | None, error: str) -> None:
        self.fail.setdefault(str(html), []).append({"src": src, "error": error})

    def add_output(self, html: Path, output: Path) -> None:
        self.outputs[str(html)] = str(output)

    @property
    def total_success(self) -> int:
        return sum(len(v) for v in self.success.values())

    @property
    def total_fail(self) -> int:
        return sum(len(v) for v in self.fail.values())

    def to_dict(self, include_outputs: bool = True) -> dict:
        data = {"success": self.success, "fail": self.fail}
        if include_outputs:
            data["outputs"] = self.outputs
        return data
