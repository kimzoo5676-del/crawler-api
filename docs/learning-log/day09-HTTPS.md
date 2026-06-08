# Day 09 — HTTPS 적용 (Let's Encrypt) + Django 보안 설정
> 자세한 정리: [Velog 포스트](https://velog.io/@zooouu/%EB%B0%B0%ED%8F%AC-%ED%95%99%EC%8A%B5%EC%9A%A9-%ED%86%A0%EC%9D%B4%ED%94%84%EB%A1%9C%EC%A0%9D%ED%8A%B8-DAY-9)

---

## 목표

Day 7에서 추후 과제로 남겨둔 HTTPS를 적용함. Nginx 리버스 프록시에 Let's Encrypt 인증서를 붙이고, Nginx 뒤(behind proxy) 구조에 맞는 Django 보안 설정을 추가하는 것.

---

## 작업 흐름 요약

1. 도메인 확보 (sslip.io)
2. 보안그룹 443 개방
3. Certbot 인증서 발급 + Nginx 설치
4. `.env` ALLOWED_HOSTS에 도메인 추가
5. prod.py 보안 설정 4종 추가 (코드, PR)
6. 외부 검증 (200 / 301 / 루프 없음)

---

## 1. 도메인 — 왜 필요했고, 무엇을 골랐나

### 왜 도메인이 선행 조건인가

Let's Encrypt의 인증서 발급은 "요청자가 이 도메인의 주인인가"를 검증함. 가장 흔한 **HTTP-01 챌린지**는 다음 흐름임.

- certbot이 서버에 임시 검증 파일을 놓음
- Let's Encrypt 서버가 `http://<도메인>/.well-known/acme-challenge/...` 로 접속해 그 파일을 확인
- 일치하면 "이 사람이 이 도메인을 통제한다"고 판단 → 발급

검증의 키가 **도메인 이름**이라서, 순수 IP에는 공인 CA가 인증서를 발급하지 않음. 그래서 도메인이 먼저 필요했음.

### sslip.io 선택 (DuckDNS 포기)

처음엔 DuckDNS(무료 서브도메인)를 쓰려 했으나, `duckdns.org` / `www.duckdns.org` 둘 다 루트 경로가 404(Jetty)를 뱉어 관리 UI 진입 자체가 안 됐음. 시간 끌 이유가 없어 **sslip.io**로 전환.

- 원리: `<IP를 하이픈으로>.sslip.io` 형태로 접속하면 DNS가 그 IP를 자동으로 돌려줌. IP가 도메인 이름 안에 박혀 있음.
- 가입·IP 등록 0단계. 내 도메인: `3-34-199-116.sslip.io`
- 검증: `dig +short 3-34-199-116.sslip.io` → `3.34.199.116` 확인
- 단점: EC2 stop/start로 IP 바뀌면 도메인 이름도 통째로 바뀜(IP가 이름에 박혀서). 인스턴스 안 끄면 문제없음.

---

## 2. Certbot 발급 — server_name 매칭 함정

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d 3-34-199-116.sslip.io
```

인증서 **발급은 성공**했으나 마지막 **자동 install 단계에서 실패**함.

```
Could not automatically find a matching server block for 3-34-199-116.sslip.io.
Set the `server_name` directive to use the Nginx installer.
```

### 원인

`--nginx` 플러그인이 인증서를 자동 설치하려면, Nginx 사이트 설정에서 `server_name`이 발급 도메인과 일치하는 블록을 찾아야 함. 그런데 기존 `sites-available/crawler-api`의 `server_name`은 IP만 있었음(`server_name 3.34.199.116;`). 도메인이 없으니 매칭 실패.

### 해결

`server_name`에 도메인을 추가 (IP도 같이 유지).

```nginx
server_name 3-34-199-116.sslip.io 3.34.199.116;
```

그 뒤 발급은 끝났으니 **install만 재시도**.

```bash
sudo nginx -t && sudo systemctl reload nginx
sudo certbot install --cert-name 3-34-199-116.sslip.io
# → Successfully deployed certificate
```

certbot이 80 블록에 리다이렉트를 자동 삽입함.

```nginx
server {
    if ($host = 3-34-199-116.sslip.io) {
        return 301 https://$host$request_uri;
    } # managed by Certbot
    listen 80;
    server_name 3-34-199-116.sslip.io 3.34.199.116;
    return 404; # managed by Certbot
}
```

> 주의 포인트: 발급 도메인이 아닌 host(= IP 직접 접속)는 `return 404`로 떨어짐. 실습상 도메인 단일화로 그냥 두기로 함.

---

## 3. 외부 curl 무한 대기 — 보안그룹 격리

certbot install 후 외부에서 curl을 쳤는데 응답 없이 매달림(`^C`로 끊음).

### 계층 격리로 범인 찾기 (Day 8에 이어 또)

서버 **내부**에서 먼저 테스트:

```bash
curl -kI https://localhost/api/   # → HTTP/1.1 200 OK
```

- 내부 200 → Nginx 443 리스닝 OK, Django OK, 인증서 OK
- 그런데 외부에서만 무한 대기 → **연결이 EC2에 도달조차 못 함** → 네트워크 계층(보안그룹) 문제로 좁혀짐

원인: **보안그룹 443 인바운드 미개방**. 인증서는 80포트로 검증해서 발급됐지만, 443으로 들어오는 트래픽이 막혀 있었음. AWS 콘솔에서 HTTPS 443 / 0.0.0.0/0 추가로 해결.

> `-k`: localhost로 접속하면 인증서 도메인(sslip.io)과 안 맞아 경고가 뜨는데, 그걸 무시하는 옵션.

---

## 4. 도메인 접속 400 — ALLOWED_HOSTS

443을 열자 이번엔 `400 Bad Request`.

### 왜 localhost는 200인데 도메인은 400인가

- `curl -kI https://localhost/api/` → Host 헤더가 `localhost` → 통과 → 200
- 외부 도메인 접속 → Host 헤더가 `3-34-199-116.sslip.io` → ALLOWED_HOSTS에 없음 → 400

Django는 들어온 요청의 Host 헤더가 `ALLOWED_HOSTS`에 있는지 검사함. (localhost가 통과한 건 .env 목록에 들어 있어서.)

### settings 구조 확인

```
base.py : ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])   # .env 주입
dev.py  : ALLOWED_HOSTS = ["*"]
prod.py : 오버라이드 없음 → base 상속 → .env 값이 운영값
```

→ 고칠 곳은 코드가 아니라 **EC2의 `.env`** (git 미추적, 서버 측 변경).

```
ALLOWED_HOSTS=3-34-199-116.sslip.io,3.34.199.116,localhost,127.0.0.1
```

```bash
sudo systemctl restart gunicorn   # .env는 Environment 주입 → 재시작 필요
```

---

## 5. Django 보안 설정 — 두 줄이 세트인 이유 (오늘의 핵심)

`config/settings/prod.py`에 추가 (PR #12로 머지).

```python
# --- HTTPS / behind Nginx proxy (Closes #12) ---
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
```

### 왜 이게 필요한가

Nginx가 TLS를 **종료(terminate)** 하고, Gunicorn에는 유닉스 소켓으로 **평문**을 넘김. 그래서 Django는 기본적으로 "나는 HTTP로 서비스 중"이라고 인식함. 이 상태면 세션/CSRF 쿠키에 Secure 플래그가 안 붙어 평문에도 노출될 수 있음.

### 무한 리다이렉트 루프 함정

`SECURE_SSL_REDIRECT = True`를 **단독으로** 켜면 루프가 발생함.

1. 요청 도착 → Django는 "HTTP네? → HTTPS로 리다이렉트"
2. 브라우저가 HTTPS로 재요청 → Nginx가 받아 소켓엔 또 **평문** 전달
3. Django는 다시 "HTTP네? → HTTPS로..." → 무한 반복

`SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`가 이 루프를 끊음.
의미: "요청 헤더에 `X-Forwarded-Proto: https`가 있으면, 이 요청을 HTTPS로 간주하라."
Nginx가 그 헤더를 붙여 보내니, Django가 "아 원래 HTTPS였구나" 인식 → 리다이렉트 안 함.

**따라서 두 설정은 반드시 세트.**

전제: Nginx `proxy_params`에 헤더 전달이 있어야 함. 이미 존재함을 확인(Day 8에 본 그 파일).

```nginx
proxy_set_header X-Forwarded-Proto $scheme;
```

---

## 6. 검증

```bash
# 로컬(외부)에서
curl -I https://3-34-199-116.sslip.io/api/   # → HTTP/1.1 200 OK
curl -I http://3-34-199-116.sslip.io/api/    # → 301 + Location: https://...
```

- 외부 HTTPS 200
- HTTP → HTTPS 301 자동 전환
- 무한 리다이렉트 루프 없음 (= proxy ssl header 정상 동작)
- `gunicorn.service` active (running), 워커 4

자동 갱신:

```bash
sudo certbot renew --dry-run   # 성공 → certbot.timer가 만료 30일 전부터 갱신
```

인증서 만료 2026-09-06.

---

## 막힌 곳 / 실수 메모

- `cerbot` / `nhinc` 오타로 패키지 설치 실패 → 정확히 `certbot`, `python3-certbot-nginx`
- `systemctl restart gunicorn`을 sudo 없이 실행 → polkit 비번 인증 요구 후 실패. systemd 제어는 `sudo` 필수.
- `systemctl status`가 pager(less)로 열려 `lines 1-18`에서 멈춤 → `q`로 빠져나옴 (에러 아님)

---

## 서버 측 변경분 (git 미추적 · 재구축 시 수동 반영)

- Nginx `server_name`에 `3-34-199-116.sslip.io` 추가
- certbot이 삽입한 443 ssl 블록 + 80 리다이렉트
- `.env` ALLOWED_HOSTS에 `3-34-199-116.sslip.io` 추가
- 인증서: `/etc/letsencrypt/live/3-34-199-116.sslip.io/`

## 코드 변경분 (PR #12 머지됨)

- `config/settings/prod.py`: SECURE_PROXY_SSL_HEADER / SECURE_SSL_REDIRECT / SESSION_COOKIE_SECURE / CSRF_COOKIE_SECURE

---

## 남은 과제

- SSH 하드닝 (`sshd_config` PasswordAuthentication no, 키 인증 강제) — HTTPS 먼저 하느라 미착수
- 다음 단계: Docker화 → GitHub Actions CI/CD