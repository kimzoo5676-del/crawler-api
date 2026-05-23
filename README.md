# crawler-api

> 데이터 수집 + REST API 토이프로젝트. Django + DRF 기반, EC2 / Docker / CI-CD 배포 학습 목적.

## 학습 목표
- DRF로 REST API 설계 및 인증/권한 구현
- AWS EC2에 수동 배포 (Gunicorn + Nginx + PostgreSQL + HTTPS)
- Docker / docker-compose로 컨테이너 배포 전환
- GitHub Actions로 CI/CD 파이프라인 구축

## Tech Stack
- Python 3.11, Django 5.2, Django REST Framework
- PostgreSQL (예정), Docker (예정), Nginx + Gunicorn (예정)
- AWS EC2, GitHub Actions (예정)

## Local Setup
````bash
git clone https://github.com/kimzoo5676-del/crawler-api.git
cd crawler-api
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # 값 채우기
python manage.py migrate
python manage.py runserver
````

## Project Structure
````
crawler-api/
├── config/
│   ├── settings/         # base / dev / prod 분리
│   ├── urls.py
│   └── wsgi.py
├── api/                  # API 앱
├── docs/learning-log/    # 일별 학습 기록
└── manage.py
````

## Learning Log
[docs/learning-log/](./docs/learning-log/) 디렉토리에 일별 작업 기록.  


긴 회고는 [Velog](https://velog.io/@zooouu)에.


## Progress
- [x] Week 1 - DRF + 데이터 수집 백엔드 (5/26 ~ 6/1)
- [ ] Week 2 - EC2 수동 배포 (6/2 ~ 6/8)
- [ ] Week 3 - Docker화 (6/9 ~ 6/15)
- [ ] Week 4 - CI/CD + 마무리 (6/16 ~ 6/20)
````
