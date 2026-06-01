from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, filters
from .models import JobPosting
from .serializers import JobPostingSerializer


# Create your views here.
class JobPostingViewSet(viewsets.ReadOnlyModelViewSet):
    """
    채용공고 조회 전용 ViewSet.
    list / retrieve 두 액션만 제공 (생성,수정,삭제는 크롤러가 담당)
    """

    queryset = JobPosting.objects.all().order_by("-created_at")
    serializer_class = JobPostingSerializer

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["source"]
    search_fields = ["title", "company", "location"]
    ordering_fields = ["created_at", "deadline"]
    ordering = ["-created_at"]
