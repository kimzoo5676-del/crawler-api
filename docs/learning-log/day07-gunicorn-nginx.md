# Day 7 (2026/6/04) — Gunicorn systemd 데몬화 + Nginx 리버스 프록시

> 자세한 정리: [Velog 포스트](https://velog.io/@zooouu/%EB%B0%B0%ED%8F%AC-%ED%95%99%EC%8A%B5%EC%9A%A9-%ED%86%A0%EC%9D%B4%ED%94%84%EB%A1%9C%EC%A0%9D%ED%8A%B8-DAY-7)

## 오늘의 목표

- Day 6에서 손으로 띄운 Gunicorn(SSH 끊기면 죽는 포그라운드 실행)을 **systemd 서비스로 등록** → 상시 구동 + 재부팅 자동 시작
- **Nginx 리버스 프록시**를 앞단에 두어 `브라우저(80) → Nginx → 소켓 → Gunicorn → Django` 체인 완성
- Gunicorn↔Nginx 연결을 공식 권장인 **유닉스 도메인 소켓**으로 구성 (포트 미사용 + 외부 비노출)
- 재부팅 자동 복구 검증 후 불필요한 8000번 포트 정리

---

## 1. 사전 준비 — 절대 경로 확인 + 연결 방식 결정

### 절대 경로 확인 (EC2)

systemd는 셸 환경(`cd`/`source`/`$PATH`)을 모름 → 모든 경로를 **절대 경로**로 명시해야 함.

```bash
source venv/bin/activate
pwd                  # /home/ubuntu/crawler-api          (프로젝트 루트)
which gunicorn       # /home/ubuntu/crawler-api/venv/bin/gunicorn
whoami               # ubuntu                            (실행 유저)
```

### 연결 방식 — 유닉스 소켓 vs 로컬 TCP

| 방식 | 특징 | 선택 |
|---|---|---|
| 유닉스 도메인 소켓 (`/run/gunicorn.sock`) | 같은 머신 내 통신. 포트 미사용, 외부 비노출, TCP 핸드셰이크 오버헤드 없음 | **공식 권장 → 채택** |
| 로컬 TCP (`127.0.0.1:8000`) | 루프백 한정. 변경 최소·디버깅 직관적 | 미채택 |

- Day 6은 `0.0.0.0:8000`(외부 TCP). Nginx를 앞에 두면 Gunicorn은 외부 노출 불필요 → 소켓으로 전환.

---

## 2. systemd 유닛 작성 — socket + service 2개 구조

Gunicorn 공식 deploy 문서의 표준 구성은 유닛을 **둘로 분리**(socket activation):
- `gunicorn.socket` — 소켓 파일 생성·관리
- `gunicorn.service` — 실제 Gunicorn 프로세스 실행

systemd가 소켓을 먼저 만들어 두고, **소켓에 첫 요청이 오는 순간 service를 자동 기동**. 부팅 의존성이 깔끔해지고 소켓 권한을 systemd가 일관 관리.

### gunicorn.socket

```bash
sudo nano /etc/systemd/system/gunicorn.socket
```

```ini
[Unit]
Description=gunicorn socket

[Socket]
ListenStream=/run/gunicorn.sock

[Install]
WantedBy=sockets.target
```

| 항목 | 역할 | 짚은 것 |
|---|---|---|
| `ListenStream=/run/gunicorn.sock` | 해당 경로에 스트림 소켓 생성 | `/run`은 부팅 시 초기화되는 런타임 전용 디렉터리 → 임시 소켓 표준 위치 |
| `WantedBy=sockets.target` | enable 시 부팅의 소켓 준비 단계에 묶임 | 부팅 시 소켓 자동 대기 |

### gunicorn.service

```bash
sudo nano /etc/systemd/system/gunicorn.service
```

```ini
[Unit]
Description=gunicorn daemon
Requires=gunicorn.socket
After=network.target

[Service]
User=ubuntu
Group=www-data
WorkingDirectory=/home/ubuntu/crawler-api
Environment="DJANGO_SETTINGS_MODULE=config.settings.prod"
ExecStart=/home/ubuntu/crawler-api/venv/bin/gunicorn \
          --access-logfile - \
          --workers 3 \
          --bind unix:/run/gunicorn.sock \
          config.wsgi:application

[Install]
WantedBy=multi-user.target
```

| 항목 | 역할 | 짚은 것 |
|---|---|---|
| `Requires=gunicorn.socket` | socket 유닛에 의존 | 소켓이 먼저 활성화돼야 동작 — 둘을 묶는 핵심 |
| `After=network.target` | 네트워크 준비 후 시작 | 순서만 지정(의존 아님) |
| `User=ubuntu` | 실행 유저 권한 | root로 안 돌리는 게 보안 정석 |
| `Group=www-data` | 프로세스 그룹 | Nginx가 속한 웹서버 그룹. 소켓을 이 그룹 소유로 두면 Nginx가 읽기 가능 → **소켓 권한 문제 해결 열쇠** |
| `WorkingDirectory` | 작업 디렉터리 | `manage.py` 있는 프로젝트 루트 |
| `Environment="DJANGO_SETTINGS_MODULE=..."` | 환경변수 주입 | Day 6에 매번 붙이던 prod 지정을 systemd가 대신 주입 |
| `--access-logfile -` | 접근 로그를 표준출력으로 | systemd가 받아 `journalctl`로 조회 |
| `--workers 3` | 워커 3개 | 공식 권장 `(2×코어)+1`이나 t3.micro 메모리(1GB) 고려해 보수적으로 3 |
| `--bind unix:/run/gunicorn.sock` | **소켓에 바인딩** | Day 6 `0.0.0.0:8000`에서 전환. socket 유닛 경로와 일치 |
| `config.wsgi:application` | WSGI 진입점 | settings 분리 구조라 패키지명 `config` |
| `WantedBy=multi-user.target` | enable 시 일반 서버 가동 단계에 묶임 | **재부팅 자동 시작의 근거** |

---

## 3. 유닛 등록·기동 + socket activation 검증

```bash
sudo systemctl daemon-reload                  # 유닛 파일 재스캔(새로 만들거나 고치면 필수)
sudo systemctl enable --now gunicorn.socket   # service가 아니라 socket을 enable+start
sudo systemctl status gunicorn.socket
file /run/gunicorn.sock                        # → socket
```

- `enable --now` = 부팅 자동시작 등록(`enable`) + 지금 시작(`--now`).
- **service가 아니라 socket을 시작**하는 게 핵심. socket이 떠 있다가 첫 요청에 service를 깨움.
- 이 시점 `gunicorn.socket`은 `active (listening)`, `gunicorn.service`는 `inactive (dead)`가 **정상**(아직 요청 없음).

### 소켓에 직접 요청 → service 자동 기동 확인

```bash
curl --unix-socket /run/gunicorn.sock localhost/api/
# → {"jobs":"http://localhost/api/jobs/"}
sudo systemctl status gunicorn.service
# → Active: active (running) / TriggeredBy: ● gunicorn.socket
```

| 항목 | 의미 | 짚은 것 |
|---|---|---|
| `curl --unix-socket` | TCP 대신 소켓 파일로 직접 HTTP 요청 | Nginx 없이 소켓에 바로 붙어 검증 |
| service가 `inactive`→`active` 전환 | socket activation 동작 | 요청이 소켓에 닿자 systemd가 service 자동 기동 |
| `gunicorn.service; disabled` | service는 disabled가 정상 | socket(enabled)만 켜두면 됨. service까지 enable하면 소켓 없이 먼저 뜨려다 충돌 |

---

## 4. Nginx 설치 + 리버스 프록시 설정

### 설치 + 기본 동작 확인

```bash
sudo apt update
sudo apt install -y nginx        # 설치 즉시 자동 start + enable
sudo systemctl status nginx      # active (running)
curl -I http://localhost         # HTTP/1.1 200 OK, Server: nginx — 서버 내부 동작 확인
```

- 브라우저 `http://<퍼블릭IP>`는 이 시점 **타임아웃**(보안그룹 80 미개방) → Nginx 문제 아님. `curl -I http://localhost`로 내부 동작은 분리 확인.

### sites-available / sites-enabled 구조

| 폴더 | 역할 |
|---|---|
| `/etc/nginx/sites-available/` | 설정 파일 보관소(있다고 적용되는 것 아님) |
| `/etc/nginx/sites-enabled/` | 실제 활성 설정. available 파일을 심볼릭 링크로 연결해야 적용 |

→ 설정을 지우지 않고 링크만 걸고 끊어 사이트를 켜고 끔.

### 설정 파일 작성

```bash
sudo nano /etc/nginx/sites-available/crawler-api
```

```nginx
server {
    listen 80;
    server_name 3.34.199.116;

    location = /favicon.ico { access_log off; log_not_found off; }

    location / {
        include proxy_params;
        proxy_pass http://unix:/run/gunicorn.sock;
    }
}
```

| 항목 | 역할 | 짚은 것 |
|---|---|---|
| `listen 80` | 80번(HTTP 기본)으로 수신 | 사용자가 포트 없이 접속 |
| `server_name` | 처리할 호스트/IP | 도메인 없으니 퍼블릭 IP. 응답의 링크에도 반영됨 |
| `location = /favicon.ico` | favicon 404 로그 억제 | 앱에 없는 자동 요청 → 로그 깔끔하게 |
| `include proxy_params` | `Host`/`X-Real-IP`/`X-Forwarded-For` 등 헤더 전달 설정 묶음 | 백엔드가 원 요청 정보(실제 IP·호스트)를 알 수 있게 |
| `proxy_pass http://unix:/run/gunicorn.sock` | **요청을 소켓으로 넘김** | `http://unix:` = 유닉스 소켓 프록시 문법 |

### 활성화 + 기본 사이트 비활성화

```bash
sudo ln -s /etc/nginx/sites-available/crawler-api /etc/nginx/sites-enabled/   # 활성화(링크)
sudo rm /etc/nginx/sites-enabled/default     # 기본 "Welcome" 사이트 링크만 제거(원본은 유지)
```

- `default`와 우리 설정이 둘 다 80번 listen → 충돌 방지로 default 링크 제거. `sites-available/default`(원본)는 두어 복구 여지 남김.

### 문법 검사 → reload

```bash
sudo nginx -t                    # 적용 전 문법만 테스트
sudo systemctl reload nginx      # 무중단으로 설정만 재적용
curl -I http://localhost/api/    # HTTP/1.1 200 OK
```

| 명령 | 역할 | 짚은 것 |
|---|---|---|
| `nginx -t` | 설정 문법 검사(미적용) | 깨진 설정으로 reload하면 Nginx가 안 뜸 → 사전 안전장치 |
| `reload` vs `restart` | reload는 연결 유지하며 설정만 재적용 | 실서비스 설정 변경의 정석 |

---

## 5. 보안그룹 80 개방 + 외부 최종 확인

- AWS 콘솔 → 보안그룹 인바운드 → 규칙 추가 → 유형 **HTTP**(포트 80 자동) / 소스 `Anywhere-IPv4`.
  - 80번은 공개 웹 포트라 IP로 좁히면 일반 사용자가 못 봄 → 단독 EC2 구성에선 `0.0.0.0/0`이 정답(앞단 LB/CDN이 있을 때만 좁힘).
- 브라우저 `http://3.34.199.116/api/` (**포트 없이**) → DRF browsable API + `Api Root` + `HTTP 200 OK` 확인.

브라우저(80) → Nginx → /run/gunicorn.sock → Gunicorn → Django  ✅

---

## 6. 재부팅 자동 복구 검증 + 8000 정리

### 재부팅 후 무손 복구 확인

```bash
sudo reboot                                   # SSH 즉시 끊김(정상). 1~2분 후 재접속
# (SSH 접속 전) 브라우저 http://3.34.199.116/api/ 가 바로 떠야 함
systemctl is-active gunicorn.socket nginx     # active / active
systemctl status gunicorn.service --no-pager | head -5
# → active (running) / TriggeredBy: ● gunicorn.socket / 새 PID
```

- 손으로 아무것도 안 켰는데 `/api/`가 뜸 = `gunicorn.socket`(enabled) + `nginx`(enabled) 자동 기동 + 첫 요청에 service 자동 깨어남. **Day 7 systemd 작업의 핵심 성과 증명.**
- Day 6 수동 `gunicorn` 실행과 결정적 차이: 재부팅·SSH 종료와 무관하게 상시 구동.

### 8000번 보안그룹 삭제

- 모든 외부 접근이 80→소켓 경로로 통일 → 8000 직통 규칙은 불필요한 공격 표면 → **삭제**.
- 검증: `http://<IP>:8000/api/` 타임아웃(차단) + `http://<IP>/api/` 정상(서비스 유지).

---

## 오늘의 정리

- Day 6의 포그라운드 Gunicorn을 systemd 유닛(socket+service)으로 데몬화 — SSH 종료·재부팅과 무관하게 상시 구동.
- socket activation: 소켓만 enable해 두면 첫 요청에 service 자동 기동. service는 `disabled`가 정상.
- Gunicorn↔Nginx를 유닉스 소켓으로 연결(`Group=www-data`로 소켓 권한 해결), Nginx가 80→소켓 리버스 프록시.
- `nginx -t`로 적용 전 문법 검증 → `reload`로 무중단 반영. sites-available/enabled 링크 구조로 사이트 토글.
- 재부팅으로 전체 스택 무손 자동 복구 확인 후, 불필요한 8000 포트 삭제로 공격 표면 정리.

## 트러블슈팅 (오늘 막힌 것)

| 증상 | 원인 | 해결 |
|---|---|---|
| `nginx: [emerg] unknown directive "proxy_pas"` | `proxy_pass`를 `proxy_pas`로 오타(`s` 누락) | `nginx -t`가 파일·줄번호까지 지목 → 교정 후 재검사. **적용 전 검사가 안전장치 역할** |
| `curl -I http://localhost` → 404 | 루트(`/`)엔 라우팅 없음(앱은 `/api/`에 존재) | 정상. 응답의 `X-Frame-Options`/`X-Content-Type-Options` 헤더 = Django까지 도달했다는 증거(Nginx 404 아님) |
| 브라우저 `http://<IP>` 타임아웃 | 보안그룹 80번 미개방 | HTTP(80) 인바운드 추가. Nginx 자체 동작은 `curl -I http://localhost`로 분리 확인 |
| `gunicorn.service; disabled` 표시 | socket activation 정상 상태 | service는 enable 안 함. socket만 enable |

## 추후 과제 (메모)

- `collectstatic` + Nginx 정적 파일 서빙(`/static/` location 추가) → DRF/admin CSS 복구
- 도메인 연결 + Let's Encrypt HTTPS(443) → 주소창 `주의 요함` 해소
- SSH(22) 보안 강화: ① 보안그룹 소스 `My IP`로 제한(유동 IP라 변경 시 콘솔 재설정) ② `sshd_config`의 `PasswordAuthentication no`로 키 인증 강제(유동 IP 무관, 더 실무적) — 현재 공인 IP 메모: 121.139.92.220
- DB 비번을 강한 값으로 교체 + `.env` `SECRET_KEY` 운영용 재발급

## 다음 (Week 3~4)

- Docker화: Django + Gunicorn + Nginx + PostgreSQL을 컨테이너로 (Docker Compose)
- GitHub Actions CI/CD: push → 빌드·테스트 → EC2 자동 배포