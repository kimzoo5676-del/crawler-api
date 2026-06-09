# Day 10 — SSH 하드닝 + Docker화 1단계 (Django + Gunicorn 단일 이미지)
> 자세한 정리: [Velog 포스트](https://velog.io/@zooouu/%EB%B0%B0%ED%8F%AC-%ED%95%99%EC%8A%B5%EC%9A%A9-%ED%86%A0%EC%9D%B4%ED%94%84%EB%A1%9C%EC%A0%9D%ED%8A%B8-DAY-10-qwi0pr5r)

---

## Part 1 — SSH 하드닝

### 목표
- Day 9에서 Part로 남겨둔 SSH 보안 강화 마무리
- 비밀번호 인증 차단, root 로그인 차단, 키 인증만 허용

### 작업 내용

**현재 설정 확인**
```bash
grep -r "PasswordAuthentication" /etc/ssh/sshd_config /etc/ssh/sshd_config.d/
```
- 메인 `sshd_config`의 `PasswordAuthentication`은 전부 주석 처리 상태(비활성)
- drop-in `60-cloudimg-settings.conf`에 이미 `PasswordAuthentication no` 존재 (AWS Ubuntu 이미지 기본값)
- 즉 비밀번호 인증은 이미 꺼져 있었으나, 의도를 명시적으로 고정하기 위해 별도 drop-in 작성

**drop-in 파일 작성**
- 위치: `/etc/ssh/sshd_config.d/99-hardening.conf`
```
PasswordAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
```

**적용 및 검증**
```bash
sudo sshd -t                     # 문법 검사 (무출력 = 정상)
sudo systemctl restart ssh       # Ubuntu 24.04 서비스명은 sshd 아닌 ssh
sudo sshd -T | grep -Ei "passwordauthentication|permitrootlogin|pubkeyauthentication"
```
검증 결과
```
permitrootlogin no
pubkeyauthentication yes
passwordauthentication no
```

**잠금 검증** (기존 세션 유지한 채 새 세션으로)
```bash
# 키 접속 — 정상 접속됨
ssh -i ~/.ssh/crawler-api-key.pem ubuntu@<도메인>

# 비번 강제 시도 — Permission denied (publickey) 거부됨
ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no ubuntu@<도메인>
```

### 핵심 정리 (개념)

- **drop-in 우선순위**: `/etc/ssh/sshd_config.d/` 안의 파일은 파일명 사전순으로 적용되며 나중 것이 이김. 따라서 `99-`로 시작하는 파일이 `60-cloudimg-settings.conf`보다 마지막에 적용되어 최종 승리. 메인 설정에 무엇이 있든 99번으로 덮어쓰기 가능
- **경로 함정**: `ssh_config.d`(클라이언트 설정)와 `sshd_config.d`(서버 데몬 설정)는 다른 디렉토리. 처음 `ssh_config.d`에 잘못 작성 → `sshd -T`의 `permitrootlogin`이 `without-password` 그대로라 미적용 확인 → `sshd_config.d`로 재작성하니 `no`로 변경됨. **`d`의 위치 차이가 핵심**
- **`without-password` vs `no`**: `without-password`는 root가 비번으론 못 들어오지만 키 있으면 가능한 상태. 완전 차단은 `no`
- **`sshd -T`의 역할**: 모든 drop-in을 병합한 **실제 런타임 값**을 출력. 파일 하나만 봐선 최종 적용값을 알 수 없으므로 검증 시 필수
- **서비스명**: Ubuntu 24.04는 `systemctl restart ssh` (`sshd` 아님), socket activation 구조
- **안전 검증 원칙**: 비번 인증을 잠그기 전후로 **기존 SSH 세션을 반드시 열어둔 채** 새 세션에서 검증. 새 접속이 막히면 기존 세션으로 롤백 가능

---

## Part 2 — Docker화 1단계 (Dockerfile 작성 및 로컬 빌드 검증)

### 목표
- Django + Gunicorn을 단일 Docker 이미지로 빌드
- 로컬에서 컨테이너 기동 후 `/api/` 응답까지 검증
- DB·Nginx 컨테이너 통합은 후속 이슈로 분리 (오늘은 "이미지가 돈다"만 확인)

### Docker화의 동기
- Day 5~9 동안 EC2 한 대에 Python·PostgreSQL·Nginx를 직접 설치하면서, Day마다 "서버 측 변경분(git 미추적, 재구축 시 수동 반영 필요)" 메모가 누적됨
- Docker는 그 수동 반영분을 **이미지(빌드 산출물)와 compose(구성)로 코드화**해서 "어느 머신에서든 같은 결과"를 만드는 것이 핵심 동기

### 환경 준비 (트러블슈팅)
- Docker Desktop 설치 직후 `com.docker.vmnetd` "악성 코드가 차단됨(Malware Blocked)" 경고 발생
- 원인: 2025년 1월부터 알려진 false positive. Docker가 일부 파일에 잘못된 코드 서명을 사용해 macOS 무결성 검사가 실패한 것. **악성코드 아님**
- 해결: 최신 버전(4.37.2 이상) 재설치로 영구 해결
- 검증: `docker run hello-world` → "Hello from Docker!" 정상 출력

### 사전 정리
- `config/settings/base.py`의 `INSTALLED_APPS`에서 `"tutorial",` 삭제
- tutorial은 DRF 튜토리얼 실습 잔재 앱. `config/urls.py`·`api/` 어디서도 미참조라 제거해도 안전
- `python manage.py check --settings=config.settings.dev` → `no issues` 확인 후 진행

### .dockerignore
빌드 컨텍스트에서 제외할 파일 지정. `docker build`는 현재 디렉토리 전체를 daemon에 전송하므로, 불필요·위험 파일을 빼야 함
```
__pycache__/
*.py[cod]
venv/
.venv/
db.sqlite3
*.log
staticfiles/
.env
.env.*
.git/
.gitignore
.github/
docs/
tutorial/
README.md
.DS_Store
```
- `venv/`: 컨테이너 안에서 `pip install`로 새로 설치하므로 불필요. macOS(arm64)에서 만든 venv는 리눅스 컨테이너와 바이너리 호환 안 됨 → 반드시 제외
- `.env`: 비밀값을 이미지에 굽지 않는 원칙. 환경변수는 실행 시 주입
- `db.sqlite3`: 데이터를 이미지에 박는 안티패턴 → 제외

### Dockerfile
```dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "config.wsgi:application"]
```

각 줄의 의도
- `FROM python:3.11-slim`: 로컬 venv가 3.11이라 버전 일치. `slim`은 최소 런타임만 담아 약 150MB (일반 이미지 약 1GB)
- `ENV PYTHONDONTWRITEBYTECODE=1`: `.pyc` 캐시 미생성 (컨테이너는 일회성이라 불필요)
- `ENV PYTHONUNBUFFERED=1`: stdout 버퍼링 비활성 → `docker logs`에 로그 즉시 출력
- `WORKDIR /app`: 이후 명령의 기준 경로
- **requirements.txt 먼저 복사 → 핵심**: Docker는 명령마다 레이어로 캐시. 앞 레이어가 안 바뀌면 뒤 레이어 캐시 재사용. 의존성(거의 불변)과 코드(자주 변경)를 분리하면, 코드만 고친 재빌드 시 `pip install` 레이어를 통째로 재사용
- `COPY . .`: 나머지 소스 복사 (.dockerignore가 걸러줌)
- `EXPOSE 8000`: 문서·메타데이터일 뿐, 실제 포트 개방은 `docker run -p`가 수행
- `CMD gunicorn --bind 0.0.0.0:8000`: `0.0.0.0`이라야 컨테이너 밖에서 접근 가능 (`127.0.0.1`이면 컨테이너 내부 전용). 진입점은 `config.wsgi:application`

### 빌드 및 실행 (트러블슈팅)
```bash
docker build -t crawler-api:dev .
```
빌드 성공 (`naming to docker.io/library/crawler-api:dev`)

**1차 실행 — 실패**
```bash
docker run --rm -p 8000:8000 crawler-api:dev
```
- gunicorn은 정상 부팅(`Listening at: http://0.0.0.0:8000`)했으나 worker가 `KeyError: 'SECRET_KEY'` → `ImproperlyConfigured`로 죽음
- 원인: `base.py`의 `SECRET_KEY = env("SECRET_KEY")`가 환경변수를 찾는데, `.env`를 `.dockerignore`로 일부러 제외했기 때문. **의도대로 동작한 것**

**2차 실행 — 성공**
```bash
docker run --rm -p 8000:8000 --env-file .env crawler-api:dev
```
- 호스트의 `.env`를 런타임에 읽어 컨테이너 환경변수로 주입
```bash
curl -i http://localhost:8000/api/
# HTTP/1.1 200 OK
# Server: gunicorn
# {"jobs":"http://localhost:8000/api/jobs/"}
```

### 핵심 정리 (개념)

- **이미지에는 코드+의존성만, 설정·비밀은 실행 시 주입**: 같은 이미지를 dev/prod/EC2 어디서나 환경변수만 바꿔 재사용하는 것이 Docker의 핵심 이점. `.env`를 안 구운 것이 정답
- **레이어 캐시**: Dockerfile 각 명령 = 한 레이어. requirements와 코드를 분리 복사하면 재빌드 속도 확보
- **포트 매핑**: `-p 8000:8000`에서 왼쪽이 호스트, 오른쪽이 컨테이너 내부. `EXPOSE`는 문서일 뿐 실제 개방은 `-p`
- **TCP 바인딩 vs 유닉스 소켓**: Day 7 EC2 gunicorn은 유닉스 소켓(`--bind unix:...`)을 썼으나, 컨테이너는 격리되어 나중에 Nginx 컨테이너와 네트워크 너머로 통신해야 하므로 TCP(`0.0.0.0:8000`)가 맞음
- **settings 선택**: `wsgi.py` 기본값이 `config.settings.dev`라 오늘은 주입 불필요. prod는 `SECURE_SSL_REDIRECT=True`(HTTP→301 https)와 `env.db()`(PostgreSQL)라 DB·Nginx 없는 단독 컨테이너 검증엔 부적합

---

## 후속 (다음 이슈)
- compose로 PostgreSQL 컨테이너 붙이기 (+migrate, prod settings·env.db 주입)
- Nginx 컨테이너화
- EC2에 compose 기동 (기존 systemd+Nginx 운영방식과 교체 방법 결정)
- arm64 로컬 이미지를 x86_64 EC2에 올릴 때 아키텍처 차이 확인