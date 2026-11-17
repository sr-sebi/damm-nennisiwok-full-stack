"""Normalizador común: registro en bruto, venga de donde venga, → valores canónicos o incidencias.

Recibe un registro ya mapeado a los campos de las reglas (`nombre`, `apellidos`, `email`,
`fecha_nacimiento`, `telefono`, `talla`) con los valores tal como los dio el lector: texto de un
CSV, fecha o número de una celda de Excel, o lo que escriba la tienda en el formulario.

Cómo funciona:

1. Limpieza común de todo texto (Unicode NFC, BOM, espacios raros, saltos de línea, espacios
   repetidos).
2. Alias de valores del canal (por ejemplo, talla «2XL» → «XXL»).
3. Una regla por campo, registrada en `RULES`, que devuelve el valor canónico o un rechazo.

Nunca lanza: un tipo inesperado o un error interno de una regla se convierten en una incidencia
de esa fila. No adivina: una fecha solo se acepta como fecha nativa, número de serie de Excel o
con uno de los formatos del canal. Lo que es una regla de negocio (obligatorio, talla permitida,
edad mínima) no está aquí: está en `rules.validate`.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from races.domain.issues import Issue, IssueCode, make_issue

FIELDS = ("nombre", "apellidos", "email", "fecha_nacimiento", "telefono", "talla")

MAX_LENGTH = {
    "nombre": 100,
    "apellidos": 150,
    "email": 254,
    "telefono": 30,
    "talla": 10,
}

DEFAULT_DATE_FORMATS = ("%d/%m/%Y",)

# Excel cuenta los días desde el 30/12/1899 (para series ≥ 61; antes arrastra el falso
# 29/02/1900 de Lotus). Ninguna fecha de nacimiento razonable cae antes de marzo de 1900.
EXCEL_EPOCH = date(1899, 12, 30)
EXCEL_FIRST_RELIABLE_SERIAL = 61

_TWO_DIGIT_YEAR = re.compile(r"^\d{1,2}\D\d{1,2}\D\d{2}$")
_NUMERIC_PHONE_WITH_DECIMALS = re.compile(r"^\+?\d+\.0+$")
_MAILTO = re.compile(r"^mailto:", re.IGNORECASE)
_ANGLE_ADDRESS = re.compile(r"^(?:[^<>]*)<([^<>]*)>$")


@dataclass(frozen=True)
class NormalizeOptions:
    """Lo que depende del canal. Llega como parámetro: el dominio no lee la base de datos.

    `aliases` es `{campo: {valor de origen: valor canónico}}`, ya combinado (los del canal
    mandan sobre los globales). El valor de origen se compara tras la limpieza común y sin
    distinguir mayúsculas.
    """

    date_formats: tuple[str, ...] = DEFAULT_DATE_FORMATS
    aliases: Mapping[str, Mapping[str, str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        formats = tuple(self.date_formats)
        if not formats:
            raise ValueError("Hace falta al menos un formato de fecha.")
        for fmt in formats:
            # Es una fecha de nacimiento: con dos cifras no se sabe el siglo.
            if "%Y" not in fmt or "%y" in fmt:
                raise ValueError(f"El formato de fecha {fmt!r} tiene que llevar el año con %Y.")
        aliases = {
            field_name: {alias_key(source): target for source, target in values.items()}
            for field_name, values in self.aliases.items()
        }
        object.__setattr__(self, "date_formats", formats)
        object.__setattr__(self, "aliases", aliases)


@dataclass(frozen=True)
class CanonicalRegistration:
    """Valores ya interpretados. `None` = vacío o no interpretable (ver las incidencias)."""

    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None  # tal como llegó, limpio: se muestra
    email_norm: str | None = None  # en minúsculas: es la clave de duplicado
    birth_date: date | None = None
    phone: str | None = None
    shirt_size: str | None = None


@dataclass(frozen=True)
class NormalizedRow:
    values: CanonicalRegistration
    raw: Mapping[str, Any]
    issues: tuple[Issue, ...]


@dataclass(frozen=True)
class Rejected:
    """Lo que devuelve una regla cuando no puede interpretar el valor."""

    code: IssueCode
    params: Mapping[str, Any] = field(default_factory=dict)


Rule = Callable[[Any, NormalizeOptions], Any]

DEFAULT_OPTIONS = NormalizeOptions()


def clean_text(value: str) -> str:
    """Limpieza común de cualquier texto antes de su regla."""
    text = value
    if not unicodedata.is_normalized("NFC", text):
        text = unicodedata.normalize("NFC", text)
    if not text.isprintable():
        # BOM, espacio de no separación, ancho cero, saltos de línea, tabuladores…
        text = "".join(
            " " if ch.isspace() else ch
            for ch in text
            if ch.isspace() or unicodedata.category(ch) not in ("Cc", "Cf")
        )
    return " ".join(text.split())


def alias_key(value: str) -> str:
    return clean_text(value).casefold()


def is_blank(raw: Any) -> bool:
    """Fila sin ningún valor: se cuenta aparte, no es un error."""
    if not isinstance(raw, Mapping):
        return False
    return all(
        value is None or (isinstance(value, str) and clean_text(value) == "")
        for value in raw.values()
    )


def normalize(raw: Mapping[str, Any], options: NormalizeOptions = DEFAULT_OPTIONS) -> NormalizedRow:
    if not isinstance(raw, Mapping):
        issue = make_issue(IssueCode.BAD_ROW, "fila", raw)
        return NormalizedRow(values=CanonicalRegistration(), raw={}, issues=(issue,))

    values: dict[str, Any] = {}
    issues: list[Issue] = []
    for field_name, rule in RULES.items():
        value = None
        try:
            value = raw.get(field_name)
            result = _apply(field_name, rule, value, options)
        except Exception:
            result = Rejected(IssueCode.INTERNAL_ERROR)
        if isinstance(result, Rejected):
            issues.append(make_issue(result.code, field_name, value, **result.params))
        else:
            values[field_name] = result

    email = values.get("email")
    canonical = CanonicalRegistration(
        first_name=values.get("nombre"),
        last_name=values.get("apellidos"),
        email=email,
        email_norm=email.lower() if email else None,
        birth_date=values.get("fecha_nacimiento"),
        phone=values.get("telefono"),
        shirt_size=values.get("talla"),
    )
    return NormalizedRow(values=canonical, raw=raw, issues=tuple(issues))


def _apply(field_name: str, rule: Rule, value: Any, options: NormalizeOptions) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        value = clean_text(value)
        if value == "":
            return None
        value = options.aliases.get(field_name, {}).get(value.casefold(), value)
        max_length = MAX_LENGTH.get(field_name)
        if max_length is not None and len(value) > max_length:
            return Rejected(IssueCode.TOO_LONG, {"length": len(value), "max_length": max_length})
    return rule(value, options)


def _unexpected(value: Any) -> Rejected:
    return Rejected(IssueCode.UNEXPECTED_TYPE, {"type_name": _type_name(value)})


def _type_name(value: Any) -> str:
    names = {bool: "sí/no", int: "número", float: "número", Decimal: "número", list: "lista"}
    return names.get(type(value), type(value).__name__)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)


# --- reglas por campo ------------------------------------------------------------------------


def text_rule(value: Any, options: NormalizeOptions) -> Any:
    """Nombres: solo limpieza. No se cambian mayúsculas («de la Fuente» se quedaría mal)."""
    if isinstance(value, str):
        return value
    return _unexpected(value)


def email_rule(value: Any, options: NormalizeOptions) -> Any:
    """Quita `mailto:` y `Nombre <…>`; conserva las mayúsculas para mostrar."""
    if not isinstance(value, str):
        return _unexpected(value)
    email = _MAILTO.sub("", value)
    match = _ANGLE_ADDRESS.match(email)
    if match:
        email = match.group(1)
    return clean_text(email) or None


def date_rule(value: Any, options: NormalizeOptions) -> Any:
    """Fecha nativa (Excel), número de serie de Excel o texto con un formato del canal."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if _is_number(value):
        return _from_excel_serial(value)
    if not isinstance(value, str):
        return _unexpected(value)
    for fmt in options.date_formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    if _TWO_DIGIT_YEAR.match(value):
        reason = "el año tiene dos cifras y no se sabe el siglo"
    else:
        expected = " o ".join(_human_format(fmt) for fmt in options.date_formats)
        reason = f"no existe o no tiene el formato {expected}"
    return Rejected(IssueCode.INVALID_DATE, {"reason": reason})


def phone_rule(value: Any, options: NormalizeOptions) -> Any:
    """Texto libre. Un número (celda de Excel, o «600000101.0» de una exportación) pasa a texto."""
    if isinstance(value, str):
        if _NUMERIC_PHONE_WITH_DECIMALS.match(value):
            return value.split(".", 1)[0]
        return value
    if _is_number(value):
        if isinstance(value, float) and not math.isfinite(value):
            return Rejected(IssueCode.INVALID_PHONE)
        if value != int(value) or value < 0:
            return Rejected(IssueCode.INVALID_PHONE)
        return str(int(value))
    return _unexpected(value)


def size_rule(value: Any, options: NormalizeOptions) -> Any:
    """Mayúsculas (los alias ya se han aplicado). Si es una talla permitida, lo dicen las reglas."""
    if isinstance(value, str):
        return value.upper()
    return _unexpected(value)


def _from_excel_serial(value: int | float | Decimal) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return Rejected(IssueCode.INVALID_DATE, {"reason": "no es un número de fecha de Excel"})
    days = int(value)  # una parte decimal es la hora: no cuenta
    if days < EXCEL_FIRST_RELIABLE_SERIAL:
        return Rejected(IssueCode.INVALID_DATE, {"reason": "no es un número de fecha de Excel"})
    try:
        return EXCEL_EPOCH + timedelta(days=days)
    except OverflowError:
        return Rejected(IssueCode.INVALID_DATE, {"reason": "no es un número de fecha de Excel"})


def _human_format(fmt: str) -> str:
    return fmt.replace("%d", "dd").replace("%m", "mm").replace("%Y", "aaaa")


# Añadir un campo o cambiar cómo se interpreta = una función aquí.
RULES: dict[str, Rule] = {
    "nombre": text_rule,
    "apellidos": text_rule,
    "email": email_rule,
    "fecha_nacimiento": date_rule,
    "telefono": phone_rule,
    "talla": size_rule,
}
