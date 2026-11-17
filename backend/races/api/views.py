from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from races.api.serializers import (
    ChannelSerializer,
    ImportBatchSerializer,
    ImportReportSerializer,
    ImportUploadSerializer,
    IssueSerializer,
    RaceSerializer,
)
from races.application.import_registrations import submit_import
from races.models import Channel, ImportBatch, Race

RECENT_IMPORTS = 20


class Pages(PageNumberPagination):
    page_size = 50


class RaceViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Race.objects.all()
    serializer_class = RaceSerializer

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


class ChannelViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = Channel.objects.all()
    serializer_class = ChannelSerializer
    pagination_class = None
