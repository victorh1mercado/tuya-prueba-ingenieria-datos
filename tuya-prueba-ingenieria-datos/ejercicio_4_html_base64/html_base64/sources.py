"""Fuentes de imágenes (local, file://, http/https, data URI).

Cada fuente implementa ImageSource; ImageLoader las recorre en orden
(abierto a extensión, cerrado a modificación).
"""

from __future__ import annotations

import base64
import mimetypes
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path

from .models import ImageProcessingError, LoadedImage

_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"BM", "image/bmp"),
    (b"\x00\x00\x01\x00", "image/x-icon"),
)
_VERIFIABLE_TYPES = {m for _, m in _SIGNATURES} | {
    "image/webp", "image/svg+xml", "image/vnd.microsoft.icon"}


def detect_mime_type(content: bytes, name_hint: str = "") -> str:
    """Detecta el tipo MIME por firma binaria; usa la extensión como respaldo."""
    for signature, mime in _SIGNATURES:
        if content.startswith(signature):
            return mime
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    head = content[:512].lstrip().lower()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in head):
        return "image/svg+xml"
    guessed, _ = mimetypes.guess_type(name_hint)
    if guessed in _VERIFIABLE_TYPES:
        raise ImageProcessingError(f"el contenido no coincide con el formato {guessed}")
    if guessed and guessed.startswith("image/"):
        return guessed  # formatos sin firma verificada aquí (tiff, avif, ...)
    raise ImageProcessingError("el contenido no corresponde a una imagen reconocida")


class ImageSource(ABC):
    @abstractmethod
    def can_handle(self, src: str) -> bool: ...

    @abstractmethod
    def load(self, src: str, base_dir: Path) -> LoadedImage: ...


class DataUriSource(ImageSource):
    """Imágenes ya embebidas: se validan y se dejan como están."""

    def can_handle(self, src: str) -> bool:
        return src.lower().startswith("data:")

    def load(self, src: str, base_dir: Path) -> LoadedImage:
        header, _, payload = src.partition(",")
        if ";base64" not in header.lower():
            raise ImageProcessingError("data URI sin codificación base64")
        try:
            content = base64.b64decode(payload, validate=True)
        except ValueError as exc:
            raise ImageProcessingError(f"data URI con base64 inválido: {exc}") from exc
        mime = header[5:].split(";")[0] or detect_mime_type(content)
        return LoadedImage(content, mime)


class LocalFileSource(ImageSource):
    """Rutas relativas al HTML, absolutas o con esquema file://."""

    def __init__(self, max_bytes: int | None = None) -> None:
        self._max_bytes = max_bytes

    def can_handle(self, src: str) -> bool:
        if src.startswith("//"):
            return False
        scheme = urllib.parse.urlsplit(src).scheme.lower()
        return scheme in ("", "file") or (len(scheme) == 1 and src[1:3] in (":\\", ":/"))

    def load(self, src: str, base_dir: Path) -> LoadedImage:
        path = self._resolve(src, base_dir)
        if not path.is_file():
            raise ImageProcessingError(f"archivo no encontrado: {path}")
        if self._max_bytes is not None and path.stat().st_size > self._max_bytes:
            raise ImageProcessingError(f"la imagen supera el tamaño máximo ({self._max_bytes} bytes)")
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise ImageProcessingError(f"no se pudo leer {path}: {exc}") from exc
        if not content:
            raise ImageProcessingError(f"archivo vacío: {path}")
        return LoadedImage(content, detect_mime_type(content, path.name))

    @staticmethod
    def _resolve(src: str, base_dir: Path) -> Path:
        parts = urllib.parse.urlsplit(src)
        if parts.scheme.lower() == "file":
            return Path(urllib.request.url2pathname(parts.path))
        if len(parts.scheme) == 1:  # ruta Windows tipo C:\...
            return Path(src)
        relative = urllib.parse.unquote(parts.path)
        path = Path(relative)
        return path if path.is_absolute() else (base_dir / path).resolve()


class HttpSource(ImageSource):
    """Descarga imágenes remotas (opcional, deshabilitado por defecto en la CLI)."""

    def __init__(self, timeout: float = 10.0, max_bytes: int | None = 10 * 1024 * 1024) -> None:
        self._timeout = timeout
        self._max_bytes = max_bytes

    def can_handle(self, src: str) -> bool:
        return urllib.parse.urlsplit(src).scheme.lower() in ("http", "https") or src.startswith("//")

    def load(self, src: str, base_dir: Path) -> LoadedImage:
        url = f"https:{src}" if src.startswith("//") else src
        request = urllib.request.Request(url, headers={"User-Agent": "html-base64/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                limit = None if self._max_bytes is None else self._max_bytes + 1
                content = response.read(limit) if limit else response.read()
                header_mime = response.headers.get_content_type()
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise ImageProcessingError(f"no se pudo descargar {url}: {exc}") from exc
        if self._max_bytes is not None and len(content) > self._max_bytes:
            raise ImageProcessingError(f"la imagen supera el tamaño máximo ({self._max_bytes} bytes)")
        try:
            mime = detect_mime_type(content, urllib.parse.urlsplit(url).path)
        except ImageProcessingError:
            if header_mime.startswith("image/"):
                mime = header_mime
            else:
                raise
        return LoadedImage(content, mime)


class ImageLoader:
    """Selecciona la primera fuente capaz de atender el src y cachea resultados."""

    def __init__(self, sources: list[ImageSource]) -> None:
        self._sources = sources
        self._cache: dict[tuple[str, Path], LoadedImage] = {}

    def load(self, src: str, base_dir: Path) -> LoadedImage:
        key = (src, base_dir)
        if key not in self._cache:
            source = next((s for s in self._sources if s.can_handle(src)), None)
            if source is None:
                raise ImageProcessingError(f"esquema no soportado o deshabilitado: {src[:60]}")
            self._cache[key] = source.load(src, base_dir)
        return self._cache[key]
