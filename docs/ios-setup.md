# iOS 물리 디바이스 설정 가이드

이 문서는 iOS 물리 디바이스를 Mobile MCP와 연결하는 방법을 설명합니다.

## 사전 요구 사항

1. **macOS** (Xcode 필요)
2. **Node.js** (go-ios 설치용)
3. **Apple 개발자 계정** (무료 개인 계정 가능)
4. **iOS 디바이스** (개발자 모드 활성화 필요)

---

## 1. go-ios 설치

go-ios는 iOS 디바이스와 통신하기 위한 도구입니다.

```bash
# npm으로 설치
npm install -g go-ios

# 또는 brew로 설치
brew install go-ios

# 설치 확인
ios version
```

---

## 2. 디바이스 연결 및 확인

### 2.1 개발자 모드 활성화

iOS 16 이상에서는 개발자 모드를 활성화해야 합니다:

1. **설정** > **개인정보 보호 및 보안** > **개발자 모드**
2. 활성화 후 디바이스 재시작

### 2.2 디바이스 페어링

```bash
# 디바이스를 USB로 연결한 후
ios pair

# 디바이스에서 "이 컴퓨터를 신뢰하시겠습니까?" 팝업에서 "신뢰" 선택
```

### 2.3 디바이스 목록 확인

```bash
ios list
```

출력 예시:
```
00008110-001234567890ABCD  iPhone 15 Pro  iOS 17.4.1
```

UDID를 메모해 두세요 (예: `00008110-001234567890ABCD`)

---

## 3. 터널링 설정 (iOS 17+)

iOS 17 이상에서는 USB 터널링이 필요합니다.

```bash
# 터널 시작 (별도 터미널에서 실행, 계속 열어두기)
ios tunnel start --userspace

# 포트 포워딩 (별도 터미널에서 실행)
ios forward 8100 8100
```

> **참고**: iOS 16 이하에서는 터널링이 필요 없습니다.

---

## 4. WebDriverAgent 설치

WebDriverAgent(WDA)는 iOS 디바이스를 자동화하는 서버입니다.

### 4.1 저장소 클론

```bash
git clone --depth 1 https://github.com/appium/WebDriverAgent.git
cd WebDriverAgent
```

### 4.2 Xcode에서 설정

1. `WebDriverAgent.xcodeproj` 열기:
   ```bash
   open WebDriverAgent.xcodeproj
   ```

2. **Signing & Capabilities** 탭에서:
   - Team: 본인의 Apple ID 선택
   - Bundle Identifier: 고유한 이름으로 변경 (예: `com.yourname.WebDriverAgentRunner`)

3. WebDriverAgentRunner 타겟도 동일하게 설정

### 4.3 WDA 실행

```bash
# UDID를 실제 값으로 교체
xcodebuild -project WebDriverAgent.xcodeproj \
  -scheme WebDriverAgentRunner \
  -destination 'platform=iOS,id=00008110-001234567890ABCD' \
  test
```

성공 시 출력:
```
ServerURLHere->http://192.168.x.x:8100<-ServerURLHere
```

> **참고**: WDA는 계속 실행 상태로 두어야 합니다.

---

## 5. Mobile MCP 연결

### 5.1 Mobile MCP 실행

```bash
# 프로젝트 디렉토리에서
mobile-mcp
```

### 5.2 Claude에서 사용

```
# 디바이스 목록 확인
"연결된 디바이스 목록 보여줘"

# iOS 디바이스 선택
"iOS 디바이스 00008110-001234567890ABCD 선택해줘"

# 앱 실행
"Settings 앱 실행해줘"
```

---

## 6. 자동 시작 스크립트 (선택)

여러 터미널을 열어야 하는 번거로움을 줄이기 위한 스크립트:

```bash
#!/bin/bash
# start-ios-mcp.sh

UDID="00008110-001234567890ABCD"  # 실제 UDID로 변경

# 터널 시작 (백그라운드)
ios tunnel start --userspace &
TUNNEL_PID=$!

# 포트 포워딩 (백그라운드)
ios forward 8100 8100 &
FORWARD_PID=$!

# WDA 시작 (백그라운드)
cd ~/WebDriverAgent
xcodebuild -project WebDriverAgent.xcodeproj \
  -scheme WebDriverAgentRunner \
  -destination "platform=iOS,id=$UDID" \
  test &
WDA_PID=$!

# 5초 대기 후 Mobile MCP 시작
sleep 5
mobile-mcp

# 종료 시 정리
trap "kill $TUNNEL_PID $FORWARD_PID $WDA_PID" EXIT
```

---

## 트러블슈팅

### `ios list`에서 디바이스가 안 보임

1. USB 케이블 확인 (데이터 지원 케이블인지)
2. 개발자 모드 활성화 확인
3. 페어링 재시도: `ios pair`

### WDA 빌드 실패

1. Xcode 업데이트
2. Signing 설정 확인
3. Bundle Identifier 고유성 확인

### 연결 불안정

```bash
# 터널 재시작
pkill -f "ios tunnel"
ios tunnel start --userspace

# 포트 포워딩 재시작
pkill -f "ios forward"
ios forward 8100 8100
```

### 권한 오류

디바이스에서 "이 컴퓨터를 신뢰하시겠습니까?" 팝업을 놓쳤다면:
1. 디바이스에서 설정 > 일반 > 재설정 > 위치 및 개인정보 보호 재설정
2. USB 재연결 후 다시 신뢰

---

## 참고 자료

- [go-ios GitHub](https://github.com/danielpaulus/go-ios)
- [WebDriverAgent GitHub](https://github.com/appium/WebDriverAgent)
- [Mobile MCP Wiki](https://github.com/mobile-next/mobile-mcp/wiki/Getting-Started-with-iOS-Physical-Device)
