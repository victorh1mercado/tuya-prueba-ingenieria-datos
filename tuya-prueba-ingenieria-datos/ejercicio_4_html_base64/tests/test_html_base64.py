"""Pruebas del procesador HTML -> base64 (solo unittest de la librería estándar).

Ejecutar desde ejercicio_4_html_base64:  python -m unittest discover -s tests -v
"""

import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from html_base64 import build_processor  # noqa: E402
from html_base64.cli import main as cli_main  # noqa: E402
from html_base64.discovery import HtmlFileCollector  # noqa: E402
from html_base64.html_rewriter import ImgSrcRewriter, ImgTagLocator  # noqa: E402
from html_base64.models import ImageProcessingError  # noqa: E402
from html_base64.sources import detect_mime_type  # noqa: E402

GIF = base64.b64decode("R0lGODlhAQABAIAAAP///wAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw==")
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
GIF_URI = "data:image/gif;base64," + base64.b64encode(GIF).decode()


class TempDirTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        return path


class TestImgTagLocator(unittest.TestCase):
    def test_ignora_comentarios_scripts_y_localiza_variantes(self):
        html = (
            "<!-- <img src='a.png'> -->\n"
            "<script>var x = '<img src=\"b.png\">';</script>\n"
            "<IMG SRC='c.png'>\n<img alt=x src=d.png />\n<img data-src='e.png'>"
        )
        tags = ImgTagLocator().find(html)
        self.assertEqual([t.src for t in tags], ["c.png", "d.png", None])
        for tag in tags:
            self.assertEqual(html[tag.start:tag.end], tag.raw)

    def test_offsets_con_saltos_de_linea_windows(self):
        html = "<p>\r\n</p>\r\n<img src='x.gif'>"
        tag = ImgTagLocator().find(html)[0]
        self.assertEqual(html[tag.start:tag.end], "<img src='x.gif'>")


class TestImgSrcRewriter(unittest.TestCase):
    def test_reemplaza_solo_src_y_no_data_src(self):
        raw = '<img data-src="keep.png" src=\'old.png\' alt="a">'
        new = ImgSrcRewriter.replace_src(raw, "data:image/png;base64,AAA")
        self.assertEqual(new, '<img data-src="keep.png" src="data:image/png;base64,AAA" alt="a">')

    def test_reemplaza_src_sin_comillas(self):
        self.assertEqual(ImgSrcRewriter.replace_src("<img src=a.png>", "X"), '<img src="X">')


class TestMimeDetection(unittest.TestCase):
    def test_firma_tiene_prioridad_sobre_extension(self):
        self.assertEqual(detect_mime_type(GIF, "foto.png"), "image/gif")

    def test_texto_con_extension_de_imagen_falla(self):
        with self.assertRaises(ImageProcessingError):
            detect_mime_type(b"hola", "falsa.png")

    def test_svg(self):
        self.assertEqual(detect_mime_type(b'<?xml version="1.0"?><svg></svg>'), "image/svg+xml")


class TestCollector(TempDirTestCase):
    def test_archivos_y_directorios_recursivos_sin_duplicados(self):
        a = self.write("a.html", "")
        self.write("sub/b.htm", "")
        self.write("sub/deep/c.HTML", "")
        self.write("sub/a_base64.html", "")
        self.write("sub/nota.txt", "")
        files, invalid = HtmlFileCollector(exclude_suffix="_base64").collect(
            [a, self.root, self.root / "no_existe", self.root / "sub/nota.txt"])
        self.assertEqual(sorted(p.name for p in files), ["a.html", "b.htm", "c.HTML"])
        self.assertEqual(len(invalid), 2)


class TestProcessor(TempDirTestCase):
    def test_flujo_completo(self):
        self.write("img/logo.png", PNG)
        self.write("img/icono con espacio.gif", GIF)
        page = self.write(
            "site/index.html",
            '<h1>Hola ñ</h1>\n<img src="../img/logo.png">\n'
            '<img src="../img/icono%20con%20espacio.gif">\n'
            f'<img src="../img/falta.png">\n<img src="{GIF_URI}">\n<img alt="x">',
        )
        original = page.read_bytes()
        report = build_processor([self.root / "site"]).process([self.root / "site"])

        self.assertEqual(page.read_bytes(), original, "el original no debe modificarse")
        output = Path(report.outputs[str(page.resolve())])
        self.assertEqual(output.name, "index_base64.html")
        content = output.read_text(encoding="utf-8")

        self.assertIn("data:image/png;base64," + base64.b64encode(PNG).decode(), content)
        self.assertIn(GIF_URI, content)
        self.assertIn('src="../img/falta.png"', content)
        self.assertIn("<h1>Hola ñ</h1>", content)

        ok = report.success[str(page.resolve())]
        ko = report.fail[str(page.resolve())]
        self.assertEqual(len(ok), 3)
        self.assertEqual({f["src"] for f in ko}, {"../img/falta.png", None})

    def test_segunda_ejecucion_no_reprocesa_salidas(self):
        self.write("a.png", PNG)
        self.write("p.html", '<img src="a.png">')
        build_processor([self.root]).process([self.root])
        report = build_processor([self.root]).process([self.root])
        self.assertEqual(list(report.outputs), [str((self.root / "p.html").resolve())])

    def test_output_dir_replica_estructura(self):
        self.write("site/sub/a.png", PNG)
        self.write("site/sub/p.html", '<img src="a.png">')
        out = self.root / "salida"
        report = build_processor([self.root / "site"], output_dir=out).process([self.root / "site"])
        self.assertTrue((out / "site" / "sub" / "p.html").is_file())
        self.assertEqual(report.total_fail, 0)

    def test_remoto_deshabilitado_por_defecto(self):
        page = self.write("p.html", '<img src="https://example.com/x.png"><img src="//cdn/x.png">')
        report = build_processor([page]).process([page])
        self.assertEqual(report.total_fail, 2)
        self.assertTrue(all("deshabilitado" in f["error"] for f in report.fail[str(page.resolve())]))

    def test_cli_genera_reporte_json(self):
        self.write("a.gif", GIF)
        page = self.write("p.html", '<img src="a.gif">')
        report_path = self.root / "reporte.json"
        with open(self.root / "stdout.txt", "w") as sink:
            stdout, sys.stdout = sys.stdout, sink
            try:
                code = cli_main([str(page), "--report", str(report_path)])
            finally:
                sys.stdout = stdout
        data = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual(set(data), {"success", "fail", "outputs"})
        self.assertEqual(data["fail"], {})


if __name__ == "__main__":
    unittest.main()
