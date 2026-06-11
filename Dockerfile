# 1) 베이스 이미지
FROM python:3.11-slim

# 2) 파이썬 런타임 환경변수
ENV PYTHONDONTWRITEBYTECODE=1 \
  PYTHONUNBUFFERED=1

# 3) 작업 디렉토리
WORKDIR /app

# 4) 의존성 먼저 복사 -> 설치 (레이어 캐시 노림)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5) 나머지 소스 복사
COPY . .

# 6) 포트 문서화
EXPOSE 8000

# 7) 시작 스크립트 복사 + 실행 권한
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# 8) 컨테이너 시작 명령
CMD ["/entrypoint.sh"]