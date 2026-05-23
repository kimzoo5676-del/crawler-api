# Day 1 - 프로젝트 셋업 (2026-05-23)

> 자세한 정리: [Velog 포스트](https://velog.io/@zooouu/%EB%B0%B0%ED%8F%AC-%ED%95%99%EC%8A%B5%EC%9A%A9-%ED%86%A0%EC%9D%B4%ED%94%84%EB%A1%9C%EC%A0%9D%ED%8A%B8-DAY-1)

## 오늘 한 것
- 가상환경 생성, Django + DRF + django-environ 설치
- `startproject config .` / `startapp api`
- settings를 base / dev / prod 로 분리
- `.env` + `.gitignore` 설정
- GitHub 저장소 생성, 첫 푸시

## 학습 포인트 (요약)
- settings.py는 평범한 Python 모듈, `DJANGO_SETTINGS_MODULE`이 가리키는 파일을 settings로 사용
- 환경별로 달라야 하는 항목: SECRET_KEY, DEBUG, ALLOWED_HOSTS, DATABASES, STATIC_ROOT
- 민감 정보는 `.env`로 분리, `.gitignore`로 소스 컨트롤 차단
- Conventional Commits로 커밋 메시지 타입 명시 (chore/feat/fix 등)

## 막힌 부분
- 분리하는 이유

## 다음 할 일
- DRF Tutorial 1~3 (Serializers, Class-based Views, Generic Views)
- 더미 모델로 CRUD API 만들기

## 참고 링크
- [Django Settings](https://docs.djangoproject.com/en/5.1/topics/settings/)
- [Deployment Checklist](https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/)
- [Conventional Commits](https://www.conventionalcommits.org/)