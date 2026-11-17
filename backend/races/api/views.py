from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from races.api.serializers import (
    ChannelSerializer,
    ConfirmationStatusSerializer,
    ImportBatchSerializer,
    ImportReportSerializer,
    ImportUploadSerializer,
    IssueSerializer,
    NotificationSerializer,
    RaceCapacitySerializer,
    RaceSerializer,
    RegistrationCreateSerializer,
    RegistrationDataSerializer,
    RegistrationSerializer,
    RegistrationSummarySerializer,
)
from races.application import register, registrations, send_confirmations
from races.application.import_registrations import submit_import
from races.application.registrations import AlreadyRegistered, RegistrationRejected
from races.application.send_confirmations import CannotRetry
from races.models import Channel, ImportBatch, Notification, Race, Registration

RECENT_IMPORTS = 20


class Pages(PageNumberPagination):
    page_size = 50


STATUSES = {value for value, _ in Registration.Status.choices}


def with_counts(queryset):
    """Confirmadas y en espera, en la misma consulta.

    Con un `annotate` de agregados Django no aplica `Meta.ordering` (GROUP BY): el orden va aquí.
    """
    by_status = Registration.Status
    return queryset.annotate(
        confirmed=Count("registrations", filter=Q(registrations__status=by_status.CONFIRMED)),
        waitlisted=Count("registrations", filter=Q(registrations__status=by_status.WAITLISTED)),
    ).order_by(*Race._meta.ordering)


def rejected(exc: RegistrationRejected) -> Response:
    return Response(exc.errors, status=status.HTTP_400_BAD_REQUEST)


def already_registered(exc: AlreadyRegistered) -> Response:
    return Response(
        {
            "detail": exc.message,
            "registration": RegistrationSummarySerializer(exc.registration).data,
        },
        status=status.HTTP_409_CONFLICT,
    )


def promoted_message(promoted) -> str:
    return " ".join(
        f"{reg.first_name} {reg.last_name} sale de la lista de espera con el dorsal {reg.bib}."
        for reg in promoted
    )


class RaceViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Race.objects.all()
    serializer_class = RaceSerializer

    def get_queryset(self):
        if self.action in ("list", "retrieve"):
            return with_counts(Race.objects.all())
        return Race.objects.all()

    def partial_update(self, request, pk=None):
        """Solo el aforo: subirlo saca de la lista de espera a quien quepa, con dorsal nuevo."""
        race = self.get_object()
        data = RaceCapacitySerializer(data=request.data)
        data.is_valid(raise_exception=True)
        promoted = register.change_capacity(race.pk, data.validated_data["capacity"])
        race = with_counts(Race.objects.filter(pk=race.pk)).get()
        return Response(
            {
                **RaceSerializer(race).data,
                "promoted": RegistrationSummarySerializer(promoted, many=True).data,
                "message": promoted_message(promoted),
            }
        )

    @action(detail=True, methods=["get", "post"], url_path="registrations")
    def registrations(self, request, pk=None):
        """GET: lista paginada (`q`, `status`). POST: alta en un canal presencial (la tienda)."""
        race = self.get_object()
        if request.method == "POST":
            return self._register(request, race)
        wanted = request.query_params.get("status") or None
        if wanted is not None and wanted not in STATUSES:
            return Response(
                {"status": [f"Estado desconocido «{wanted}»: {', '.join(sorted(STATUSES))}."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        queryset = registrations.search(race, request.query_params.get("q", ""), wanted)
        paginator = Pages()
        page = paginator.paginate_queryset(queryset, request, view=self)
        data = RegistrationSerializer(page, many=True, context={"race_date": race.date}).data
        return paginator.get_paginated_response(data)

    def _register(self, request, race):
        data = RegistrationCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        fields = {k: v for k, v in data.validated_data.items() if k != "channel"}
        try:
            result = registrations.register_in_app(race, data.validated_data["channel"], fields)
        except RegistrationRejected as exc:
            return rejected(exc)
        except AlreadyRegistered as exc:
            return already_registered(exc)
        reg = result.registration
        if result.outcome is registrations.Outcome.WAITLISTED:
            message = (
                f"Aforo completo: {reg.first_name} {reg.last_name} queda en lista de espera "
                f"(posición {reg.waitlist_position})."
            )
        else:
            message = f"Alta de {reg.first_name} {reg.last_name} con el dorsal {reg.bib}."
        duplicate = result.possible_duplicate_of
        return Response(
            {
                "outcome": result.outcome.value,
                "message": message,
                "registration": RegistrationSerializer(reg, context={"race_date": race.date}).data,
                "possible_duplicate": (
                    registrations.possible_duplicate_message(duplicate) if duplicate else ""
                ),
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="registrations/check")
    def check_registration(self, request, pk=None):
        """Aviso antes de guardar: ya inscrita, posible duplicado, o irá a lista de espera.

        Solo lee: no bloquea la carrera ni escribe. Es POST para que el email vaya en el cuerpo y
        no en la URL, que acaba en los logs de acceso, en proxys y en el historial.
        """
        race = self.get_object()
        data = RegistrationDataSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        result = registrations.check(race, data.validated_data)

        def describe(registration, message):
            if registration is None:
                return None
            return {
                "message": message,
                "registration": RegistrationSummarySerializer(registration).data,
            }

        return Response(
            {
                "already_registered": describe(result.already_registered, result.already_message),
                "possible_duplicate": describe(result.possible_duplicate, result.duplicate_message),
                "waitlist": result.waitlist_message,
            }
        )

    @action(detail=True, methods=["get", "post"], url_path="imports")
    def imports(self, request, pk=None):
        race = self.get_object()
        if request.method == "GET":
            batches = race.imports.select_related("channel").order_by("-id")[:RECENT_IMPORTS]
            return Response(ImportBatchSerializer(batches, many=True).data)
        upload = ImportUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)
        batch = submit_import(race, upload.validated_data["channel"], upload.validated_data["file"])
        return Response(ImportBatchSerializer(batch).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["get", "post"], url_path="confirmations")
    def confirmations(self, request, pk=None):
        """GET: cifras del envío de confirmaciones y las fallidas con su motivo.
        POST: encola el envío de las pendientes de esta carrera (202)."""
        race = self.get_object()
        if request.method == "GET":
            data = send_confirmations.race_status(race)
            return Response(ConfirmationStatusSerializer(data).data)
        if race.date < timezone.localdate():
            return Response(
                {"detail": "La carrera ya se ha celebrado: no se envían confirmaciones."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        pending = send_confirmations.request_send(race)
        if not pending:
            return Response(
                {"queued": False, "pending": 0, "message": "No hay confirmaciones pendientes."}
            )
        return Response(
            {
                "queued": True,
                "pending": pending,
                "message": f"Enviando {pending} confirmaciones en segundo plano.",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class ImportBatchViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = ImportBatch.objects.select_related("channel")
    serializer_class = ImportReportSerializer

    @action(detail=True, methods=["get"])
    def issues(self, request, pk=None):
        """Todas las incidencias, paginadas. Filtros: kind, code, field, value, new=1."""
        batch = get_object_or_404(ImportBatch, pk=pk)
        issues = batch.issues.select_related("registration").order_by("line", "id")
        for param, lookup in (
            ("kind", "kind"),
            ("code", "code"),
            ("field", "field"),
            ("value", "group_value"),
        ):
            if param in request.query_params:
                issues = issues.filter(**{lookup: request.query_params[param]})
        if request.query_params.get("new") in ("1", "true"):
            issues = issues.filter(is_new=True)
        paginator = Pages()
        page = paginator.paginate_queryset(issues, request, view=self)
        return paginator.get_paginated_response(IssueSerializer(page, many=True).data)


class RegistrationViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Registration.objects.select_related(
        "race", "channel", "possible_duplicate_of"
    ).prefetch_related("also_channels", "notifications")
    serializer_class = RegistrationSerializer

    def partial_update(self, request, pk=None):
        """Corregir datos. Dorsal, estado y canal no se cambian desde aquí."""
        self.get_object()  # 404 si no existe
        data = RegistrationDataSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            result = registrations.update_registration(int(pk), data.validated_data)
        except RegistrationRejected as exc:
            return rejected(exc)
        except AlreadyRegistered as exc:
            return already_registered(exc)
        return Response(
            {
                "registration": RegistrationSerializer(self.get_object()).data,
                "changes": [d.describe() for d in result.changes],
                "notice": result.notice,
            }
        )

    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        """Baja manual o confirmación de la baja de un ausente: el dorsal no se reutiliza."""
        self.get_object()
        result = register.withdraw(int(pk))
        reg = result.registration
        if result.already_withdrawn:
            message = f"La inscripción de {reg.first_name} {reg.last_name} ya estaba de baja."
        else:
            message = (
                f"Baja de {reg.first_name} {reg.last_name}. {promoted_message(result.promoted)}"
            )
        return Response(
            {
                "registration": RegistrationSerializer(self.get_object()).data,
                "already_withdrawn": result.already_withdrawn,
                "promoted": RegistrationSummarySerializer(result.promoted, many=True).data,
                "message": message.strip(),
            }
        )


class NotificationViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Notification.objects.select_related("registration__channel")
    serializer_class = NotificationSerializer

    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        """Una fallida vuelve a pendiente (intentos a cero, misma clave) y se encola el envío."""
        self.get_object()  # 404 si no existe
        try:
            send_confirmations.retry_failed(int(pk))
        except CannotRetry as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(
            {
                "notification": NotificationSerializer(self.get_object()).data,
                "message": "Se volverá a intentar enseguida.",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class ChannelViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Channel.objects.all()
    serializer_class = ChannelSerializer
    pagination_class = None
