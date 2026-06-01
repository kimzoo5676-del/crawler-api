# Day 4 (2026/6/01) — DRF ViewSet + Router + 필터링 + 페이지네이션으로 조회 API 완성

> 자세한 정리: [Velog 포스트](https://velog.io/@zooouu/%EB%B0%B0%ED%8F%AC-%ED%95%99%EC%8A%B5%EC%9A%A9-%ED%86%A0%EC%9D%B4%ED%94%84%EB%A1%9C%EC%A0%9D%ED%8A%B8-DAY-4)

## 오늘의 목표

- Day 3의 `JobPosting` 모델·ModelSerializer를 바탕으로 조회용 REST API 구성
- view를 ViewSet으로 통합 (FBV → CBV → Generics 다음 단계)
- Router로 URL 자동 생성
- django-filter + DRF 내장 필터로 검색·정렬·필터링
- 페이지네이션으로 대량 응답 분할

---

## 1. ViewSet

### Generics 다음 단계

Day 3까지의 view 진화는 FBV → CBV → Generics. Generics는 list용·detail용 클래스를 분리하면서 동일한 `queryset`·`serializer_class`를 반복 선언하는 중복이 남음. ViewSet은 이 중복을 단일 클래스로 통합.

> A ViewSet class is simply a type of class-based View, that does not provide any method handlers such as .get() or .post(), and instead provides actions such as .list() and .create(). The method handlers for a ViewSet are only bound to the corresponding actions at the point of finalizing the view, using the .as_view() method.

번역: ViewSet은 클래스 기반 view의 일종이나 `.get()`·`.post()` 같은 메서드 핸들러를 제공하지 않고, 대신 `.list()`·`.create()` 같은 action을 제공. 메서드 핸들러는 `.as_view()`로 view를 최종 확정하는 시점에야 해당 action에 바인딩.

→ HTTP 메서드(get/post)가 아니라 추상적 action(list/retrieve/create)으로 사고하는 것이 핵심. 어떤 action이 어떤 URL·메서드에 묶일지는 마지막 순간에 결정(late binding)되며, 그 결정을 Router가 관례대로 자동 처리.

### action ↔ HTTP 메서드 ↔ URL 매핑

| Action | HTTP Method | URL |
|---|---|---|
| list | GET | `/jobs/` |
| create | POST | `/jobs/` |
| retrieve | GET | `/jobs/{pk}/` |
| update | PUT | `/jobs/{pk}/` |
| partial_update | PATCH | `/jobs/{pk}/` |
| destroy | DELETE | `/jobs/{pk}/` |

URL은 두 종류(`/jobs/`, `/jobs/{pk}/`)이며 HTTP 메서드에 따라 다른 action으로 분기. Day 3의 `if request.method` 분기를 Router가 이 표대로 대신 처리.

### ViewSet 종류 선택 — ReadOnlyModelViewSet

> The actions provided by the ModelViewSet class are .list(), .retrieve(), .create(), .update(), .partial_update(), and .destroy().
>
> (ReadOnlyModelViewSet) unlike ModelViewSet only provides the 'read-only' actions, .list() and .retrieve().

번역: ModelViewSet은 6개 action 전체(list/retrieve/create/update/partial_update/destroy)를 제공. ReadOnlyModelViewSet은 읽기 전용 action인 `.list()`·`.retrieve()`만 제공.

crawler-api에서 데이터의 출처는 크롤러. 클라이언트는 조회만 하며, 생성·수정·삭제는 크롤러의 `update_or_create`가 담당. 클라이언트에 쓰기 action을 노출할 설계 의도가 없으므로 ReadOnlyModelViewSet 채택.

ModelViewSet을 쓰면 POST·PUT·PATCH·DELETE 엔드포인트가 자동 노출되어, 크롤러가 채우는 DB를 클라이언트가 임의로 수정·삭제할 수 있는 표면이 생김. ReadOnlyModelViewSet은 해당 action을 애초에 라우팅하지 않으므로, 권한으로 막기보다 노출 표면 자체를 제거. 최소 권한(least privilege)의 API 레이어 적용.

### 코드 (api/views.py)

```python
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, filters

from .models import JobPosting
from .serializers import JobPostingSerializer


class JobPostingViewSet(viewsets.ReadOnlyModelViewSet):
    """
    채용공고 조회 전용 ViewSet.
    list / retrieve 두 액션만 제공 (생성·수정·삭제는 크롤러가 담당).
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
```

### 짚은 것

- `queryset`·`serializer_class`: Day 3 Generics에서 쓰던 두 속성 그대로. ViewSet도 `GenericAPIView` 자식이라 동일하게 동작. `model = ...` 속성은 없음 — 모델은 `queryset`에서 추론.
- `.order_by("-created_at")`: 정렬 미지정 시 페이지네이션에서 페이지별 순서가 어긋날 수 있어 명시 필요. 최근 수집 항목을 상단에 두는 의도도 반영.

---

## 2. Router

### URL 자동 생성

ViewSet의 action ↔ URL 매핑을 관례에 따라 자동 생성. urlconf 수동 작성 불필요.

> (DefaultRouter) is similar to SimpleRouter as above, but additionally includes a default API root view, that returns a response containing hyperlinks to all the list views. It also generates routes for optional .json style format suffixes.

번역: DefaultRouter는 SimpleRouter와 유사하나, 모든 list view로 향하는 하이퍼링크를 담은 API 루트 view, 그리고 `.json` 형식 접미사 라우트를 추가 생성.

→ SimpleRouter는 action↔URL 매핑만 생성. DefaultRouter는 거기에 API 루트 view(`/api/`)와 `.json` 접미사를 추가.

### DefaultRouter 채택

학습·검증 단계에서 API 루트 view와 Browsable API의 탐색 편의가 유용. 브라우저로 엔드포인트·필터·페이지네이션을 직접 확인 가능. 운영용 순수 API 서버라면 노출 표면 최소화 관점에서 SimpleRouter를 고려할 여지가 있으나, 현 단계 목표가 브라우저 검증이므로 DefaultRouter가 적합.

### 코드 (api/urls.py)

```python
from rest_framework.routers import DefaultRouter

from .views import JobPostingViewSet


router = DefaultRouter()
router.register(r"jobs", JobPostingViewSet, basename="jobposting")

urlpatterns = router.urls
```

### 코드 (config/urls.py)

```python
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
]
```

### 짚은 것

- prefix(`r"jobs"`)에 끝 슬래시 미포함. 표준 Django URL과 달리 Router가 슬래시를 자동 부착하므로 `r"jobs/"`로 쓰면 안 됨.
- `basename` 명시: `queryset`이 있으면 자동 추론되나, 추후 `get_queryset()` override 시 자동 추론이 깨지며 에러 발생. 미리 명시해 함정 회피.
- `api/` 접두사를 프로젝트 레벨에서 단일 지정. 앱별 URL 분리 구조. 최종 경로 — `/api/`(루트), `/api/jobs/`(list), `/api/jobs/{pk}/`(retrieve).

---

## 3. 필터링

### 필터 백엔드 3종의 용도 구분

JobPosting 필드별로 "어떻게 거를지"가 셋으로 갈림.

| 백엔드 | 파라미터 | 매칭 | 대상 |
|---|---|---|---|
| DjangoFilterBackend | `?source=` | 정확히 일치 | source |
| SearchFilter | `?search=` | 부분 일치 | title·company·location |
| OrderingFilter | `?ordering=` | 정렬 | created_at·deadline |

source(수집 출처)는 카테고리성 값이라 정확히 일치, title 등 자유 텍스트는 부분 검색, 날짜 필드는 정렬이 자연스러움.

> By default, searches will use case-insensitive partial matches.

번역: 기본적으로 검색은 대소문자 구분 없는 부분 일치(icontains) 사용.

> (ordering_fields 명시는) helps prevent unexpected data leakage, such as allowing users to order against a password hash field or other sensitive data.

번역: 정렬 허용 필드를 명시하면 password 해시 등 민감 데이터에 대한 정렬을 막아 의도치 않은 노출을 방지.

### 설치·등록

```bash
pip install django-filter
```

```python
INSTALLED_APPS = [
    # ...
    "rest_framework",
    "django_filters",  # 설치명 django-filter, 앱명 django_filters
    "api",
]
```

DjangoFilterBackend만 별도 패키지. SearchFilter·OrderingFilter는 DRF 내장이라 설치 불필요.

### 짚은 것

- 등록 위치(뷰별): 필터는 ViewSet에 `filter_backends`로 뷰별 선언. 각 엔드포인트가 지원하는 필터를 코드에 명시적으로 드러냄. 전역 설정의 암묵적 동작보다 추적 가능성을 우선.
- import 경로가 둘로 갈림: `DjangoFilterBackend`는 `django_filters.rest_framework`, `SearchFilter`·`OrderingFilter`는 `rest_framework.filters`. 가장 헷갈리는 지점.

### 검증

- `?source=fake-jobs`: 크롤러가 source를 "fake-jobs" 고정 저장하므로 이 값만 매칭.
- `?source=engineer`: 정확히 일치하는 source가 없어 빈 리스트 `[]` 반환(404 아님, list는 비어도 200).
- `?search=engineer`: title에 "engineer" 포함 항목 반환. 대문자 "Engineer"도 매칭되어 icontains(대소문자 무시 부분 일치) 동작 확인.

---

## 4. 페이지네이션

### 페이지네이션 3종과 offset의 한계

| 방식 | 파라미터 | 특징 |
|---|---|---|
| PageNumberPagination | `?page=4` | 페이지 번호. 임의 페이지 점프 가능 |
| LimitOffsetPagination | `?limit=20&offset=40` | SQL LIMIT/OFFSET |
| CursorPagination | `?cursor=...` | 커서. 앞뒤 이동만. 대용량에 강함 |

PageNumber·LimitOffset은 SQL OFFSET 기반이라 두 문제를 가짐. 깊은 페이지일수록 DB가 앞 데이터를 세고 건너뛰어 느려지며, 페이징 도중 상단에 데이터가 삽입되면 중복·누락 발생.

> Provides a consistent pagination view. When used properly CursorPagination ensures that the client will never see the same item twice when paging through records, even when new items are being inserted by other clients during the pagination process.

번역: CursorPagination은 일관된 페이지 뷰를 제공. 제대로 사용하면 페이징 도중 다른 클라이언트가 새 항목을 삽입해도 동일 항목을 두 번 보는 일이 없음.

### 설계상 정답은 커서, 실습은 PageNumber

crawler-api는 크롤러가 주기적으로 새 공고를 상단(`-created_at`)에 삽입하는 타임라인형 데이터로, "페이징 도중 삽입" 시나리오에 직접 해당. `created_at`(`auto_now_add`)은 생성 시 한 번만 찍히는 불변값이라 커서의 정렬 필드 요건을 충족. 설계상 CursorPagination이 최적.

다만 커서는 특정 페이지 점프가 불가하고 커서 문자열의 가독성이 낮아 학습 초기 부담. 기본 구조(count·next·previous·results) 체득을 위해 PageNumberPagination으로 실습을 시작하고, 추후 커서 전환을 별도 마이그레이션 학습 소재로 보류.

> Note that you need to set both the pagination class, and the page size that should be used. Both DEFAULT_PAGINATION_CLASS and PAGE_SIZE are None by default.

번역: 페이지네이션 클래스와 page size 양쪽을 모두 설정해야 함. 둘 다 기본값이 `None`이라 한쪽이라도 누락되면 페이지네이션이 적용되지 않음.

### 코드 (settings — base)

```python
REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}
```

### 짚은 것

- 등록 위치(전역): 필터와 달리 페이지네이션은 settings에 전역 등록. API 전체의 일관된 스타일 유지가 관례. 설정 분리(base/dev/prod) 구조에서 환경 공통이므로 base에 배치.
- views.py 수정 불필요: ViewSet은 GenericAPIView 자식이라 전역 설정이 자동 적용.
- 클래스와 PAGE_SIZE 둘 다 필요: 하나만 설정하면 조용히 미적용되는 가장 흔한 실수.

### 응답 구조 변화

적용 전에는 데이터 배열을 직접 반환했으나, 적용 후 메타데이터로 래핑.

```json
{
    "count": 100,
    "next": "http://127.0.0.1:8000/api/jobs/?page=2",
    "previous": null,
    "results": [ ... ]
}
```

| 키 | 의미 |
|---|---|
| count | 전체 개수(필터 적용 시 필터된 전체) |
| next | 다음 페이지 URL(마지막이면 null) |
| previous | 이전 페이지 URL(1페이지면 null) |
| results | 이번 페이지 데이터 배열 |

→ 데이터가 `results` 안으로 들어가므로, 프론트 연동 시 접근 경로가 `response.data` → `response.data.results`로 변경. 백엔드-프론트 계약(contract)의 일부가 됨.

### 검증

- `/api/jobs/`: `count: 100`, `results` 20개, `next`에 page=2 URL, `previous: null`.
- `id: 100` "Ship broker"가 results 최상단. `-created_at` 정렬과 페이지네이션 연동 확인.
- Browsable API 하단에 페이지 버튼 `« 1 2 3 4 5 »` 생성(100 ÷ 20 = 5페이지).
- `?search=engineer&page=1`: 필터·정렬·페이지네이션이 한 URL에서 함께 동작.

---

## 오늘의 정리

- 조회 API 완성: ReadOnlyModelViewSet(list·retrieve) + DefaultRouter(자동 라우팅·Browsable API) + 3종 필터(source/search/ordering) + PageNumberPagination(20개씩).
- 두 가지 설계 결정의 "왜"를 확보: ReadOnly 채택(노출 표면 최소화), 커서가 설계상 정답이나 PageNumber로 실습 시작(기본 구조 체득 후 전환).
- 필터(뷰별)와 페이지네이션(전역)의 등록 위치 구분 — 추적 가능성 vs API 일관성의 트레이드오프.
- Day 3 설계(url unique, auto_now_add 불변값)가 Day 4의 update_or_create 중복 방지·커서 정렬 필드 요건으로 그대로 이어짐.

## 다음 (Week 2)

EC2 수동 배포. 설정 분리(base/dev/prod) 구조 기반으로 prod 환경 적용.