"""Normalización y validación de teléfonos colombianos (referencia del ejercicio 1).

Implementa las reglas de la capa Silver: limpieza, conversión a E.164,
clasificación (móvil / fijo) y detección de números sospechosos.
Plan de numeración vigente desde 2021: móviles y fijos de 10 dígitos;
fijos con prefijo 60 + indicativo departamental.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

CODIGO_PAIS = "57"
_INDICATIVOS_FIJOS = set("12345678")
_MOVIL = re.compile(r"^3\d{9}$")
_FIJO = re.compile(r"^60[1-8]\d{7}$")
_FIJO_ANTIGUO = re.compile(r"^[1-8]\d{7}$")  # indicativo de 1 dígito + 7 dígitos
_SECUENCIAS = ("0123456789", "1234567890", "9876543210")


class TipoTelefono(str, Enum):
    MOVIL = "MOVIL"
    FIJO = "FIJO"
    DESCONOCIDO = "DESCONOCIDO"


class Estado(str, Enum):
    VALIDO = "VALIDO"
    CORREGIDO = "CORREGIDO"      # válido tras una transformación (p. ej. fijo antiguo)
    SOSPECHOSO = "SOSPECHOSO"    # formato válido pero patrón de relleno
    INVALIDO = "INVALIDO"


@dataclass(frozen=True)
class ResultadoTelefono:
    original: str | None
    e164: str | None
    nacional: str | None
    tipo: TipoTelefono
    estado: Estado
    motivo: str | None = None

    @property
    def utilizable(self) -> bool:
        return self.estado in (Estado.VALIDO, Estado.CORREGIDO)


def _solo_digitos(valor: str) -> str:
    texto = re.split(r"(?i)\s*(?:ext\.?|extensi[oó]n|x)\s*\d+\s*$", valor.strip())[0]
    return re.sub(r"\D", "", texto)


def _quitar_prefijo_pais(digitos: str) -> str:
    for prefijo in ("0057", "57"):
        if digitos.startswith(prefijo) and len(digitos) - len(prefijo) in (8, 10):
            return digitos[len(prefijo):]
    return digitos


def _es_sospechoso(nacional: str) -> bool:
    abonado = nacional[3:]  # sin prefijo de operador / indicativo
    return (
        len(set(abonado)) == 1
        or len(set(nacional)) <= 2
        or any(abonado in s for s in _SECUENCIAS)
    )


def normalizar(valor: str | None, indicativo_ciudad: str | None = None) -> ResultadoTelefono:
    """Normaliza un teléfono. `indicativo_ciudad` (1 dígito) permite completar fijos de 7 dígitos."""
    if valor is None or not str(valor).strip():
        return ResultadoTelefono(valor, None, None, TipoTelefono.DESCONOCIDO, Estado.INVALIDO, "vacío")

    digitos = _quitar_prefijo_pais(_solo_digitos(str(valor)))
    estado = Estado.VALIDO
    motivo = None

    # Marcación de larga distancia antigua: 0 + indicativo + 7  /  0 + operador + indicativo + 7
    if len(digitos) == 9 and digitos[0] == "0":
        digitos = digitos[1:]
    elif len(digitos) == 10 and digitos[0] == "0" and digitos[1] in "3579":
        digitos = digitos[2:]
    if len(digitos) == 7 and indicativo_ciudad in _INDICATIVOS_FIJOS:
        digitos = indicativo_ciudad + digitos
    if _FIJO_ANTIGUO.match(digitos):
        digitos = "60" + digitos
        estado, motivo = Estado.CORREGIDO, "fijo migrado al plan de 10 dígitos"

    if _MOVIL.match(digitos):
        tipo = TipoTelefono.MOVIL
    elif _FIJO.match(digitos):
        tipo = TipoTelefono.FIJO
    else:
        razon = "fijo sin indicativo" if len(digitos) == 7 else f"formato no reconocido ({len(digitos)} dígitos)"
        return ResultadoTelefono(valor, None, None, TipoTelefono.DESCONOCIDO, Estado.INVALIDO, razon)

    if _es_sospechoso(digitos):
        estado, motivo = Estado.SOSPECHOSO, "patrón repetido o secuencial"

    return ResultadoTelefono(valor, f"+{CODIGO_PAIS}{digitos}", digitos, tipo, estado, motivo)
