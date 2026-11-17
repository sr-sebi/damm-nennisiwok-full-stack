from rest_framework.routers import DefaultRouter

from races.api.views import ChannelViewSet, ImportBatchViewSet, RaceViewSet, RegistrationViewSet

router = DefaultRouter()
router.register("races", RaceViewSet)
router.register("imports", ImportBatchViewSet)
router.register("channels", ChannelViewSet)
router.register("registrations", RegistrationViewSet)

urlpatterns = router.urls
