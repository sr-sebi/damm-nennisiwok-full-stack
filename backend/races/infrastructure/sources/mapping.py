"""Mapeo de columnas: cabecera del fichero → campo de las reglas.

Las cabeceras se comparan normalizadas (minúsculas, sin tildes, espacios y guiones como `_`), así
que `Teléfono` y `Talla_camiseta` de la tienda valen igual que `telefono` y `talla_camiseta`. Un
proveedor con otros nombres se configura con alias en su canal, sin código.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping

from races.domain.normalize import FIELDS, clean_text
from races.infrastructure.sources.base import SourceError

# Cabeceras de `docs/reglas-de-negocio.md`.
DEFAULT_HEADERS = {
    "nombre": "nombre",
    "apellidos": "apellidos",
    "email": "email",
    "fecha_nacimiento": "fecha_nacimiento",
    "telefono": "telefono",
    "talla": "talla_camiseta",
}
# El teléfono puede faltar como valor y también como columna.
REQUIRED_FIELDS = ("nombre", "apellidos", "email", "fecha_nacimiento", "talla")

_SEPARATORS = re.compile(r"[\s\-]+")


def header_key(header: str) -> str:
    text = unicodedata.normalize("NFKD", clean_text(header).casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return _SEPARATORS.sub("_", text).strip("_")


def map_columns(headers: list[str], aliases: Mapping[str, str]) -> tuple[dict[str, int], list[str]]:
    """Devuelve `{campo: índice de columna}` y las cabeceras que no se usan.

    Lanza `SourceError` si falta una columna obligatoria o si dos columnas dan el mismo campo.
    """
    known = {header_key(header): field for field, header in DEFAULT_HEADERS.items()}
    for source, field in aliases.items():
        if field not in FIELDS:
            raise SourceError(
                f"El canal tiene un alias de columna hacia un campo que no existe: «{field}»."
            )
        known[header_key(source)] = field

    positions: dict[str, int] = {}
    ignored: list[str] = []
    for index, header in enumerate(headers):
        field = known.get(header_key(header))
        if field is None:
            if clean_text(header):
                ignored.append(clean_text(header))
            continue
        if field in positions:
            first = clean_text(headers[positions[field]])
            raise SourceError(
                f"Las columnas «{first}» y «{clean_text(header)}» son las dos "
                f"«{DEFAULT_HEADERS[field]}»: deja solo una."
            )
        positions[field] = index

    missing = [DEFAULT_HEADERS[field] for field in REQUIRED_FIELDS if field not in positions]
    if missing:
        found = ", ".join(clean_text(h) for h in headers if clean_text(h)) or "ninguna"
        raise SourceError(
            f"Faltan columnas obligatorias: {', '.join(missing)}. Cabeceras del fichero: {found}."
        )
    return positions, ignored
