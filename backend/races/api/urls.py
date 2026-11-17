from rest_framework.routers import DefaultRouter

from races.api.views import ChannelViewSet, ImportBatchViewSet, RaceViewSet

router = DefaultRouter()
router.register("races", RaceViewSet)
router.register("imports", ImportBatchViewSet)
router.register("channels", ChannelViewSet)

urlpatterns = router.urls
