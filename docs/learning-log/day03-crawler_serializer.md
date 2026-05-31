# Day 3 (2026/5/28) — 본 프로젝트 모델 설계 + 크롤러 + ModelSerializer

> 자세한 정리: [Velog 포스트](https://velog.io/@zooouu/%EB%B0%B0%ED%8F%AC-%ED%95%99%EC%8A%B5%EC%9A%A9-%ED%86%A0%EC%9D%B4%ED%94%84%EB%A1%9C%EC%A0%9D%ED%8A%B8-DAY-3)

## 오늘의 목표

- `api` 앱에 채용공고 수집 대상 모델(`JobPosti₩ng`) 설계
- `requests` + `BeautifulSoup` 크롤러 모듈 작성
- 크롤링 결과를 management command로 DB에 저장
- Day 2의 수동 Serializer를 ModelSerializer로 자동화

---

## 1. JobPosting 모델 설계

### 수집 대상 결정

실제 채용 사이트(사람인) robots.txt 확인 결과, 공고 상세 경로(`/zf_user/recruit/view/`)가 `Disallow`로 막혀 있고 AI/봇 계열은 전체 차단(`User-agent: GPTBot Disallow: /`). 약관상으로도 크롤링 금지. 따라서 크롤링 연습용으로 공개된 `https://realpython.github.io/fake-jobs/`(SSR, robots 허용)를 대상으로 결정.

robots.txt를 먼저 읽고 수집 가능 여부를 판단하는 과정 자체가 크롤러 개발의 첫 단계.

### 모델 코드

```python
from django.db import models


class JobPosting(models.Model):
    company = models.CharField(max_length=100)
    title = models.CharField(max_length=200)
    url = models.URLField(unique=True)
    location = models.CharField(max_₩₩₩₩length=100, blank=True)
    deadline = models.DateField(null=True, blank=True)
    source = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"[{self.company}] {self.title}"
```

### 설계 근거

#### url에 unique=True

크롤러는 같은 공고를 여러 번 수집하게 되므로, URL을 유니크 키로 잡아 `update_or_create(url=...)`로 "있으면 갱신, 없으면 생성" 처리. 

#### null과 blank의 차이

> If True, Django will store empty values as NULL in the database. (null)
>
> If True, the field is allowed to be blank. Note that this is different than null. null is purely database-related, whereas blank is validation-related. (blank)

번역: `null=True`는 빈 값을 DB에 NULL로 저장하는 것(데이터베이스 관련). `blank=True`는 필드가 비어 있어도 됨을 의미하는 것(검증 관련).

- `null=True`만: DB에는 NULL 허용하나, 폼/Serializer 검증에서는 필수로 거부
- `null=True, blank=True`: DB·검증 양쪽 모두 빈 값 허용

`deadline`은 상시채용 공고에서 마감일이 없을 수 있고, 코드(크롤러)와 API 요청 양쪽 경로 모두에서 비어 있어야 하므로 둘 다 적용.

#### CharField에는 null을 쓰지 않음

> Avoid using null on string-based fields such as CharField and TextField. If a string-based field has null=True, that means it has two possible values for "no data": NULL, and the empty string. The Django convention is to use the empty string, not NULL.

번역: 문자열 기반 필드에 `null=True`를 주면 '데이터 없음'을 나타내는 값이 NULL과 빈 문자열 두 개가 되어버림. Django 관례는 빈 문자열 사용.

→ `location`(CharField)은 `blank=True`만 적용, `null`은 미적용. 빈 위치는 `""`로 저장. 반면 `deadline`(DateField)은 빈 문자열 개념이 없으므로 `null=True`가 정당.

#### auto_now_add vs auto_now

> auto_now_add: Automatically set the field to now when the object is first created.
>
> auto_now: Automatically set the field to now every time the object is saved.

번역: `auto_now_add`는 객체가 처음 생성될 때, `auto_now`는 저장될 때마다 현재 시각으로 설정.

→ `created_at`은 생성 시 한 번만 찍혀야 하므로 `auto_now_add`, `updated_at`은 갱신마다 찍혀야 하므로 `auto_now`.

### 마이그레이션

```bash
python manage.py makemigrations   # 설계도 생성 → 0001_initial.py
python manage.py migrate           # 실제 DB에 테이블 생성
```

`makemigrations`는 모델 변경을 바탕으로 마이그레이션 파일 생성(DB 미변경), `migrate`는 이를 실제 DB에 적용. `Applying api.0001_initial... OK`로 `api_jobposting` 테이블 생성 확인.

---

## 2. 크롤러 모듈 (requests + BeautifulSoup)

### HTML 구조 분석

브라우저 검사(Inspect)로 직접 확인한 fake-jobs 카드 구조:

| 모델 필드 | HTML 위치 | 선택자 |
|---|---|---|
| title | `<h2 class="title is-5">` | `h2.title` |
| company | `<h3 class="subtitle is-6 company">` | `h3.company` |
| location | `<p class="location">` | `p.location` |
| url | footer의 두 번째 `<a>` (Apply) | `footer.card-footer a` 중 [1] |

footer에는 `<a>`가 두 개(Learn / Apply). 첫 번째는 realpython.com(불필요), 두 번째가 공고 상세 링크.

### 라이브러리 역할

> Requests allows you to send HTTP/1.1 requests extremely easily.

번역: Requests는 HTTP/1.1 요청을 매우 쉽게 보낼 수 있게 함.

> Beautiful Soup is a Python library for pulling data out of HTML and XML files. It provides idiomatic ways of navigating, searching, and modifying the parse tree.

번역: Beautiful Soup는 HTML·XML에서 데이터를 추출하는 라이브러리. 파스 트리를 탐색·검색·수정하는 방법 제공.

→ requests가 HTML을 받아오고, BeautifulSoup가 그 HTML에서 데이터를 뽑아냄. 한 쌍.

### 크롤러 코드 (api/crawler.py)

```python
import requests
from bs4 import BeautifulSoup

URL = "https://realpython.github.io/fake-jobs/"


def fetch_html(url):
    response = requests.get(url)
    response.raise_for_status()
    return response.text


def parse_jobs(html):
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("div.card-content")
    print(f"찾은 카드 수: {len(cards)}")
    return cards


def extract_one(card):
    title = card.select_one("h2.title").get_text(strip=True)
    company = card.select_one("h3.company").get_text(strip=True)
    location = card.select_one("p.location").get_text(strip=True)
    links = card.select("footer.card-footer a")
    url = links[1]["href"]
    return {
        "title": title,
        "company": company,
        "location": location,
        "url": url,
        "source": "fake-jobs",
    }


def crawl():
    html = fetch_html(URL)
    cards = parse_jobs(html)
    return [extract_one(card) for card in cards]


if __name__ == "__main__":
    jobs = crawl()
    print(f"총 {len(jobs)}개 수집")
    print(jobs[0])
```

### 짚은 것

- `response.raise_for_status()`: 4XX/5XX 응답 시 예외 발생. 빈 HTML을 파싱하다 엉뚱한 에러가 나는 것을 방지하고 즉시 중단.
- `select` vs `select_one`: `select`는 일치 요소 전부를 리스트로 반환, `select_one`은 첫 번째 하나만 반환. 제목은 카드당 하나이므로 `select_one`, footer 링크는 두 개이므로 `select` 후 인덱스로 선택.
- `get_text(strip=True)`: 텍스트만 추출하고 앞뒤 공백·줄바꿈 제거. `strip=True` 없으면 `\n` 공백이 딸려옴.
- `links[1]["href"]`: 태그 속성은 딕셔너리처럼 접근. 인덱스 1 = Apply 링크.
- crawler.py는 "긁어서 딕셔너리 리스트 반환"까지만 담당. DB 저장은 분리(관심사 분리).

실행 결과: 카드 100개 수집 확인.

---

## 3. management command로 DB 저장

### 순수 파이썬 실행으로는 ORM 사용 불가

`python api/crawler.py`로 실행하면 Django 설정이 로드되지 않아 `JobPosting.objects...` 사용 시 에러. Django ORM은 Django가 부팅된 상태에서만 동작.

> Applications can register their own actions with manage.py. This is the recommended way to create a script that needs to access the Django ORM and other Django features.

번역: 애플리케이션은 manage.py에 자신의 동작을 등록 가능. Django ORM 등에 접근하는 스크립트를 만드는 권장 방법.

### 폴더 구조

```
api/management/__init__.py
api/management/commands/__init__.py
api/management/commands/crawl_jobs.py
```

`__init__.py` 두 개 필수(파이썬 패키지 인식용). 폴더명은 정확히 `management`, `commands`(복수형). 하나라도 어긋나면 `Unknown command` 발생. `Unknown command`는 "명령 내용이 틀렸다"가 아니라 "파일을 발견조차 못 했다"는 신호이므로, 코드가 아니라 위치·이름·`__init__.py` 구조부터 의심하는 것이 정석.

### command 코드 (api/management/commands/crawl_jobs.py)

```python
from django.core.management.base import BaseCommand

from api.crawler import crawl
from api.models import JobPosting


class Command(BaseCommand):
    help = "fake-jobs 사이트에서 채용공고를 수집해 DB에 저장"

    def handle(self, *args, **options):
        jobs = crawl()
        created_count = 0
        updated_count = 0

        for job in jobs:
            obj, created = JobPosting.objects.update_or_create(
                url=job["url"],
                defaults={
                    "title": job["title"],
                    "company": job["company"],
                    "location": job["location"],
                    "source": job["source"],
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"완료 - 생성 {created_count}개, 갱신 {updated_count}개"
            )
        )
```

### 짚은 것

- `BaseCommand` 상속 + `handle()` 메서드: 클래스명은 반드시 `Command`, 로직은 `handle()` 안. Django가 이 규약으로 발견·실행.
- `update_or_create(url=..., defaults={...})`:

> A convenience method for updating an object with the given kwargs, creating a new one if necessary. Returns a tuple of (object, created).

번역: 주어진 kwargs로 객체를 갱신하되 필요 시 새로 생성하는 편의 메서드. `(객체, 생성여부)` 튜플 반환.

→ `url`로 기존 레코드를 찾고, 있으면 `defaults` 값으로 갱신, 없으면 생성. `created`(True/False)로 구분.
- `self.stdout.write` / `self.style.SUCCESS`: command 내부에서는 `print` 대신 사용.

### 실행 결과 — update_or_create 검증

```
# 1회차
완료 - 생성 100개, 갱신 0개
# 2회차
완료 - 생성 0개, 갱신 100개
```

두 번 실행해도 공고가 200개로 불어나지 않음. `url` unique 제약 + `update_or_create`가 중복을 막는 것을 실제로 확인. Day 1에 "왜 url에 unique를 거는가"로 설계한 이유가 동작으로 증명됨.

---

## 4. ModelSerializer

### Day 2 수동 Serializer의 자동화

> The ModelSerializer class is the same as a regular Serializer class, except that: It will automatically generate a set of fields for you, based on the model. It will automatically generate validators for the serializer. It includes simple default implementations of .create() and .update().

번역: ModelSerializer는 일반 Serializer와 같되, 모델을 바탕으로 필드 집합을 자동 생성하고, 검증기를 자동 생성하며, `.create()`/`.update()`의 기본 구현을 포함.

→ Day 2에 손으로 선언한 필드 + create/update를 모델 기반으로 전부 자동화.

### 코드 (api/serializers.py)

```python
from rest_framework import serializers

from .models import JobPosting


class JobPostingSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobPosting
        fields = "__all__"
```

- `class Meta`: 어떤 모델을, 어떤 필드로 직렬화할지 선언.
- `fields = "__all__"`: 모델의 모든 필드 포함. 단, 실무에서는 민감 필드의 의도치 않은 노출을 막기 위해 명시적 나열을 권장. 학습 단계라 전체 확인 목적으로 `__all__` 사용.

### 직렬화 결과 확인

```python
from api.models import JobPosting
from api.serializers import JobPostingSerializer

job = JobPosting.objects.first()
serializer = JobPostingSerializer(job)
print(serializer.data)

jobs = JobPosting.objects.all()[:3]
serializer = JobPostingSerializer(jobs, many=True)
print(serializer.data)
```

출력 예시:

```python
{'id': 1, 'company': 'Payne, Roberts and Davis', 'title': 'Senior Python Developer',
 'url': 'https://realpython.github.io/fake-jobs/jobs/senior-python-developer-0.html',
 'location': 'Stewartbury, AA', 'deadline': None, 'source': 'fake-jobs',
 'created_at': '2026-05-31T16:23:32.222325+09:00',
 'updated_at': '2026-05-31T16:23:45.280244+09:00'}
```

### 출력에서 확인된 설계 검증

- `deadline: None`: `null=True, blank=True`로 설계한 필드가 JSON에서 `null`로 직렬화. (값이 있었다면 `location`의 빈 값은 `""`로 나왔을 것 — null vs blank 차이의 실데이터 반영)
- `created_at`(16:23:32)과 `updated_at`(16:23:45) 시각 차이: 크롤러 2회 실행 결과. 1회차 생성 시 `created_at`, 2회차 갱신 시 `updated_at`만 갱신. `auto_now_add` vs `auto_now` 차이가 타임스탬프로 증명.
- `+09:00`: Day 1에 설정한 KST 시간대가 ISO 8601 직렬화에 반영.
- `id`: 모델에 선언하지 않았으나 Django가 자동 생성한 PK가 `__all__`로 포함.
- `many=True`: 단일 객체는 그냥, 쿼리셋/리스트는 `many=True` 플래그 필요.

---

## 오늘의 정리

- 설계(모델) → 구현(크롤러 + command) → 검증(직렬화 출력)이 한 바퀴 완결.
- 설계 단계의 "왜"(url unique, null vs blank, auto_now 차이)가 전부 실제 동작·출력으로 확인됨.
- robots.txt를 읽고 수집 대상을 판단하는 것, 추측이 아니라 브라우저 검사로 HTML 구조를 확인하는 것, management command 인식 실패를 구조 문제로 진단하는 것 — 크롤러/Django 실무의 기본기.

## 다음 (Day 4)

DRF ViewSet + Router, 필터링(django-filter), 페이지네이션으로 조회 API 완성.