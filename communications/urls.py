from rest_framework.routers import DefaultRouter

from .views import CommunicationViewSet, CommunicationTemplateViewSet

router = DefaultRouter()
# Register specific prefixes first so they are not swallowed by the empty prefix route.
router.register(r"templates", CommunicationTemplateViewSet, basename="communication-templates")
router.register(r"", CommunicationViewSet, basename="communications")

urlpatterns = router.urls
