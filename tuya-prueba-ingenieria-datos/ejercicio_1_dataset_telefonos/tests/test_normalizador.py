import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from normalizador_telefono import Estado, TipoTelefono, normalizar  # noqa: E402


class TestNormalizador(unittest.TestCase):
    def test_moviles_en_distintos_formatos(self):
        for valor in ("3158204761", "+57 315 820 4761", "(57) 315-820-4761", "0057 3158204761", "315.820.4761"):
            with self.subTest(valor=valor):
                r = normalizar(valor)
                self.assertEqual((r.e164, r.tipo, r.estado), ("+573158204761", TipoTelefono.MOVIL, Estado.VALIDO))

    def test_fijo_nuevo_plan(self):
        r = normalizar("601 271 8493")
        self.assertEqual((r.e164, r.tipo, r.estado), ("+576012718493", TipoTelefono.FIJO, Estado.VALIDO))

    def test_fijo_antiguo_se_migra(self):
        for valor in ("(4) 271 8493", "042718493", "034 2718493","+57 4 2718493"):
            with self.subTest(valor=valor):
                r = normalizar(valor)
                self.assertEqual((r.nacional, r.estado), ("6042718493", Estado.CORREGIDO))

    def test_fijo_de_7_digitos_requiere_indicativo(self):
        self.assertEqual(normalizar("2718493").estado, Estado.INVALIDO)
        self.assertEqual(normalizar("2718493", indicativo_ciudad="1").nacional, "6012718493")

    def test_extension_se_descarta(self):
        self.assertEqual(normalizar("6012718493 ext 123").nacional, "6012718493")

    def test_sospechosos(self):
        for valor in ("3000000000", "3111111111", "3001234567"):
            with self.subTest(valor=valor):
                r = normalizar(valor)
                self.assertEqual(r.estado, Estado.SOSPECHOSO)
                self.assertFalse(r.utilizable)

    def test_invalidos(self):
        for valor in (None, "", "abc", "12345", "21045678901"):
            with self.subTest(valor=valor):
                self.assertEqual(normalizar(valor).estado, Estado.INVALIDO)


if __name__ == "__main__":
    unittest.main()
