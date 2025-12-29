FROM python:3.12-slim

WORKDIR /app

# 시스템 의존성 설치
RUN apt-get update && apt-get install -y \
    android-tools-adb \
    usbutils \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python 패키지 설치
COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir -e ".[sse]"

# 환경 변수
ENV ANDROID_HOME=/usr/lib/android-sdk
ENV PYTHONUNBUFFERED=1

# 포트 노출
EXPOSE 51821

# 헬스체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:51821/health || exit 1

# 실행 (토큰은 환경변수로 전달)
CMD ["mobile-mcp", "--mode", "sse", "--host", "0.0.0.0", "--port", "51821"]
