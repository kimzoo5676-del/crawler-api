# Day 12 — Docker화 3단계 (Nginx 컨테이너화 / 리버스 프록시·정적 파일 서빙)

> 자세한 정리: [Velog 포스트](https://velog.io/@zooouu/%EB%B0%B0%ED%8F%AC-%ED%95%99%EC%8A%B5%EC%9A%A9-%ED%86%A0%EC%9D%B4%ED%94%84%EB%A1%9C%EC%A0%9D%ED%8A%B8-DAY-12)

---

## 목표

- Day 11에서 만든 2-컨테이너 구성(web + db)에 **Nginx를 별도 컨테이너로** 추가
- 기존 EC2의 systemd Nginx가 하던 역할(요청 전달 + 정적 파일 서빙)을 **컨테이너 한 개로 이전**
- 손님(인터넷) → nginx → web(Django) → db(Postgres)로 이어지는 3단 구성을 `docker-compose.yml` 하나로 기동
- web과 nginx가 정적 파일을 named volume으로 공유하는 구조 구성
- 컨테이너 시작 시 migrate·collectstatic이 자동으로 도는 entrypoint 도입

---

## 왜 Nginx를 컨테이너로 (동기)

- Day 7~9의 EC2에서는 Nginx를 **호스트에 직접 설치**(systemd)해서 운영했음. 그 Nginx가 두 가지 일을 함: ① 손님 요청을 Gunicorn에 전달(리버스 프록시) ② `/static/` 정적 파일 직접 서빙
- 이 방식의 한계: Nginx 설정이 **EC2라는 특정 머신에 묶여 있음**. 새 서버에 옮기려면 거기서 또 설치·설정해야 함
- Docker화의 목적은 "실행에 필요한 걸 전부 이미지에 싸넣어 어디서든 똑같이 동작"이므로, Nginx도 **설정까지 포함한 이미지**로 만들어 컨테이너로 띄우는 것이 일관된 방향
- 결과: web·db·nginx 세 컨테이너가 `docker compose up` 한 번에 함께 뜨고, 이 묶음을 그대로 EC2든 어디든 올릴 수 있게 됨

---

## 핵심 개념 1 — Nginx는 "맨 앞에서 손님을 받는 문지기"

- 구성: `손님(인터넷) → nginx → web(Django+Gunicorn) → db(Postgres)`
- nginx가 80번 포트로 손님을 받아, 뒤에 있는 web에게 요청을 넘기고(프록시), web이 만든 답을 다시 손님에게 전달함
- web은 더 이상 외부에 직접 노출되지 않음. 손님은 **오직 nginx를 통해서만** 들어옴
- EC2(Day 7~9)에서 호스트 Nginx가 하던 그 역할을, 이번엔 컨테이너가 동일하게 수행하는 것뿐. 새 개념이 아니라 **아는 역할을 다른 그릇(컨테이너)에 담는 것**

### 컨테이너 만드는 방식 — 공식 이미지 + conf 마운트 vs Dockerfile

| 방식 | 내용 | 특징 |
|---|---|---|
| A. 공식 이미지 + conf 마운트 | `image: nginx` 쓰고 conf를 실행 시 바깥에서 빌려옴 | 간단. 설정 자주 바꾸는 실험에 유리. 단 이미지 단독으론 불완전(설정이 호스트에 남음) |
| B. Dockerfile로 굽기 | `FROM nginx` + `COPY nginx.conf` 로 설정을 이미지에 박아넣음 | "설정까지 포함된 나만의 nginx 이미지". 그 이미지 하나만 옮기면 끝 |

- **B를 채택.** Docker화의 핵심(이미지 하나로 어디서든 동일 동작)에 더 부합. web을 Dockerfile로 구운 것과도 대칭이 맞음
- 현업에선 설정 실험이 잦으면 A도 씀. 다만 학습 목표가 "컨테이너화 원리 체득"이라 B가 정석

---

## 핵심 개념 2 — 컨테이너 간 통신은 TCP(서비스명:포트)

- web↔nginx 연결을 **유닉스 소켓**(Day 7의 `/run/gunicorn.sock`)이 아니라 **TCP**(`web:8000`)로 구성
- 유닉스 소켓: 같은 머신 안에서만 쓰는 파일 형태의 통로. 컨테이너끼리 공유하려면 소켓 파일을 볼륨으로 마운트해야 해서 격리 원칙과 어긋나고 잔버그가 많음
- TCP: 주소:포트로 통신. compose는 **서비스 이름이 곧 네트워크 주소**(Day 11의 `@db`와 동일 원리)라서 `web:8000`이 그대로 동작함
- 그래서 web의 Gunicorn은 Day 10·11과 동일하게 `--bind 0.0.0.0:8000` 유지. `0.0.0.0`이라야 컨테이너 밖(nginx)에서 접근 가능

---

## 핵심 개념 3 — 정적 파일을 named volume으로 공유

- Day 8: 호스트 Nginx가 `STATIC_ROOT`(collectstatic 수집 폴더)를 직접 읽어 `/static/`을 서빙했음
- 컨테이너 환경에서는 web과 nginx가 **서로 다른 작은 머신**이라, web이 모은 정적 파일을 nginx가 그냥은 못 봄
- 해결: `static_data`라는 named volume(컨테이너 바깥 공용 창고)을 만들어 **web과 nginx 양쪽이 같은 경로(`/app/staticfiles`)로 연결**
  - web: 이 창고에 collectstatic 결과를 쌓음 (쓰는 쪽)
  - nginx: 같은 창고를 읽어 `/static/`을 서빙 (읽는 쪽)
- **3개 경로 일치가 핵심**: Django `STATIC_ROOT`(=`/app/staticfiles`) ↔ web·nginx 볼륨 마운트 경로(`/app/staticfiles`) ↔ nginx.conf의 `alias /app/staticfiles/` — 셋이 전부 같아야 동작

---

## 핵심 개념 4 — entrypoint로 시작 작업 자동화

- Day 11까지는 migrate를 컨테이너 띄운 뒤 **손으로** 따로 실행했음(`docker compose exec web ...`)
- 이번엔 web 컨테이너가 켜질 때마다 migrate·collectstatic을 **자동**으로 돌리고 나서 Gunicorn을 띄우도록 시작 스크립트(`entrypoint.sh`)를 도입
- 명령 여러 개를 순서대로 실행해야 해서 한 줄 CMD로는 부족 → 작은 셸 스크립트로 분리

```sh
#!/bin/sh

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec gunicorn --bind 0.0.0.0:8000 config.wsgi:application
```

- `--noinput`: 자동 실행이라 사람이 yes/no에 답할 수 없으므로 질문 없이 진행
- **`exec` 의의**: gunicorn이 스크립트를 **대체**해 컨테이너의 메인 프로세스(PID 1)가 됨. 안 붙이면 컨테이너 종료 신호가 gunicorn에 제대로 전달되지 않아 깔끔하게 안 꺼짐
- collectstatic이 여기서 도므로, 컨테이너 켜질 때마다 정적 파일 창고가 자동으로 채워짐

---

## 작성·수정한 파일

### nginx/nginx.conf (신규)

```nginx
upstream django {
    server web:8000;
}

server {
    listen 80;

    location / {
        proxy_pass http://django;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /app/staticfiles/;
    }
}
```

| 블록 | 역할 |
|---|---|
| `upstream django { server web:8000; }` | 요청을 넘길 대상(web:8000)에 `django`라는 별명 부여. 서비스명 DNS로 해석 |
| `listen 80` | 80번 포트로 손님을 받음 (http 기본 문) |
| `location /` | 모든 요청을 web으로 전달(`proxy_pass`) + 출처 정보 쪽지 4종 부착 |
| `proxy_set_header Host $host` | 원래 접속 주소 전달. Django ALLOWED_HOSTS 검사에 필요(Day 9의 400 원인) |
| `X-Real-IP` / `X-Forwarded-For` | 손님의 진짜 IP 전달. 없으면 web은 모든 손님을 nginx로 인식 |
| `X-Forwarded-Proto $scheme` | 손님이 들어온 방식(http/https)을 전달. Day 9의 리다이렉트 루프 차단 핵심 |
| `location /static/ { alias ... }` | `/static/` 요청은 web 안 거치고 nginx가 창고에서 직접 서빙(Day 8 alias 개념) |

### nginx/Dockerfile (신규)

```dockerfile
FROM nginx:1.27-alpine

RUN rm /etc/nginx/conf.d/default.conf

COPY nginx.conf /etc/nginx/conf.d/
```

- `FROM nginx:1.27-alpine`: 공식 nginx 토대. 버전 고정(빌드 재현성) + alpine(초경량 OS, 이미지 크기 최소화)
- `RUN rm .../default.conf`: 공식 이미지에 든 샘플 설정 제거(우리 설정과 충돌 방지)
- `COPY nginx.conf /etc/nginx/conf.d/`: 우리 설정을 이미지에 **굽는** 동작. nginx는 이 폴더의 `.conf`를 자동으로 읽음

### Dockerfile (web, 수정)

```dockerfile
# 7) 시작 스크립트 복사 + 실행 권한
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# 8) 컨테이너 시작 명령
CMD ["/entrypoint.sh"]
```

- 기존 `CMD ["gunicorn", ...]`를 교체. gunicorn 기동은 entrypoint.sh 마지막 줄이 담당
- `chmod +x`: 스크립트는 실행 권한이 있어야 동작(Day 8의 권한 개념)

### docker-compose.yml (수정)

```yaml
  web:
    # ...
    volumes:
      - static_data:/app/staticfiles   # [추가] 정적 파일 창고 연결
    expose:
      - "8000"                         # [변경] ports → expose (외부 직접 노출 차단)

  nginx:                               # [신규] 문지기 컨테이너
    build: ./nginx
    volumes:
      - static_data:/app/staticfiles   # web과 같은 창고를 같은 경로로 공유
    ports:
      - "80:80"                        # 손님은 이제 80번으로만 진입
    depends_on:
      - web

volumes:
  postgres_data:
  static_data:                         # [추가] 정적 파일 창고 선언
```

| 변경 | 이유 |
|---|---|
| web: `ports` → `expose` | 8000 직통문을 닫음. `expose`는 compose 내부(nginx)에만 열어둠 |
| web: `volumes` 추가 | collectstatic 결과를 `static_data` 창고에 쌓기 위함 |
| nginx 서비스 추가 | `build: ./nginx`로 nginx 폴더의 Dockerfile 빌드. 80번 노출 |
| nginx: `depends_on: web` | web이 먼저 떠야 `web:8000` 해석 가능 → 시작 순서 보장 |
| 최상위 `volumes`에 `static_data` | 사용처(services)와 선언처(최상위) 둘 다 있어야 함(Day 11 동일) |

---

## 검증 흐름 (실제 명령)

### 1. 기동

```bash
docker compose up --build
```

- `--build`: Dockerfile(web·nginx)을 수정했으므로 이미지를 새로 구워야 변경이 반영됨
- 로그에서 순서 확인:

```
Volume crawler-api_static_data Created
Container crawler-api-db-1  Healthy
web-1 | Running migrations: No migrations to apply.
web-1 | 154 static files copied to '/app/staticfiles'.   ← 창고 자동 채움
web-1 | [INFO] Listening at: http://0.0.0.0:8000
nginx-1 | start worker process ...
```

> `nginx-1 | ... default.conf is not a file or does not exist` 로그는 에러 아님. Dockerfile에서 그 파일을 지웠으니 "기본 설정 없네" 하고 넘어가는 정상 동작

### 2. nginx 경유 + 정적 파일 검증

```bash
# 헤더만 보기 — 301 (nginx 경유 + redirect 동작)
curl -I http://localhost/api/
#   HTTP/1.1 301 Moved Permanently
#   Server: nginx/1.27.5            ← 응답이 nginx를 거쳐 나옴(문지기 연결 증명)
#   Location: https://localhost/api/

# 정적 파일 — 200 (창고 공유 증명)
curl -I http://localhost/static/admin/css/base.css
#   HTTP/1.1 200 OK
#   Content-Type: text/css
#   Content-Length: 22120          ← web이 넣은 파일을 nginx가 직접 꺼내 서빙
```

- 핵심: 이제 주소가 `:8000`이 아니라 **80번**. `Server: nginx`가 찍힌다는 건 손님→nginx→web 줄이 살아있다는 증거
- 정적 파일 200 + `Last-Modified`가 collectstatic 시각과 일치 → web·nginx 창고 공유 확인

### 핵심 차이 — 로컬 curl 우회가 이제 안 통함 (Day 11과 비교)

- Day 11: nginx가 없어서 `curl -H "X-Forwarded-Proto: https"`로 붙인 쪽지가 Django에 직접 전달 → 200 우회 가능
- Day 12: nginx가 중간에 있고, nginx.conf의 `proxy_set_header X-Forwarded-Proto $scheme`가 **그 쪽지를 자기 기준($scheme)으로 다시 씀**
  - 로컬은 http로 접속 → `$scheme`=`http` → curl이 붙인 `https`를 `http`로 덮어씀 → Django는 http로 인식 → 301
- **이건 버그가 아니라 nginx가 제 역할을 정확히 하는 증거.** 로컬은 실제 http 접속이므로 301로 https 유도가 맞음
- EC2에선 손님이 https(443)로 들어오면 `$scheme`=`https`가 되어 통과. 설계대로 동작

> 로컬에서 200 JSON 본문을 끝까지 보려면 dev 설정으로 잠깐 띄우거나(SECURE_SSL_REDIRECT 없음), 로컬 nginx에 https를 깔아야 함. 검증 목적상 불필요 — 301과 정적 200으로 연결·공유는 이미 증명됨

---

## 오늘의 한 줄 정리

> Nginx를 설정까지 구운 이미지(B 방식)로 만들어 컨테이너 묶음에 추가하니, 손님→nginx→web→db 3단 구성이 compose 한 번에 뜬다. web↔nginx는 서비스명 TCP(web:8000)로 연결하고, 정적 파일은 named volume을 양쪽이 같은 경로로 공유해 web이 넣고 nginx가 꺼낸다. nginx가 X-Forwarded-Proto를 $scheme로 다시 쓰므로 Day 11의 curl 우회는 더 이상 통하지 않으며, 이는 오히려 nginx가 올바로 동작한다는 신호다.

---

## 후속 (다음 이슈)

- EC2에 compose 기동 — 기존 systemd Gunicorn + 호스트 Nginx 운영 방식을 컨테이너 묶음으로 교체. 80번을 컨테이너 nginx가 잡으려면 호스트 Nginx를 먼저 내려야 함
- arm64(로컬 Mac) 이미지를 x86_64(EC2)에 올릴 때의 아키텍처 차이 확인
- 이후 GitHub Actions CI/CD (push → 빌드·테스트 → EC2 자동 배포)