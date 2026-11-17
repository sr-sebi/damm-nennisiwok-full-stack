"""Enviar los emails de confirmación: bandeja de salida, reintentos, ritmo y reserva.

Lo mismo para el botón, la tarea y el envío programado: todos llaman a
`send_pending(race_id, load_send_config())`.

**A quién**: inscripciones confirmadas con dorsal, sin email enviado, sin marca de posible
duplicado y en carreras que no se han celebrado (la fecha de la carrera es hoy o después). Quien
sale de la lista de espera pasa a confirmada con dorsal y entra sola en la lista siguiente.

**Bandeja de salida** (`Notification`, una fila por mensaje lógico). `enqueue` crea la fila
pendiente de cada destinataria que aún no la tiene, con la clave `confirmacion-{id}-{dorsal}`, que
es la misma en todos los intentos. La base de datos es la fuente de verdad de «ya enviado»: el
proveedor solo recuerda la clave 24 h.

**Reserva**: antes de enviar, un UPDATE condicional pasa la fila de `pendiente` (o de `enviando`
con el plazo vencido) a `enviando`, con `next_attempt_at = ahora + RESERVA` como plazo y el
número de intentos que se leyó. Si dos envíos a la vez (botón y programado) intentan reservar la
misma fila, la base de datos aplica un UPDATE y el otro no encuentra la fila en ese estado (en
PostgreSQL y en SQL Server el segundo UPDATE espera al primero y vuelve a evaluar la condición
sobre la fila nueva; SQLite serializa las escrituras): solo uno la envía. No hace falta
`select_for_update(skip_locked=...)`. Una fila `enviada` no cumple la condición: es la comprobación
en la base de datos antes de enviar. Si el worker muere a mitad, la fila se queda en `enviando` y,
al vencer el plazo, otro envío la retoma con la misma clave (el proveedor no la manda dos veces).
El resultado se guarda con otro UPDATE condicional a que la reserva siga siendo suya (mismo plazo).

**Resultados** (`races.infrastructure.email`):

- `Accepted` → `enviada`, con el id del proveedor.
- `RetryLater` sin espera (5xx, sin respuesta, red) → vuelve a `pendiente` con espera
  exponencial con jitter; agotados `max_attempts` intentos → `fallida` con el motivo.
- `RetryLater(after_seconds)` (429) → espera exactamente eso, no gasta intento, y se pausa todo
  el envío ese tiempo.
- `Rejected` → `fallida` con el motivo, sin reintentar.
- `ConfigError` → se para el lote; la fila vuelve a `pendiente` sin gastar el intento.

**Ritmo**: un solo hilo reserva y reparte a un ritmo fijo (`rate_per_second`, por debajo de las
20/s del proveedor) y `SEND_THREADS` hilos envían, porque una de cada diez respuestas tarda 3 s y,
de uno en uno, 20.000 emails serían horas. Las esperas cortas (reintentos que vencen en menos de
`MAX_INLINE_WAIT`) se esperan dentro del mismo envío; las más largas quedan para el siguiente.

Los logs llevan ids y cifras: nunca emails, nombres ni el motivo que da el proveedor.
"""

from __future__ import annotations

import logging
import queue
import random
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta

from django.db import IntegrityError, connection, transaction
from django.db.models import Count, Min, Q, QuerySet
from django.utils import timezone

from races.domain.email_template import DEFAULT_BODY, DEFAULT_SUBJECT, render, template_errors
from races.infrastructure.email import (
    Accepted,
    ConfigError,
    EmailProvider,
    Rejected,
    RetryLater,
    SendResult,
    UnknownProvider,
    active_provider_name,
    get_provider,
)
from races.models import Notification, Race, Registration

logger = logging.getLogger(__name__)

N = Notification.Status

DEFAULT_RATE_PER_SECOND = 15.0
DEFAULT_MAX_ATTEMPTS = 6
# Plazo de la reserva: de sobra para una petición (timeout de 10 s) y su resultado.
SENDING_LEASE = timedelta(seconds=60)
# Espera entre intentos: 2, 4, 8, 16, 32 s… (× 0,5–1,5 de jitter), con tope.
BASE_DELAY_SECONDS = 2.0
MAX_DELAY_SECONDS = 300.0
# Reintentos que vencen antes de esto se esperan en el mismo envío.
MAX_INLINE_WAIT = timedelta(seconds=120)
SEND_THREADS = 8
FETCH_SIZE = 100
CREATE_CHUNK = 500
FAILURES_SHOWN = 100


@dataclass(frozen=True)
class SendConfig:
    subject: str = DEFAULT_SUBJECT
    body: str = DEFAULT_BODY
    rate_per_second: float = DEFAULT_RATE_PER_SECOND
    max_attempts: int = DEFAULT_MAX_ATTEMPTS


def load_send_config() -> SendConfig:
    """La configuración de envío. Por ahora, los valores por defecto."""
    return SendConfig()


@dataclass
class SendSummary:
    sent: int = 0
    # Siguen pendientes al terminar: se reintentan en el próximo envío.
    retry_later: int = 0
    # Pasadas a `fallida` en este envío (rechazadas o sin intentos).
    failed: int = 0
    # Reservadas por otro envío a la vez, o pendientes que ya no se envían (baja, en espera,
    # posible duplicado o carrera pasada).
    skipped: int = 0
    config_error: bool = False
    config_error_reason: str = ""
    # Respuestas «reintentar» (5xx, sin respuesta, red) y «espera» (429) durante el envío.
    retries: int = 0
    throttled: int = 0
    next_attempt_at: datetime | None = None

    def as_dict(self) -> dict:
        data = asdict(self)
        if self.next_attempt_at is not None:
            data["next_attempt_at"] = self.next_attempt_at.isoformat()
        return data


class CannotRetry(Exception):
    """No se puede reintentar este email. El mensaje es para el usuario."""


# --- a quién --------------------------------------------------------------------------------


def eligible_q(today: date, prefix: str = "") -> Q:
    """Confirmada con dorsal, sin marca de posible duplicado, en una carrera no celebrada."""
    return Q(
        **{
            f"{prefix}status": Registration.Status.CONFIRMED,
            f"{prefix}bib__isnull": False,
            f"{prefix}possible_duplicate_of__isnull": True,
            f"{prefix}race__date__gte": today,
        }
    )


def is_eligible(registration: Registration, race_date: date, today: date | None = None) -> bool:
    return (
        registration.status == Registration.Status.CONFIRMED
        and registration.bib is not None
        and registration.possible_duplicate_of_id is None
        and race_date >= (today or timezone.localdate())
    )


def ineligible_reason(registration: Registration, today: date | None = None) -> str:
    if registration.race.date < (today or timezone.localdate()):
        return "La carrera ya se ha celebrado: no se envían confirmaciones."
    if registration.status != Registration.Status.CONFIRMED or registration.bib is None:
        return "La inscripción ya no está confirmada (está de baja o en lista de espera)."
    if registration.possible_duplicate_of_id is not None:
        return "La inscripción tiene la marca de posible duplicado: revísala antes de enviar."
    return ""


def enqueue(race_id: int | None = None, today: date | None = None) -> int:
    """Crea la fila pendiente de cada destinataria que aún no tiene. Devuelve cuántas ha creado.

    En lotes de `CREATE_CHUNK`. Si otro envío a la vez crea la misma fila, el único de la clave lo
    para y ese lote se repite fila a fila.
    """
    today = today or timezone.localdate()
    missing = Registration.objects.filter(eligible_q(today), notifications__isnull=True)
    if race_id is not None:
        missing = missing.filter(race_id=race_id)
    rows = list(missing.order_by("id").values_list("id", "bib"))
    now = timezone.now()
    created = 0
    for start in range(0, len(rows), CREATE_CHUNK):
        objects = [
            Notification(
                registration_id=registration_id,
                idempotency_key=Notification.confirmation_key(registration_id, bib),
                next_attempt_at=now,
            )
            for registration_id, bib in rows[start : start + CREATE_CHUNK]
        ]
        try:
            with transaction.atomic():
                Notification.objects.bulk_create(objects)
            created += len(objects)
        except IntegrityError:
            for obj in objects:
                _, made = Notification.objects.get_or_create(
                    idempotency_key=obj.idempotency_key,
                    defaults={"registration_id": obj.registration_id, "next_attempt_at": now},
                )
                created += made
    return created


# --- estado para la pantalla ------------------------------------------------------------------


def race_status(race: Race) -> dict:
    """Cifras del envío de una carrera y las fallidas, con su motivo."""
    today = timezone.localdate()
    by_status = {
        row["status"]: row["n"]
        for row in Notification.objects.filter(registration__race=race)
        .values("status")
        .annotate(n=Count("id"))
    }
    pending = pending_count(race, today)
    held_duplicates = (
        Registration.objects.filter(
            race=race,
            status=Registration.Status.CONFIRMED,
            possible_duplicate_of__isnull=False,
        )
        .exclude(notifications__status=N.SENT)
        .count()
    )
    failures = (
        Notification.objects.filter(registration__race=race, status=N.FAILED)
        .select_related("registration__channel")
        .order_by("-updated_at", "-id")[:FAILURES_SHOWN]
    )
    return {
        "race": race.pk,
        "race_past": race.date < today,
        "provider": active_provider_name(),
        "pending": pending,
        "sending": by_status.get(N.SENDING, 0),
        "sent": by_status.get(N.SENT, 0),
        "failed": by_status.get(N.FAILED, 0),
        "held_duplicates": held_duplicates,
        "failures": list(failures),
    }


def pending_count(race: Race, today: date | None = None) -> int:
    """Destinatarias sin email enviado ni fallido: sin fila todavía, pendientes o enviándose."""
    today = today or timezone.localdate()
    return (
        Registration.objects.filter(eligible_q(today), race=race)
        .exclude(notifications__status__in=[N.SENT, N.FAILED])
        .count()
    )


# --- acciones ---------------------------------------------------------------------------------


def request_send(race: Race) -> int:
    """Encola el envío de la carrera (al confirmar la transacción). Devuelve cuántas hay."""
    from races.tasks import send_confirmations  # la tarea importa este módulo

    pending = pending_count(race)
    if pending:
        transaction.on_commit(lambda: send_confirmations.delay(race.pk))
    return pending


def retry_failed(notification_id: int) -> Notification:
    """Una fallida vuelve a `pendiente` con los intentos a cero y la misma clave."""
    notification = Notification.objects.select_related("registration__race").get(pk=notification_id)
    if notification.status != N.FAILED:
        raise CannotRetry(
            f"Solo se puede reintentar un email fallido; este está «{notification.status}»."
        )
    reason = ineligible_reason(notification.registration)
    if reason:
        raise CannotRetry(reason)
    now = timezone.now()
    updated = Notification.objects.filter(pk=notification.pk, status=N.FAILED).update(
        status=N.PENDING, attempts=0, next_attempt_at=now, last_error="", updated_at=now
    )
    if not updated:
        raise CannotRetry("Este email ha cambiado de estado mientras tanto; vuelve a cargar.")
    notification.refresh_from_db()
    from races.tasks import send_confirmations

    race_id = notification.registration.race_id
    transaction.on_commit(lambda: send_confirmations.delay(race_id))
    logger.info("Notificación %s: reintento pedido a mano", notification.pk)
    return notification


# --- enviar -----------------------------------------------------------------------------------


def send_pending(
    race_id: int | None,
    config: SendConfig,
    *,
    provider: EmailProvider | None = None,
    threads: int | None = None,
) -> SendSummary:
    """Envía lo pendiente de una carrera (o de todas las no celebradas, con `None`)."""
    summary = SendSummary()
    problems = [
        *(f"Asunto: {e}" for e in template_errors(config.subject)),
        *(f"Cuerpo: {e}" for e in template_errors(config.body)),
    ]
    if config.rate_per_second <= 0:
        problems.append("El ritmo de envío tiene que ser mayor que 0 emails por segundo.")
    if config.max_attempts < 1:
        problems.append("Los intentos máximos tienen que ser al menos 1.")
    if provider is None and not problems:
        try:
            provider = get_provider()
        except UnknownProvider as exc:
            problems.append(str(exc))
    if problems:
        summary.config_error = True
        summary.config_error_reason = " ".join(problems)
        logger.warning("Confirmaciones (carrera %s): configuración no válida", race_id)
        return summary

    today = timezone.localdate()
    scope = Q() if race_id is None else Q(registration__race_id=race_id)
    created = enqueue(race_id, today)
    summary.skipped += (
        Notification.objects.filter(scope, status=N.PENDING).exclude(
            eligible_q(today, "registration__")
        )
    ).count()

    if threads is None:
        threads = SEND_THREADS
    if connection.vendor == "sqlite" or connection.in_atomic_block:
        # Los hilos abren otra conexión: en SQLite (y dentro de una transacción) no verían lo
        # mismo. De uno en uno.
        threads = 1
    started = time.monotonic()
    _Sender(provider, config, scope, today, summary, threads).run()

    remaining = Notification.objects.filter(
        scope, eligible_q(today, "registration__"), status=N.PENDING
    )
    summary.retry_later = remaining.count()
    summary.next_attempt_at = remaining.aggregate(first=Min("next_attempt_at"))["first"]
    logger.info(
        "Confirmaciones (carrera %s): %s nuevas en la bandeja, %s enviadas, %s fallidas, "
        "%s para más tarde, %s omitidas, %s reintentos, %s esperas (429)%s en %.1f s",
        race_id if race_id is not None else "todas",
        created,
        summary.sent,
        summary.failed,
        summary.retry_later,
        summary.skipped,
        summary.retries,
        summary.throttled,
        ", parado por configuración" if summary.config_error else "",
        time.monotonic() - started,
    )
    return summary


@dataclass(frozen=True)
class _Job:
    notification_id: int
    registration_id: int
    attempts: int  # ya contado este intento
    lease: datetime
    to: str
    subject: str
    body: str
    key: str


class _Pacer:
    """Reparte las peticiones a un ritmo fijo; un 429 lo pausa para todos."""

    def __init__(self, rate_per_second: float):
        self.interval = 1.0 / rate_per_second
        self.next_slot = time.monotonic()
        self.lock = threading.Lock()

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            slot = max(now, self.next_slot)
            self.next_slot = slot + self.interval
        if slot > now:
            time.sleep(slot - now)

    def pause(self, seconds: float) -> None:
        with self.lock:
            self.next_slot = max(self.next_slot, time.monotonic() + seconds)


@dataclass
class _Sender:
    provider: EmailProvider
    config: SendConfig
    scope: Q
    today: date
    summary: SendSummary
    threads: int
    stop: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    in_flight: int = 0

    def run(self) -> None:
        self.pacer = _Pacer(self.config.rate_per_second)
        self.slots = threading.Semaphore(self.threads)
        self.jobs: queue.Queue[_Job | None] = queue.Queue()
        workers = []
        if self.threads > 1:
            workers = [
                threading.Thread(target=self._worker, name=f"confirmaciones-{i}", daemon=True)
                for i in range(self.threads)
            ]
            for worker in workers:
                worker.start()
        try:
            self._dispatch()
        finally:
            for _ in workers:
                self.jobs.put(None)
            for worker in workers:
                worker.join()

    # --- reparto (un solo hilo) ---------------------------------------------------------------

    def _dispatch(self) -> None:
        while not self.stop.is_set():
            batch = list(self._due(timezone.now()))
            if not batch:
                if not self._wait_for_more():
                    return
                continue
            for notification in batch:
                if self.stop.is_set():
                    return
                self.slots.acquire()
                self.pacer.wait()
                job = None if self.stop.is_set() else self._claim(notification)
                if job is None:
                    self.slots.release()
                    continue
                with self.lock:
                    self.in_flight += 1
                if self.threads > 1:
                    self.jobs.put(job)
                else:
                    self._process(job)

    def _due(self, now: datetime) -> QuerySet[Notification]:
        return (
            Notification.objects.filter(
                self.scope,
                eligible_q(self.today, "registration__"),
                status__in=[N.PENDING, N.SENDING],
                next_attempt_at__lte=now,
            )
            .select_related("registration__race")
            .order_by("next_attempt_at", "id")[:FETCH_SIZE]
        )

    def _wait_for_more(self) -> bool:
        """Nada que enviar ahora. ¿Hay algo en marcha o un reintento que vence pronto?"""
        with self.lock:
            busy = self.in_flight > 0
        if busy:
            time.sleep(0.1)
            return True
        # Solo las pendientes: un `enviando` ajeno es de otro envío que sigue en marcha (si murió,
        # lo retomará el siguiente).
        first = Notification.objects.filter(
            self.scope, eligible_q(self.today, "registration__"), status=N.PENDING
        ).aggregate(first=Min("next_attempt_at"))["first"]
        if first is None:
            return False
        wait = first - timezone.now()
        if wait > MAX_INLINE_WAIT:
            return False
        time.sleep(min(1.0, max(0.05, wait.total_seconds())))
        return True

    def _claim(self, notification: Notification) -> _Job | None:
        """UPDATE condicional: solo un envío pasa la fila a `enviando`. Ver el docstring."""
        now = timezone.now()
        lease = now + SENDING_LEASE
        attempts = notification.attempts + 1
        claimed = Notification.objects.filter(
            pk=notification.pk,
            status__in=[N.PENDING, N.SENDING],
            next_attempt_at__lte=now,
            attempts=notification.attempts,
        ).update(
            status=N.SENDING,
            next_attempt_at=lease,
            attempts=attempts,
            provider=self.provider.name,
            updated_at=now,
        )
        if not claimed:
            self._count("skipped")
            return None
        registration = notification.registration
        race = registration.race
        values = {
            "nombre": registration.first_name,
            "dorsal": registration.bib,
            "carrera": race.name,
            "fecha": race.date.strftime("%d/%m/%Y"),
        }
        return _Job(
            notification_id=notification.pk,
            registration_id=registration.pk,
            attempts=attempts,
            lease=lease,
            to=registration.email,
            subject=render(self.config.subject, values),
            body=render(self.config.body, values),
            key=notification.idempotency_key,
        )

    # --- envío (uno o varios hilos) -----------------------------------------------------------

    def _worker(self) -> None:
        try:
            while (job := self.jobs.get()) is not None:
                self._process(job)
        finally:
            connection.close()  # cada hilo tiene su conexión

    def _process(self, job: _Job) -> None:
        try:
            if self.stop.is_set():
                # Parado por configuración mientras esperaba: se devuelve sin enviar.
                self._finish(job, status=N.PENDING, attempts=job.attempts - 1, delay=0)
                return
            try:
                result = self.provider.send(job.to, job.subject, job.body, job.key)
            except Exception as exc:  # un adaptador no debería lanzar; si lo hace, se reintenta
                logger.error(
                    "Notificación %s: el proveedor ha lanzado %s",
                    job.notification_id,
                    type(exc).__name__,
                )
                result = RetryLater(reason="Error inesperado al llamar al proveedor.")
            self._record(job, result)
        except Exception as exc:
            # Un error de base de datos al guardar: la reserva vence y otro envío la retoma.
            logger.error(
                "Notificación %s: no se ha podido guardar el resultado (%s)",
                job.notification_id,
                type(exc).__name__,
            )
        finally:
            with self.lock:
                self.in_flight -= 1
            self.slots.release()

    def _record(self, job: _Job, result: SendResult) -> None:
        if isinstance(result, Accepted):
            if self._finish(
                job, status=N.SENT, provider_id=result.provider_id, sent_at=timezone.now()
            ):
                self._count("sent")
        elif isinstance(result, RetryLater) and result.after_seconds is not None:
            # El proveedor pide esperar: no es un fallo y no gasta intento.
            self.pacer.pause(result.after_seconds)
            self._finish(
                job,
                status=N.PENDING,
                attempts=job.attempts - 1,
                delay=result.after_seconds,
                last_error=result.reason,
            )
            self._count("throttled")
        elif isinstance(result, RetryLater):
            self._count("retries")
            if job.attempts >= self.config.max_attempts:
                self._fail(
                    job,
                    f"No se ha podido enviar tras {job.attempts} intentos. Último error: "
                    f"{result.reason}",
                )
            else:
                self._finish(
                    job, status=N.PENDING, delay=backoff(job.attempts), last_error=result.reason
                )
        elif isinstance(result, Rejected):
            self._fail(job, result.reason)
        elif isinstance(result, ConfigError):
            first = not self.stop.is_set()
            self.stop.set()
            self._finish(
                job, status=N.PENDING, attempts=job.attempts - 1, delay=0, last_error=result.reason
            )
            with self.lock:
                self.summary.config_error = True
                self.summary.config_error_reason = result.reason
            if first:
                logger.warning(
                    "Confirmaciones: el proveedor %s no está bien configurado; lote parado "
                    "(notificación %s)",
                    self.provider.name,
                    job.notification_id,
                )

    def _fail(self, job: _Job, reason: str) -> None:
        if self._finish(job, status=N.FAILED, last_error=reason):
            self._count("failed")
            logger.warning(
                "Notificación %s (inscripción %s): fallida tras %s intentos",
                job.notification_id,
                job.registration_id,
                job.attempts,
            )

    def _finish(
        self,
        job: _Job,
        *,
        status: str,
        delay: float | None = None,
        attempts: int | None = None,
        **fields,
    ) -> bool:
        """Guarda el resultado si la reserva sigue siendo nuestra (mismo plazo)."""
        now = timezone.now()
        if status == N.SENT:
            fields["last_error"] = ""
        if attempts is not None:
            fields["attempts"] = attempts
        updated = Notification.objects.filter(
            pk=job.notification_id, status=N.SENDING, next_attempt_at=job.lease
        ).update(
            status=status,
            next_attempt_at=now + timedelta(seconds=delay or 0),
            updated_at=now,
            **fields,
        )
        if not updated:
            # Se venció la reserva y la ha retomado otro envío, con la misma clave.
            logger.warning(
                "Notificación %s: la reserva ya no era de este envío; no se guarda el resultado",
                job.notification_id,
            )
            self._count("skipped")
        return bool(updated)

    def _count(self, name: str) -> None:
        with self.lock:
            setattr(self.summary, name, getattr(self.summary, name) + 1)


def backoff(attempts: int) -> float:
    """Espera tras el intento `attempts` (1, 2, …): exponencial, con tope y con jitter."""
    delay = min(MAX_DELAY_SECONDS, BASE_DELAY_SECONDS * 2 ** (attempts - 1))
    return delay * random.uniform(0.5, 1.5)


__all__ = [
    "CannotRetry",
    "SendConfig",
    "SendSummary",
    "backoff",
    "enqueue",
    "load_send_config",
    "pending_count",
    "race_status",
    "request_send",
    "retry_failed",
    "send_pending",
]
