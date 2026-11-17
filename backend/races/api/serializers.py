from pathlib import Path

from django.conf import settings
from django.db.models import Case, Count, IntegerField, Q, Value, When
from rest_framework import serializers

from races.application.send_confirmations import is_eligible
from races.domain.email_template import template_errors
from races.domain.issues import Issue, IssueCode, group_message
from races.domain.rules import category_for
from races.infrastructure.email import active_provider_name
from races.models import (
    Channel,
    ImportBatch,
    ImportIssue,
    JobRun,
    Notification,
    Race,
    Registration,
)
from races.models import Settings as AppSettings

ALLOWED_EXTENSIONS = {".xlsx": Channel.Format.XLSX, ".csv": Channel.Format.CSV}
EXAMPLES_PER_GROUP = 5
# Orden del informe: primero lo que pide una acción de la organización.
KIND_ORDER = [
    ImportIssue.Kind.ALREADY_REGISTERED,
    ImportIssue.Kind.POSSIBLE_DUPLICATE,
    ImportIssue.Kind.REPEATED,
    ImportIssue.Kind.REJECTED,
    ImportIssue.Kind.MISSING,
]
KIND_TITLES = {
    ImportIssue.Kind.ALREADY_REGISTERED: (
        "Ya inscritas por otro canal: no se les ha dado otro dorsal ni se han cambiado sus datos"
    ),
    ImportIssue.Kind.POSSIBLE_DUPLICATE: (
        "Posibles duplicados: mismo nombre y fecha de nacimiento con otro email"
    ),
    ImportIssue.Kind.REPEATED: (
        "Mismo email que otra fila del fichero, con otros datos: solo se ha inscrito la primera"
    ),
    ImportIssue.Kind.MISSING: "No aparecen en este listado (siguen inscritas)",
}


class ChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Channel
        fields = ["id", "code", "name", "kind", "format"]


class RaceSerializer(serializers.ModelSerializer):
    # Cuentas anotadas en la consulta de la vista (`with_counts`); en un alta recién creada, 0.
    confirmed = serializers.SerializerMethodField()
    waitlisted = serializers.SerializerMethodField()

    class Meta:
        model = Race
        fields = [
            "id",
            "name",
            "date",
            "location",
            "capacity",
            "confirmed",
            "waitlisted",
            "created_at",
        ]
        read_only_fields = ["created_at"]

    def get_confirmed(self, race):
        return getattr(race, "confirmed", 0)

    def get_waitlisted(self, race):
        return getattr(race, "waitlisted", 0)


class StrictSerializer(serializers.Serializer):
    """Rechaza campos que no conoce: que no parezca que se ha cambiado algo que no se cambia."""

    def validate(self, attrs):
        unknown = sorted(set(self.initial_data) - set(self.fields))
        if unknown:
            raise serializers.ValidationError(
                {name: ["Este campo no se puede cambiar desde aquí."] for name in unknown}
            )
        return attrs


class RaceCapacitySerializer(StrictSerializer):
    capacity = serializers.IntegerField(
        min_value=1,
        allow_null=True,
        error_messages={"min_value": "El aforo tiene que ser al menos 1 (vacío = sin límite)."},
    )


def _text_field():
    # Sin recortar ni limitar: limpiar y validar es cosa del normalizador y de las reglas, igual
    # que en una importación.
    return serializers.CharField(
        required=False, allow_blank=True, allow_null=True, trim_whitespace=False
    )


class RegistrationDataSerializer(StrictSerializer):
    first_name = _text_field()
    last_name = _text_field()
    email = _text_field()
    birth_date = _text_field()  # AAAA-MM-DD (o dd/mm/aaaa)
    phone = _text_field()
    shirt_size = _text_field()


class RegistrationCreateSerializer(RegistrationDataSerializer):
    channel = serializers.SlugRelatedField(
        slug_field="code",
        queryset=Channel.objects.all(),
        error_messages={
            "required": "Falta el canal.",
            "does_not_exist": "No existe el canal «{value}».",
        },
    )


class RegistrationSummarySerializer(serializers.ModelSerializer):
    """Lo justo para nombrar otra inscripción en un aviso."""

    channel = serializers.CharField(source="channel.name", read_only=True)

    class Meta:
        model = Registration
        fields = [
            "id",
            "bib",
            "status",
            "waitlist_position",
            "first_name",
            "last_name",
            "email",
            "channel",
        ]
        read_only_fields = fields


class RegistrationSerializer(serializers.ModelSerializer):
    """Una fila de la lista. La categoría se calcula con la fecha de la carrera (no se guarda)."""

    channel = ChannelSerializer(read_only=True)
    also_channels = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    possible_duplicate_of = serializers.SerializerMethodField()
    email_status = serializers.SerializerMethodField()

    class Meta:
        model = Registration
        fields = [
            "id",
            "race",
            "bib",
            "status",
            "waitlist_position",
            "first_name",
            "last_name",
            "email",
            "birth_date",
            "category",
            "phone",
            "shirt_size",
            "channel",
            "also_channels",
            "possible_duplicate_of",
            "missing_since",
            "email_status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_category(self, registration):
        race_date = self.context.get("race_date") or registration.race.date
        return category_for(registration.birth_date, race_date)

    def get_also_channels(self, registration):
        # `.all()` usa lo precargado con prefetch_related: sin consulta por fila.
        return [channel.name for channel in registration.also_channels.all()]

    def get_possible_duplicate_of(self, registration):
        other = registration.possible_duplicate_of
        if other is None:
            return None
        return {
            "id": other.pk,
            "bib": other.bib,
            "first_name": other.first_name,
            "last_name": other.last_name,
        }

    def get_email_status(self, registration):
        """Email de confirmación: su fila de la bandeja de salida, o «pendiente» si aún no la tiene
        y le toca. `null` si no le toca (en espera, baja, posible duplicado, carrera pasada)."""
        # `.all()` usa lo precargado con prefetch_related: sin consulta por fila.
        notifications = list(registration.notifications.all())
        if notifications:
            return NotificationStatusSerializer(max(notifications, key=lambda n: n.pk)).data
        race_date = self.context.get("race_date") or registration.race.date
        if not is_eligible(registration, race_date):
            return None
        return {
            "id": None,
            "status": Notification.Status.PENDING,
            "attempts": 0,
            "last_error": "",
            "sent_at": None,
            "updated_at": None,
        }


class NotificationStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "status", "attempts", "last_error", "sent_at", "updated_at"]
        read_only_fields = fields


class NotificationSerializer(serializers.ModelSerializer):
    """Un email de la bandeja de salida, con a quién va (para la lista de fallidas)."""

    registration = RegistrationSummarySerializer(read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id",
            "registration",
            "status",
            "attempts",
            "last_error",
            "provider",
            "sent_at",
            "next_attempt_at",
            "updated_at",
        ]
        read_only_fields = fields


class ConfirmationStatusSerializer(serializers.Serializer):
    race = serializers.IntegerField()
    race_past = serializers.BooleanField()
    provider = serializers.CharField()
    pending = serializers.IntegerField()
    sending = serializers.IntegerField()
    sent = serializers.IntegerField()
    failed = serializers.IntegerField()
    held_duplicates = serializers.IntegerField()
    failures = NotificationSerializer(many=True)
    last_send = serializers.SerializerMethodField()

    def get_last_send(self, data):
        run = data["last_send"]
        return JobRunSerializer(run).data if run else None


class ImportUploadSerializer(serializers.Serializer):
    channel = serializers.SlugRelatedField(
        slug_field="code",
        queryset=Channel.objects.all(),
        error_messages={"does_not_exist": "No existe el canal «{value}»."},
    )
    file = serializers.FileField(
        allow_empty_file=False,
        error_messages={
            "required": "Falta el fichero.",
            "empty": "El fichero está vacío.",
            "invalid": "No se ha recibido un fichero.",
        },
    )

    def validate_file(self, file):
        extension = Path(file.name).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(
                f"Solo se pueden importar ficheros .xlsx o .csv (se ha subido «{file.name}»)."
            )
        max_bytes = settings.IMPORT_MAX_UPLOAD_MB * 1024 * 1024
        if file.size > max_bytes:
            raise serializers.ValidationError(
                f"El fichero ocupa {file.size / 1024 / 1024:.1f} MB y el máximo es "
                f"{settings.IMPORT_MAX_UPLOAD_MB} MB."
            )
        return file

    def validate(self, attrs):
        channel, file = attrs["channel"], attrs["file"]
        if ALLOWED_EXTENSIONS[Path(file.name).suffix.lower()] != channel.format:
            raise serializers.ValidationError(
                {
                    "file": (
                        f"{channel.name} manda ficheros .{channel.format}; se ha subido otro tipo."
                    )
                }
            )
        return attrs


class ImportBatchSerializer(serializers.ModelSerializer):
    channel = ChannelSerializer(read_only=True)
    phase = serializers.SerializerMethodField()
    percent = serializers.SerializerMethodField()
    queue_ahead = serializers.SerializerMethodField()

    class Meta:
        model = ImportBatch
        fields = [
            "id",
            "race",
            "channel",
            "original_filename",
            "status",
            "phase",
            "percent",
            "total_rows",
            "processed_rows",
            "created",
            "waitlisted",
            "updated",
            "unchanged",
            "repeated",
            "already_registered",
            "possible_duplicates",
            "rejected",
            "blank",
            "missing",
            "error",
            "queue_ahead",
            "created_at",
            "started_at",
            "finished_at",
        ]
        read_only_fields = fields

    def get_phase(self, batch):
        if batch.status != ImportBatch.Status.PROCESSING:
            return batch.status
        if batch.total_rows is None:
            return "leyendo"
        if batch.processed_rows < batch.total_rows:
            return "guardando"
        return "comprobando_ausencias"

    def get_percent(self, batch):
        if batch.status == ImportBatch.Status.DONE:
            return 100
        if not batch.total_rows:
            return 0
        return min(99, batch.processed_rows * 100 // batch.total_rows)

    def get_queue_ahead(self, batch):
        """Las que van antes en la cola de su carrera (la que está en marcha, la primera)."""
        if batch.status != ImportBatch.Status.QUEUED:
            return []
        ahead = (
            ImportBatch.objects.filter(race_id=batch.race_id)
            .filter(
                Q(status=ImportBatch.Status.PROCESSING)
                | Q(status=ImportBatch.Status.QUEUED, id__lt=batch.pk)
            )
            .select_related("channel")
            .order_by("-status", "id")  # «procesando» antes que «en_cola»
        )
        return [
            {
                "id": b.pk,
                "original_filename": b.original_filename,
                "channel": b.channel.name,
                "status": b.status,
            }
            for b in ahead
        ]


def issue_order():
    """Por línea, con las que no tienen (ausentes) al final en todos los motores.

    PostgreSQL ordena los NULL al final y SQL Server al principio.
    """
    without_line_last = Case(
        When(line__isnull=True, then=Value(1)), default=Value(0), output_field=IntegerField()
    )
    return (without_line_last, "line", "id")


class ImportReportSerializer(ImportBatchSerializer):
    issue_groups = serializers.SerializerMethodField()

    class Meta(ImportBatchSerializer.Meta):
        fields = [*ImportBatchSerializer.Meta.fields, "issue_groups"]
        read_only_fields = fields

    def get_issue_groups(self, batch):
        """Incidencias agrupadas en la base de datos por tipo, código, campo y valor."""
        rows = batch.issues.values("kind", "code", "field", "group_value").annotate(
            count=Count("id"), new=Count("id", filter=Q(is_new=True))
        )
        rows = sorted(rows, key=lambda r: (KIND_ORDER.index(r["kind"]), -r["count"]))
        groups = []
        for row in rows:
            filters = {k: row[k] for k in ("kind", "code", "field", "group_value")}
            examples = list(
                batch.issues.filter(**filters)
                .select_related("registration")
                .order_by(*issue_order())[:EXAMPLES_PER_GROUP]
            )
            groups.append(
                {
                    **filters,
                    "count": row["count"],
                    "new": row["new"],
                    "title": _group_title(row, examples),
                    "examples": [IssueSerializer(issue).data for issue in examples],
                }
            )
        return groups


class IssueSerializer(serializers.ModelSerializer):
    bib = serializers.IntegerField(source="registration.bib", default=None, read_only=True)
    # Nombre de la inscripción enlazada: un ausente no tiene fila en bruto con la que nombrarlo.
    person = serializers.SerializerMethodField()

    class Meta:
        model = ImportIssue
        fields = [
            "id",
            "kind",
            "line",
            "code",
            "field",
            "group_value",
            "message",
            "differences",
            "raw",
            "is_new",
            "registration",
            "bib",
            "person",
        ]
        read_only_fields = fields

    def get_person(self, issue):
        reg = issue.registration
        return f"{reg.first_name} {reg.last_name}" if reg else ""


def _group_title(row, examples) -> str:
    if row["kind"] != ImportIssue.Kind.REJECTED:
        return KIND_TITLES[row["kind"]]
    try:
        code = IssueCode(row["code"])
    except ValueError:
        return examples[0].message if examples else row["code"]
    sample = examples[0].message if examples else ""
    return group_message(
        Issue(code=code, field=row["field"], raw=row["group_value"], message=sample)
    )


def _limits(low, high, too_high):
    # DRF no usa el mensaje de los validadores del modelo para min/max: se le da aquí.
    return {
        "min_value": low,
        "max_value": high,
        "error_messages": {
            "min_value": f"Tiene que ser al menos {low}.",
            "max_value": too_high,
            "invalid": "Tiene que ser un número entero.",
        },
    }


class SettingsSerializer(serializers.ModelSerializer):
    """La configuración editable. El proveedor de email se enseña, pero no se cambia aquí: se
    elige en el entorno (`EMAIL_PROVIDER`), junto con sus credenciales."""

    email_provider = serializers.SerializerMethodField()
    last_scheduled_send = serializers.SerializerMethodField()

    class Meta:
        model = AppSettings
        fields = [
            "auto_send_enabled",
            "auto_send_time",
            "email_subject",
            "email_body",
            "send_rate_per_second",
            "max_attempts",
            "import_stale_minutes",
            "email_provider",
            "last_scheduled_send",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]
        extra_kwargs = {
            "auto_send_time": {
                "format": "%H:%M",
                "input_formats": ["%H:%M", "%H:%M:%S"],
                "error_messages": {"invalid": "Hora no válida: usa HH:MM (por ejemplo, 08:00)."},
            },
            "send_rate_per_second": _limits(
                1,
                19,
                "El ritmo máximo es 19 emails por segundo: el proveedor corta a partir de 20.",
            ),
            "max_attempts": _limits(1, 20, "Como mucho 20 intentos por email."),
            "import_stale_minutes": _limits(1, 1440, "Como mucho 1440 minutos (un día)."),
        }

    def get_email_provider(self, obj):
        return active_provider_name()

    def get_last_scheduled_send(self, obj):
        run = (
            JobRun.objects.filter(job=JobRun.Job.SCHEDULED_SEND)
            .exclude(result=JobRun.Result.LOCKED)
            .first()
        )
        return JobRunSerializer(run).data if run else None

    def validate_email_subject(self, value):
        return _template(value)

    def validate_email_body(self, value):
        return _template(value)


def _template(value):
    errors = template_errors(value)
    if errors:
        raise serializers.ValidationError(errors)
    return value


class JobRunSerializer(serializers.ModelSerializer):
    job_display = serializers.CharField(source="get_job_display", read_only=True)
    result_display = serializers.CharField(source="get_result_display", read_only=True)

    class Meta:
        model = JobRun
        fields = [
            "id",
            "job",
            "job_display",
            "started_at",
            "finished_at",
            "result",
            "result_display",
            "summary",
        ]
        read_only_fields = fields
