from pathlib import Path

from django.conf import settings
from django.db.models import Count, Q
from rest_framework import serializers

from races.domain.issues import Issue, IssueCode, group_message
from races.models import Channel, ImportBatch, ImportIssue, Race

ALLOWED_EXTENSIONS = {".xlsx": Channel.Format.XLSX, ".csv": Channel.Format.CSV}
EXAMPLES_PER_GROUP = 5
# Orden del informe: primero lo que pide una acción de la organización.
KIND_ORDER = [
    ImportIssue.Kind.ALREADY_REGISTERED,
    ImportIssue.Kind.POSSIBLE_DUPLICATE,
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
    ImportIssue.Kind.MISSING: "No aparecen en este listado (siguen inscritas)",
}


class RaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Race
        fields = ["id", "name", "date", "location", "capacity", "created_at"]
        read_only_fields = ["created_at"]


class ChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Channel
        fields = ["id", "code", "name", "kind", "format"]


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
                batch.issues.filter(**filters).order_by("line", "id")[:EXAMPLES_PER_GROUP]
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
        ]
        read_only_fields = fields


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
