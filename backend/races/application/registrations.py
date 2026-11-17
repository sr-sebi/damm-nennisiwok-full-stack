"""Inscripciones desde la app: comprobar antes de guardar, alta en tienda, corregir datos y buscar.

El formulario entra por el mismo camino que un fichero: el normalizador común con las opciones del
canal (y además la fecha ISO del formulario) y después `rules.validate`. Las reglas son las mismas
venga de donde venga.

- `check` solo lee: no bloquea la carrera ni escribe. Es un aviso para el mostrador; lo que manda
  es el alta, que vuelve a mirar con la carrera bloqueada.
- `register_in_app` no actualiza nunca a quien ya está inscrito, aunque fuera por la propia tienda:
  un alta con un email que ya existe es un «ya inscrita» (409) y no toca nada.
- `update_registration` corrige datos con la carrera bloqueada; no cambia dorsal, estado ni canal.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from django.db.models import Case, IntegerField, Q, QuerySet, Value, When

from races.application.channel_options import ChannelConfigError, options_for
from races.application.register import (
    Outcome,
    RegisterResult,
    as_canonical,
    find_possible_duplicate,
    race_registrar,
    registration_fields,
)
from races.domain.identity import Difference, differences, fold
from races.domain.issues import Issue
from races.domain.normalize import (
    DEFAULT_DATE_FORMATS,
    CanonicalRegistration,
    NormalizeOptions,
    normalize,
)
from races.domain.rules import validate
from races.models import Channel, Race, Registration

Status = Registration.Status

# El formulario manda la fecha como `<input type="date">`: AAAA-MM-DD, sin ambigüedad.
FORM_DATE_FORMAT = "%Y-%m-%d"

# Nombre en la API → campo del normalizador.
API_FIELDS = {
    "first_name": "nombre",
    "last_name": "apellidos",
    "email": "email",
    "birth_date": "fecha_nacimiento",
    "phone": "telefono",
    "shirt_size": "talla",
}
DOMAIN_TO_API = {domain: api for api, domain in API_FIELDS.items()}


class RegistrationRejected(Exception):
    """Datos que no pasan las reglas. `errors` es `{campo de la API: [mensajes]}`."""

    def __init__(self, errors: dict[str, list[str]]):
        super().__init__("Inscripción no válida")
        self.errors = errors


class AlreadyRegistered(Exception):
    """El email ya está inscrito en la carrera. `message` es para el usuario."""

    def __init__(self, registration: Registration, message: str):
        super().__init__(message)
        self.registration = registration
        self.message = message


@dataclass(frozen=True)
class CheckResult:
    already_registered: Registration | None = None
    already_message: str = ""
    possible_duplicate: Registration | None = None
    duplicate_message: str = ""
    waitlist_message: str = ""


@dataclass(frozen=True)
class UpdateResult:
    registration: Registration
    changes: tuple[Difference, ...]
    notice: str = ""


# --- mensajes -------------------------------------------------------------------------------


def describe_registration(registration: Registration) -> str:
    """«Plataforma B, dorsal 9», «Tienda, en lista de espera (posición 3)»…"""
    channel = registration.channel.name
    if registration.status == Status.WAITLISTED:
        return f"{channel}, en lista de espera (posición {registration.waitlist_position})"
    if registration.status == Status.WITHDRAWN:
        return f"{channel}, dada de baja (tenía el dorsal {registration.bib})"
    return f"{channel}, dorsal {registration.bib}"


def already_registered_message(registration: Registration) -> str:
    return (
        f"Ya inscrita por {describe_registration(registration)}: "
        f"{registration.first_name} {registration.last_name}."
    )


def possible_duplicate_message(registration: Registration) -> str:
    return (
        "Hay otra inscripción con el mismo nombre y fecha de nacimiento y otro email: "
        f"{registration.first_name} {registration.last_name} ({registration.email}), "
        f"{describe_registration(registration)}. "
        "Si es la misma persona, no la des de alta otra vez."
    )


def waitlist_message(race: Race, confirmed: int) -> str:
    if race.capacity is None or confirmed < race.capacity:
        return ""
    return (
        f"El aforo ({race.capacity}) está completo: el alta irá a la lista de espera, sin dorsal "
        "hasta que haya una plaza libre."
    )


# --- casos de uso ---------------------------------------------------------------------------


def check(race: Race, raw: Mapping[str, Any]) -> CheckResult:
    """Aviso antes de guardar, con lo que haya escrito: email, o nombre + apellidos + fecha.

    Un campo que no se entiende (un email a medio escribir) se ignora: esto no valida, avisa.
    """
    values = normalize(_domain_raw(raw), _check_options()).values
    found: dict[str, Any] = {}
    if values.email_norm:
        existing = (
            Registration.objects.select_related("channel")
            .filter(race=race, email_norm=values.email_norm)
            .first()
        )
        if existing is not None:
            found["already_registered"] = existing
            found["already_message"] = already_registered_message(existing)
    if values.first_name and values.last_name and values.birth_date:
        duplicate = find_possible_duplicate(race.pk, values)
        if duplicate is not None and duplicate != found.get("already_registered"):
            found["possible_duplicate"] = duplicate
            found["duplicate_message"] = possible_duplicate_message(duplicate)
    if "already_registered" not in found:
        confirmed = Registration.objects.filter(race=race, status=Status.CONFIRMED).count()
        found["waitlist_message"] = waitlist_message(race, confirmed)
    return CheckResult(**found)


def register_in_app(race: Race, channel: Channel, raw: Mapping[str, Any]) -> RegisterResult:
    """Alta en un canal presencial: dorsal, o lista de espera si el aforo está lleno."""
    if channel.kind != Channel.Kind.IN_PERSON:
        raise RegistrationRejected(
            {
                "channel": [
                    f"{channel.name} es una plataforma online: sus inscripciones se importan "
                    "con su listado, no se dan de alta en la app."
                ]
            }
        )
    values = _clean(_domain_raw(raw), channel, race)
    with race_registrar(race.pk) as registrar:
        existing = registrar.find_by_email(values.email_norm)
        if existing is not None:
            raise AlreadyRegistered(existing, already_registered_message(existing))
        return registrar.register(values, channel, note_channel=False)


def update_registration(registration_id: int, changes: Mapping[str, Any]) -> UpdateResult:
    """Corrige datos de una inscripción. Dorsal, estado, canal y posición no cambian.

    El email de una inscripción de plataforma no se cambia aquí: es lo que la une a su listado, y
    con otro email la próxima importación la daría de alta otra vez con otro dorsal.
    """
    race_id = Registration.objects.values_list("race_id", flat=True).get(pk=registration_id)
    with race_registrar(race_id) as registrar:
        registration = Registration.objects.select_related("channel").get(pk=registration_id)
        current = as_canonical(registration)
        raw = {
            "nombre": current.first_name,
            "apellidos": current.last_name,
            "email": current.email,
            "fecha_nacimiento": current.birth_date,
            "telefono": current.phone,
            "talla": current.shirt_size,
            **_domain_raw(changes),
        }
        values = _clean(raw, registration.channel, registrar.race)

        if values.email_norm != registration.email_norm:
            if registration.channel.kind == Channel.Kind.ONLINE:
                raise RegistrationRejected(
                    {
                        "email": [
                            f"Esta inscripción llega del listado de {registration.channel.name} "
                            "y el email es lo que la une a él: hay que cambiarlo en la plataforma. "
                            "Si se cambia aquí, la próxima importación la daría de alta otra vez "
                            "con otro dorsal."
                        ]
                    }
                )
            other = registrar.find_by_email(values.email_norm)
            if other is not None:
                raise AlreadyRegistered(
                    other,
                    f"Ese email ya es de otra inscripción. {already_registered_message(other)}",
                )

        found = differences(current, values)
        if found:
            changed = []
            for name, value in registration_fields(values).items():
                if getattr(registration, name) != value:
                    setattr(registration, name, value)
                    changed.append(name)
            registration.save(update_fields=[*changed, "updated_at"])

        notice = ""
        if found and registration.channel.kind == Channel.Kind.ONLINE:
            notice = (
                f"Los datos de esta inscripción llegan de {registration.channel.name}: si su "
                "próximo listado trae otros, se volverán a cambiar."
            )
        return UpdateResult(registration, found, notice)


def search(race: Race, q: str = "", status: str | None = None) -> QuerySet[Registration]:
    """Lista de una carrera: confirmadas y bajas por dorsal, después la lista de espera en orden.

    `q` numérico es el dorsal exacto. Si no, cada palabra tiene que estar en el nombre y apellidos
    normalizados (sin tildes, en minúsculas) o en el email: «garcia» encuentra «García» sin depender
    de la collation del motor, y «ruiz alex» encuentra a «Álex Ruiz».
    """
    queryset = Registration.objects.filter(race=race)
    if status:
        queryset = queryset.filter(status=status)
    q = (q or "").replace("\x00", "").strip()
    # `"²".isdigit()` es True pero `int("²")` falla: el dorsal, solo con cifras 0–9.
    if q.isascii() and q.isdigit():
        queryset = queryset.filter(bib=int(q))
    elif q:
        for word in q.split():
            queryset = queryset.filter(
                Q(search_text__icontains=fold(word)) | Q(email_norm__icontains=word.lower())
            )
    # Las de lista de espera no tienen dorsal. Ordenar los NULL depende del motor (PostgreSQL los
    # pone al final y SQL Server al principio), así que se ordena primero por «tiene dorsal».
    without_bib_last = Case(
        When(bib__isnull=True, then=Value(1)), default=Value(0), output_field=IntegerField()
    )
    return (
        queryset.select_related("channel", "possible_duplicate_of")
        .prefetch_related("also_channels", "notifications")
        .order_by(without_bib_last, "bib", "waitlist_position", "id")
    )


# --- internos -------------------------------------------------------------------------------


def _domain_raw(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {API_FIELDS[name]: value for name, value in raw.items() if name in API_FIELDS}


def _check_options() -> NormalizeOptions:
    return NormalizeOptions(date_formats=(*DEFAULT_DATE_FORMATS, FORM_DATE_FORMAT))


def _form_options(channel: Channel) -> NormalizeOptions:
    try:
        base = options_for(channel).normalize
    except ChannelConfigError as exc:
        raise RegistrationRejected({"channel": [str(exc)]}) from exc
    formats = base.date_formats
    if FORM_DATE_FORMAT not in formats:
        formats = (*formats, FORM_DATE_FORMAT)
    return NormalizeOptions(date_formats=formats, aliases=base.aliases)


def _clean(raw: Mapping[str, Any], channel: Channel, race: Race) -> CanonicalRegistration:
    row = normalize(raw, _form_options(channel))
    issues = [*row.issues, *validate(row, race.date)]
    if issues:
        raise RegistrationRejected(_errors_by_field(issues))
    return row.values


def _errors_by_field(issues: list[Issue]) -> dict[str, list[str]]:
    errors: dict[str, list[str]] = {}
    for issue in issues:
        errors.setdefault(DOMAIN_TO_API.get(issue.field, "non_field_errors"), []).append(
            issue.message
        )
    return errors


__all__ = [
    "AlreadyRegistered",
    "CheckResult",
    "Outcome",
    "RegistrationRejected",
    "UpdateResult",
    "check",
    "register_in_app",
    "search",
    "update_registration",
]
