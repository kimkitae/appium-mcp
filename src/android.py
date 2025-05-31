import os
import subprocess
from typing import List, Dict, Any, Optional, Literal
from dataclasses import dataclass
import xml.etree.ElementTree as ET

from .robot import (
    ActionableError, Button, InstalledApp, Robot, ScreenElement, 
    ScreenElementRect, ScreenSize, SwipeDirection, Orientation
)


@dataclass
class AndroidDevice:
    """Android 디바이스 정보"""
    device_id: str
    device_type: Literal["tv", "mobile"]


@dataclass
class UiAutomatorXmlNode:
    """UI Automator XML 노드"""
    node: Optional[List['UiAutomatorXmlNode']] = None
    class_name: Optional[str] = None
    text: Optional[str] = None
    bounds: Optional[str] = None
    hint: Optional[str] = None
    focused: Optional[str] = None
    content_desc: Optional[str] = None
    resource_id: Optional[str] = None


@dataclass
class UiAutomatorXml:
    """UI Automator XML 루트"""
    hierarchy: Dict[str, Any]


def get_adb_path() -> str:
    """ADB 실행 파일 경로를 반환합니다."""
    executable = "adb"
    android_home = os.environ.get("ANDROID_HOME")
    
    if android_home:
        executable = os.path.join(android_home, "platform-tools", "adb")
    
    return executable


BUTTON_MAP: Dict[Button, str] = {
    "BACK": "KEYCODE_BACK",
    "HOME": "KEYCODE_HOME",
    "VOLUME_UP": "KEYCODE_VOLUME_UP",
    "VOLUME_DOWN": "KEYCODE_VOLUME_DOWN",
    "ENTER": "KEYCODE_ENTER",
    "DPAD_CENTER": "KEYCODE_DPAD_CENTER",
    "DPAD_UP": "KEYCODE_DPAD_UP",
    "DPAD_DOWN": "KEYCODE_DPAD_DOWN",
    "DPAD_LEFT": "KEYCODE_DPAD_LEFT",
    "DPAD_RIGHT": "KEYCODE_DPAD_RIGHT",
}

TIMEOUT = 30
MAX_BUFFER_SIZE = 4 * 1024 * 1024  # 4MB

AndroidDeviceType = Literal["tv", "mobile"]


class AndroidRobot(Robot):
    """Android 디바이스 제어 구현"""
    
    def __init__(self, device_id: str):
        self.device_id = device_id
    
    def adb(self, *args: str) -> bytes:
        """ADB 명령을 실행합니다."""
        cmd = [get_adb_path(), "-s", self.device_id] + list(args)
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=TIMEOUT,
            check=True
        )
        
        return result.stdout
    
    def get_system_features(self) -> List[str]:
        """시스템 기능 목록을 가져옵니다."""
        output = self.adb("shell", "pm", "list", "features").decode('utf-8')
        
        features = []
        for line in output.split('\n'):
            line = line.strip()
            if line.startswith("feature:"):
                features.append(line[len("feature:"):])
        
        return features
    
    async def get_screen_size(self) -> ScreenSize:
        """화면 크기를 가져옵니다."""
        output = self.adb("shell", "wm", "size").decode('utf-8')
        
        # "Physical size: 1080x1920" 형식에서 크기 추출
        parts = output.split()
        if parts:
            screen_size = parts[-1]
            width, height = map(int, screen_size.split('x'))
            return ScreenSize(width=width, height=height, scale=1)
        
        raise ValueError("화면 크기를 가져올 수 없습니다")
    
    async def list_apps(self) -> List[InstalledApp]:
        """설치된 앱 목록을 가져옵니다."""
        output = self.adb(
            "shell", "cmd", "package", "query-activities",
            "-a", "android.intent.action.MAIN",
            "-c", "android.intent.category.LAUNCHER"
        ).decode('utf-8')
        
        apps = []
        seen = set()
        
        for line in output.split('\n'):
            line = line.strip()
            if line.startswith("packageName="):
                package_name = line[len("packageName="):]
                if package_name not in seen:
                    seen.add(package_name)
                    apps.append(InstalledApp(
                        package_name=package_name,
                        app_name=package_name
                    ))
        
        return apps
    
    async def launch_app(self, package_name: str) -> None:
        """앱을 실행합니다."""
        self.adb(
            "shell", "monkey", "-p", package_name,
            "-c", "android.intent.category.LAUNCHER", "1"
        )
    
    async def list_running_processes(self) -> List[str]:
        """실행 중인 프로세스 목록을 가져옵니다."""
        output = self.adb("shell", "ps", "-e").decode('utf-8')
        
        processes = []
        for line in output.split('\n'):
            line = line.strip()
            if line.startswith("u"):  # 비시스템 프로세스
                parts = line.split()
                if len(parts) > 8:
                    processes.append(parts[8])
        
        return processes
    
    async def swipe(self, direction: SwipeDirection) -> None:
        """스와이프합니다."""
        screen_size = await self.get_screen_size()
        center_x = screen_size.width // 2
        
        if direction == "up":
            x0 = x1 = center_x
            y0 = int(screen_size.height * 0.80)
            y1 = int(screen_size.height * 0.20)
        elif direction == "down":
            x0 = x1 = center_x
            y0 = int(screen_size.height * 0.20)
            y1 = int(screen_size.height * 0.80)
        else:
            raise ActionableError(f'스와이프 방향 "{direction}"은 지원되지 않습니다')
        
        self.adb("shell", "input", "swipe", str(x0), str(y0), str(x1), str(y1), "1000")
    
    async def get_screenshot(self) -> bytes:
        """스크린샷을 가져옵니다."""
        return self.adb("exec-out", "screencap", "-p")
    
    def _collect_elements(self, node: ET.Element) -> List[ScreenElement]:
        """XML 노드에서 화면 요소를 수집합니다."""
        elements: List[ScreenElement] = []
        
        # 자식 노드 처리
        for child in node:
            elements.extend(self._collect_elements(child))
        
        # 현재 노드 처리
        text = node.get('text')
        content_desc = node.get('content-desc')
        hint = node.get('hint')
        
        if text or content_desc or hint:
            rect = self._get_screen_element_rect(node)
            
            if rect.width > 0 and rect.height > 0:
                element = ScreenElement(
                    type=node.get('class', 'text'),
                    text=text,
                    label=content_desc or hint or "",
                    rect=rect
                )
                
                if node.get('focused') == 'true':
                    element.focused = True
                
                resource_id = node.get('resource-id')
                if resource_id:
                    element.identifier = resource_id
                
                elements.append(element)
        
        return elements
    
    async def get_elements_on_screen(self) -> List[ScreenElement]:
        """화면의 모든 요소를 가져옵니다."""
        xml_str = await self._get_ui_automator_dump()
        root = ET.fromstring(xml_str)
        
        return self._collect_elements(root)
    
    async def terminate_app(self, package_name: str) -> None:
        """앱을 종료합니다."""
        self.adb("shell", "am", "force-stop", package_name)
    
    async def open_url(self, url: str) -> None:
        """URL을 엽니다."""
        self.adb("shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url)
    
    async def send_keys(self, text: str) -> None:
        """키 입력을 전송합니다."""
        # 일부 디바이스에서 `adb shell input text` 명령은 비 ASCII 문자나 공백이
        # 포함된 경우 제대로 동작하지 않아 NullPointerException이 발생할 수
        # 있습니다. 보다 안정적으로 입력하기 위해 항상 Appium의 UnicodeIME와
        # 브로드캐스트 방식을 사용합니다.

        old_ime: Optional[str] = None

        # 현재 IME 저장 시도 (실패해도 무시)
        try:
            old_ime = (
                self.adb(
                    "shell",
                    "settings",
                    "get",
                    "secure",
                    "default_input_method",
                )
                .decode("utf-8")
                .strip()
            )
        except Exception:
            pass

        # Appium UnicodeIME 설정 시도 (실패해도 무시)
        try:
            self.adb("shell", "ime", "set", "io.appium.settings/.UnicodeIME")
        except Exception:
            pass

        # 브로드캐스트를 통해 텍스트 입력
        self.adb(
            "shell",
            "am",
            "broadcast",
            "-a",
            "ADB_INPUT_TEXT",
            "--es",
            "msg",
            text,
        )

        # 기존 IME로 복원 시도
        if old_ime and "io.appium.settings/.UnicodeIME" not in old_ime:
            try:
                self.adb("shell", "ime", "set", old_ime)
            except Exception:
                pass

    
    async def press_button(self, button: Button) -> None:
        """버튼을 누릅니다."""
        if button not in BUTTON_MAP:
            raise ActionableError(f'버튼 "{button}"은 지원되지 않습니다')
        
        self.adb("shell", "input", "keyevent", BUTTON_MAP[button])
    
    async def tap(self, x: int, y: int) -> None:
        """지정된 좌표를 탭합니다."""
        self.adb("shell", "input", "tap", str(x), str(y))
    
    async def set_orientation(self, orientation: Orientation) -> None:
        """화면 방향을 설정합니다."""
        orientation_value = 0 if orientation == "portrait" else 1
        
        self.adb(
            "shell", "content", "insert", "--uri", "content://settings/system",
            "--bind", "name:s:user_rotation", "--bind", f"value:i:{orientation_value}"
        )
        self.adb("shell", "settings", "put", "system", "accelerometer_rotation", "0")
    
    async def get_orientation(self) -> Orientation:
        """현재 화면 방향을 가져옵니다."""
        rotation = self.adb("shell", "settings", "get", "system", "user_rotation").decode('utf-8').strip()
        return "portrait" if rotation == "0" else "landscape"
    
    async def _get_ui_automator_dump(self) -> str:
        """UI Automator 덤프를 가져옵니다."""
        for _ in range(10):
            dump = self.adb("exec-out", "uiautomator", "dump", "/dev/tty").decode("utf-8")

            if "null root node returned by UiTestAutomationBridge" not in dump:
                # uiautomator prints a log line before the actual XML
                # e.g. "UI hierchary dumped to: /dev/tty". Trim anything before
                # the first XML tag to avoid XML parse errors.
                start = dump.find("<")
                if start != -1:
                    dump = dump[start:]
                    end = dump.rfind(">")
                    if end != -1:
                        dump = dump[: end + 1]
                return dump
        
        raise ActionableError("UI Automator XML을 가져올 수 없습니다")
    
    def _get_screen_element_rect(self, node: ET.Element) -> ScreenElementRect:
        """노드의 화면 위치를 가져옵니다."""
        bounds = node.get('bounds', '')
        
        # "[left,top][right,bottom]" 형식 파싱
        import re
        match = re.match(r'^\[(\d+),(\d+)\]\[(\d+),(\d+)\]$', bounds)
        
        if match:
            left, top, right, bottom = map(int, match.groups())
            return ScreenElementRect(
                x=left,
                y=top,
                width=right - left,
                height=bottom - top
            )
        
        return ScreenElementRect(x=0, y=0, width=0, height=0)


class AndroidDeviceManager:
    """Android 디바이스 관리자"""
    
    def _get_device_type(self, device_id: str) -> AndroidDeviceType:
        """디바이스 타입을 판별합니다."""
        device = AndroidRobot(device_id)
        features = device.get_system_features()
        
        if "android.software.leanback" in features or "android.hardware.type.television" in features:
            return "tv"
        
        return "mobile"
    
    def get_connected_devices(self) -> List[AndroidDevice]:
        """연결된 디바이스 목록을 가져옵니다."""
        try:
            result = subprocess.run(
                [get_adb_path(), "devices"],
                capture_output=True,
                text=True,
                check=True
            )
            
            devices = []
            for line in result.stdout.split('\n'):
                if line and not line.startswith("List of devices attached"):
                    parts = line.split('\t')
                    if parts and parts[0]:
                        device_id = parts[0]
                        devices.append(AndroidDevice(
                            device_id=device_id,
                            device_type=self._get_device_type(device_id)
                        ))
            
            return devices
            
        except Exception as error:
            print("ADB 명령을 실행할 수 없습니다. ANDROID_HOME이 설정되지 않았을 수 있습니다.")
            return [] 
