from django.urls import path
from rest_framework.routers import DefaultRouter

from races.api.views import (
    ChannelViewSet,
    ImportBatchViewSet,
    JobRunViewSet,
    NotificationViewSet,
    RaceViewSet,
    RegistrationViewSet,
    SettingsView,
)

router = DefaultRouter()
router.register("races", RaceViewSet)
router.register("imports", ImportBatchViewSet)
router.register("channels", ChannelViewSet)
router.register("registrations", RegistrationViewSet)
router.register("notifications", NotificationViewSet)
router.register("job-runs", JobRunViewSet, basename="job-run")

urlpatterns = [path("settings/", SettingsView.as_view(), name="settings"), *router.urls]
