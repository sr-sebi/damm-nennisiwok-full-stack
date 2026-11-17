"""Incidencias tipadas de una fila: código, campo y valor en bruto.

Una incidencia nunca es una excepción: la fila se rechaza y el fichero sigue. Las incidencias
se agrupan para el informe, de forma que 17 filas con la talla «Única» salgan como una sola
línea («17 filas: talla «Única» no permitida») y la solución sea configurar un alias, no
leer 17 líneas iguales.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any

FIELD_LABELS = {
    "fila": "la fila",
    "nombre": "el nombre",
    "apellidos": "los apellidos",
    "email": "el email",
    "fecha_nacimiento": "la fecha de nacimiento",
    "telefono": "el teléfono",
    "talla": "la talla",
}

RAW_TEXT_LIMIT = 200


class IssueCode(str, Enum):
    """Cada código sabe si sus incidencias se agrupan también por valor.

    Se agrupan por valor las que se resuelven configurando algo para ese valor (un alias de
    talla, por ejemplo). Las que dependen de cada persona (un email mal escrito, una fecha
    concreta) se agrupan solo por código y campo, con algunos ejemplos.
    """

    def __new__(cls, value: str, group_by_value: bool):
        member = str.__new__(cls, value)
        member._value_ = value
        member.group_by_value = group_by_value
        return member

    # Forma: el valor no se puede interpretar.
    BAD_ROW = ("fila_no_valida", False)
    TOO_MANY_COLUMNS = ("columnas_de_mas", False)
    UNEXPECTED_TYPE = ("tipo_inesperado", True)
    TOO_LONG = ("demasiado_largo", False)
    INVALID_DATE = ("fecha_no_valida", False)
    INVALID_PHONE = ("telefono_no_valido", False)
    INTERNAL_ERROR = ("error_interno", False)
    # Reglas de negocio: el valor se entiende, pero no se admite.
    REQUIRED = ("obligatorio", False)
    INVALID_EMAIL = ("email_no_valido", False)
    SIZE_NOT_ALLOWED = ("talla_no_permitida", True)
    BORN_AFTER_RACE = ("nacimiento_posterior_a_carrera", False)
    UNDER_MIN_AGE = ("menor_de_edad_minima", False)


@dataclass(frozen=True)
class Issue:
    code: IssueCode
    field: str
    raw: str
    message: str

    @property
    def group_value(self) -> str:
        return self.raw if self.code.group_by_value else ""

    @property
    def group_key(self) -> tuple[str, str, str]:
        return (self.code.value, self.field, self.group_value)


@dataclass(frozen=True)
class IssueGroup:
    code: IssueCode
    field: str
    value: str
    count: int
    examples: tuple[str, ...]
    message: str


def raw_text(value: Any) -> str:
    """El valor tal como llegó, como texto y recortado: sirve para el informe y para agrupar."""
    if value is None:
        return ""
    try:
        text = str(value)
    except Exception:
        text = f"<{type(value).__name__}>"
    if len(text) > RAW_TEXT_LIMIT:
        return text[:RAW_TEXT_LIMIT] + "…"
    return text


def make_issue(code: IssueCode, field: str, raw: Any, **params: Any) -> Issue:
    text = raw_text(raw)
    return Issue(code=code, field=field, raw=text, message=_message(code, field, text, params))


def group_issues(issues: Iterable[Issue], max_examples: int = 3) -> list[IssueGroup]:
    """Agrupa por código, campo y (si el código lo pide) valor; los grupos más grandes, primero."""
    counts: dict[tuple[str, str, str], int] = {}
    examples: dict[tuple[str, str, str], list[str]] = {}
    first: dict[tuple[str, str, str], Issue] = {}
    for issue in issues:
        key = issue.group_key
        counts[key] = counts.get(key, 0) + 1
        first.setdefault(key, issue)
        seen = examples.setdefault(key, [])
        if len(seen) < max_examples and issue.raw not in seen:
            seen.append(issue.raw)
    groups = [
        IssueGroup(
            code=first[key].code,
            field=first[key].field,
            value=key[2],
            count=counts[key],
            examples=tuple(examples[key]),
            message=group_message(first[key]),
        )
        for key in counts
    ]
    return sorted(groups, key=lambda group: -group.count)


def _label(field: str) -> str:
    return FIELD_LABELS.get(field, field)


def _missing(label: str) -> str:
    verb = "Faltan" if label.startswith(("los ", "las ")) else "Falta"
    return f"{verb} {label}"


def _message(code: IssueCode, field: str, raw: str, params: dict[str, Any]) -> str:
    label = _label(field)
    if code is IssueCode.BAD_ROW:
        return "La fila no tiene un formato que se pueda leer."
    if code is IssueCode.TOO_MANY_COLUMNS:
        return (
            f"La fila tiene {params['found']} columnas y la cabecera {params['expected']}: "
            "puede que un valor lleve el separador sin comillas."
        )
    if code is IssueCode.UNEXPECTED_TYPE:
        return f"No se entiende {label}: llega un valor de tipo {params['type_name']}."
    if code is IssueCode.TOO_LONG:
        return (
            f"{label.capitalize()} es demasiado largo "
            f"({params['length']} caracteres; máximo {params['max_length']})."
        )
    if code is IssueCode.INVALID_DATE:
        return f"Fecha de nacimiento no válida: «{raw}» ({params['reason']})."
    if code is IssueCode.INVALID_PHONE:
        return f"Teléfono no válido: «{raw}»."
    if code is IssueCode.INTERNAL_ERROR:
        return f"No se ha podido interpretar {label} por un error inesperado."
    if code is IssueCode.REQUIRED:
        return f"{_missing(label)}."
    if code is IssueCode.INVALID_EMAIL:
        return f"Email no válido: «{raw}»."
    if code is IssueCode.SIZE_NOT_ALLOWED:
        return f"Talla «{raw}» no permitida (se admiten {params['allowed']})."
    if code is IssueCode.BORN_AFTER_RACE:
        return (
            f"La fecha de nacimiento ({params['birth_date']:%d/%m/%Y}) es posterior a la carrera."
        )
    if code is IssueCode.UNDER_MIN_AGE:
        return (
            f"Tiene {params['age']} años el día de la carrera; "
            f"la edad mínima es {params['min_age']}."
        )
    return f"Incidencia en {label}."


def group_message(issue: Issue) -> str:
    """Texto del grupo: el de la incidencia si el grupo es por valor; si no, uno genérico."""
    if issue.code.group_by_value:
        return issue.message
    label = _label(issue.field)
    generic = {
        IssueCode.BAD_ROW: "Filas con un formato que no se puede leer",
        IssueCode.TOO_MANY_COLUMNS: "Filas con más columnas que la cabecera",
        IssueCode.TOO_LONG: f"{label.capitalize()} demasiado largo",
        IssueCode.INVALID_DATE: "Fecha de nacimiento no válida",
        IssueCode.INVALID_PHONE: "Teléfono no válido",
        IssueCode.INTERNAL_ERROR: f"Error inesperado al interpretar {label}",
        IssueCode.REQUIRED: _missing(label),
        IssueCode.INVALID_EMAIL: "Email no válido",
        IssueCode.BORN_AFTER_RACE: "Fecha de nacimiento posterior a la carrera",
        IssueCode.UNDER_MIN_AGE: "Menor de la edad mínima el día de la carrera",
    }
    return generic.get(issue.code, issue.message)
