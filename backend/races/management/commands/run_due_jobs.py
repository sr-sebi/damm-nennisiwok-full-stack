from django.core.management.base import BaseCommand

from races.application.scheduled_jobs import run_due_jobs


class Command(BaseCommand):
    help = (
        "Ejecuta el latido una vez: importaciones caídas y envío programado si toca. "
        "Sirve sin Docker (sin beat) o para lanzarlo a mano."
    )

    def handle(self, *args, **options):
        for outcome in run_due_jobs():
            self.stdout.write(f"{outcome.job}: {outcome.result} · {outcome.summary}")
