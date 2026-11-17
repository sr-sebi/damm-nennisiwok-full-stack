"""El latido: lo que se comprueba cada minuto (Celery beat) o a mano con `manage.py run_due_jobs`.

El horario no está en beat: beat solo late cada minuto, y aquí se lee la configuración de la base de
datos y se decide si toca. Así un cambio de hora en la pantalla vale en el siguiente latido, sin
reiniciar nada. Un latido de más no hace daño: el envío es idempotente (bandeja de salida) y el
cerrojo de `JobRun` impide dos envíos a la vez.

1. **Importaciones**: una `procesando` sin avanzar desde hace `import_stale_minutes` se da por
   caída y la cola sigue; una `en_cola` sin ninguna en marcha (la tarea se perdió) se relanza. Sin
   esto, una importación caída solo se detectaba al subir otra.
2. **Envío programado**: si está activado, ya es la hora de hoy y hoy no se ha hecho (ni con error),
   se envían las confirmaciones pendientes de todas las carreras. Un error deja el día hecho: se ve
   en la pantalla y se puede enviar con el botón, en vez de reintentar cada minuto contra un
   proveedor que falla. Un envío que lleva `RUN_STALE_AFTER` «en marcha» (el worker murió) pasa a
   «caído», que no cuenta como hecho, y el mismo latido lo vuelve a lanzar: la bandeja de salida no
   repite lo ya enviado.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from races.models import ImportBatch, JobRun, Settings

logger = logging.getLogger(__name__)

Job = JobRun.Job
Result = JobRun.Result

# Una cola sin ninguna en marcha durante este rato es una tarea perdida (no un hueco normal entre
# subir y que el worker la coja).
ORPHAN_QUEUE_AFTER = timedelta(minutes=2)
# Un envío programado «en marcha» más tiempo que esto se da por caído (20.000 emails a 15/s son
# unos 35 min).
RUN_STALE_AFTER = timedelta(hours=3)


@dataclass(frozen=True)
class JobOutcome:
    job: str
    result: str
    summary: str


def run_due_jobs(now: datetime | None = None, send: Callable | None = None) -> list[JobOutcome]:
    now = now or timezone.now()
    config = Settings.load()
    return [recover_imports(now, config), run_scheduled_send(now, config, send)]


# --- importaciones --------------------------------------------------------------------------


def recover_imports(now: datetime, config: Settings) -> JobOutcome:
    """Relanza la cola de las carreras con una importación caída o con una cola sin arrancar."""
    from races.tasks import process_imports  # la tarea importa el módulo de importación

    stale = now - timedelta(minutes=config.import_stale_minutes)
    running = ImportBatch.objects.filter(status=ImportBatch.Status.PROCESSING)
    stuck = set(running.filter(updated_at__lt=stale).values_list("race_id", flat=True))
    busy = set(running.values_list("race_id", flat=True))
    queued = set(
        ImportBatch.objects.filter(
            status=ImportBatch.Status.QUEUED, created_at__lt=now - ORPHAN_QUEUE_AFTER
        ).values_list("race_id", flat=True)
    )
    races = sorted(stuck | (queued - busy))
    for race_id in races:
        # `claim_next` decide con la carrera bloqueada: relanzar de más no arranca dos.
        process_imports.delay(race_id)
    if races:
        logger.warning("Latido: cola de importación relanzada en las carreras %s", races)
        return JobOutcome("importaciones", "ok", f"Cola relanzada en {len(races)} carrera(s).")
    return JobOutcome("importaciones", Result.IDLE, "Ninguna importación caída ni parada.")


# --- envío programado -----------------------------------------------------------------------


def run_scheduled_send(now: datetime, config: Settings, send: Callable | None = None) -> JobOutcome:
    job = Job.SCHEDULED_SEND
    local = timezone.localtime(now)
    if not config.auto_send_enabled:
        return JobOutcome(job, Result.IDLE, "El envío programado está desactivado.")
    if local.time() < config.auto_send_time:
        return JobOutcome(
            job, Result.IDLE, f"Todavía no es la hora ({config.auto_send_time:%H:%M})."
        )
    day_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    if _done_today(job, day_start):
        return JobOutcome(job, Result.IDLE, "El envío de hoy ya está hecho.")

    _expire_stale_runs(job, now)
    running = JobRun.objects.filter(job=job, result=Result.RUNNING).first()
    if running is not None:
        # Mientras dura un envío largo, cada latido acabaría aquí: no se apunta una fila por minuto.
        since = timezone.localtime(running.started_at)
        return JobOutcome(
            job, Result.LOCKED, f"El envío de hoy sigue en marcha (desde las {since:%H:%M})."
        )
    try:
        with transaction.atomic():
            run = JobRun.objects.create(job=job, started_at=now, result=Result.RUNNING)
    except IntegrityError:
        # Otro latido lo ha arrancado justo ahora: se apunta, porque es un choque real.
        summary = "Otro latido ha arrancado el envío a la vez; este no hace nada."
        JobRun.objects.create(
            job=job, started_at=now, finished_at=now, result=Result.LOCKED, summary=summary
        )
        logger.info("Latido: envío programado ocupado")
        return JobOutcome(job, Result.LOCKED, summary)

    # Con el cerrojo cogido, otra vez: un latido que se solapó con este puede haber terminado el
    # envío de hoy entre la primera comprobación y el cerrojo.
    if _done_today(job, day_start):
        run.delete()
        return JobOutcome(job, Result.IDLE, "El envío de hoy ya está hecho.")
    logger.info("Latido: envío programado %s empieza", run.pk)
    try:
        result, summary = _send_all(send)
    except Exception as exc:
        # Solo el tipo: el texto de una excepción puede llevar un email.
        logger.error("Envío programado %s: error inesperado (%s)", run.pk, type(exc).__name__)
        result, summary = Result.ERROR, "Error inesperado. Revisa los registros del worker."
    run.result, run.summary, run.finished_at = result, summary, timezone.now()
    run.save(update_fields=["result", "summary", "finished_at"])
    logger.info("Envío programado %s: %s", run.pk, result)
    return JobOutcome(job, result, summary)


def _done_today(job: str, day_start: datetime) -> bool:
    return JobRun.objects.filter(
        job=job,
        result__in=[Result.OK, Result.ERROR],
        started_at__gte=day_start,
        started_at__lt=day_start + timedelta(days=1),
    ).exists()


def _send_all(send: Callable | None) -> tuple[str, str]:
    """Envía las pendientes de todas las carreras con la configuración de este momento."""
    from races.application import send_confirmations
    from races.tasks import follow_up

    send = send or send_confirmations.send_pending
    summary = send(None, send_confirmations.load_send_config())
    # Los reintentos que vencen más tarde no esperan al día siguiente: se encolan para su hora.
    follow_up(None, summary)
    return describe_send(summary)


def describe_send(summary) -> tuple[str, str]:
    """Resultado y resumen en cifras de `send_pending`."""
    text = (
        f"{summary.sent} enviados, {summary.retry_later} para reintentar más tarde, "
        f"{summary.failed} fallidos, {summary.skipped} omitidos."
    )
    if summary.config_error:
        reason = summary.config_error_reason or "El proveedor de email rechaza la configuración."
        return Result.ERROR, f"{reason} {text}"
    return Result.OK, text


def _expire_stale_runs(job: str, now: datetime) -> None:
    for run in JobRun.objects.filter(
        job=job, result=Result.RUNNING, started_at__lt=now - RUN_STALE_AFTER
    ):
        run.result = Result.ABANDONED
        run.finished_at = now
        since = timezone.localtime(run.started_at)
        run.summary = (
            f"Se dio por caído: seguía en marcha desde las {since:%H:%M} del {since:%d/%m}."
        )
        run.save(update_fields=["result", "finished_at", "summary"])
        logger.warning("Envío programado %s: dado por caído", run.pk)
