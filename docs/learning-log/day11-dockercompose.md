# Day 11 — Docker화 2단계 (Docker Compose로 PostgreSQL 컨테이너 연결)

> 자세한 정리: [Velog 포스트](https://velog.io/@zooouu/%EB%B0%B0%ED%8F%AC-%ED%95%99%EC%8A%B5%EC%9A%A9-%ED%86%A0%EC%9D%B4%ED%94%84%EB%A1%9C%EC%A0%9D%ED%8A%B8-DAY-11)

---

## 목표

- Day 10에서 만든 단일 Django 이미지에 **PostgreSQL을 별도 컨테이너로** 붙이기
- 두 컨테이너(웹 + DB)를 `docker-compose.yml` 한 파일로 함께 기동
- prod settings로 띄워 실제 운영과 같은 DB 연결 경로(`env.db()`)를 로컬에서 검증
- compose 기동 → migrate → `/api/` 응답까지 확인

---

## 왜 Compose인가 (동기)

- Day 10까지는 컨테이너가 **하나(Django+Gunicorn)** 뿐이라 `docker run` 한 줄로 충분했음
- 이번엔 DB 컨테이너가 하나 더 생겨 **둘**이 됨. 컨테이너가 둘 이상이 되는 순간, 각각을 손으로 띄우고 서로 연결하는 작업이 번거로워짐
- Docker Compose = **"컨테이너 여러 개를 어떻게 띄우고 서로 연결할지"를 yaml 파일 하나에 적어두고 `docker compose up` 한 번으로 기동하는 도구**
- 즉 `docker-compose.yml`은 여러 컨테이너로 이루어진 시스템의 **설계도**에 해당함

---

## 핵심 개념 1 — 컨테이너는 어떻게 서로를 찾는가

- compose 안에 정의한 각 컨테이너를 **서비스(service)** 라 부름. 이번 구성은 `web`과 `db` 두 서비스
- **서비스 이름이 곧 네트워크 주소(호스트명)가 됨**. compose는 같은 파일 안의 서비스들을 하나의 가상 네트워크로 묶어주고, 서로를 서비스 이름으로 부를 수 있게 해줌
- 그래서 web이 DB에 접속할 때 주소를 `db`라고 적으면, compose가 알아서 db 컨테이너로 연결해줌
- 비교: EC2(Day 6)에서는 Django와 PostgreSQL이 **같은 머신 안**에 있어서 주소가 `localhost`였음. 컨테이너 환경에서는 각 컨테이너가 독립된 작은 머신이라, web 입장에서 `localhost`는 "자기 자신"을 가리킴 → DB를 못 찾음. 그래서 호스트명이 `localhost`가 아니라 서비스명 `db`가 되어야 함

---

## 핵심 개념 2 — DB 접속 정보의 "양쪽 일치"

DB 컨테이너와 웹 컨테이너는 접속 정보를 **각자 따로** 들고 있고, 둘이 일치해야만 연결됨.

- **DB 컨테이너 쪽**: PostgreSQL 공식 이미지는 처음 켜질 때 `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`라는 환경변수를 보고 **그 값으로 유저와 데이터베이스를 자동 생성**함. 즉 "이 유저/비번/DB로 문을 만들어라"는 지시
- **웹 컨테이너 쪽**: Django는 `DATABASE_URL` 한 줄로 "어디에 / 누구로 / 무슨 비번으로 / 어느 DB에" 붙을지를 지정함

  ```
  DATABASE_URL = postgres://유저 : 비번 @ 호스트 : 포트 / DB이름
  ```

  즉 "이 유저/비번/DB로 문을 두드린다"는 지시
- **결론**: DB 컨테이너가 만든 유저/비번/DB이름과, 웹의 `DATABASE_URL` 안에 적은 유저/비번/DB이름이 **글자 하나까지 같아야** 접속 성공. 한쪽은 문을 만들고, 다른 한쪽은 그 문을 두드리는 구조이기 때문
- 호스트 자리만은 예외적으로 비번이 아니라 **"어느 컨테이너로 갈지"** 라서, 앞서 본 서비스명 `db`를 적음

---

## 핵심 개념 3 — "실행 중"과 "준비됨"은 다르다 (healthcheck)

- 단순히 "db 먼저, web 나중"이라고만 적으면(`depends_on`만 사용) 문제가 생김. compose의 기본 동작은 **컨테이너가 "실행 중(running)"이 되면** 다음 컨테이너를 시작하는 것이지, **DB가 "접속을 받을 준비(ready)"가 됐는지**까지는 보지 않음
- PostgreSQL은 컨테이너가 켜진 뒤에도 내부적으로 초기화하는 데 몇 초가 걸림. 그 사이에 web이 먼저 떠서 DB에 붙으려 하면 "연결 거부"로 실패함
- 해결책이 **healthcheck**: DB 컨테이너 안에서 "지금 접속 받을 준비 됐냐?"를 주기적으로 물어보는 명령을 정의함. PostgreSQL은 `pg_isready`라는 전용 명령을 제공
- 그리고 web 쪽에 **"db가 healthy 상태가 된 뒤에 시작하라"** 는 조건을 걸면(`condition: service_healthy`), DB가 진짜 준비될 때까지 web이 기다림 → 기동 순서가 안전하게 보장됨

### 보조 개념 — start_period

- healthcheck는 "몇 초마다 검사하고, 몇 번 실패하면 unhealthy로 판정"하는 구조
- 그런데 DB가 막 켜지는 **초기 몇 초의 실패**까지 실패 횟수로 세면, 미처 준비되기도 전에 실패 횟수를 다 채워 unhealthy로 떨어져버림
- `start_period`는 **"컨테이너 시작 직후 이 시간 동안의 실패는 횟수에 세지 말고 봐줘라"** 는 유예 기간. 그 안에 한 번이라도 성공하면 즉시 healthy로 전환됨

---

## 핵심 개념 4 — named volume (데이터 영속화)

- 컨테이너는 기본적으로 **일회용**임. 컨테이너를 지우면 그 안의 데이터(DB에 쌓은 레코드 등)도 함께 사라짐
- 이러면 컨테이너를 다시 만들 때마다 DB가 빈 상태로 돌아가버림 → 곤란
- **named volume**: 데이터를 컨테이너 바깥의 별도 저장 공간에 두고, DB 컨테이너의 데이터 디렉토리를 거기에 연결함. 그러면 컨테이너를 지우고 다시 만들어도 데이터가 보존됨
- 확인 방법: 컨테이너를 재생성한 뒤 로그에 `Skipping initialization`(이미 데이터가 있어 초기화를 건너뜀)이 보이면, volume이 제 역할을 하고 있다는 증거

---

## docker-compose.yml (전체 완성본)

```yaml
services:
  # -- DB 컨테이너 --------------------------------------
  db:
    image: postgres:16                 # EC2의 PostgreSQL과 버전 일치
    env_file:
      - .env                           # POSTGRES_* 값을 .env에서 읽음
    volumes:
      - postgres_data:/var/lib/postgresql/data   # 데이터 영속화
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 5
      start_period: 10s                # 시작 직후 10초는 실패를 세지 않음

  # -- Django(web) 컨테이너 -----------------------------
  web:
    build: .                           # Day 10 Dockerfile로 빌드
    env_file:
      - .env
    environment:
      - DJANGO_SETTINGS_MODULE=config.settings.prod   # prod로 기동
    ports:
      - "8000:8000"
    depends_on:
      db:
        condition: service_healthy     # db가 healthy 된 뒤 web 시작

# -- named volume 선언 (services와 나란한 최상위) --------
volumes:
  postgres_data:
```

- **구조상 주의**: `volumes` 선언은 `services` 안이 아니라 **`services`와 나란한 최상위 항목**임. compose 파일은 맨 바깥에 `services`, `volumes`, `networks` 같은 항목들이 형제로 나열되는 구조

### .env 추가분

```bash
# DB 컨테이너가 생성할 값 (문을 만드는 쪽)
POSTGRES_DB=crawler_db
POSTGRES_USER=crawler_user
POSTGRES_PASSWORD=mypass123

# Django가 접속할 대상 (문을 두드리는 쪽) — 위 값과 글자 단위로 일치, 호스트=서비스명 db
DATABASE_URL=postgres://crawler_user:mypass123@db:5432/crawler_db
```

---

## 검증 흐름 (실제 명령)

### 0. 사전 점검

```bash
docker compose config        # yaml 문법·해석 결과를 띄우기 전 확인
```

### 1. 기동

```bash
docker compose up
```

로그에서 순서 확인 — db가 먼저 뜨고, healthy가 된 뒤 web 시작:

```
db-1  | ... database system is ready to accept connections
Container crawler-api-db-1  Healthy
web-1 | [INFO] Starting gunicorn 23.0.0
web-1 | [INFO] Booting worker with pid: 7
```

(이 터미널은 로그 창이므로 그대로 두고, 이후 명령은 새 탭에서)

### 2. migrate — 핵심 검증

```bash
docker compose exec web python manage.py migrate
```

- `docker compose exec web` = 실행 중인 web 컨테이너 안에서 명령 실행
- 모든 마이그레이션 `OK` → web이 prod settings의 `env.db()` 경로로 db 컨테이너에 접속해 테이블 생성 성공 → 오늘의 핵심 목표 달성

### 3. /api/ 응답 — 헤더 유무 비교

```bash
# 헤더 없이 — 301 (https로 리다이렉트)
curl -i http://localhost:8000/api/
#   HTTP/1.1 301 Moved Permanently
#   Location: https://localhost:8000/api/

# 헤더 붙여서 — 200 (정상 JSON)
curl -H "X-Forwarded-Proto: https" http://localhost:8000/api/
#   {"jobs":"http://localhost:8000/api/jobs/"}
```

- `-H "헤더이름: 값"` = 요청에 HTTP 헤더를 직접 추가
- `X-Forwarded-Proto: https` = 운영 환경에서 Nginx가 자동으로 붙여주는 헤더. 로컬엔 Nginx가 없어 curl이 임시로 대신 붙인 것

### HTTPS 리다이렉트 우회 (prod settings의 부수 효과)

- prod에는 `SECURE_SSL_REDIRECT=True`가 켜져 있어, http 요청을 https로 강제 리다이렉트함(Day 9)
- 이 설정은 **앞단의 Nginx가 "원래 https로 들어온 요청"이라는 표시(`X-Forwarded-Proto` 헤더)를 붙여준다는 전제** 위에서 동작함(Day 9에서 정리한 구조)
- 그런데 이번 로컬 검증에는 Nginx가 없음 → 그 표시를 붙여줄 주체가 없어 리다이렉트에 걸림
- 그래서 검증할 때만 그 헤더를 직접 붙여 요청을 보냄. **prod.py 코드는 그대로 두고**, 로컬에서만 우회하는 것이 핵심 (같은 이미지를 EC2에 그대로 올릴 수 있음)

---

## 오늘의 한 줄 정리

> 컨테이너가 둘 이상이 되면 Compose로 묶는다. 서비스 이름이 곧 컨테이너 사이의 주소가 되고, DB 접속 정보는 양쪽(DB가 만들고 / 웹이 두드림)이 일치해야 하며, "실행 중"과 "준비됨"은 다르므로 healthcheck로 진짜 준비 상태를 기다린다. 데이터는 named volume으로 컨테이너 수명과 분리해 보존한다.

---

## 후속 (다음 이슈)

- Nginx 컨테이너화 (현재 구성에 웹 서버 계층 추가)
- EC2에 compose 기동 (기존 systemd + Nginx 운영 방식과의 교체 방법 결정)
- arm64(로컬 Mac) 이미지를 x86_64(EC2)에 올릴 때의 아키텍처 차이 확인