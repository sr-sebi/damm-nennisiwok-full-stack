"""Quién es quién: clave de nombre para el posible duplicado y la búsqueda, y diferencias de datos.

El duplicado seguro es el mismo `email_norm` en la carrera. El posible es el mismo nombre y
apellidos normalizados con la misma fecha de nacimiento y otro email: no se fusiona, decide una
persona. Las diferencias se enseñan cuando alguien ya inscrito vuelve a llegar por otro canal,
para que la organización hable con el corredor en vez de sobrescribir sus datos.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import date

from races.domain.normalize import MAX_LENGTH, CanonicalRegistration, clean_text

NAME_KEY_MAX_LENGTH = MAX_LENGTH["nombre"] + MAX_LENGTH["apellidos"] + 1

# Campo de `CanonicalRegistration` → cómo se llama en un mensaje.
COMPARED_FIELDS = (
    ("first_name", "nombre"),
    ("last_name", "apellidos"),
    ("email", "email"),
    ("birth_date", "fecha de nacimiento"),
    ("phone", "teléfono"),
    ("shirt_size", "talla"),
)


def fold(text: str) -> str:
    """Sin tildes ni diacríticos y en minúsculas: «Íñigo Larrañaga» → «inigo larranaga».

    No depende de la collation del motor (SQL Server suele ignorar tildes; PostgreSQL y SQLite
    no), así que «garcia» encuentra «García» en los tres.
    """
    decomposed = unicodedata.normalize("NFKD", clean_text(text))
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return clean_text(stripped).casefold()


def name_key(first_name: str, last_name: str) -> str:
    """Nombre y apellidos normalizados: es el `search_text` y la mitad del posible duplicado."""
    return fold(f"{first_name} {last_name}")[:NAME_KEY_MAX_LENGTH]


@dataclass(frozen=True)
class Difference:
    field: str
    label: str
    current: str
    incoming: str

    def describe(self) -> str:
        return f"{self.label}: {self.current or '(vacío)'} → {self.incoming or '(vacío)'}"


def differences(
    current: CanonicalRegistration, incoming: CanonicalRegistration
) -> tuple[Difference, ...]:
    """Lo que trae `incoming` distinto de lo que ya tenemos, campo a campo.

    El email se compara tal como llegó (con sus mayúsculas): `email_norm` es igual por definición.
    """
    found = []
    for attr, label in COMPARED_FIELDS:
        old, new = _display(getattr(current, attr)), _display(getattr(incoming, attr))
        if old != new:
            found.append(Difference(field=attr, label=label, current=old, incoming=new))
    return tuple(found)


def describe_differences(found: tuple[Difference, ...]) -> str:
    return "; ".join(difference.describe() for difference in found)


def _display(value: str | date | None) -> str:
    if value is None:
        return ""
    if isinstance(value, date):
        return f"{value:%d/%m/%Y}"
    return value
