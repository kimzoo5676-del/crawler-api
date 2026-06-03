# Day 6 (2026/6/03) — EC2에 운영 환경 구성 + PostgreSQL 연결 + Gunicorn 외부 구동

> 자세한 정리: [Velog 포스트](https://velog.io/@zooouu)

## 오늘의 목표

- Day 5에서 만든 EC2 인스턴스 안에 실제 운영 환경을 손으로 구성: 패키지 설치 → 코드 배치 → DB·환경변수 → 마이그레이션 → 서버 구동
- 로컬 SQLite에서 운영 PostgreSQL로 전환하고, `base`/`prod` 분리 구조가 의도대로 동작하도록 정리
- Gunicorn으로 Django 앱을 띄워 **외부 브라우저에서 API 응답까지** 확인
- 수정 내역을 이슈·브랜치·PR 워크플로우로 추적하고, 로컬·GitHub·EC2 세 환경의 정본을 일치

---

## 1. 시스템 패키지 설치 (EC2 / Ubuntu 24.04)

### 명령어와 역할

```bash
sudo apt update                                      # 패키지 인덱스 재동기화
sudo apt upgrade -y                                  # 설치된 패키지를 최신으로 교체
sudo apt install -y python3-venv python3-pip         # 가상환경·패키지 도구
sudo apt install -y postgresql postgresql-contrib    # DB 서버 + 추가 유틸
git --version                                        # git 기본 포함 확인
```

| 명령 | 역할 | 짚은 것 |
|---|---|---|
| `apt update` | 저장소에서 "어떤 패키지의 어떤 버전이 받을 수 있는지" 목록(인덱스)을 갱신 | **설치가 아님.** 실제 패키지는 안 건드림. 공식 표현으로 "패키지 인덱스 재동기화" |
| `apt upgrade -y` | 갱신된 인덱스 기준으로 실제 새 버전 내려받아 교체 | `-y`는 yes/no 확인 자동 승인 |
| `python3-venv` | 프로젝트별 의존성 격리용 가상환경 모듈 | Ubuntu는 venv·pip이 본체와 분리 패키징 |
| `postgresql` / `-contrib` | DB 서버 본체 / 공식 추가 확장·유틸 | 설치 시 systemd 서비스로 자동 등록·시작 |

### 짚은 것 — 커널 업그레이드 후 재부팅

`apt upgrade` 중 커널이 새 버전으로 갱신되면서 안내가 떴다.

```
Pending kernel upgrade!
Running kernel version:  6.17.0-1012-aws
... is not the expected kernel version 6.17.0-1017-aws.
```

- **메모리에서 도는 커널은 옛 버전**, 디스크엔 새 커널이 깔린 상태. 새 커널은 재부팅해야 적용 → `sudo reboot`.
- 재부팅 시 SSH가 끊기며 `Connection reset by peer` / `Broken pipe` 출력 — **에러가 아니라 정상적인 재부팅 결과**. 서버가 내려가며 연결이 강제 종료된 것.
- **재부팅(reboot)은 퍼블릭 IP 유지**, 중지(stop) 후 재시작은 IP 변동. 그래서 같은 IP로 30초~1분 뒤 재접속 가능.

---

## 2. 코드 배치 — clone → venv → 의존성 설치

### 명령어와 역할

```bash
cd ~                                                 # /home/ubuntu
git clone https://github.com/kimzoo5676-del/crawler-api.git
cd crawler-api
python3 -m venv venv                                 # 가상환경 생성
source venv/bin/activate                             # 활성화 → 프롬프트에 (venv)
pip install --upgrade pip
pip install -r requirements.txt                      # 명시 버전 그대로 설치
pip list                                             # 설치 확인
```

| 명령 | 역할 | 짚은 것 |
|---|---|---|
| `git clone` | 원격 저장소 전체(히스토리 포함)를 복제 | public repo라 HTTPS로 인증 없이 |
| `python3 -m venv venv` | 시스템 Python과 격리된 전용 환경 생성 | 마지막 `venv`는 폴더명(관례) |
| `source venv/bin/activate` | 현재 셸의 PATH를 venv 쪽으로 전환 | `source`는 스크립트를 현재 셸에 적용 |
| `pip install -r` | 파일에 적힌 패키지 일괄 설치 | Day 5에서 추가한 gunicorn·psycopg2-binary 포함 |

### 짚은 것 — 로컬과 EC2의 Python 버전 분리

재부팅 직후 SSH가 끊겨 프롬프트가 로컬 Mac으로 돌아온 상태에서 `python3 --version`을 치니 **3.11.9(Mac)** 가 나왔다. EC2가 아님. 프롬프트 호스트명(`zoo@MacZoo-Pro` vs `ubuntu@ip-...`)으로 어느 환경인지 항상 확인할 것. EC2는 Ubuntu 24.04라 Python 3.12.

- `psycopg2-binary`는 컴파일된 wheel이라 빌드 도구 없이 설치됨. 만약 컴파일 에러가 나면 `libpq-dev python3-dev build-essential` 추가 후 재시도(이번엔 불필요).

---

## 3. PostgreSQL DB·유저 생성

### peer 인증으로 관리자 진입

```bash
sudo -u postgres psql        # postgres OS 계정 권한으로 psql 진입 → postgres=#
```

PostgreSQL은 설치 시 OS 계정 `postgres`를 만들고, 그 계정으로 DB superuser에 비번 없이 접속(**peer 인증**: OS 사용자명과 DB 사용자명이 같으면 허용).

### DB·유저 생성 (SQL)

```sql
CREATE DATABASE crawler_db;
CREATE USER crawler_user WITH PASSWORD 'your_strong_password';
ALTER ROLE crawler_user SET client_encoding TO 'utf8';
ALTER ROLE crawler_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE crawler_user SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE crawler_db TO crawler_user;
\c crawler_db
GRANT ALL ON SCHEMA public TO crawler_user;
\q
```

| 구문 | 역할 | 짚은 것 |
|---|---|---|
| `ALTER ROLE ... SET` 3종 | 인코딩 utf8 / 격리수준 read committed / 타임존 UTC 고정 | Django 공식 문서 권장 PostgreSQL 유저 기본 설정. 매 연결 시 설정하는 수고를 덜고 일관성 보장 |
| `GRANT ALL PRIVILEGES ON DATABASE` | DB 레벨 권한 부여 | 이것만으론 부족 |
| `GRANT ALL ON SCHEMA public` | **PG 15+ 필수.** public 스키마에 테이블 생성 권한 부여 | 누락 시 `migrate`에서 `permission denied for schema public` |

### 짚은 것

- 트랜잭션 격리수준 `read committed`는 Django가 기대하는 기본값. 명시적으로 맞춰 일관성 확보.
- `\c`(connect) / `\q`(quit) 등 백슬래시 명령은 psql 메타 명령으로 `;` 불필요. 반면 SQL은 `;`가 있어야 실행(아래 트러블슈팅 1).

---

## 4. 환경변수 주입 — .env + django-environ

### .env 작성·권한 잠금

```bash
nano .env
chmod 600 .env          # 소유자만 읽기/쓰기 — 비번·시크릿키 보호
ls -l .env              # -rw------- 확인
```

```dotenv
SECRET_KEY=<get_random_secret_key()로 생성한 값>
DEBUG=False
DATABASE_URL=postgres://crawler_user:your_strong_password@localhost:5432/crawler_db
ALLOWED_HOSTS=<퍼블릭IP>,localhost,127.0.0.1
```

| 키 | 역할 | 짚은 것 |
|---|---|---|
| `SECRET_KEY` | Django 암호 서명용 키 | 노출 금지라 `.env`로 분리. `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`로 생성 |
| `DEBUG` | 디버그 모드 | prod는 False. django-environ `env.bool()`이 문자열 `"False"`→파이썬 `False` 변환 |
| `DATABASE_URL` | `postgres://유저:비번@호스트:포트/DB명` | `env.db()`가 이 한 줄을 Django `DATABASES` 딕셔너리로 파싱. 같은 서버라 호스트는 `localhost`, 포트 5432 |
| `ALLOWED_HOSTS` | 허용 호스트 | 퍼블릭 IP 누락 시 `DisallowedHost`(400). 콤마 구분 리스트로 읽음 |

### settings 분리 구조 검증

운영 settings(`config.settings.prod`)가 `.env`를 제대로 읽는지 `migrate` 전에 확인:

```bash
DJANGO_SETTINGS_MODULE=config.settings.prod python manage.py shell \
  -c "from django.conf import settings; print(settings.DATABASES['default']['ENGINE'])"
# → django.db.backends.postgresql  (성공)
```

명령 앞에 `DJANGO_SETTINGS_MODULE=config.settings.prod`를 붙이면 그 명령에 한해 prod settings로 실행. 안 붙이면 기본값(base→SQLite)으로 감.

---

## 5. settings 버그 수정 (base/prod 분리)

배포 검증 중 settings 환경변수 주입 버그 2건 발견·수정. (이슈 #6 / PR `settings-6`)

### 버그 1 — DEBUG가 SECRET_KEY를 읽음

```python
# base.py  (before)
DEBUG = env("SECRET_KEY")          # SECRET_KEY 문자열이 DEBUG에 대입 → truthy → 항상 True
# base.py  (after)
DEBUG = env.bool("DEBUG", default=False)
```

비어있지 않은 문자열은 파이썬에서 참 → prod인데 디버그가 켜지는 보안 위험. `env.bool()`이 아니라 `env("DEBUG")`로 읽어도 문자열 `"False"`가 truthy라 위험 → `.bool()` 필수.

### 버그 2·3 — prod이 SQLite를 상속

```python
# prod.py  (before)
from .base import *               # base의 SQLite DATABASES를 그대로 상속
# prod.py  (after)
from .base import *
DEBUG = False
DATABASES = {
    "default": env.db(),          # .env의 DATABASE_URL을 파싱해 PostgreSQL로 오버라이드
}
```

### 짚은 것 — 왜 base는 SQLite를 남겨두나

settings 로딩 순서: `prod.py`가 `from .base import *`로 SQLite를 일단 가져온 뒤, 같은 이름 `DATABASES`를 다시 대입해 **덮어씀**(파이썬은 나중 대입이 이김). 따라서

- **base의 SQLite** = 로컬 Mac 개발 기본값(Postgres 설치 없이 바로 구동)
- **prod의 PostgreSQL** = EC2 운영용(`env.db()`)

어느 settings로 실행하느냐로 갈림 → `DJANGO_SETTINGS_MODULE`이 핵심. 환경별 차이만 prod이 덮어쓰는 것이 base/prod 분리의 요점.

---

## 6. migrate + Gunicorn 구동

### migrate

```bash
DJANGO_SETTINGS_MODULE=config.settings.prod python manage.py migrate
# Applying ... OK  (12개 테이블 생성)
sudo -u postgres psql -d crawler_db -c "\dt"   # 테이블 목록 확인
```

`\dt` 출력에서 `api_jobposting`, `tutorial_snippet`, Django 기본 테이블의 **Owner가 모두 `crawler_user`** → 스키마 GRANT가 제대로 먹어 유저가 직접 테이블을 생성했다는 증거.

### 보안그룹 8000번 개방 (AWS 콘솔)

Gunicorn 구동 전, 보안그룹 인바운드에 **Custom TCP 8000 / 0.0.0.0/0** 추가. 안 열면 외부 브라우저 접속이 타임아웃(방화벽이 막음). Day 5의 22번과 같은 "필요할 때 연다" 원칙.

### Gunicorn 단독 구동

```bash
DJANGO_SETTINGS_MODULE=config.settings.prod \
  gunicorn config.wsgi:application --bind 0.0.0.0:8000
```

| 토큰 | 의미 | 짚은 것 |
|---|---|---|
| `config.wsgi:application` | `config/wsgi.py`의 `application` 객체를 WSGI 서버로 구동 | base의 `WSGI_APPLICATION`과 일치 |
| `--bind 0.0.0.0:8000` | 모든 인터페이스 8000번에서 수신 | `127.0.0.1`로 묶으면 EC2 내부에서만 접근 가능 → 외부 브라우저 불가 |

→ 브라우저 `http://<퍼블릭IP>:8000/api/`에서 DRF browsable API + `Api Root`(`"jobs": ".../api/jobs/"`) + `HTTP 200 OK` 확인. **외부에서 운영 환경 API 응답 성공.**

### 짚은 것

- `DEBUG=False`라 `/admin/` CSS가 깨져 보이는 건 정상(정적 파일 미수집). `collectstatic`+Nginx 정적 서빙은 다음 과제.
- 브라우저 `주의 요함`(Not Secure)은 HTTP라 뜨는 것. HTTPS(Nginx+인증서) 단계에서 해소.

---

## 7. 이슈·브랜치·PR 워크플로우

EC2에서 직접 고친 settings 수정을 정본으로 만들기 위해 **로컬에서 동일 수정 → commit/push → PR → EC2 pull** 순으로 정리.

```bash
# 로컬 Mac
git switch -c settings-6                            # 이슈 #6 기반 브랜치 ({영역}-{이슈번호})
git commit -m "Fix: DEBUG env.bool 수정, prod DATABASES env.db 추가"
git push -u origin settings-6                       # upstream 설정 동시
# → GitHub에서 PR 생성, 본문에 Closes #6 → 머지 시 이슈 자동 닫힘 → 셀프 머지
git switch main && git pull                         # 로컬 main 최신화
```

```bash
# EC2 — 정본 동기화
git stash                # 손으로 고친 변경을 임시 보관(충돌 방지)
git pull origin main     # Fast-forward로 정본 수신
git stash drop           # 동일 내용이라 보관분 폐기
```

| 개념 | 역할 | 짚은 것 |
|---|---|---|
| 브랜치 네이밍 | `{영역}-{이슈번호}` (예: `settings-6`) | 혼자 하는 토이플젝이라도 일관 컨벤션 유지 |
| `Closes #6` | PR 본문에 넣으면 머지 시 이슈 자동 종료 | 커밋 메시지엔 이슈 번호 미기재(PR이 추적 담당) |
| `git stash` → `pull` → `drop` | EC2 수동 수정과 원격 정본 충돌 회피 | EC2를 코드 origin으로 쓰지 않음(배포 서버에 push 권한 부여는 비권장) |

→ 결과적으로 **로컬·GitHub·EC2 세 환경의 settings 정본이 완전 일치**. EC2 pull은 `Fast-forward`로 충돌 없이 완료.

---

## 오늘의 정리

- Day 5에서 만든 빈 EC2에 운영 스택(Python·PostgreSQL·git → venv·의존성 → DB·.env → migrate → Gunicorn)을 손으로 쌓아 **외부 브라우저에서 API 응답까지** 도달.
- 로컬 SQLite → 운영 PostgreSQL 전환을 `base`/`prod` 분리로 처리: base는 개발용 SQLite 유지, prod만 `env.db()`로 오버라이드. `DJANGO_SETTINGS_MODULE`이 환경을 가르는 스위치.
- `.env` + django-environ으로 비밀값(SECRET_KEY·DB 비번)을 코드 밖으로 분리하고 `chmod 600`으로 잠금 — Day 5의 키 권한(600)과 동일한 최소 권한 사고.
- 수정 내역을 이슈→브랜치→PR→머지→3환경 동기화로 추적. 배포 서버(EC2)는 코드를 받기만 하고 origin으로 쓰지 않는 단방향 흐름 정립.

## 트러블슈팅 (오늘 막힌 것)

| 증상 | 원인 | 해결 |
|---|---|---|
| `syntax error at or near "ALTER"` | `CREATE USER` 줄 끝 `;` 누락 → 다음 SQL과 한 덩어리로 합쳐짐 (`postgres-#` 입력대기) | 각 SQL 끝에 `;`. 프롬프트가 `-#`면 `;` 치고 엔터 |
| `syntax error at or near "."` | `crawler.user`로 입력(점) | `crawler_user`(언더스코어). 점은 `스키마.객체` 구분자 |
| (예상) `permission denied for schema public` | PG 15+에서 DB 권한만으론 public 스키마 테이블 생성 불가 | `\c crawler_db` 후 `GRANT ALL ON SCHEMA public TO crawler_user` |
| `ModuleNotFoundError: No module named 'config.settigns'` | `settings`를 `settigns`로 오타 | 철자 교정. 긴 명령은 복붙 |
| `src refspec settings does not match any` | `git push -u origin settings -6`처럼 브랜치명에 공백 | `settings-6` 붙여서 |
| Gunicorn 구동했는데 브라우저 무한 대기 | 보안그룹 8000번 미개방 | 인바운드 Custom TCP 8000 추가 |

## 추후 과제 (메모)

- Gunicorn을 **systemd 서비스**로 등록 → SSH 끊겨도 상시 구동 + 재부팅 자동 시작
- **Nginx 리버스 프록시**(80→8000) + 정적 파일 서빙 + HTTPS
- `collectstatic`로 admin/DRF 정적 파일 수집
- 보안그룹 8000/22 출처를 "내 IP"로 제한
- DB 비번을 추측 어려운 강한 값으로 교체(`ALTER ROLE ... WITH PASSWORD`)
- `.env`의 `SECRET_KEY`를 운영용 신규 키로 재발급

## 다음 (Day 7)

- systemd로 Gunicorn 데몬화 (`.service` 유닛 작성, `systemctl enable/start`)
- Nginx 설치·리버스 프록시 설정, 80번 개방
- (Week 3) Docker화 → (Week 4) GitHub Actions CI/CD