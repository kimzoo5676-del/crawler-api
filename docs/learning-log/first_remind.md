# Learning Log — Week 1~2 (Day 1~8)

crawler-api 배포 학습 프로젝트의 진행 기록. 각 Day의 상세 정리는 [Velog](https://velog.io/@zooouu/%EB%B0%B0%ED%8F%AC-%ED%95%99%EC%8A%B5%EC%9A%A9-%ED%86%A0%EC%9D%B4%ED%94%84%EB%A1%9C%EC%A0%9D%ED%8A%B8-Remind-01)에, 이 문서는 전체 흐름의 인덱스 역할.

## 개요

| 구간 | 목표 | 경계선 |
|---|---|---|
| Week 1 (Day 1~4) | 애플리케이션 만들기 | 내 노트북에서 도는 조회 API |
| Week 2 (Day 5~8) | 배포하기 | 세상이 접속하는 운영 서버 |

두 주는 `runserver`에서 갈린다. Week 1은 앱을 만들고, Week 2는 그 앱을 `runserver` 없이 돌게 만든다.

## Day 인덱스

### Week 1 — 애플리케이션

- **Day 1 · settings 분리** — `base/dev/prod` 분리, `.env`+django-environ, `DJANGO_SETTINGS_MODULE` 전환. 핵심: "환경 차이 = `.env` 값 차이". → [Velog](#)
- **Day 2 · DRF 기초 · 뷰 추상화** — Serializer(직렬화+검증), `read_only`/`write_only`, FBV → APIView → generics 진화. → [Velog](#)
- **Day 3 · 모델 · 크롤러 · ModelSerializer** — `JobPosting` 설계(url unique, null/blank, auto_now류), requests+BeautifulSoup, `update_or_create` 멱등성. → [Velog](#)
- **Day 4 · ViewSet · Router · 필터 · 페이지네이션** — ReadOnlyModelViewSet, DefaultRouter, 필터 3종(뷰별)·페이지네이션(전역). 조회 API 완성. → [Velog](#)

### Week 2 — 배포

- **Day 5 · EC2 · SSH** — 인스턴스 생성(Ubuntu 24.04, t3.micro), 보안그룹 22번, 키페어 `chmod 600`, SSH 접속. → [Velog](#)
- **Day 6 · 빈 EC2에 운영 스택** — Python·PostgreSQL·git → venv·의존성 → DB·권한(PG15 스키마) → `.env` → migrate → Gunicorn. 외부 API 응답. → [Velog](#)
- **Day 7 · Gunicorn systemd · Nginx** — 소켓 활성화(socket+service), Nginx 리버스 프록시, 재부팅 자동 복구. → [Velog](#)
- **Day 8 · collectstatic · 정적 서빙 · 400 디버깅** — `collectstatic`, Nginx `alias`, `chmod o+x`, 계층 격리로 Host 헤더 중복 400 해결. → [Velog](#)

## 관통 원칙

1. **최소 권한** — 위험을 사후에 막지 않고 노출 표면 자체를 없앤다. (Day 4 ReadOnly / 5 보안그룹·SSH키 / 6 PG15·chmod600 / 8 chmod o+x)
2. **추상화 계단** — 줄여주는 도구 안에 무엇이 있는지 안다. (Day 2·4 뷰 추상화 / 7 "활성화=심볼릭 링크")
3. **계층 격리** — 어디서 깨지는가를 반씩 잘라 좁힌다. (Day 7·8 응답 헤더 판독, `curl --unix-socket`)

## 최종 구조

```
브라우저(80)
   → Nginx ┬ /static/ → 디스크 직접 (alias)
           └ /        → 유닉스 소켓 → Gunicorn → Django → PostgreSQL
```

systemd가 socket·service를 관리해 재부팅·SSH 종료와 무관하게 상시 구동.

## 다음 (Week 3~4)

- **Docker화** — Django + Gunicorn + Nginx + PostgreSQL을 Docker Compose 컨테이너로. (손으로 쌓은 6개 층을 코드로 재현)
- **CI/CD** — GitHub Actions: push → 빌드·테스트 → EC2 자동 배포. (Day 6의 단방향 배포를 자동화)