from celery import shared_task

from races.application.import_registrations import process_queue


@shared_task(ignore_result=True)
def process_imports(race_id: int) -> None:
    """Procesa la cola de importaciones de una carrera. Si ya hay otra en marcha, no hace nada:
    la que está en marcha coge la siguiente al terminar."""
    process_queue(race_id)
