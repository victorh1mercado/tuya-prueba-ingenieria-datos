"""Orquestación: recorre los HTML, codifica sus imágenes y escribe archivos nuevos."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path

from .discovery import HtmlFileCollector
from .html_rewriter import Base64Encoder, ImgSrcRewriter, ImgTagLocator
from .models import ImageProcessingError, ProcessingReport
from .sources import DataUriSource, HttpSource, ImageLoader, LocalFileSource

logger = logging.getLogger(__name__)

DEFAULT_SUFFIX = "_base64"


# -----------------------------------------------------------------------------
# Estrategias de nombre de salida (nunca se sobrescribe el original)
# -----------------------------------------------------------------------------
class OutputPathStrategy(ABC):
    @abstractmethod
    def output_for(self, html_file: Path) -> Path: ...


class SuffixOutputStrategy(OutputPathStrategy):
    """pagina.html -> pagina_base64.html en la misma carpeta."""

    def __init__(self, suffix: str = DEFAULT_SUFFIX) -> None:
        if not suffix:
            raise ValueError("el sufijo no puede ser vacío: se sobrescribiría el original")
        self.suffix = suffix

    def output_for(self, html_file: Path) -> Path:
        return html_file.with_name(f"{html_file.stem}{self.suffix}{html_file.suffix}")


class MirrorDirOutputStrategy(OutputPathStrategy):
    """Replica la estructura relativa a `root` dentro de `output_dir`."""

    def __init__(self, output_dir: Path, roots: Iterable[Path]) -> None:
        self.output_dir = output_dir.resolve()
        self.roots = sorted({r.resolve() for r in roots}, key=lambda p: len(p.parts), reverse=True)

    def output_for(self, html_file: Path) -> Path:
        for root in self.roots:
            base = root if root.is_dir() else root.parent
            if html_file.is_relative_to(base):
                return self.output_dir / base.name / html_file.relative_to(base)
        return self.output_dir / html_file.name


# -----------------------------------------------------------------------------
# Procesador
# -----------------------------------------------------------------------------
class HtmlImageProcessor:
    def __init__(
        self,
        loader: ImageLoader,
        output_strategy: OutputPathStrategy,
        collector: HtmlFileCollector | None = None,
        locator: ImgTagLocator | None = None,
        encoder: Base64Encoder | None = None,
        rewriter: ImgSrcRewriter | None = None,
        encoding: str = "utf-8",
    ) -> None:
        self._loader = loader
        self._output = output_strategy
        self._collector = collector or HtmlFileCollector()
        self._locator = locator or ImgTagLocator()
        self._encoder = encoder or Base64Encoder()
        self._rewriter = rewriter or ImgSrcRewriter()
        self._encoding = encoding

    def process(self, paths: Iterable[str | Path]) -> ProcessingReport:
        report = ProcessingReport()
        html_files, invalid = self._collector.collect(paths)
        for path, reason in invalid:
            report.add_fail(path, None, reason)
        for html_file in html_files:
            self._process_file(html_file, report)
        return report

    def _process_file(self, html_file: Path, report: ProcessingReport) -> None:
        output = self._output.output_for(html_file)
        if output.resolve() == html_file.resolve():
            report.add_fail(html_file, None, "la ruta de salida coincide con el original")
            return
        try:
            # surrogateescape conserva bytes no UTF-8 al reescribir el archivo
            document = html_file.read_text(encoding=self._encoding, errors="surrogateescape")
        except OSError as exc:
            report.add_fail(html_file, None, f"no se pudo leer el HTML: {exc}")
            return

        replacements = []
        for tag in self._locator.find(document):
            if not tag.src:
                report.add_fail(html_file, tag.src, "etiqueta <img> sin atributo src")
                continue
            try:
                image = self._loader.load(tag.src, html_file.parent)
            except ImageProcessingError as exc:
                report.add_fail(html_file, tag.src, str(exc))
                continue
            if not tag.src.lower().startswith("data:"):
                new_raw = self._rewriter.replace_src(tag.raw, self._encoder.to_data_uri(image))
                replacements.append((tag, new_raw))
            report.add_success(html_file, tag.src, image.mime_type, len(image.content))

        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                self._rewriter.apply(document, replacements),
                encoding=self._encoding,
                errors="surrogateescape",
                newline="",
            )
        except OSError as exc:
            report.add_fail(html_file, None, f"no se pudo escribir la salida: {exc}")
            return
        report.add_output(html_file, output)
        logger.info("%s -> %s (%d imágenes)", html_file, output, len(replacements))


def build_processor(
    paths: Iterable[str | Path],
    output_dir: Path | None = None,
    suffix: str = DEFAULT_SUFFIX,
    allow_remote: bool = False,
    max_bytes: int | None = None,
) -> HtmlImageProcessor:
    """Fábrica con la configuración por defecto."""
    sources = [DataUriSource()]
    if allow_remote:
        sources.append(HttpSource(max_bytes=max_bytes))
    sources.append(LocalFileSource(max_bytes=max_bytes))
    strategy = (
        MirrorDirOutputStrategy(output_dir, [Path(p) for p in paths])
        if output_dir
        else SuffixOutputStrategy(suffix)
    )
    return HtmlImageProcessor(
        loader=ImageLoader(sources),
        output_strategy=strategy,
        collector=HtmlFileCollector(
            exclude_suffix=None if output_dir else suffix,
            exclude_dirs=[output_dir] if output_dir else (),
        ),
    )
