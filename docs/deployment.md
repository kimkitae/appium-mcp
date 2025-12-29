# Mobile MCP 배포 가이드

이 문서는 Mobile MCP 서버를 다양한 환경에 배포하는 방법을 설명합니다.

## 실행 모드

Mobile MCP는 두 가지 모드를 지원합니다:

| 모드 | 용도 | 프로토콜 |
|------|------|----------|
| **stdio** | 로컬 실행 (Claude Desktop, Claude Code) | 표준 입출력 |
| **sse** | 원격 서버 (HTTP 연결) | Server-Sent Events |

---

## 1. 로컬 실행 (macOS/Linux)

### 설치

```bash
# 저장소 클론
git clone https://github.com/kimkitae/appium-mcp.git
cd appium-mcp

# 가상환경 생성 및 활성화
python3 -m venv venv
source venv/bin/activate

# 의존성 설치
pip install -e .
```

### stdio 모드로 실행

```bash
# 기본 실행
mobile-mcp

# 또는 명시적으로
mobile-mcp --mode stdio
```

### Claude Desktop 설정 (stdio)

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "mobile-mcp": {
      "command": "/path/to/venv/bin/mobile-mcp",
      "args": []
    }
  }
}
```

### Claude Code 설정 (stdio)

```bash
claude mcp add mobile-mcp /path/to/venv/bin/mobile-mcp
```

---

## 2. 원격 서버 배포 (Ubuntu)

### 서버 설치

```bash
# 저장소 클론
git clone https://github.com/kimkitae/appium-mcp.git
cd appium-mcp

# 가상환경 생성
python3 -m venv venv
source venv/bin/activate

# SSE 모드 의존성 포함 설치
pip install -e ".[sse]"
```

### SSE 모드로 실행

```bash
# localhost만 접속 허용 (기본)
mobile-mcp --mode sse

# 외부 접속 허용
mobile-mcp --mode sse --host 0.0.0.0 --port 3000

# 커스텀 포트
mobile-mcp --mode sse --host 0.0.0.0 --port 8080
```

### systemd 서비스 등록

`/etc/systemd/system/mobile-mcp.service`:

```ini
[Unit]
Description=Mobile MCP Server
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/appium-mcp
Environment=PATH=/home/ubuntu/appium-mcp/venv/bin:/usr/bin
ExecStart=/home/ubuntu/appium-mcp/venv/bin/mobile-mcp --mode sse --host 0.0.0.0 --port 3000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# 서비스 등록 및 시작
sudo systemctl daemon-reload
sudo systemctl enable mobile-mcp
sudo systemctl start mobile-mcp

# 상태 확인
sudo systemctl status mobile-mcp

# 로그 확인
sudo journalctl -u mobile-mcp -f
```

### Docker 배포

`Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# 시스템 의존성 설치 (ADB, go-ios 등 필요시)
RUN apt-get update && apt-get install -y \
    android-tools-adb \
    && rm -rf /var/lib/apt/lists/*

# Python 패키지 설치
COPY pyproject.toml .
COPY src/ src/
RUN pip install -e ".[sse]"

# 환경 변수
ENV ANDROID_HOME=/usr/lib/android-sdk

# 포트 노출
EXPOSE 3000

# 실행
CMD ["mobile-mcp", "--mode", "sse", "--host", "0.0.0.0", "--port", "3000"]
```

```bash
# 빌드
docker build -t mobile-mcp .

# 실행 (USB 디바이스 접근을 위해 privileged 필요)
docker run -d \
  --name mobile-mcp \
  --privileged \
  -v /dev/bus/usb:/dev/bus/usb \
  -p 3000:3000 \
  mobile-mcp
```

---

## 3. 클라이언트에서 원격 서버 연결

### Claude Desktop 설정 (SSE)

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mobile-mcp": {
      "url": "http://your-server-ip:3000/sse"
    }
  }
}
```

### Claude Code 설정 (SSE)

```bash
# 현재 Claude Code는 stdio만 지원
# SSH 터널링 사용
ssh -L 3000:localhost:3000 user@your-server

# 또는 socat으로 stdio-to-TCP 변환
```

### Python 클라이언트

```python
from mcp import ClientSession
from mcp.client.sse import sse_client

async def connect_remote():
    async with sse_client("http://your-server:3000/sse") as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 도구 목록 조회
            tools = await session.list_tools()
            print(tools)

            # 도구 호출
            result = await session.call_tool(
                "mobile_take_screenshot",
                {}
            )
            print(result)
```

---

## 4. 네트워크 설정

### 방화벽 설정 (Ubuntu)

```bash
# UFW 사용 시
sudo ufw allow 3000/tcp

# iptables 사용 시
sudo iptables -A INPUT -p tcp --dport 3000 -j ACCEPT
```

### Nginx 리버스 프록시 (선택사항)

`/etc/nginx/sites-available/mobile-mcp`:

```nginx
server {
    listen 80;
    server_name mcp.your-domain.com;

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;
        proxy_cache off;
    }
}
```

### SSL/TLS (권장)

```bash
# Let's Encrypt 사용
sudo certbot --nginx -d mcp.your-domain.com
```

클라이언트 설정:
```json
{
  "mcpServers": {
    "mobile-mcp": {
      "url": "https://mcp.your-domain.com/sse"
    }
  }
}
```

---

## 5. 헬스체크

```bash
# 서버 상태 확인
curl http://your-server:3000/health

# 응답
{"status": "ok", "server": "mobile-mcp"}
```

---

## 6. 트러블슈팅

### USB 디바이스 접근 권한 (Linux)

```bash
# udev 규칙 추가
sudo tee /etc/udev/rules.d/51-android.rules << 'EOF'
SUBSYSTEM=="usb", ATTR{idVendor}=="*", MODE="0666", GROUP="plugdev"
EOF

sudo udevadm control --reload-rules
sudo usermod -aG plugdev $USER
```

### ADB 서버 문제

```bash
# ADB 서버 재시작
adb kill-server
adb start-server

# 디바이스 확인
adb devices
```

### 연결 타임아웃

SSE 연결이 끊기는 경우 Nginx 설정 확인:

```nginx
proxy_read_timeout 86400;
proxy_send_timeout 86400;
keepalive_timeout 86400;
```
