"""Inscribir: el núcleo común a la importación y al alta en la tienda.

Una fila ya normalizada y validada, más el canal por el que llega, da uno de estos resultados:

- alta con dorsal, o en lista de espera si las confirmadas ya llenan el aforo;
- actualización (o sin cambios) si ya estaba y llegó por este mismo canal; el dorsal no cambia;
- «ya inscrita» si ya estaba por otro canal: no se crea otra ni se sobrescribe nada, se
  devuelven las diferencias para que la organización hable con el corredor;
- y, en un alta, el enlace al posible duplicado (mismo nombre y fecha con otro email).

Todo pasa con la carrera bloqueada (`select_for_update`): dorsales, plazas y posiciones de
espera se reparten dentro de esa transacción, así que dos altas a la vez no se pisan. La red
de seguridad son los únicos filtrados de la base de datos. En SQLite `select_for_update` no hace
nada; ahí serializa la transacción inmediata de los settings.

Un dorsal no se reutiliza nunca: una baja lo conserva y `Race.next_bib` solo sube.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum

from django.db import transaction
from django.db.models import Max

from races.domain.identity import Difference, differences, name_key
from races.domain.normalize import CanonicalRegistration
from races.models import Channel, Race, Registration

Status = Registration.Status
REQUIRED = ("first_name", "last_name", "email", "email_norm", "birth_date", "shirt_size")


class Outcome(str, Enum):
    CREATED = "alta"
    WAITLISTED = "en_espera"
    UPDATED = "actualizada"
    UNCHANGED = "sin_cambios"
    ALREADY_REGISTERED = "ya_inscrita"


@dataclass(frozen=True)
class RegisterResult:
    outcome: Outcome
    registration: Registration
    # Con «ya inscrita»: lo que trae el canal nuevo distinto de lo guardado (no se aplica).
    # Con «actualizada»: lo que se ha cambiado.
    differences: tuple[Difference, ...] = ()
    possible_duplicate_of: Registration | None = None
    # Estaba marcada como ausente de su listado y ha vuelto a aparecer: la marca se quita.
    reappeared: bool = False


@dataclass(frozen=True)
class WithdrawResult:
    registration: Registration
    promoted: list[Registration]
    already_withdrawn: bool = False


class RaceRegistrar:
    """Inscribe en una carrera bloqueada en la transacción en curso.

    No se crea a mano: se usa `race_registrar(race_id)`, que bloquea la carrera y guarda el
    siguiente dorsal al salir. Lleva la cuenta de confirmadas y de la siguiente posición de espera
    para no consultarlas en cada fila. Las búsquedas por email y por nombre son métodos aparte para
    que una importación grande pueda sustituirlas por un índice en memoria.
    """

    def __init__(self, race: Race):
        self.race = race
        self._initial_next_bib = race.next_bib
        registrations = Registration.objects.filter(race=race)
        self._confirmed = registrations.filter(status=Status.CONFIRMED).count()
        last_position = registrations.aggregate(last=Max("waitlist_position"))["last"]
        self._next_position = (last_position or 0) + 1

    # --- búsquedas --------------------------------------------------------------------------

    def find_by_email(self, email_norm: str) -> Registration | None:
        return Registration.objects.filter(race=self.race, email_norm=email_norm).first()

    def find_possible_duplicate(self, values: CanonicalRegistration) -> Registration | None:
        return find_possible_duplicate(self.race.pk, values)

    def has_also_channel(self, registration: Registration, channel: Channel) -> bool:
        return registration.also_channels.filter(pk=channel.pk).exists()

    def remember(self, registration: Registration) -> None:
        """Se llama tras guardar un alta: un índice en memoria la apunta aquí."""

    # --- casos de uso -----------------------------------------------------------------------

    def register(
        self, values: CanonicalRegistration, channel: Channel, *, note_channel: bool = True
    ) -> RegisterResult:
        """`values` tiene que venir ya validada (`rules.validate` sin incidencias).

        Con `note_channel=False` una «ya inscrita» no apunta el canal nuevo en `also_channels`:
        es para el alta en la tienda, que avisa y no guarda.
        """
        missing = [name for name in REQUIRED if getattr(values, name) is None]
        if missing:
            raise ValueError(f"Fila sin validar: faltan {', '.join(missing)}.")

        existing = self.find_by_email(values.email_norm)
        if existing is None:
            return self._create(values, channel)
        if existing.channel_id == channel.id:
            return self._update(existing, values)
        found = differences(as_canonical(existing), values)
        if note_channel and not self.has_also_channel(existing, channel):
            existing.also_channels.add(channel)
        return RegisterResult(Outcome.ALREADY_REGISTERED, existing, differences=found)

    def withdraw(self, registration: Registration) -> WithdrawResult:
        """Baja manual, o confirmación de la baja de un ausente: es lo mismo.

        Conserva el dorsal (no se reutiliza) y libera la plaza para la lista de espera.
        """
        if registration.status == Status.WITHDRAWN:
            return WithdrawResult(registration, promoted=[], already_withdrawn=True)
        if registration.status == Status.CONFIRMED:
            self._confirmed -= 1
        registration.status = Status.WITHDRAWN
        registration.waitlist_position = None
        registration.save(update_fields=["status", "waitlist_position", "updated_at"])
        return WithdrawResult(registration, promoted=self.fill_vacancies())

    def change_capacity(self, capacity: int | None) -> list[Registration]:
        """Bajar el aforo no saca a nadie (sus dorsales ya están dados); subirlo promociona."""
        if capacity is not None and capacity < 1:
            raise ValueError("El aforo tiene que ser al menos 1.")
        self.race.capacity = capacity
        self.race.save(update_fields=["capacity"])
        return self.fill_vacancies()

    def fill_vacancies(self) -> list[Registration]:
        """Pasa a confirmadas, por orden de llegada, tantas en espera como plazas libres haya."""
        promoted = []
        while self._has_room():
            first = (
                Registration.objects.filter(race=self.race, status=Status.WAITLISTED)
                .order_by("waitlist_position")
                .first()
            )
            if first is None:
                break
            first.status = Status.CONFIRMED
            first.waitlist_position = None
            first.bib = self._take_bib()
            first.save(update_fields=["status", "waitlist_position", "bib", "updated_at"])
            self._confirmed += 1
            promoted.append(first)
        return promoted

    def flush(self) -> None:
        if self.race.next_bib != self._initial_next_bib:
            self.race.save(update_fields=["next_bib"])
            self._initial_next_bib = self.race.next_bib

    # --- internos ---------------------------------------------------------------------------

    def _has_room(self) -> bool:
        return self.race.capacity is None or self._confirmed < self.race.capacity

    def _take_bib(self) -> int:
        bib = self.race.next_bib
        self.race.next_bib += 1
        return bib

    def _create(self, values: CanonicalRegistration, channel: Channel) -> RegisterResult:
        duplicate_of = self.find_possible_duplicate(values)
        registration = Registration(
            race=self.race,
            channel=channel,
            possible_duplicate_of=duplicate_of,
            **registration_fields(values),
        )
        if self._has_room():
            registration.status = Status.CONFIRMED
            registration.bib = self._take_bib()
            self._confirmed += 1
            outcome = Outcome.CREATED
        else:
            registration.status = Status.WAITLISTED
            registration.waitlist_position = self._next_position
            self._next_position += 1
            outcome = Outcome.WAITLISTED
        registration.save()
        self.remember(registration)
        return RegisterResult(outcome, registration, possible_duplicate_of=duplicate_of)

    def _update(self, registration: Registration, values: CanonicalRegistration) -> RegisterResult:
        """Mismo canal: se aplican los cambios. Estado, dorsal y posición no se tocan."""
        found = differences(as_canonical(registration), values)
        changed = []
        if found:
            for name, value in registration_fields(values).items():
                if getattr(registration, name) != value:
                    setattr(registration, name, value)
                    changed.append(name)
        reappeared = registration.missing_since is not None
        if reappeared:
            registration.missing_since = None
            changed.append("missing_since")
        if changed:
            registration.save(update_fields=[*changed, "updated_at"])
        outcome = Outcome.UPDATED if found else Outcome.UNCHANGED
        return RegisterResult(outcome, registration, differences=found, reappeared=reappeared)


@contextmanager
def race_registrar(
    race_id: int, registrar_class: type[RaceRegistrar] = RaceRegistrar
) -> Iterator[RaceRegistrar]:
    """Transacción con la carrera bloqueada hasta el final; un error lo deshace todo."""
    with transaction.atomic():
        race = Race.objects.select_for_update().get(pk=race_id)
        registrar = registrar_class(race)
        yield registrar
        registrar.flush()


def register(
    race_id: int, channel: Channel, values: CanonicalRegistration, *, note_channel: bool = True
) -> RegisterResult:
    with race_registrar(race_id) as registrar:
        return registrar.register(values, channel, note_channel=note_channel)


def withdraw(registration_id: int) -> WithdrawResult:
    race_id = Registration.objects.values_list("race_id", flat=True).get(pk=registration_id)
    with race_registrar(race_id) as registrar:
        # Se vuelve a leer con la carrera ya bloqueada: el estado puede haber cambiado.
        registration = Registration.objects.get(pk=registration_id)
        return registrar.withdraw(registration)


def change_capacity(race_id: int, capacity: int | None) -> list[Registration]:
    with race_registrar(race_id) as registrar:
        return registrar.change_capacity(capacity)


def find_possible_duplicate(race_id: int, values: CanonicalRegistration) -> Registration | None:
    """La más antigua con el mismo nombre normalizado y fecha de nacimiento, y otro email."""
    queryset = Registration.objects.filter(
        race_id=race_id,
        birth_date=values.birth_date,
        search_text=name_key(values.first_name, values.last_name),
    )
    if values.email_norm:
        queryset = queryset.exclude(email_norm=values.email_norm)
    return queryset.order_by("id").first()


def as_canonical(registration: Registration) -> CanonicalRegistration:
    return CanonicalRegistration(
        first_name=registration.first_name,
        last_name=registration.last_name,
        email=registration.email,
        email_norm=registration.email_norm,
        birth_date=registration.birth_date,
        phone=registration.phone or None,
        shirt_size=registration.shirt_size,
    )


def registration_fields(values: CanonicalRegistration) -> dict:
    """Valores canónicos → campos de `Registration`, con su `search_text`."""
    return {
        "first_name": values.first_name,
        "last_name": values.last_name,
        "email": values.email,
        "email_norm": values.email_norm,
        "birth_date": values.birth_date,
        "phone": values.phone or "",
        "shirt_size": values.shirt_size,
        "search_text": name_key(values.first_name, values.last_name),
    }
