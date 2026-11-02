"""Localización de etiquetas <img> y reemplazo del atributo src.

Se usa html.parser para ubicar las etiquetas de forma robusta (comentarios,
scripts y atributos con '>' no generan falsos positivos) y se reemplaza solo el
texto de cada etiqueta, conservando intacto el resto del documento.
"""

from __future__ import annotations

import base64
import html
import re
from html.parser import HTMLParser

from .models import ImgTag, LoadedImage

_SRC_ATTR = re.compile(
    r"""(?P<prefix>(?<![\w:-])src\s*=\s*)(?P<value>"[^"]*"|'[^']*'|[^\s"'>]+)""",
    re.IGNORECASE,
)


class _ImgTagParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.positions: list[tuple[int, int, str, str | None]] = []

    def handle_starttag(self, tag, attrs):
        self._record(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        self._record(tag, attrs)

    def _record(self, tag, attrs):
        if tag != "img":
            return
        line, column = self.getpos()
        raw = self.get_starttag_text() or ""
        src = next((value for name, value in attrs if name == "src"), None)
        self.positions.append((line, column, raw, src))


class ImgTagLocator:
    def find(self, document: str) -> list[ImgTag]:
        parser = _ImgTagParser()
        parser.feed(document)
        parser.close()
        line_offsets = self._line_offsets(document)
        tags = []
        for line, column, raw, src in parser.positions:
            start = line_offsets[line - 1] + column
            if document[start:start + len(raw)] != raw:  # salvaguarda de posición
                start = document.find(raw, start)
                if start < 0:
                    continue
            tags.append(ImgTag(start, start + len(raw), raw, src.strip() if src else src))
        return tags

    @staticmethod
    def _line_offsets(document: str) -> list[int]:
        """HTMLParser cuenta líneas solo con '\\n'; se replica ese criterio."""
        offsets = [0]
        offsets.extend(i + 1 for i, char in enumerate(document) if char == "\n")
        return offsets


class Base64Encoder:
    @staticmethod
    def to_data_uri(image: LoadedImage) -> str:
        payload = base64.b64encode(image.content).decode("ascii")
        return f"data:{image.mime_type};base64,{payload}"


class ImgSrcRewriter:
    @staticmethod
    def replace_src(raw_tag: str, new_src: str) -> str:
        escaped = html.escape(new_src, quote=True)
        return _SRC_ATTR.sub(lambda m: f'{m.group("prefix")}"{escaped}"', raw_tag, count=1)

    @staticmethod
    def apply(document: str, replacements: list[tuple[ImgTag, str]]) -> str:
        """Aplica los reemplazos de atrás hacia adelante para no desplazar offsets."""
        result = document
        for tag, new_raw in sorted(replacements, key=lambda r: r[0].start, reverse=True):
            result = result[:tag.start] + new_raw + result[tag.end:]
        return result
