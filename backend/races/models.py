from __future__ import annotations

import datetime

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from races.domain.normalize import FIELDS, MAX_LENGTH, NormalizeOptions
from races.domain.rules import SHIRT_SIZES

FIELD_CHOICES = [(name, name) for name in FIELDS]


class Race(models.Model):
    name = models.CharField(max_length=200)
    date = models.DateField()
    location = models.CharField(max_length=200, blank=True)
    # Sin aforo (null) no hay lista de espera.
    capacity = models.PositiveIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1)], verbose_name="aforo"
    )
    # Siguiente dorsal libre. Se reserva con la carrera bloqueada (select_for_update) y nunca
    # baja: un dorsal dado de baja no se reutiliza.
    next_bib = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "name"]

    def __str__(self):
        return f"{self.name} ({self.date:%d/%m/%Y})"


class Channel(models.Model):
    """Por dónde llegan las inscripciones.

    Un proveedor nuevo con un formato conocido es una fila más, sin código.
    """

    class Kind(models.TextChoices):
        ONLINE = "plataforma_online", "Plataforma online"
        IN_PERSON = "presencial", "Presencial"

    class Format(models.TextChoices):
        XLSX = "xlsx", "Excel (.xlsx)"
        CSV = "csv", "CSV"

    code = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    format = models.CharField(max_length=10, choices=Format.choices)
    # Vacío = se detecta al leer.
    encoding = models.CharField(max_length=30, blank=True)
    delimiter = models.CharField(max_length=1, blank=True)
    # Formatos de fecha en orden, uno por línea (sintaxis de strptime). Un texto en vez de
    # JSONField para no depender del soporte de JSON de cada motor.
    date_formats = models.TextField(default="%d/%m/%Y")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def date_format_list(self) -> tuple[str, ...]:
        return tuple(line.strip() for line in self.date_formats.splitlines() if line.strip())

    def clean(self):
        try:
            NormalizeOptions(date_formats=self.date_format_list)
        except ValueError as exc:
            raise ValidationError({"date_formats": str(exc)}) from exc


class ChannelColumn(models.Model):
    """Alias de cabecera de un proveedor que no usa los nombres de las reglas."""

    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name="columns")
    source_header = models.CharField(max_length=100)
    field = models.CharField(max_length=30, choices=FIELD_CHOICES)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["channel", "source_header"], name="channel_column_unique_header"
            ),
        ]

    def __str__(self):
        return f"{self.channel}: {self.source_header} → {self.field}"


class ValueAlias(models.Model):
    """Valor de origen → valor canónico (talla «2XL» → «XXL»). Sin canal, vale para todos."""

    channel = models.ForeignKey(
        Channel, null=True, blank=True, on_delete=models.CASCADE, related_name="value_aliases"
    )
    field = models.CharField(max_length=30, choices=FIELD_CHOICES)
    source_value = models.CharField(max_length=100)
    value = models.CharField(max_length=100)

    class Meta:
        verbose_name_plural = "value aliases"
        # Dos restricciones y no una con `channel`: PostgreSQL y SQLite tratan los NULL como
        # distintos y SQL Server como iguales, así que una sola daría reglas distintas por motor.
        constraints = [
            models.UniqueConstraint(
                fields=["channel", "field", "source_value"],
                condition=Q(channel__isnull=False),
                name="value_alias_unique_per_channel",
            ),
            models.UniqueConstraint(
                fields=["field", "source_value"],
                condition=Q(channel__isnull=True),
                name="value_alias_unique_global",
            ),
        ]

    def __str__(self):
        return f"{self.field}: {self.source_value} → {self.value}"


class Registration(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = "confirmada", "Confirmada"
        WAITLISTED = "en_espera", "En lista de espera"
        WITHDRAWN = "baja", "Baja"

    race = models.ForeignKey(Race, on_delete=models.CASCADE, related_name="registrations")
    first_name = models.CharField(max_length=MAX_LENGTH["nombre"])
    last_name = models.CharField(max_length=MAX_LENGTH["apellidos"])
    # Tal como llegó, para mostrar; `email_norm` (minúsculas) es la clave de duplicado.
    email = models.CharField(max_length=MAX_LENGTH["email"])
    email_norm = models.CharField(max_length=MAX_LENGTH["email"])
    birth_date = models.DateField()
    phone = models.CharField(max_length=MAX_LENGTH["telefono"], blank=True)
    shirt_size = models.CharField(max_length=3, choices=[(s, s) for s in SHIRT_SIZES])
    # Canal por el que llegó primero: solo ese canal la actualiza o la marca como ausente.
    channel = models.ForeignKey(Channel, on_delete=models.PROTECT, related_name="registrations")
    # Canales por los que volvió a llegar (mismo email): aviso de «ya inscrita».
    also_channels = models.ManyToManyField(Channel, blank=True, related_name="+")
    status = models.CharField(max_length=20, choices=Status.choices)
    bib = models.PositiveIntegerField(null=True, blank=True, verbose_name="dorsal")
    waitlist_position = models.PositiveIntegerField(null=True, blank=True)
    # Mismo nombre y fecha de nacimiento con otro email: no se fusiona, decide una persona.
    possible_duplicate_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # Nombre y apellidos sin tildes y en minúsculas: buscar «garcia» encuentra «García» sin
    # depender de la collation del motor.
    search_text = models.CharField(max_length=MAX_LENGTH["nombre"] + MAX_LENGTH["apellidos"] + 1)
    # No aparece en el último listado completo de su canal. No es una baja: la confirma una persona.
    missing_since = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["race", "bib", "waitlist_position", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["race", "email_norm"], name="registration_unique_email"
            ),
            # Con condición: SQL Server trata los NULL como iguales en un índice único, y sin ella
            # dos inscripciones en lista de espera (sin dorsal) chocarían.
            models.UniqueConstraint(
                fields=["race", "bib"],
                condition=Q(bib__isnull=False),
                name="registration_unique_bib",
            ),
            models.UniqueConstraint(
                fields=["race", "waitlist_position"],
                condition=Q(waitlist_position__isnull=False),
                name="registration_unique_waitlist_position",
            ),
            models.CheckConstraint(
                condition=~Q(status="confirmada") | Q(bib__isnull=False),
                name="registration_confirmed_has_bib",
            ),
            models.CheckConstraint(
                condition=~Q(status="en_espera")
                | Q(bib__isnull=True, waitlist_position__isnull=False),
                name="registration_waitlisted_has_position",
            ),
        ]
        indexes = [
            # Posible duplicado: mismo nombre normalizado y fecha de nacimiento.
            models.Index(fields=["race", "birth_date"], name="registration_race_birth"),
            models.Index(fields=["race", "status"], name="registration_race_status"),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.race_id}, dorsal {self.bib})"


def import_upload_path(instance, filename):
    return f"imports/race_{instance.race_id}/{filename}"


class ImportBatch(models.Model):
    """Una importación de un fichero. Se procesan de una en una por carrera, en orden de llegada."""

    class Status(models.TextChoices):
        QUEUED = "en_cola", "En cola"
        PROCESSING = "procesando", "Procesando"
        DONE = "hecho", "Hecho"
        ERROR = "error", "Error"

    race = models.ForeignKey(Race, on_delete=models.CASCADE, related_name="imports")
    channel = models.ForeignKey(Channel, on_delete=models.PROTECT, related_name="imports")
    file = models.FileField(upload_to=import_upload_path)
    original_filename = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    total_rows = models.PositiveIntegerField(null=True, blank=True)
    processed_rows = models.PositiveIntegerField(default=0)
    created = models.PositiveIntegerField(default=0)
    waitlisted = models.PositiveIntegerField(default=0)
    updated = models.PositiveIntegerField(default=0)
    unchanged = models.PositiveIntegerField(default=0)
    repeated = models.PositiveIntegerField(default=0)
    already_registered = models.PositiveIntegerField(default=0)
    possible_duplicates = models.PositiveIntegerField(default=0)
    rejected = models.PositiveIntegerField(default=0)
    blank = models.PositiveIntegerField(default=0)
    missing = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    # Última señal de vida: sin progreso en un rato, la importación se da por caída.
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            # La garantía de «una sola en marcha por carrera» la da la base de datos, no un
            # cerrojo en memoria (hay varios procesos de worker).
            models.UniqueConstraint(
                fields=["race"],
                condition=Q(status="procesando"),
                name="import_one_processing_per_race",
            ),
        ]
        indexes = [models.Index(fields=["race", "status", "created_at"], name="import_queue")]

    def __str__(self):
        return f"Importación {self.pk} ({self.channel}, {self.get_status_display()})"


class ImportIssue(models.Model):
    """Una fila que no ha entrado como alta normal, con su línea y su motivo."""

    class Kind(models.TextChoices):
        REJECTED = "rechazada", "Rechazada"
        ALREADY_REGISTERED = "ya_inscrita", "Ya inscrita por otro canal"
        POSSIBLE_DUPLICATE = "posible_duplicada", "Posible duplicado"
        MISSING = "ausente", "No aparece en el listado"

    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="issues")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    line = models.PositiveIntegerField(null=True, blank=True)  # un ausente no tiene línea
    # Código, campo y valor de agrupación de `races.domain.issues.Issue`.
    code = models.CharField(max_length=40, blank=True)
    field = models.CharField(max_length=30, blank=True)
    group_value = models.CharField(max_length=210, blank=True)
    message = models.TextField()
    differences = models.TextField(blank=True)
    # La fila tal como llegó, para poder contactar con el corredor. Va a la base de datos,
    # nunca a los logs.
    raw = models.TextField(blank=True)
    # Huella de la incidencia para saber si ya salió en la importación anterior del mismo canal.
    fingerprint = models.CharField(max_length=64)
    is_new = models.BooleanField(default=True)
    registration = models.ForeignKey(
        Registration, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["batch", "line", "id"]
        indexes = [
            models.Index(fields=["batch", "kind"], name="import_issue_batch_kind"),
            models.Index(
                fields=["batch", "code", "field", "group_value"], name="import_issue_group"
            ),
        ]

    def __str__(self):
        return f"Línea {self.line}: {self.message}"


class Notification(models.Model):
    """Bandeja de salida: una fila por mensaje lógico (hoy, el email de confirmación).

    La fuente de verdad de «ya enviado» es esta tabla, no la clave de idempotencia del proveedor
    (el real la recuerda 24 h). `idempotency_key` es la misma en todos los intentos.

    `next_attempt_at` dice cuándo se puede volver a intentar. En `enviando` hace de plazo de la
    reserva: quien la reserva pone `ahora + plazo`; si el worker muere a mitad, al vencer el plazo
    otro la retoma con la misma clave.
    """

    class Status(models.TextChoices):
        PENDING = "pendiente", "Pendiente"
        SENDING = "enviando", "Enviando"
        SENT = "enviada", "Enviada"
        FAILED = "fallida", "Fallida"

    registration = models.ForeignKey(
        Registration, on_delete=models.CASCADE, related_name="notifications"
    )
    idempotency_key = models.CharField(max_length=255, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    # Intentos gastados. Un «espera» del proveedor (429) no cuenta.
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField()
    # Motivo del último fallo, para el usuario. Nunca va a los logs.
    last_error = models.TextField(blank=True)
    provider = models.CharField(max_length=50, blank=True)
    provider_id = models.CharField(max_length=255, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(fields=["status", "next_attempt_at"], name="notification_due"),
        ]

    def __str__(self):
        return f"{self.idempotency_key} ({self.get_status_display()})"

    @staticmethod
    def confirmation_key(registration_id: int, bib: int) -> str:
        return f"confirmacion-{registration_id}-{bib}"


class Settings(models.Model):
    """Configuración operativa, en una sola fila (pk=1), editable en la pantalla «Configuración».

    Se lee al empezar cada tarea, sin caché: un cambio vale en el siguiente latido. Los secretos y
    la URL del proveedor de email no están aquí (dependen del entorno y no deben verse en una
    pantalla), ni las reglas de negocio (categorías, edad mínima, tallas: van en código).
    """

    auto_send_enabled = models.BooleanField(default=False, verbose_name="envío programado")
    # Hora local (TIME_ZONE) a partir de la cual se hace el envío del día.
    auto_send_time = models.TimeField(default=datetime.time(8, 0), verbose_name="hora de envío")
    email_subject = models.CharField(max_length=200, verbose_name="asunto")
    email_body = models.TextField(verbose_name="cuerpo")
    # El proveedor admite 20 por segundo: el ritmo propio se queda por debajo.
    send_rate_per_second = models.PositiveSmallIntegerField(
        default=15,
        validators=[
            MinValueValidator(1, "El ritmo tiene que ser de al menos 1 email por segundo."),
            MaxValueValidator(
                19, "El ritmo máximo es 19 emails por segundo: el proveedor corta a partir de 20."
            ),
        ],
        verbose_name="emails por segundo",
    )
    max_attempts = models.PositiveSmallIntegerField(
        default=6,
        validators=[
            MinValueValidator(1, "Hace falta al menos 1 intento."),
            MaxValueValidator(20, "Como mucho 20 intentos por email."),
        ],
        verbose_name="intentos máximos",
    )
    import_stale_minutes = models.PositiveSmallIntegerField(
        default=10,
        validators=[
            MinValueValidator(1, "Al menos 1 minuto."),
            MaxValueValidator(1440, "Como mucho 1440 minutos (un día)."),
        ],
        verbose_name="minutos sin avanzar para dar una importación por caída",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "configuración"
        verbose_name_plural = "configuración"
        constraints = [models.CheckConstraint(condition=Q(id=1), name="settings_single_row")]

    def __str__(self):
        return "Configuración"

    @classmethod
    def load(cls) -> Settings:
        """La fila única; la crea con los valores por defecto la primera vez."""
        row = cls.objects.filter(pk=1).first()
        if row is not None:
            return row
        from races.domain.email_template import DEFAULT_BODY, DEFAULT_SUBJECT

        row, _ = cls.objects.get_or_create(
            pk=1, defaults={"email_subject": DEFAULT_SUBJECT, "email_body": DEFAULT_BODY}
        )
        return row


class JobRun(models.Model):
    """Una ejecución de un trabajo programado, con su resultado y un resumen en cifras.

    La fila `en_marcha` es también el cerrojo: solo puede haber una por trabajo (lo garantiza la
    base de datos, como «procesando» en las importaciones), así que dos latidos a la vez no hacen
    dos envíos.
    """

    class Job(models.TextChoices):
        SCHEDULED_SEND = "envio_programado", "Envío programado de confirmaciones"

    class Result(models.TextChoices):
        RUNNING = "en_marcha", "En marcha"
        OK = "ok", "Hecho"
        IDLE = "idle", "No tocaba"
        LOCKED = "locked", "Otro en marcha"
        ERROR = "error", "Error"

    job = models.CharField(max_length=30, choices=Job.choices)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    result = models.CharField(max_length=20, choices=Result.choices)
    summary = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["job"], condition=Q(result="en_marcha"), name="job_run_one_running"
            ),
        ]
        indexes = [models.Index(fields=["job", "started_at"], name="job_run_job_started")]

    def __str__(self):
        return f"{self.get_job_display()} {self.started_at:%d/%m/%Y %H:%M}: {self.result}"
