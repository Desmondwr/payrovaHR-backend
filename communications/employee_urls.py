from rest_framework.routers import DefaultRouter

from .views import EmployeeCommunicationViewSet

router = DefaultRouter()
router.register(r"", EmployeeCommunicationViewSet, basename="employee-communications")

urlpatterns = router.urls
