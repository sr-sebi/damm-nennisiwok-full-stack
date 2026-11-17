"""Reglas de negocio de `docs/reglas-de-negocio.md`: obligatorios, email, talla, edad y categoría.

Van en código y no en la configuración: la categoría se calcula al vuelo, así que cambiar los
tramos cambiaría la de carreras ya celebradas.
"""

from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from races.domain.issues import Issue, IssueCode, make_issue
from races.domain.normalize import NormalizedRow

SHIRT_SIZES = ("XS", "S", "M", "L", "XL", "XXL")
MIN_AGE = 16

# (edad mínima, categoría), de mayor a menor.
CATEGORIES = (
    (55, "Veterano C"),
    (45, "Veterano B"),
    (35, "Veterano A"),
    (20, "Senior"),
    (MIN_AGE, "Junior"),
)

REQUIRED_FIELDS = ("nombre", "apellidos", "email", "fecha_nacimiento", "talla")


def age_on(birth_date: date, on: date) -> int:
    """Años cumplidos ese día: quien cumple ese mismo día ya los tiene.

    Quien nació un 29 de febrero cumple, en año no bisiesto, el 1 de marzo.
    """
    return on.year - birth_date.year - ((on.month, on.day) < (birth_date.month, birth_date.day))


def category_for(birth_date: date, race_date: date) -> str | None:
    """Categoría por la edad el día de la carrera; `None` si no llega a la edad mínima."""
    age = age_on(birth_date, race_date)
    for min_age, name in CATEGORIES:
        if age >= min_age:
            return name
    return None


def validate(row: NormalizedRow, race_date: date) -> list[Issue]:
    """Incidencias de negocio de una fila ya normalizada (todas, no solo la primera).

    Un campo que ya tiene una incidencia de forma no se vuelve a juzgar aquí: «fecha no
    válida» no tiene que salir también como «falta la fecha».
    """
    if any(issue.code is IssueCode.BAD_ROW for issue in row.issues):
        return []
    values = row.values
    already_flagged = {issue.field for issue in row.issues}
    by_field = {
        "nombre": values.first_name,
        "apellidos": values.last_name,
        "email": values.email,
        "fecha_nacimiento": values.birth_date,
        "talla": values.shirt_size,
    }
    issues: list[Issue] = []

    def add(code: IssueCode, field_name: str, **params) -> None:
        issues.append(make_issue(code, field_name, row.raw.get(field_name), **params))

    for field_name in REQUIRED_FIELDS:
        if field_name not in already_flagged and by_field[field_name] is None:
            add(IssueCode.REQUIRED, field_name)

    if values.email is not None and not _is_valid_email(values.email):
        add(IssueCode.INVALID_EMAIL, "email")

    if values.shirt_size is not None and values.shirt_size not in SHIRT_SIZES:
        add(IssueCode.SIZE_NOT_ALLOWED, "talla", allowed=", ".join(SHIRT_SIZES))

    if values.birth_date is not None:
        if values.birth_date > race_date:
            add(IssueCode.BORN_AFTER_RACE, "fecha_nacimiento", birth_date=values.birth_date)
        else:
            age = age_on(values.birth_date, race_date)
            if age < MIN_AGE:
                add(IssueCode.UNDER_MIN_AGE, "fecha_nacimiento", age=age, min_age=MIN_AGE)

    return issues


def _is_valid_email(email: str) -> bool:
    # El validador de Django es una función pura: no toca la base de datos.
    try:
        validate_email(email)
    except ValidationError:
        return False
    return True
