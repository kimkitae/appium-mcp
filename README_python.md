# Mobile MCP (Python Version)

모바일 디바이스 제어를 위한 MCP(Model Context Protocol) 서버의 Python 구현입니다.

## 기능

- iOS 시뮬레이터, 물리적 iOS 디바이스, Android 디바이스 지원
- 스크린샷 캡처
- 화면 요소 탐색 및 상호작용
- 앱 실행 및 종료
- 텍스트 입력 및 스와이프 제스처
- 한글 등 유니코드 문자 입력 지원
- 화면 방향 제어

## 설치

### 요구사항

- Python 3.8 이상
- iOS 지원을 위한 macOS (선택사항)
- Android 지원을 위한 Android SDK (선택사항)

### 패키지 설치

```bash
pip install -r requirements.txt
```

또는 개발 모드로 설치:

```bash
pip install -e .
```

## 사용법

### 서버 실행

```bash
python -m src.main
```

또는 설치 후:

```bash
mobile-mcp
```

### MCP 클라이언트와 연동

MCP 클라이언트 설정에서 다음과 같이 추가:

```json
{
  "mcpServers": {
    "mobile-mcp": {
      "command": "python",
      "args": ["-m", "src.main"]
    }
  }
}
```

## 개발

### 코드 포맷팅

```bash
black src/
isort src/
```

### 타입 체크

```bash
mypy src/
```

### 한글 키보드가 보이지 않을 때

디바이스에서 영어 키보드만 보인다면 설정에서 한국어 키보드를 추가해야 합니다.

- **Android:** `설정` → `시스템` → `언어 및 입력` → `가상 키보드` → `Gboard` → `언어` → `키보드 추가` 에서 **한국어**를 선택합니다.
- **iOS:** `설정` → `일반` → `키보드` → `키보드` → `새로운 키보드 추가`에서 **한국어**를 선택합니다.

## 라이선스

MIT License 
