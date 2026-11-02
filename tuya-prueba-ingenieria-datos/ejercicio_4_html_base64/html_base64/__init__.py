"""Procesamiento de archivos HTML: embebe imágenes <img> como data URI base64.

Uso programático:
    from html_base64 import build_processor
    report = build_processor(["sitio/"]).process(["sitio/"])
    report.to_dict()  # {"success": {...}, "fail": {...}, "outputs": {...}}
"""

from .models import ProcessingReport
from .processor import HtmlImageProcessor, build_processor

__all__ = ["HtmlImageProcessor", "ProcessingReport", "build_processor"]
__version__ = "1.0.0"
