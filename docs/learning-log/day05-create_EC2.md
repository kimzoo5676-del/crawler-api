# Day 5 (2026/6/02) — EC2 인스턴스 생성 + SSH 원격 접속으로 배포 환경 진입

> 자세한 정리: [Velog 포스트](https://velog.io/@zooouu/%EB%B0%B0%ED%8F%AC-%ED%95%99%EC%8A%B5%EC%9A%A9-%ED%86%A0%EC%9D%B4%ED%94%84%EB%A1%9C%EC%A0%9D%ED%8A%B8-DAY-5)

## 오늘의 목표

- Week 2 시작. 첫 EC2 인스턴스를 직접 생성하고 로컬에서 SSH 원격 접속 성공까지
- 배포 사전 작업으로 운영용 라이브러리(gunicorn, psycopg2-binary)를 requirements에 명시·커밋
- 키페어·보안그룹·퍼블릭 IP의 역할과 SSH 인증 흐름 정리

---

## 1. 배포용 라이브러리 추가

### 추가한 라이브러리

```
gunicorn==23.0.0
psycopg2-binary==2.9.10
```

| 라이브러리 | 역할 | 비고 |
|---|---|---|
| gunicorn | WSGI HTTP 서버. Django 앱을 프로세스로 띄워 실제 요청을 처리 | 개발용 `runserver`는 단일·디버그용이라 운영 부적합. Day 6에서 구동 |
| psycopg2-binary | PostgreSQL용 Python 드라이버. Django ORM ↔ PostgreSQL 통신을 담당 | `-binary`는 컴파일된 wheel이라 `libpq-dev`/`gcc` 없이 설치. 운영 정석은 소스빌드 `psycopg2`(추후 과제) |

### 기존 의존성 역할 정리 (Day 4까지)

| 라이브러리 | 역할 |
|---|---|
| Django | 웹 프레임워크 본체 |
| djangorestframework | DRF. 시리얼라이저·뷰셋·라우터 |
| django-filter | DRF 필터 백엔드(`filterset_fields`) |
| django-environ | `.env`/환경변수를 settings에 주입. `env.db()`로 `DATABASE_URL` 파싱 |
| requests · beautifulsoup4 · soupsieve | 크롤러의 HTTP 요청·HTML 파싱 |

### 코드·커밋

```bash
# requirements.txt에 2줄 추가 후
pip install -r requirements.txt   # 파일 통째로 설치 → 명시 버전과 실제 설치 일치
git add requirements.txt          # 의도한 파일만 콕 집어 add
git commit -m "chore: gunicorn, psycopg2-binary 의존성 추가"
git push
```

### 짚은 것

- `pip install gunicorn psycopg2-binary` 따로 치지 않고 `-r requirements.txt`로 설치. 파일에 적은 버전(`==23.0.0`, `==2.9.10`)과 실제 설치본을 정확히 일치시키기 위함.
- 설치 시 `packaging`이 전이 의존성으로 딸려옴. requirements엔 **직접 의존성만** 명시하고 전이 의존성은 pip이 자동 해결 → 별도 추가하지 않음. 전체 스냅샷 고정이 필요하면 `requirements.lock` 분리(추후 과제).
- 커밋 메시지 원칙: 행위("라이브러리 설치")가 아니라 변경 대상("무엇이 추가됐나")을 기록. Day 4의 `feat: JobPostingViewSet, Router, 필터링, 페이지네이션 추가` 스타일과 일관.

---

## 2. SSH 인증 모델

### 키페어 = 자물쇠와 열쇠

SSH는 비밀번호가 아니라 키페어로 인증. 퍼블릭 키(자물쇠)는 AWS가 EC2 내부에 심고, 프라이빗 키(`.pem`, 열쇠)는 사용자가 다운로드해 보관. 둘이 맞아야 접속 성립.

> AWS는 프라이빗 키를 저장하지 않음 → 키페어 생성 시 `.pem`이 **1회만** 다운로드되며, 분실 시 복구 불가(인스턴스 재생성 또는 키 재주입 필요).

### 키 파일 권한 요구 — chmod 600/400 필수

AWS 공식 문서가 명시하는 SSH 접속의 전제 조건.

> Your private key file must be protected from read and write operations from any other users. If your private key can be read or written to by anyone but you, then SSH ignores your key and you see the following warning message below.

번역: 프라이빗 키 파일은 다른 사용자의 읽기·쓰기로부터 보호되어야 함. 본인 외 누구든 읽거나 쓸 수 있으면 SSH가 키를 무시하고 경고를 출력.

→ 권한이 과도하게 열려 있으면(`-rw-r--r--` 등) SSH가 `WARNING: UNPROTECTED PRIVATE KEY FILE` / `Permission denied (publickey)`로 접속을 **거부**. 권한으로 "막는" 것이 아니라, 안전하지 않은 키는 아예 "쓰지 않는" 설계. Day 4의 ReadOnly 채택(노출 표면 자체 제거)과 결이 같은 최소 권한 사고.

| 권한 | 의미 | 용도 |
|---|---|---|
| 400 | `r--------` | 소유자 읽기 전용. 키 보관만 하면 충분할 때 |
| 600 | `rw-------` | 소유자 읽기+쓰기. 본 로그에서 채택 |

---

## 3. EC2 인스턴스 생성 (AWS 콘솔)

### 3-0. 리전 — 서울(ap-northeast-2)

물리적으로 가까울수록 지연이 짧음. 또한 **자원(인스턴스·키페어·보안그룹)은 리전별로 독립** → 처음부터 한 리전으로 고정해야 "내 서버가 어느 리전에 있는지" 혼동을 방지.

### 3-1. AMI — Ubuntu 24.04 LTS (x86, 프리티어)

| 후보 | 채택 여부 | 이유 |
|---|---|---|
| Ubuntu 24.04 LTS | 채택 | `apt` 기반 자료가 가장 풍부 → 막혔을 때 검색 효율. LTS는 장기 지원·안정 |
| Ubuntu 26.04 LTS | 제외 | 최신이라 PostgreSQL·Nginx 설치 자료가 덜 축적. "최신=좋음"이 아니라 "검증 덜 됨" |
| Amazon Linux | 제외 | `yum`/`dnf` 사용·패키지명 상이 → 자료 매칭이 어긋남 |
| with SQL Server / Ubuntu Pro | 제외 | 유료·불필요 |

→ 접속 기본 계정도 AMI로 갈림: Ubuntu는 `ubuntu`, Amazon Linux는 `ec2-user`.

### 3-2. 인스턴스 유형 — t3.micro

2 vCPU / 1 GiB, 프리티어 대상. Django+Postgres 실습에 충분. "모든 세대" 토글은 끔(비싼 옵션 오선택 방지).

> 과거 프리티어 대표는 t2.micro였으나 현재 서울 리전은 t3.micro가 프리티어로 지정. 둘 다 1 GiB로 용도상 차이 없음.

### 3-3. 키 페어

- 이름 `crawler-api-key` / 유형 **RSA** / 형식 **`.pem`**
- `.pem`은 Mac·Linux·VSCode 터미널의 `ssh` 명령용. `.ppk`는 Windows PuTTY 전용이라 미사용.

### 3-4. 보안그룹 — 인바운드 SSH 22번

**보안그룹 = EC2 앞 방화벽.** 기본 전부 차단 → 명시적으로 연 포트만 허용.

| 항목 | 설정 | 이유 |
|---|---|---|
| 인바운드 규칙 | SSH(22) 허용 | SSH는 항상 22번. 안 열면 접속 문 자체가 없음 |
| 출처(Source) | 위치 무관 `0.0.0.0/0` | 학습 편의(IP 변동에도 안 막힘). 단 논리적으로 더 열림 |
| HTTP(80)/HTTPS(443) | 오늘은 미개방 | 웹 서버(Nginx/Gunicorn) 붙이는 Day 6에 개방. "필요할 때 연다" |

→ `0.0.0.0/0`은 전 세계에서 22번 **접속 시도**만 가능한 것이고, 실제 로그인은 `.pem` 보유자만 가능. 키만 안 새면 안전. 운영 정석은 "내 IP" 또는 더 좁은 제한(추후 과제).

### 3-5. 스토리지 — 8 GiB gp3

프리티어 30 GiB 한도 내. gp3 = 기본 SSD. "파일시스템"은 별도 설정 없음 — AMI(Ubuntu)에 ext4로 이미 포맷·포함. 화면의 "인스턴스 저장소 볼륨" 문구는 임시 디스크(인스턴스 스토어) 얘기로 EBS와 무관.

### 짚은 것

- **퍼블릭 IP 자동 할당: 활성화** 확인 — 외부 접속 주소가 생기는 필수 옵션. 비활성이면 프라이빗 서브넷이 되어 직접 SSH 불가.
- 상태 변화 2단계: **실행 중(Running)** 은 1~2분, **상태 검사 2/2 통과** 는 2~3분. 후자까지 돼야 서버 부팅이 완료된 것.
- 퍼블릭 IP는 인스턴스 상세의 "퍼블릭 IPv4 주소"에서 확인. **중지(Stop) 시 IP가 바뀌므로** 학습 중엔 켜두는 편이 재접속에 유리. 고정이 필요하면 Elastic IP(추후 과제).

---

## 4. 키 관리 + SSH 접속 (로컬 Mac, zsh)

### 명령어와 역할

```bash
mkdir -p ~/.ssh                                  # SSH 표준 폴더(없으면 생성, 있으면 통과)
mv ~/Downloads/crawler-api-key.pem ~/.ssh/       # 다운로드 → 고정 위치로 이동
chmod 600 ~/.ssh/crawler-api-key.pem             # 소유자만 읽기/쓰기
ls -l ~/.ssh/crawler-api-key.pem                 # 확인: -rw------- 이어야 함
```

| 명령 | 역할 | 짚은 것 |
|---|---|---|
| `mkdir -p` | 폴더 생성 | `-p`는 이미 있으면 에러 없이 통과 |
| `mv` | 이동 | Downloads 잔류 시 분실·혼동 위험 → 고정 위치로. `~/.ssh`는 프로젝트와 분리되어 git 커밋 사고 방지 |
| `chmod 600` | 권한 설정 | SSH 접속의 **필수 조건**(2절 참조). 미적용 시 `UNPROTECTED PRIVATE KEY FILE`로 거부 |
| `ls -l` | 권한 확인 | 맨 앞 `-rw-------`이면 600 적용. `@`는 macOS의 "인터넷 다운로드 파일" 표식 — 무시 |

### SSH 접속

```bash
ssh -i ~/.ssh/crawler-api-key.pem ubuntu@<퍼블릭IP>
```

| 토큰 | 의미 |
|---|---|
| `ssh` | 접속 명령 |
| `-i <키경로>` | 이 프라이빗 키로 인증(`-i` = identity) |
| `ubuntu` | Ubuntu AMI 기본 계정 |
| `@<퍼블릭IP>` | 서버 주소(EC2 상세의 퍼블릭 IPv4) |

### 검증

- 첫 접속 시 호스트 신뢰 확인 프롬프트(`Are you sure you want to continue connecting (yes/no)?`) → `yes`(최초 1회만, 이후 `known_hosts`에 등록되어 생략).
- 프롬프트가 `ubuntu@ip-172-31-xx-xx:~$`로 바뀌면 **서버 내부 진입 성공**. 접속 직후 Ubuntu 배너와 `run: sudo apt update` 안내 출력 확인.
- `exit`로 SSH 연결만 종료. **인스턴스는 계속 실행 중** → 동일 `ssh` 명령으로 재접속 가능.

---

## 오늘의 정리

- 첫 EC2 인스턴스(서울 / Ubuntu 24.04 / t3.micro / 8GiB gp3) 생성 후 로컬에서 SSH 접속 성공. 모든 배포의 입구를 직접 손으로 구성.
- 키페어·보안그룹·퍼블릭 IP의 역할 확보: 키페어(인증), 보안그룹(22번 방화벽), 퍼블릭 IP(접속 주소)의 3요소가 모두 맞아야 접속 성립.
- AMI·인스턴스 유형·출처(SSH) 선택마다 "왜 이걸 골랐나"의 트레이드오프 정리 — 자료 풍부성·프리티어·학습 편의 vs 보안.
- `chmod 600`은 SSH가 안전하지 않은 키를 "쓰지 않는" 설계 때문이며, Day 4의 ReadOnly(노출 표면 제거)와 동일한 최소 권한 사고.

## 추후 과제 (메모)

- 보안그룹 SSH 출처를 "내 IP" 또는 더 좁은 대역으로 제한
- `psycopg2-binary` → 소스빌드 `psycopg2` 전환
- `requirements.lock` 분리(전체 스냅샷 고정)
- 결제 알림(Billing Alarm) 설정
- Elastic IP(고정 IP) 부여

## 다음 (Day 6)

- EC2에서 `sudo apt update` → Python·PostgreSQL·git 설치
- `git clone` → venv → 의존성 설치
- PostgreSQL DB·유저 생성 + `.env` 작성(`chmod 600`)
- `migrate` → Gunicorn 단독 구동 테스트
- env 주입은 `.env` + django-environ, env 객체·`read_env`는 `base.py`에 배치 예정