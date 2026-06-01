from rest_framework.routers import DefaultRouter

from .views import JobPostingViewSet


router = DefaultRouter()
router.register(r"jobs", JobPostingViewSet, basename="jobposting")

urlpatterns = router.urls