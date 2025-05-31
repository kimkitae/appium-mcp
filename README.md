# Appium MCP (자동화 연결 버전)

Appium을 사용한 모바일 디바이스 자동화 제어를 위한 MCP (Model Context Protocol) 서버입니다.
**자동 연결 및 서버 관리 기능**이 포함되어 있어 간편하게 모바일 테스트 자동화를 시작할 수 있습니다.

## ✨ 주요 기능

- 🚀 **자동 Appium 서버 시작/중지**
- 📱 **디바이스 자동 검색 및 연결**
- 🔧 **설정 파일 기반 자동화**
- 📊 **연결 상태 실시간 모니터링**
- 🔄 **연결 재시작 및 복구**
- 📋 **사용 가능한 모든 디바이스 목록 조회**

## 🛠️ 사전 요구사항

### Android
```bash
# Android SDK 설치 (adb 포함)
brew install android-platform-tools  # macOS
# 또는 Android Studio 설치

# USB 디버깅 활성화 필요
```

### iOS
```bash
# libimobiledevice 설치
brew install libimobiledevice  # macOS

# 디바이스가 신뢰할 수 있는 컴퓨터로 설정되어야 함
```

### Appium
```bash
# Node.js 설치 후
npm install -g appium
npm install -g @appium/doctor

# 설치 확인
appium-doctor
```

## 📦 설치

```bash
# 의존성 설치
pip install -r requirements.txt

# 설정 파일 확인 (자동 생성됨)
cat config.json
```

## 🚀 빠른 시작

### 1. 자동화 연결 (권장)
```bash
# 원클릭 자동 설정 및 연결
python start_automation.py
```

### 2. MCP 서버 수동 시작
```bash
# MCP 서버 시작
python app.py
```

## 🔧 설정 파일 (config.json)

```json
{
    "appium": {
        "server_url": "http://localhost:4723",
        "auto_start": true,
        "timeout": 60
    },
    "android": {
        "auto_connect": true,
        "preferred_device": null,
        "default_app_package": "com.example.app",
        "default_app_activity": ".MainActivity"
    },
    "ios": {
        "auto_connect": true,
        "preferred_device": null,
        "default_bundle_id": "com.example.app"
    },
    "logging": {
        "level": "INFO",
        "enable_detailed_logs": false
    }
}
```

## 📱 사용 가능한 MCP 도구들

### 연결 관리
- `auto_setup()` - 자동 서버 시작 및 디바이스 연결
- `connect()` - 특정 디바이스에 수동 연결  
- `disconnect()` - 연결 해제
- `restart_connection()` - 연결 재시작

### 상태 확인
- `check_connection_status()` - 현재 연결 상태 확인
- `list_available_devices()` - 사용 가능한 디바이스 목록
- `current_device_info()` - 현재 연결된 디바이스 정보

### 디바이스 제어
- `screenshot()` - 스크린샷 캡처
- `click(by, value)` - 요소 클릭
- `swipe(start_x, start_y, end_x, end_y)` - 스와이프
- `long_press(by, value)` - 길게 누르기
- `is_displayed(by, value)` - 요소 표시 여부 확인
- `get_attribute(by, value, attribute)` - 요소 속성 가져오기
- `get_page_source()` - 페이지 소스 가져오기

## 💡 사용 예시

### 자동 연결 후 스크린샷
```python
# 1. 자동 설정
await auto_setup()

# 2. 스크린샷 캡처
screenshot_base64 = await screenshot()

# 3. 상태 확인
status = await check_connection_status()
```

### 특정 디바이스 연결
```python
# Android 특정 디바이스
await connect(
    platform="android",
    udid="your_device_serial",
    appPackage="com.example.app",
    appActivity=".MainActivity"
)

# iOS 특정 디바이스  
await connect(
    platform="ios",
    udid="your_device_udid",
    bundleId="com.example.app"
)
```

## 🔍 문제 해결

### 일반적인 문제들

1. **"adb 명령을 찾을 수 없습니다"**
   - Android SDK 설치 및 PATH 설정 확인

2. **"연결된 Android 장치가 없습니다"**
   - USB 디버깅 활성화 확인
   - `adb devices` 명령으로 디바이스 인식 확인

3. **"Appium 서버를 시작할 수 없습니다"**
   - `npm install -g appium` 설치 확인
   - 포트 4723 사용 중인지 확인

4. **"iOS 장치 연결 실패"**
   - libimobiledevice 설치 확인
   - 디바이스가 신뢰할 수 있는 컴퓨터로 설정되었는지 확인

### 로그 활성화
```json
{
    "logging": {
        "level": "DEBUG",
        "enable_detailed_logs": true
    }
}
```

## 📝 라이센스

이 프로젝트는 MIT 라이센스 하에 배포됩니다. 
