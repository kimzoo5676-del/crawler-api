# Day 2 - DRF Serializer & View (2026-05-27)

> 자세한 정리: [Velog 포스트](https://velog.io/@zooouu/%EB%B0%B0%ED%8F%AC-%ED%95%99%EC%8A%B5%EC%9A%A9-%ED%86%A0%EC%9D%B4%ED%94%84%EB%A1%9C%EC%A0%9D%ED%8A%B8-DAY-2)

## 오늘 한 것
- tutorial 앱 생성, Snippet 모델 + 마이그레이션
- SnippetSerializer 작성 (create/update 메서드 포함)
- Django Shell로 직렬화/역직렬화 흐름 실습 (3 시나리오)
- View 발전 단계: FBV → APIView → Generic View
- URL 매핑 (path, include, .as_view)
- GitHub Milestones 4개 + Week 2 이슈 4개 세팅

## 학습 포인트
### 모델 / DB
- Model = 설계도 / makemigrations = 계획서 / migrate = 실제 공사
- `CharField(choices=..., default=..., max_length=...)` 필드 옵션 조합
- `class Meta: ordering = ["created"]` — 조회 기본 정렬 (오름차순)

### Serializer
- Serializer = 객체 ↔ JSON 양방향 통역사 + 검사관
- `Serializer(객체)` = 직렬화 / `Serializer(data=...)` = 역직렬화
- `many=True`로 QuerySet 직렬화
- `read_only=True`는 출력만 허용, 입력 무시 (보안 패턴)
- 흐름:
  - 직렬화: `[DB] Python 객체 → Serializer → JSON → [클라이언트]`
  - 역직렬화: `[클라이언트] JSON → Serializer → Python 객체 → DB`

### View 추상화 사다리
- `@api_view` (FBV) → `APIView` (CBV) → `generics.XxxAPIView`
- Generic View = mixin + GenericAPIView 조합의 별명
- `.as_view()`로 클래스 → URL 연결 가능한 형태로 변환

## 막힌 부분
- 환경 옮긴 후 SECRET_KEY 에러 → `.env`는 .gitignore에 있으니 새 환경에서 새로 생성 (어제 학습한 보안 패턴 실증)
- `from snippets.models` → 우리 앱은 `tutorial`이라 import 경로 변경 필요
- `tutorial/urls.py` 빈 파일 → "no patterns" 에러
- `SnippetDetail`에 `queryset` 줄 빠뜨림 → "should include queryset attribute"
- POST 시 JSON 직접 입력 문법 실수 → HTML form 탭이 더 안전

## 공식과 다르게 간 부분
- 단계 A (csrf_exempt + JSONParser) 생략, 바로 @api_view부터
- format_suffix_patterns 생략
- mixins 단계는 개념만 이해하고 generics로 도약

## 다음 할 일 (Day 3)
- api 앱에 본 프로젝트 모델 설계
- ModelSerializer 사용 (오늘 손으로 짠 Serializer의 자동화 버전)
- 데이터 수집 크롤러 모듈 시작

## 참고 링크
- [DRF Tutorial 1 - Serialization](https://www.django-rest-framework.org/tutorial/1-serialization/)
- [DRF Tutorial 2 - Requests and Responses](https://www.django-rest-framework.org/tutorial/2-requests-and-responses/)
- [DRF Tutorial 3 - Class based views](https://www.django-rest-framework.org/tutorial/3-class-based-views/)