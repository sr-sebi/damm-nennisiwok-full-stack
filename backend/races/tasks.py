import math

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from races.application.import_registrations import process_queue
from races.application.send_confirmations import load_send_config, send_pending
from races.models import JobRun


@shared_task(ignore_result=True)
def process_imports(race_id: int) -> None:
    """Procesa la cola de importaciones de una carrera. Si ya hay otra en marcha, no hace nada:
    la que está en marcha coge la siguiente al terminar."""
    process_queue(race_id)


@shared_task(ignore_result=True)
def send_confirmations(race_id: int | None = None) -> None:
    """Envía las confirmaciones pendientes de una carrera (o de todas, con `None`).

    Lo que quede para más tarde (un reintento lejano) se vuelve a encolar para su hora. Con un
    error de configuración, no: hay que arreglarla, y el siguiente envío lo retoma.
    """
    started = timezone.now()
    try:
        summary = send_pending(race_id, load_send_config())
    except Exception:
        if race_id is not None:
            _record_button_send(race_id, started, None)
        raise
    if race_id is not None:
        _record_button_send(race_id, started, summary)
    follow_up(race_id, summary)


def _record_button_send(race_id: int, started, summary) -> None:
    """Resultado del envío de una carrera, para que el panel sepa que ha terminado y cómo."""
    from races.application.scheduled_jobs import describe_send

    if summary is None:
        result, text = JobRun.Result.ERROR, "Error inesperado. Revisa los registros del worker."
    else:
        result, text = describe_send(summary)
    JobRun.objects.create(
        job=JobRun.Job.BUTTON_SEND,
        race_id=race_id,
        started_at=started,
        finished_at=timezone.now(),
        result=result,
        summary=text,
    )


def follow_up(race_id: int | None, summary) -> None:
    """Si quedan reintentos para más tarde, vuelve a encolar el envío para su hora.

    Lo usan la tarea del botón y el envío programado. Con un error de configuración, no: hay que
    arreglarla, y el siguiente envío lo retoma. Sin worker (tareas en la petición), tampoco: sería
    un bucle dentro de la petición.
    """
    if (
        summary.retry_later
        and summary.next_attempt_at is not None
        and not summary.config_error
        and not settings.CELERY_TASK_ALWAYS_EAGER
    ):
        wait = (summary.next_attempt_at - timezone.now()).total_seconds()
        send_confirmations.apply_async(args=[race_id], countdown=max(1, math.ceil(wait)))


@shared_task(ignore_result=True)
def heartbeat() -> None:
    """Cada minuto (Celery beat): importaciones caídas y envío programado, si toca."""
    from races.application.scheduled_jobs import run_due_jobs

    run_due_jobs()
