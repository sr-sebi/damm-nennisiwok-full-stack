import math

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from races.application.import_registrations import process_queue
from races.application.send_confirmations import load_send_config, send_pending


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
    summary = send_pending(race_id, load_send_config())
    if (
        summary.retry_later
        and summary.next_attempt_at is not None
        and not summary.config_error
        and not settings.CELERY_TASK_ALWAYS_EAGER  # en la propia petición sería un bucle
    ):
        wait = (summary.next_attempt_at - timezone.now()).total_seconds()
        send_confirmations.apply_async(args=[race_id], countdown=max(1, math.ceil(wait)))
