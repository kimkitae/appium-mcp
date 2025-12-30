# Appium 모드 (UiAutomator2 서버)

Mobile MCP는 Android 디바이스 제어를 위해 두 가지 모드를 지원합니다:

## 모드 비교

| 항목 | ADB 모드 (기본) | Appium 모드 |
|------|----------------|-------------|
| 설정 | 없음 | UiAutomator2 APK 설치 필요 |
| 요소 가져오기 | ~500-2000ms | ~100-300ms |
| 스크린샷 | ~200-500ms | ~100-200ms |
| 안정성 | 가끔 실패 가능 | 매우 안정적 |
| 호환성 | 모든 Android | Android 5.0+ |

## Appium 모드 활성화

### 1. UiAutomator2 서버 APK 설치

UiAutomator2 서버 APK를 디바이스에 설치해야 합니다.

**방법 A: Appium 설치 후 자동 설치**
```bash
# Appium 설치
npm install -g appium

# UiAutomator2 드라이버 설치
appium driver install uiautomator2

# Appium으로 세션 생성 시 자동으로 APK가 설치됨
```

**방법 B: 직접 APK 빌드/설치**
```bash
# 저장소 클론
git clone https://github.com/appium/appium-uiautomator2-server.git
cd appium-uiautomator2-server

# 빌드
./gradlew clean assembleServerDebug assembleServerDebugAndroidTest

# APK 설치
adb install -r app/build/outputs/apk/server/debug/appium-uiautomator2-server-debug.apk
adb install -r app/build/outputs/apk/androidTest/server/debug/appium-uiautomator2-server-debug-androidTest.apk
```

**방법 C: 사전 빌드된 APK 다운로드**
```bash
# Appium npm 패키지에서 APK 추출
npm pack appium-uiautomator2-driver
tar -xzf appium-uiautomator2-driver-*.tgz
cd package

# APK 위치
# node_modules/appium-uiautomator2-server/apks/
```

### 2. 환경변수 설정

```bash
# Appium 모드 활성화
export MOBILE_MCP_USE_APPIUM=1

# Mobile MCP 실행
mobile-mcp
```

또는 코드에서 직접 설정:
```python
from src.android import AndroidRobot

robot = AndroidRobot(device_id="your-device-id", use_appium=True)
```

## 작동 원리

```
┌─────────────────┐     HTTP/REST      ┌─────────────────────┐
│  Mobile MCP     │ ◄─────────────────► │  UiAutomator2 Server │
│  (Python)       │    localhost:8200   │  (Android 디바이스)   │
└─────────────────┘                     └─────────────────────┘
        │                                        │
        │ adb forward tcp:8200 tcp:6790         │
        └────────────────────────────────────────┘
```

1. Mobile MCP가 ADB 포트 포워딩 설정 (8200 → 6790)
2. UiAutomator2 서버 시작 (`am instrument`)
3. HTTP REST API로 통신
4. 서버가 UIAutomator2 프레임워크를 통해 디바이스 제어

## API 엔드포인트 (참고)

UiAutomator2 서버는 W3C WebDriver 프로토콜을 구현합니다:

| 엔드포인트 | 설명 |
|-----------|------|
| `GET /status` | 서버 상태 확인 |
| `POST /session` | 세션 생성 |
| `DELETE /session/:id` | 세션 삭제 |
| `GET /session/:id/source` | 페이지 소스 (XML) |
| `GET /session/:id/screenshot` | 스크린샷 (Base64) |
| `POST /session/:id/element` | 요소 찾기 |
| `POST /session/:id/element/:id/click` | 요소 클릭 |
| `POST /session/:id/actions` | W3C Actions (tap, swipe 등) |

## 트러블슈팅

### 서버가 시작되지 않음

```bash
# 서버 상태 확인
adb shell pm list packages | grep uiautomator2

# 수동으로 서버 시작
adb shell am instrument -w io.appium.uiautomator2.server.test/androidx.test.runner.AndroidJUnitRunner

# 포트 포워딩 확인
adb forward --list
```

### 권한 문제

```bash
# 앱 권한 부여
adb shell pm grant io.appium.uiautomator2.server android.permission.SYSTEM_ALERT_WINDOW
adb shell pm grant io.appium.uiautomator2.server android.permission.ACCESS_FINE_LOCATION
```

### 서버 충돌

```bash
# 서버 강제 종료
adb shell am force-stop io.appium.uiautomator2.server

# 포트 포워딩 제거 후 재시도
adb forward --remove tcp:8200
```

## 성능 팁

1. **세션 재사용**: 세션을 유지하면 요청마다 새 세션을 생성하는 오버헤드를 줄일 수 있습니다.

2. **요소 캐싱**: 동일한 화면에서 여러 작업을 수행할 때 요소 목록을 캐싱하세요.

3. **XPath 대신 ID 사용**: 요소를 찾을 때 XPath보다 resource-id나 accessibility-id가 더 빠릅니다.

```python
# 느림: XPath
element = await server.find_element("xpath", "//android.widget.Button[@text='Login']")

# 빠름: ID
element = await server.find_element("id", "com.example:id/login_button")

# 빠름: Accessibility ID
element = await server.find_element("accessibility id", "Login Button")
```
