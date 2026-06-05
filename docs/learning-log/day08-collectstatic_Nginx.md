# Day 8 (2026/6/05) — collectstatic + Nginx 정적 파일 서빙

> 자세한 정리: [Velog 포스트](https://velog.io/@zooouu/%EB%B0%B0%ED%8F%AC-%ED%95%99%EC%8A%B5%EC%9A%A9-%ED%86%A0%EC%9D%B4%ED%94%84%EB%A1%9C%EC%A0%9D%ED%8A%B8-DAY-8)

## 오늘의 목표

- `DEBUG=False` 운영환경에서 Django가 서빙하지 않는 **정적 파일**(DRF/admin CSS·JS)을 **Nginx가 디스크에서 직접 서빙**하도록 구성
- `STATIC_ROOT` 지정 → `collectstatic`으로 정적 파일을 한곳에 수집 → Nginx `/static/` location 추가
- `브라우저 → Nginx(/static/는 디스크 직접 / 나머지는 소켓) → Gunicorn → Django` 체인에서 정적 파일 경로 분기 완성
- (작업 중 발견) Day 7부터 잠재해 있던 **Nginx Host 헤더 중복**으로 인한 `/api/` 400 버그 해결

---

## 1. STATIC_ROOT 설정 — STATIC_URL과의 구분

운영환경에서 `DEBUG=False`면 Django는 정적 파일을 서빙하지 않음(의도된 동작). 따라서 정적 파일은 한곳에 모아 Nginx가 직접 내보내야 함.

`config/settings/base.py`:

```python
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
```

| 항목 | 역할 | 짚은 것 |
|---|---|---|
| `STATIC_URL` | 브라우저가 요청하는 **URL prefix** | `/static/admin/css/base.css`의 `/static/` 부분 |
| `STATIC_ROOT` | `collectstatic`이 파일을 **복사해 모으는 실제 디스크 경로** | Nginx가 이 디렉터리를 직접 읽음. URL이 아니라 파일 위치 |
| `BASE_DIR / "staticfiles"` | 프로젝트 루트 하위 수집 디렉터리 | `pathlib`의 `/` 연산자로 경로 결합. 폴더명을 `static`이 아닌 `staticfiles`로 둬 `STATICFILES_DIRS`(개발용 소스)와 충돌 회피 |

- `base.py`에 둔 이유: dev/prod 공통. dev는 `runserver`가 알아서 서빙하나, prod는 `collectstatic` 목적지로 `STATIC_ROOT` 필수 → 공통 base에 두면 일관됨.

---

## 2. collectstatic — 정적 파일 수집 (EC2)

브랜치 검증 방식(B안): 로컬에서 `deploy-10` 커밋·푸시 후, **PR 머지 전 EC2에서 직접 브랜치를 체크아웃해 실환경 검증**.

```bash
# 로컬: 커밋 + 푸시
git add config/settings/base.py
git commit -m "Deploy: STATIC_ROOT 설정 추가"
git push -u origin deploy-10

# EC2: 브랜치 체크아웃
git fetch origin
git switch deploy-10

# EC2: 정적 파일 수집
source venv/bin/activate
python manage.py collectstatic --noinput
# → 154 static files copied to '/home/ubuntu/crawler-api/staticfiles'.
```

| 항목 | 역할 | 짚은 것 |
|---|---|---|
| `git fetch` + `git switch` | 원격 브랜치 추적해 체크아웃 | EC2는 받기만 하는 단방향. PR 머지 전 실환경 검증용 |
| `collectstatic` | admin·DRF 정적 파일을 `STATIC_ROOT`로 복사 | 흩어진 앱별 static을 한곳에 모음 |
| `--noinput` | 덮어쓰기 확인 프롬프트 생략 | 자동화 시 필수 |

---

## 3. Nginx /static/ location — alias vs root

`/etc/nginx/sites-available/crawler-api`의 `server` 블록에 추가:

```nginx
location /static/ {
    alias /home/ubuntu/crawler-api/staticfiles/;
}
```

| 항목 | 역할 | 짚은 것 |
|---|---|---|
| `alias` | location 경로(`/static/`)를 **떼어내고** 지정 경로에 매핑 | `/static/admin/css/base.css` → `.../staticfiles/admin/css/base.css` (정확) |
| (`root`였다면) | location 경로를 **떼지 않고** 뒤에 붙임 | `.../staticfiles/static/admin/...` → 404. `staticfiles` 안엔 `static/` 폴더 없음 → **alias가 정답** |
| location 순서 | `/static/`을 `location /`보다 위에 | 구체적 prefix를 위에 두는 관례. 가독성·안전성 |
| 끝 슬래시 | `location /static/`와 `alias .../staticfiles/` 모두 `/`로 끝 | 경로 결합이 깔끔하게 이어짐 |

검증:

```bash
sudo nginx -t && sudo systemctl reload nginx
curl -I http://localhost/static/rest_framework/css/bootstrap.min.css
```

- 응답에 `Content-Type: text/css` + `Last-Modified`/`ETag`/`Accept-Ranges: bytes` → **Nginx가 파일 시스템에서 직접 서빙**한 증거(Gunicorn 경유 시 안 붙음). 요청이 `location /static/`에서 잡혀 소켓까지 안 감.

---

## 4. 정적 파일 403 — www-data 디렉터리 진입 권한

`curl` 검증 시 `403 Forbidden` 발생. 권한 문제.

### 원인 추적 — namei로 경로 단계별 권한 확인

```bash
namei -l /home/ubuntu/crawler-api/staticfiles/rest_framework/css/bootstrap.min.css
```

```
drwxr-x--- ubuntu ubuntu ubuntu        ← other 진입 불가(여기서 막힘)
drwxrwxr-x ubuntu ubuntu crawler-api   ← 이하 other r-x 있음(통과 가능)
drwxrwxr-x ubuntu ubuntu staticfiles
...
-rw-r--r-- ubuntu ubuntu bootstrap.min.css  ← other 읽기 가능
```

- Nginx 워커는 `www-data`(other) 권한으로 동작. 파일까지 가려면 경로상 **모든 상위 디렉터리에 진입권(`x`)** 필요.
- `/home/ubuntu`가 `750`(`drwxr-x---`) → other에 `x` 없음 → 진입 불가 → 403.

### 해결 — 진입권만 부여 (읽기권은 미부여)

```bash
chmod o+x /home/ubuntu
```

| 항목 | 역할 | 짚은 것 |
|---|---|---|
| `o+x` | other에 **실행(=디렉터리 통과)** 권한만 추가 | `r`은 안 줌 → www-data는 `/home/ubuntu` **통과**만 가능, 내부 목록 조회 불가 |
| 노출 최소화 | 딱 필요한 만큼만 개방 | Day 4 ReadOnlyViewSet·Day 5 `chmod 600`과 같은 결 |

- 변경 후 `namei`: `drwxr-x--x`(other에 `x` 추가). 나머지 경로는 이미 `r-x`라 한 군데만 풀면 됨.
- 더 정석적인 대안: 정적 파일을 `/var/www/`로 분리(STATIC_ROOT 변경) → 홈 디렉터리 권한 미변경. 단계가 늘어 토이플젝 단계에선 미채택, 메모만.

---

## 5. /api/ 400 — 긴 디버깅 끝에 Nginx Host 헤더 중복

정적 파일 200 확인 후, `/api/`가 `400 Bad Request`. `Bad Request (400)` 페이지 = Django의 `ALLOWED_HOSTS` 거절로 단정하고 출발 → **여러 헛다리** 끝에 진범은 Nginx였음.

### 배제해 나간 과정 (가설 → 검증 → 배제)

| 가설 | 검증 방법 | 결과 |
|---|---|---|
| `.env`에 IP 누락 | `grep ALLOWED .env` | `3.34.199.116,localhost,127.0.0.1` 존재 → 배제 |
| `deploy-10`에 설정 누락 | `git diff main deploy-10 -- config/settings/` | 차이 없음 → 배제 |
| prod.py가 ALLOWED_HOSTS 덮어씀 | `cat config/settings/prod.py` | 재정의 없음(`from .base import *`만) → 배제 |
| Gunicorn이 옛 설정 보유 | `systemctl restart gunicorn` | 여전히 400 → 배제 |
| `.env` 마지막 줄 개행 없음 | `tail -c 20 .env \| xxd` | `0a`로 정상 종료 → 배제 |
| `read_env`가 `.env` 못 읽음 | `python -c "...read_env...print(ALLOWED)"` | 셋 다 정상 출력 → 배제 |
| Django 로딩 자체 문제 | `DJANGO_SETTINGS_MODULE=...prod ./venv/bin/python -c "django.setup(); print(settings.ALLOWED_HOSTS)"` | `['3.34.199.116', ...]` 정상 → **Django 완전 결백** |

### 결정적 분기 — Gunicorn 직접 vs Nginx 경유

```bash
# Gunicorn에 직접(소켓) 요청 → 200
curl -I --unix-socket /run/gunicorn.sock http://localhost/api/   # HTTP/1.1 200 OK

# Nginx 경유 요청 → 400
curl -I http://localhost/api/                                    # HTTP/1.1 400 Bad Request
```

- 동일 시점, 같은 Gunicorn 프로세스인데 **소켓 직접 = 200 / Nginx 경유 = 400**. 차이는 오직 **Nginx가 손대는 요청 헤더** → 범인 확정.

### 진범 — proxy_set_header Host 중복

```nginx
location / {
    include proxy_params;          # 이 안에 proxy_set_header Host $http_host;
    proxy_pass http://unix:/run/gunicorn.sock;
    proxy_set_header Host $host;    # ← 여기서 Host를 또 설정 → 중복
}
```

- `/etc/nginx/proxy_params`에 이미 `proxy_set_header Host $http_host;`가 있는데, 사이트 설정에서 `proxy_set_header Host $host;`를 **또** 지정.
- 같은 헤더를 `proxy_set_header`로 이중 지정 → Host 헤더가 중복/깨진 형태로 전달 → Django가 Invalid HTTP_HOST 판정 → 400.
- Day 7에서 `Host $host`를 직접 넣었으나, `proxy_params`가 이미 Host를 처리하고 있던 걸 몰랐던 게 원인.

### 해결 — 중복 줄 삭제

```nginx
location / {
    include proxy_params;
    proxy_pass http://unix:/run/gunicorn.sock;
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx
curl -I http://localhost/api/   # HTTP/1.1 200 OK
```

- `proxy_params`의 `Host $http_host` 하나만 남겨 깔끔하게 전달 → 200.
- `$host`(포트 제거) vs `$http_host`(원본·포트 포함) 차이도 정리했으나, 이번 400의 직접 원인은 값 차이가 아니라 **중복 지정** 자체였음.

---

## 오늘의 정리

- `DEBUG=False`에서 Django가 안 하는 정적 파일 서빙을 Nginx로 이관: `STATIC_ROOT` 지정 → `collectstatic` 수집 → `location /static/` + `alias`로 디스크 직접 서빙.
- `alias`와 `root`의 경로 처리 차이(location 경로 제거 여부)를 이해하고 `alias` 채택.
- 정적 파일 403은 `www-data`의 홈 디렉터리 진입권 부재 → `chmod o+x`로 통과권만 부여(읽기권 미부여, 노출 최소화).
- `/api/` 400은 가설을 하나씩 배제(`.env`·git·prod.py·read_env·Django 로딩 전부 결백 확인)한 뒤, **소켓 직접 요청 vs Nginx 경유**로 범위를 좁혀 Nginx Host 헤더 중복으로 확정·해결.
- 디버깅 교훈: "어디서 실패하는가"를 **계층을 격리**해 좁히는 것이 핵심. `--unix-socket`으로 Nginx를 건너뛴 한 번의 요청이 Django 결백과 Nginx 범인을 동시에 증명.

## 트러블슈팅 (오늘 막힌 것)

| 증상 | 원인 | 해결 |
|---|---|---|
| `/static/...` → 403 Forbidden | `/home/ubuntu`가 `750` → Nginx(www-data) 디렉터리 진입 불가 | `chmod o+x /home/ubuntu`로 통과권만 부여. `namei -l`로 막힌 단계 특정 |
| `/api/` → 400 Bad Request | Nginx `proxy_params`의 `Host $http_host`와 사이트 설정의 `Host $host` 중복 지정 | 사이트 설정의 `proxy_set_header Host $host;` 삭제 |
| 400 디버깅 장기화 | Django/`.env`/`read_env`를 의심해 헛다리 | `curl --unix-socket`으로 Nginx 격리 → 소켓 직접 200 확인으로 범위 즉시 축소 |

## 서버 측 변경분 (git 미추적 — 재현 시 필수)

> Nginx 설정과 디렉터리 권한은 git 바깥(EC2에만 존재). 재구축 시 아래를 수동 반영해야 함.

- `/etc/nginx/sites-available/crawler-api`에 `location /static/ { alias /home/ubuntu/crawler-api/staticfiles/; }` 추가
- 같은 파일 `location /`에서 `proxy_set_header Host $host;` 삭제(Host 중복 제거)
- `chmod o+x /home/ubuntu` (www-data 진입권)
- EC2에서 `python manage.py collectstatic --noinput` 실행(코드 pull 후 매번)

## 추후 과제 (메모)

- 도메인 연결 + Let's Encrypt HTTPS(443) → 주소창 `주의 요함` 해소
- SSH(22) 보안 강화: `sshd_config`의 `PasswordAuthentication no`로 키 인증 강제
- DB 비번 강한 값 교체 + `.env` `SECRET_KEY` 운영용 재발급
- 정적 파일을 `/var/www/`로 분리(홈 디렉터리 권한 미의존하는 정석 구성) 검토

## 다음 (Week 3~4)

- Docker화: Django + Gunicorn + Nginx + PostgreSQL을 컨테이너로 (Docker Compose)
- GitHub Actions CI/CD: push → 빌드·테스트 → EC2 자동 배포