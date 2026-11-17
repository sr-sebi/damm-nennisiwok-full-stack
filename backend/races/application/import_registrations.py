"""Importar un listado: cola por carrera, lectura, inscripción por lotes y ausencias.

1. **Cola**. `submit_import` guarda el fichero en una importación `en_cola` y encola la tarea.
   `process_queue(race_id)` coge la siguiente con la carrera bloqueada: solo puede haber una
   `procesando` por carrera (lo garantiza un único filtrado en la base de datos), en orden de
   subida. Carreras distintas van en paralelo. Una que lleva un rato sin avanzar se da por caída
   y libera la cola.
2. **Lectura**. Se lee y se valida todo el fichero antes de escribir nada: un fichero ilegible
   no deja ninguna inscripción a medias.
3. **Inscripción por lotes** de `LOT_SIZE` filas, cada lote en su transacción con la carrera
   bloqueada y con el progreso y los contadores guardados en esa misma transacción. Desde fuera
   se ve el avance; si algo falla a mitad, lo guardado es coherente («X de Y filas») y volver a
   importar el fichero lo completa, porque inscribir es idempotente por email.
4. **Ausencias**. Las plataformas mandan el listado completo: quien llegó por ese canal y no está
   en el fichero queda marcado (`missing_since`), sin baja automática. La tienda no manda el
   listado completo (y sus altas en la app no salen en su CSV), así que a ella no se le aplica.

Las incidencias llevan una huella: las que ya salieron en la importación anterior del mismo canal
se marcan como vistas (`is_new=False`), para que el informe de cada noche no repita lo mismo.

Los logs solo llevan ids, líneas y cifras: nunca emails, teléfonos ni el texto de una excepción
(el de un error de base de datos puede incluir los valores de la fila).
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import traceback
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from races.application.channel_options import ChannelConfigError, options_for
from races.application.register import Outcome, RaceRegistrar, RegisterResult, race_registrar
from races.domain.identity import describe_differences, name_key
from races.domain.issues import Issue, raw_text
from races.domain.normalize import CanonicalRegistration, is_blank, normalize
from races.domain.rules import validate
from races.infrastructure.sources import SourceError, read_registrations
from races.models import Channel, ImportBatch, ImportIssue, Race, Registration

logger = logging.getLogger(__name__)

LOT_SIZE = 500
# Tope de valores en un `__in`: SQL Server admite 2.100 parámetros por consulta.
IN_CHUNK = 500

Batch = ImportBatch.Status
Kind = ImportIssue.Kind

COUNTER_FOR = {
    Outcome.CREATED: "created",
    Outcome.WAITLISTED: "waitlisted",
    Outcome.UPDATED: "updated",
    Outcome.UNCHANGED: "unchanged",
    Outcome.ALREADY_REGISTERED: "already_registered",
}
COUNTERS = (
    "created",
    "waitlisted",
    "updated",
    "unchanged",
    "repeated",
    "already_registered",
    "possible_duplicates",
    "rejected",
    "blank",
)


class ImportAborted(Exception):
    """La importación ya no está en marcha (se dio por caída): este proceso no sigue."""


# --- cola ---------------------------------------------------------------------------------------


def submit_import(race: Race, channel: Channel, uploaded_file) -> ImportBatch:
    """Guarda el fichero y lo deja en cola; la tarea arranca al confirmar la transacción."""
    from races.tasks import process_imports  # la tarea importa este módulo

    batch = ImportBatch.objects.create(
        race=race,
        channel=channel,
        file=uploaded_file,
        original_filename=uploaded_file.name[:255],
    )
    logger.info("Importación %s: en cola (carrera %s, canal %s)", batch.pk, race.pk, channel.code)
    transaction.on_commit(lambda: process_imports.delay(race.pk))
    return batch


def process_queue(race_id: int) -> None:
    """Procesa las importaciones en cola de la carrera, una tras otra, hasta vaciarla."""
    while (batch_id := claim_next(race_id)) is not None:
        run_batch(batch_id)


def claim_next(race_id: int) -> int | None:
    """La siguiente en cola pasa a `procesando`, si no hay otra en marcha (o la que hay, cayó)."""
    with transaction.atomic():
        if not Race.objects.select_for_update().filter(pk=race_id).exists():
            return None
        now = timezone.now()
        current = ImportBatch.objects.filter(race_id=race_id, status=Batch.PROCESSING).first()
        if current is not None:
            if current.updated_at > now - stale_after():
                return None
            _give_up(current, now)
        batch = (
            ImportBatch.objects.filter(race_id=race_id, status=Batch.QUEUED)
            .order_by("created_at", "id")
            .first()
        )
        if batch is None:
            return None
        batch.status = Batch.PROCESSING
        batch.started_at = now
        batch.save(update_fields=["status", "started_at", "updated_at"])
        return batch.pk


def stale_after() -> timedelta:
    return timedelta(minutes=settings.IMPORT_STALE_MINUTES)


def _give_up(batch: ImportBatch, now) -> None:
    since = timezone.localtime(batch.updated_at)
    batch.status = Batch.ERROR
    batch.finished_at = now
    batch.error = (
        f"Se ha dado por caída: no avanzaba desde las {since:%H:%M} del {since:%d/%m/%Y}. "
        f"{_saved_so_far(batch)}"
    )
    batch.save(update_fields=["status", "finished_at", "error", "updated_at"])
    logger.warning("Importación %s: dada por caída (sin avances desde %s)", batch.pk, since)


def _saved_so_far(batch: ImportBatch) -> str:
    if not batch.processed_rows:
        return "No se ha guardado ninguna fila; vuelve a importar el fichero."
    return (
        f"Se han guardado {batch.processed_rows} de {batch.total_rows} filas; vuelve a importar "
        "el mismo fichero para completarla (lo ya guardado no se duplica)."
    )


# --- una importación ----------------------------------------------------------------------------


@dataclass(frozen=True)
class PreparedRow:
    line: int
    state: str  # "vacia" | "rechazada" | "repetida" | "valida"
    values: CanonicalRegistration
    issues: tuple[Issue, ...]
    raw: Mapping[str, Any]


def run_batch(batch_id: int) -> None:
    batch = ImportBatch.objects.select_related("race", "channel").get(pk=batch_id)
    started = time.monotonic()
    logger.info(
        "Importación %s: empieza (carrera %s, canal %s)",
        batch.pk,
        batch.race_id,
        batch.channel.code,
    )
    try:
        options = options_for(batch.channel)
        with batch.file.open("rb") as file:
            result = read_registrations(file, options.source)
    except (SourceError, ChannelConfigError) as exc:
        _finish(batch, Batch.ERROR, str(exc))
        logger.info("Importación %s: fichero no válido (%s)", batch.pk, type(exc).__name__)
        return
    except Exception as exc:
        _log_unexpected(batch, exc)
        _finish(
            batch, Batch.ERROR, "No se ha podido leer el fichero. Comprueba que no está dañado."
        )
        return

    rows, present = prepare(result.records, options.normalize, batch.race.date)
    batch.total_rows = len(rows)
    batch.save(update_fields=["total_rows", "updated_at"])
    logger.info("Importación %s: %s filas leídas", batch.pk, len(rows))

    seen_before = previous_fingerprints(batch)
    try:
        for start in range(0, len(rows), LOT_SIZE):
            save_lot(batch, rows[start : start + LOT_SIZE], seen_before)
        if batch.channel.kind == Channel.Kind.ONLINE:
            mark_missing(batch, present, seen_before)
    except ImportAborted:
        logger.warning("Importación %s: ya no estaba en marcha; se deja", batch.pk)
        return
    except Exception as exc:
        _log_unexpected(batch, exc)
        batch.refresh_from_db()
        _finish(batch, Batch.ERROR, f"Error inesperado. {_saved_so_far(batch)}")
        return

    _finish(batch, Batch.DONE)
    counts = ", ".join(f"{name}={getattr(batch, name)}" for name in (*COUNTERS, "missing"))
    logger.info(
        "Importación %s: hecha en %.1f s (%s)", batch.pk, time.monotonic() - started, counts
    )


def prepare(records: Iterable, options, race_date) -> tuple[list[PreparedRow], set[str]]:
    """Normaliza y valida todo el fichero sin escribir nada.

    Una fila válida con el email de otra válida anterior del mismo fichero es «repetida»: cuenta
    la primera. Devuelve también los emails presentes en el listado, incluidos los de filas
    rechazadas por otro motivo: quien está en el listado con un dato mal no ha desaparecido de él.
    """
    rows: list[PreparedRow] = []
    present: set[str] = set()
    valid_emails: set[str] = set()
    for record in records:
        if not record.issues and is_blank(record.values):
            rows.append(PreparedRow(record.line, "vacia", CanonicalRegistration(), (), {}))
            continue
        normalized = normalize(record.values, options)
        values = normalized.values
        issues = (*record.issues, *normalized.issues, *validate(normalized, race_date))
        if values.email_norm:
            present.add(values.email_norm)
        if issues:
            state = "rechazada"
        elif values.email_norm in valid_emails:
            state = "repetida"
        else:
            state = "valida"
            valid_emails.add(values.email_norm)
        rows.append(PreparedRow(record.line, state, values, tuple(issues), record.values))
    return rows, present


def save_lot(batch: ImportBatch, lot: Sequence[PreparedRow], seen_before: set[str]) -> None:
    with race_registrar(batch.race_id, ImportRegistrar) as registrar:
        _ensure_running(batch)
        registrar.prefetch(row.values for row in lot if row.state == "valida")
        counts: Counter[str] = Counter()
        issues: list[ImportIssue] = []
        channel_names = dict(Channel.objects.values_list("id", "name"))
        for row in lot:
            if row.state == "vacia":
                counts["blank"] += 1
            elif row.state == "repetida":
                counts["repeated"] += 1
            elif row.state == "rechazada":
                counts["rejected"] += 1
                issues.extend(_rejected_issues(batch, row, seen_before))
            else:
                result = registrar.register(row.values, batch.channel)
                counts[COUNTER_FOR[result.outcome]] += 1
                if result.outcome is Outcome.ALREADY_REGISTERED:
                    issues.append(
                        _already_registered_issue(batch, row, result, seen_before, channel_names)
                    )
                if result.possible_duplicate_of is not None:
                    counts["possible_duplicates"] += 1
                    issues.append(_possible_duplicate_issue(batch, row, result, seen_before))
        ImportIssue.objects.bulk_create(issues)
        batch.processed_rows += len(lot)
        for name, value in counts.items():
            setattr(batch, name, getattr(batch, name) + value)
        batch.save(update_fields=["processed_rows", *COUNTERS, "updated_at"])


def mark_missing(batch: ImportBatch, present: set[str], seen_before: set[str]) -> None:
    """Quien llegó por este canal y no está en el listado completo queda marcado, sin baja."""
    with race_registrar(batch.race_id):
        _ensure_running(batch)
        today = timezone.localdate()
        candidates = (
            Registration.objects.filter(race_id=batch.race_id, channel=batch.channel)
            .exclude(status=Registration.Status.WITHDRAWN)
            .only("id", "email_norm", "missing_since", "bib", "status")
            .order_by("id")
        )
        missing = [reg for reg in candidates if reg.email_norm not in present]
        to_mark = [reg.pk for reg in missing if reg.missing_since is None]
        now = timezone.now()
        for chunk in chunks(to_mark, IN_CHUNK):
            Registration.objects.filter(pk__in=chunk).update(missing_since=today, updated_at=now)
        issues = []
        for reg in missing:
            since = reg.missing_since or today
            fingerprint = _fingerprint(Kind.MISSING, reg.pk)
            where = f"con el dorsal {reg.bib}" if reg.bib else "en lista de espera"
            issues.append(
                ImportIssue(
                    batch=batch,
                    kind=Kind.MISSING,
                    registration_id=reg.pk,
                    message=(
                        f"No aparece en el listado de {batch.channel.name} desde el "
                        f"{since:%d/%m/%Y}. Sigue inscrita {where}: si se ha dado de baja en la "
                        "plataforma, confirma la baja."
                    ),
                    fingerprint=fingerprint,
                    is_new=fingerprint not in seen_before,
                )
            )
        ImportIssue.objects.bulk_create(issues)
        batch.missing = len(missing)
        batch.save(update_fields=["missing", "updated_at"])


def previous_fingerprints(batch: ImportBatch) -> set[str]:
    """Huellas de la última importación terminada del mismo canal en la carrera.

    Se cargan en un set de Python y no se comparan con `__in`: pueden ser miles.
    """
    previous = (
        ImportBatch.objects.filter(
            race_id=batch.race_id, channel_id=batch.channel_id, status=Batch.DONE, id__lt=batch.pk
        )
        .order_by("-id")
        .first()
    )
    if previous is None:
        return set()
    return set(previous.issues.values_list("fingerprint", flat=True))


def _ensure_running(batch: ImportBatch) -> None:
    """Con la carrera ya bloqueada: si otro proceso la dio por caída, este no sigue escribiendo."""
    if not ImportBatch.objects.filter(pk=batch.pk, status=Batch.PROCESSING).exists():
        raise ImportAborted


def _finish(batch: ImportBatch, status: str, error: str = "") -> None:
    now = timezone.now()
    ImportBatch.objects.filter(pk=batch.pk, status=Batch.PROCESSING).update(
        status=status, error=error, finished_at=now, updated_at=now
    )
    batch.status, batch.error, batch.finished_at = status, error, now


def _log_unexpected(batch: ImportBatch, exc: Exception) -> None:
    # Solo el tipo y la pila: el texto de la excepción puede llevar valores de la fila.
    stack = "".join(traceback.format_tb(exc.__traceback__))
    logger.error("Importación %s: error inesperado %s\n%s", batch.pk, type(exc).__name__, stack)


# --- incidencias --------------------------------------------------------------------------------


def _rejected_issues(batch, row: PreparedRow, seen_before: set[str]) -> list[ImportIssue]:
    raw = _raw_json(row.raw)
    issues = []
    for issue in row.issues:
        fingerprint = _fingerprint(Kind.REJECTED, issue.code.value, issue.field, raw)
        issues.append(
            ImportIssue(
                batch=batch,
                kind=Kind.REJECTED,
                line=row.line,
                code=issue.code.value,
                field=issue.field,
                group_value=issue.group_value[:210],
                message=issue.message,
                raw=raw,
                fingerprint=fingerprint,
                is_new=fingerprint not in seen_before,
            )
        )
    return issues


def _already_registered_issue(
    batch, row, result: RegisterResult, seen_before, channel_names
) -> ImportIssue:
    existing = result.registration
    channel = channel_names.get(existing.channel_id, "otro canal")
    where = f"dorsal {existing.bib}" if existing.bib else existing.get_status_display().lower()
    differences = describe_differences(result.differences)
    fingerprint = _fingerprint(Kind.ALREADY_REGISTERED, existing.pk, differences)
    return ImportIssue(
        batch=batch,
        kind=Kind.ALREADY_REGISTERED,
        line=row.line,
        registration=existing,
        message=f"Ya inscrita por {channel} ({where}): no se le ha dado otro dorsal.",
        differences=differences,
        raw=_raw_json(row.raw),
        fingerprint=fingerprint,
        is_new=fingerprint not in seen_before,
    )


def _possible_duplicate_issue(batch, row, result: RegisterResult, seen_before) -> ImportIssue:
    new, other = result.registration, result.possible_duplicate_of
    where = f"dorsal {other.bib}" if other.bib else other.get_status_display().lower()
    fingerprint = _fingerprint(Kind.POSSIBLE_DUPLICATE, new.pk, other.pk)
    return ImportIssue(
        batch=batch,
        kind=Kind.POSSIBLE_DUPLICATE,
        line=row.line,
        registration=new,
        message=(
            f"Mismo nombre y fecha de nacimiento que {other.first_name} {other.last_name} "
            f"({where}), con otro email. Se ha inscrito aparte: revisa si es la misma persona."
        ),
        raw=_raw_json(row.raw),
        fingerprint=fingerprint,
        is_new=fingerprint not in seen_before,
    )


def _raw_json(raw: Mapping[str, Any]) -> str:
    return json.dumps({k: raw_text(v) for k, v in raw.items()}, ensure_ascii=False, sort_keys=True)


def _fingerprint(*parts: Any) -> str:
    """Igual para la misma incidencia aunque cambie su línea en el fichero."""
    text = "\x1f".join(str(part) for part in parts)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- inscribir por lotes ------------------------------------------------------------------------


class ImportRegistrar(RaceRegistrar):
    """Inscribir con las búsquedas de un lote cargadas de antemano.

    Sin esto, cada fila son una o dos consultas (20.000 filas del maratón = 40.000). Cada lote
    carga las inscripciones de sus emails y de sus fechas de nacimiento en `__in` de como mucho
    `IN_CHUNK` valores, y apunta en el índice las altas que va creando. Con la carrera bloqueada
    durante el lote, nadie más la cambia mientras tanto.
    """

    def __init__(self, race: Race):
        super().__init__(race)
        self._by_email: dict[str, Registration] = {}
        self._by_name: dict[tuple, list[Registration]] = defaultdict(list)
        self._also: set[tuple[int, int]] = set()

    def prefetch(self, rows: Iterable[CanonicalRegistration]) -> None:
        rows = list(rows)
        emails = sorted({row.email_norm for row in rows})
        dates = sorted({row.birth_date for row in rows})
        base = Registration.objects.filter(race=self.race)
        for chunk in chunks(emails, IN_CHUNK):
            for reg in base.filter(email_norm__in=chunk):
                self._by_email[reg.email_norm] = reg
        for chunk in chunks(dates, IN_CHUNK):
            for reg in base.filter(birth_date__in=chunk).order_by("id"):
                self._by_name[(reg.search_text, reg.birth_date)].append(reg)
        ids = [reg.pk for reg in self._by_email.values()]
        through = Registration.also_channels.through.objects
        for chunk in chunks(ids, IN_CHUNK):
            pairs = through.filter(registration_id__in=chunk).values_list(
                "registration_id", "channel_id"
            )
            self._also.update(pairs)

    def find_by_email(self, email_norm: str) -> Registration | None:
        return self._by_email.get(email_norm)

    def find_possible_duplicate(self, values: CanonicalRegistration) -> Registration | None:
        key = (name_key(values.first_name, values.last_name), values.birth_date)
        for reg in self._by_name.get(key, ()):
            if reg.email_norm != values.email_norm:
                return reg
        return None

    def has_also_channel(self, registration: Registration, channel: Channel) -> bool:
        return (registration.pk, channel.pk) in self._also

    def remember(self, registration: Registration) -> None:
        self._by_email[registration.email_norm] = registration
        self._by_name[(registration.search_text, registration.birth_date)].append(registration)


def chunks(values: Sequence, size: int) -> Iterable[Sequence]:
    for start in range(0, len(values), size):
        yield values[start : start + size]
