import asyncio
import os
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from typing import Optional as OptionalType
from .robot import (
    ActionableError,
    Button,
    InstalledApp,
    Orientation,
    Robot,
    ScreenElement,
    ScreenElementRect,
    ScreenSize,
    SwipeDirection,
)
from .uiautomator2_server import UiAutomator2Server, DEFAULT_HOST_PORT


@dataclass
class AndroidDevice:
    """Android 디바이스 정보"""

    device_id: str
    device_type: Literal["tv", "mobile"]


@dataclass
class UiAutomatorXmlNode:
    """UI Automator XML 노드"""

    node: Optional[List["UiAutomatorXmlNode"]] = None
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
    """Android 디바이스 제어 구현

    두 가지 모드를 지원합니다:
    1. ADB 모드 (기본): adb 명령어를 직접 사용
    2. Appium 모드: UiAutomator2 서버와 HTTP 통신 (더 빠르고 안정적)

    Appium 모드를 사용하려면:
    - UiAutomator2 서버 APK가 설치되어 있어야 함
    - use_appium=True로 초기화하거나 MOBILE_MCP_USE_APPIUM=1 환경변수 설정
    """

    # 기준 density (mdpi = 160dpi)
    BASE_DENSITY = 160

    def __init__(
        self,
        device_id: str,
        use_appium: OptionalType[bool] = None,
        appium_port: int = DEFAULT_HOST_PORT,
    ):
        self.device_id = device_id
        self._cached_scale: OptionalType[float] = None
        self._appium_port = appium_port

        # Appium 모드 결정
        if use_appium is None:
            use_appium = os.environ.get("MOBILE_MCP_USE_APPIUM", "").lower() in ("1", "true", "yes")
        self._use_appium = use_appium

        # UiAutomator2 서버 클라이언트 (지연 초기화)
        self._ua2_server: OptionalType[UiAutomator2Server] = None
        self._ua2_server_checked = False
        self._ua2_server_available = False

    async def _get_ua2_server(self) -> OptionalType[UiAutomator2Server]:
        """UiAutomator2 서버 클라이언트를 반환합니다. 사용 불가능하면 None을 반환합니다."""
        if not self._use_appium:
            return None

        if self._ua2_server_checked:
            return self._ua2_server if self._ua2_server_available else None

        self._ua2_server_checked = True

        # 서버 클라이언트 생성
        self._ua2_server = UiAutomator2Server(
            device_id=self.device_id,
            host_port=self._appium_port,
        )

        # 서버가 이미 실행 중인지 확인
        if await self._ua2_server.is_running():
            self._ua2_server_available = True
            return self._ua2_server

        # 서버 APK가 설치되어 있는지 확인
        if not self._ua2_server.is_server_installed():
            self._ua2_server_available = False
            return None

        # 서버 시작 시도
        try:
            self._ua2_server.start_server()
            if await self._ua2_server.wait_for_server(timeout=10):
                self._ua2_server_available = True
                return self._ua2_server
        except Exception:
            pass

        self._ua2_server_available = False
        return None

    def adb(self, *args: str) -> bytes:
        """ADB 명령을 실행합니다."""
        cmd = [get_adb_path(), "-s", self.device_id] + list(args)

        result = subprocess.run(cmd, capture_output=True, timeout=TIMEOUT, check=True)

        return result.stdout

    def get_system_features(self) -> List[str]:
        """시스템 기능 목록을 가져옵니다."""
        output = self.adb("shell", "pm", "list", "features").decode("utf-8")

        features = []
        for line in output.split("\n"):
            line = line.strip()
            if line.startswith("feature:"):
                features.append(line[len("feature:") :])

        return features

    def _get_density(self) -> int:
        """디바이스의 화면 density(dpi)를 가져옵니다."""
        try:
            output = self.adb("shell", "wm", "density").decode("utf-8")
            # "Physical density: 420" 또는 "Override density: 420" 형식
            for line in output.strip().split('\n'):
                if 'density:' in line.lower():
                    parts = line.split(':')
                    if len(parts) >= 2:
                        return int(parts[-1].strip())
        except Exception:
            pass
        return self.BASE_DENSITY  # 기본값

    def _get_scale(self) -> float:
        """density 기반 scale 값을 계산합니다."""
        if self._cached_scale is None:
            density = self._get_density()
            # scale = density / 160 (160dpi = 1x, 320dpi = 2x, 480dpi = 3x)
            self._cached_scale = density / self.BASE_DENSITY
        return self._cached_scale

    async def get_screen_size(self) -> ScreenSize:
        """화면 크기를 가져옵니다. 논리적 크기와 scale을 반환합니다."""
        output = self.adb("shell", "wm", "size").decode("utf-8")

        # "Physical size: 1080x1920" 형식에서 크기 추출
        parts = output.split()
        if parts:
            screen_size = parts[-1]
            pixel_width, pixel_height = map(int, screen_size.split("x"))
            scale = self._get_scale()
            # 논리적 크기 반환 (픽셀 / scale)
            logical_width = int(pixel_width / scale)
            logical_height = int(pixel_height / scale)
            return ScreenSize(width=logical_width, height=logical_height, scale=scale)

        raise ValueError("화면 크기를 가져올 수 없습니다")

    async def list_apps(self) -> List[InstalledApp]:
        """설치된 앱 목록을 가져옵니다."""
        output = self.adb(
            "shell",
            "cmd",
            "package",
            "query-activities",
            "-a",
            "android.intent.action.MAIN",
            "-c",
            "android.intent.category.LAUNCHER",
        ).decode("utf-8")

        apps = []
        seen = set()

        for line in output.split("\n"):
            line = line.strip()
            if line.startswith("packageName="):
                package_name = line[len("packageName=") :]
                if package_name not in seen:
                    seen.add(package_name)
                    apps.append(InstalledApp(package_name=package_name, app_name=package_name))

        return apps

    async def launch_app(self, package_name: str) -> None:
        """앱을 실행합니다."""
        self.adb(
            "shell", "monkey", "-p", package_name, "-c", "android.intent.category.LAUNCHER", "1"
        )

    async def list_running_processes(self) -> List[str]:
        """실행 중인 프로세스 목록을 가져옵니다."""
        output = self.adb("shell", "ps", "-e").decode("utf-8")

        processes = []
        for line in output.split("\n"):
            line = line.strip()
            if line.startswith("u"):  # 비시스템 프로세스
                parts = line.split()
                if len(parts) > 8:
                    processes.append(parts[8])

        return processes

    async def swipe(self, direction: SwipeDirection) -> None:
        """스와이프합니다. 내부적으로 논리적 좌표를 픽셀로 변환합니다."""
        screen_size = await self.get_screen_size()
        scale = self._get_scale()
        center_x = screen_size.width // 2
        center_y = screen_size.height // 2

        if direction == "up":
            x0 = x1 = center_x
            y0 = int(screen_size.height * 0.80)
            y1 = int(screen_size.height * 0.20)
        elif direction == "down":
            x0 = x1 = center_x
            y0 = int(screen_size.height * 0.20)
            y1 = int(screen_size.height * 0.80)
        elif direction == "left":
            y0 = y1 = center_y
            x0 = int(screen_size.width * 0.80)
            x1 = int(screen_size.width * 0.20)
        elif direction == "right":
            y0 = y1 = center_y
            x0 = int(screen_size.width * 0.20)
            x1 = int(screen_size.width * 0.80)
        else:
            raise ActionableError(f'스와이프 방향 "{direction}"은 지원되지 않습니다')

        # 논리적 좌표를 픽셀 좌표로 변환
        px0, py0 = int(x0 * scale), int(y0 * scale)
        px1, py1 = int(x1 * scale), int(y1 * scale)
        self.adb("shell", "input", "swipe", str(px0), str(py0), str(px1), str(py1), "1000")

    async def swipe_between_points(self, start_x: int, start_y: int, end_x: int, end_y: int) -> None:
        """지정된 좌표에서 다른 좌표까지 스와이프합니다. 좌표는 논리적(dp) 단위."""
        scale = self._get_scale()
        px0 = int(start_x * scale)
        py0 = int(start_y * scale)
        px1 = int(end_x * scale)
        py1 = int(end_y * scale)
        self.adb(
            "shell",
            "input",
            "swipe",
            str(px0),
            str(py0),
            str(px1),
            str(py1),
            "1000",
        )

    async def swipe_from_coordinate(
        self, x: int, y: int, direction: SwipeDirection, distance: OptionalType[int] = None
    ) -> None:
        """지정된 좌표에서 특정 방향으로 스와이프합니다. 좌표는 논리적(dp) 단위."""
        screen_size = await self.get_screen_size()
        scale = self._get_scale()

        # 기본 거리: 화면 크기의 30%
        default_distance_y = int(screen_size.height * 0.3)
        default_distance_x = int(screen_size.width * 0.3)
        swipe_distance_y = distance if distance else default_distance_y
        swipe_distance_x = distance if distance else default_distance_x

        if direction == "up":
            x0 = x1 = x
            y0 = y
            y1 = max(0, y - swipe_distance_y)
        elif direction == "down":
            x0 = x1 = x
            y0 = y
            y1 = min(screen_size.height, y + swipe_distance_y)
        elif direction == "left":
            x0 = x
            x1 = max(0, x - swipe_distance_x)
            y0 = y1 = y
        elif direction == "right":
            x0 = x
            x1 = min(screen_size.width, x + swipe_distance_x)
            y0 = y1 = y
        else:
            raise ActionableError(f'스와이프 방향 "{direction}"은 지원되지 않습니다')

        # 논리적 좌표를 픽셀 좌표로 변환
        px0, py0 = int(x0 * scale), int(y0 * scale)
        px1, py1 = int(x1 * scale), int(y1 * scale)
        self.adb("shell", "input", "swipe", str(px0), str(py0), str(px1), str(py1), "1000")

    def _get_display_count(self) -> int:
        """디스플레이 수를 가져옵니다 (폴더블 디바이스 지원)."""
        try:
            output = self.adb("shell", "dumpsys", "SurfaceFlinger", "--display-id")
            if isinstance(output, bytes):
                output = output.decode("utf-8")
            # 각 줄이 하나의 디스플레이 ID
            lines = [line.strip() for line in output.strip().split('\n') if line.strip()]
            return len(lines)
        except Exception:
            return 1

    def _get_first_display_id(self) -> OptionalType[str]:
        """첫 번째 활성 디스플레이 ID를 가져옵니다."""
        # 방법 1: cmd display get-displays (Android 11+)
        try:
            output = self.adb("shell", "cmd", "display", "get-displays")
            if isinstance(output, bytes):
                output = output.decode("utf-8")

            for line in output.strip().split('\n'):
                if "state ON" in line:
                    # 예: "Display id=0, uniqueId=xxx, state ON, ..."
                    # uniqueId 추출
                    if "uniqueId=" in line:
                        parts = line.split("uniqueId=")
                        if len(parts) > 1:
                            unique_id = parts[1].split(",")[0].split()[0].strip()
                            return unique_id
        except Exception:
            pass

        # 방법 2: dumpsys display 파싱 (fallback)
        try:
            output = self.adb("shell", "dumpsys", "display")
            if isinstance(output, bytes):
                output = output.decode("utf-8")

            for line in output.strip().split('\n'):
                if "DisplayViewport" in line and "isActive=true" in line and "type=INTERNAL" in line:
                    # uniqueId 추출
                    if "uniqueId=" in line:
                        parts = line.split("uniqueId=")
                        if len(parts) > 1:
                            unique_id = parts[1].split(",")[0].split()[0].strip()
                            return unique_id
        except Exception:
            pass

        return None

    async def get_screenshot(self) -> bytes:
        """스크린샷을 가져옵니다.

        UiAutomator2 서버가 사용 가능하면 서버를 통해 가져옵니다.
        폴더블 디바이스의 경우 활성 디스플레이를 캡처합니다.
        """
        # UiAutomator2 서버 시도 (Appium 모드)
        ua2_server = await self._get_ua2_server()
        if ua2_server:
            try:
                return await ua2_server.get_screenshot()
            except Exception:
                # 서버 실패 시 adb 폴백
                pass

        # adb screencap 폴백
        display_count = self._get_display_count()

        if display_count > 1:
            display_id = self._get_first_display_id()
            if display_id:
                return self.adb("exec-out", "screencap", "-p", "-d", display_id)

        # 단일 디스플레이 또는 디스플레이 ID를 가져올 수 없는 경우
        return self.adb("exec-out", "screencap", "-p")

    def _collect_elements(self, node: ET.Element) -> List[ScreenElement]:
        """XML 노드에서 화면 요소를 수집합니다."""
        elements: List[ScreenElement] = []

        # 자식 노드 처리
        for child in node:
            elements.extend(self._collect_elements(child))

        # 현재 노드 처리
        text = node.get("text")
        content_desc = node.get("content-desc")
        hint = node.get("hint")

        if text or content_desc or hint:
            rect = self._get_screen_element_rect(node)

            if rect.width > 0 and rect.height > 0:
                element = ScreenElement(
                    type=node.get("class", "text"),
                    text=text,
                    label=content_desc or hint or "",
                    rect=rect,
                )

                if node.get("focused") == "true":
                    element.focused = True

                resource_id = node.get("resource-id")
                if resource_id:
                    element.identifier = resource_id

                elements.append(element)

        return elements

    async def get_elements_on_screen(self) -> List[ScreenElement]:
        """화면의 모든 요소를 가져옵니다.

        UiAutomator2 서버가 사용 가능하면 서버를 통해 가져옵니다 (더 빠름).
        그렇지 않으면 adb uiautomator dump를 사용합니다.
        """
        # UiAutomator2 서버 시도 (Appium 모드)
        ua2_server = await self._get_ua2_server()
        if ua2_server:
            try:
                return await ua2_server.get_elements_on_screen()
            except Exception:
                # 서버 실패 시 adb 폴백
                pass

        # adb uiautomator dump 폴백
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
        # 기본 입력 방식은 `adb shell input text` 명령을 사용합니다.
        # 이 방식은 ASCII 문자에만 제대로 동작하므로,
        # 비 ASCII 문자가 포함된 경우 Appium UnicodeIME를 이용해
        # 브로드캐스트 방식으로 입력을 전달합니다.

        def is_ascii(s: str) -> bool:
            try:
                s.encode("ascii")
                return True
            except UnicodeEncodeError:
                return False

        if is_ascii(text):
            escaped_text = text.replace(" ", "\\ ")
            self.adb("shell", "input", "text", escaped_text)
            return

        # UnicodeIME 사용을 위해 IME를 설정하고 브로드캐스트 전송
        try:
            self.adb("shell", "ime", "set", "io.appium.settings/.UnicodeIME")
        except Exception:
            # 설치되지 않았거나 이미 설정된 경우 무시합니다
            pass

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

    async def press_button(self, button: Button) -> None:
        """버튼을 누릅니다."""
        if button not in BUTTON_MAP:
            raise ActionableError(f'버튼 "{button}"은 지원되지 않습니다')

        self.adb("shell", "input", "keyevent", BUTTON_MAP[button])

    async def tap(self, x: int, y: int) -> None:
        """지정된 좌표를 탭합니다. 좌표는 논리적(dp) 단위."""
        scale = self._get_scale()
        px = int(x * scale)
        py = int(y * scale)
        self.adb("shell", "input", "tap", str(px), str(py))

    async def double_tap(self, x: int, y: int) -> None:
        """지정된 좌표를 더블탭합니다. 좌표는 논리적(dp) 단위."""
        scale = self._get_scale()
        px = int(x * scale)
        py = int(y * scale)
        # Android는 두 번 빠르게 탭으로 구현
        self.adb("shell", "input", "tap", str(px), str(py))
        self.adb("shell", "input", "tap", str(px), str(py))

    async def long_press(self, x: int, y: int, duration: OptionalType[int] = None) -> None:
        """지정된 좌표를 길게 누릅니다. 좌표는 논리적(dp) 단위."""
        scale = self._get_scale()
        px = int(x * scale)
        py = int(y * scale)
        # Android에서는 swipe를 같은 좌표로 하면 long press가 됨
        press_duration = duration if duration else 1000  # 기본 1초
        self.adb("shell", "input", "swipe", str(px), str(py), str(px), str(py), str(press_duration))

    async def install_app(self, path: str) -> None:
        """APK 파일을 설치합니다."""
        try:
            self.adb("install", "-r", path)
        except subprocess.CalledProcessError as e:
            raise ActionableError(f"앱 설치 실패: {e.stderr.decode() if e.stderr else str(e)}")

    async def uninstall_app(self, package_name: str) -> None:
        """앱을 삭제합니다."""
        try:
            self.adb("uninstall", package_name)
        except subprocess.CalledProcessError as e:
            raise ActionableError(f"앱 삭제 실패: {e.stderr.decode() if e.stderr else str(e)}")

    async def set_orientation(self, orientation: Orientation) -> None:
        """화면 방향을 설정합니다."""
        orientation_value = 0 if orientation == "portrait" else 1

        self.adb(
            "shell",
            "content",
            "insert",
            "--uri",
            "content://settings/system",
            "--bind",
            "name:s:user_rotation",
            "--bind",
            f"value:i:{orientation_value}",
        )
        self.adb("shell", "settings", "put", "system", "accelerometer_rotation", "0")

    async def get_orientation(self) -> Orientation:
        """현재 화면 방향을 가져옵니다."""
        rotation = (
            self.adb("shell", "settings", "get", "system", "user_rotation").decode("utf-8").strip()
        )
        return "portrait" if rotation == "0" else "landscape"

    async def hide_keyboard(self) -> bool:
        """키보드를 숨깁니다. BACK 버튼으로 키보드를 닫습니다."""
        # 키보드가 표시되어 있는지 확인
        dumpsys = self.adb("shell", "dumpsys", "input_method").decode("utf-8")
        if "mInputShown=true" in dumpsys:
            self.adb("shell", "input", "keyevent", "KEYCODE_BACK")
            return True
        return False

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
        """노드의 화면 위치를 가져옵니다. 좌표는 논리적(dp) 단위로 변환됩니다."""
        bounds = node.get("bounds", "")

        # "[left,top][right,bottom]" 형식 파싱
        import re

        match = re.match(r"^\[(\d+),(\d+)\]\[(\d+),(\d+)\]$", bounds)

        if match:
            left, top, right, bottom = map(int, match.groups())
            # 픽셀 좌표를 논리적 좌표로 변환
            scale = self._get_scale()
            return ScreenElementRect(
                x=int(left / scale),
                y=int(top / scale),
                width=int((right - left) / scale),
                height=int((bottom - top) / scale)
            )

        return ScreenElementRect(x=0, y=0, width=0, height=0)


class AndroidDeviceManager:
    """Android 디바이스 관리자"""

    def _get_device_type(self, device_id: str) -> AndroidDeviceType:
        """디바이스 타입을 판별합니다."""
        device = AndroidRobot(device_id)
        features = device.get_system_features()

        if (
            "android.software.leanback" in features
            or "android.hardware.type.television" in features
        ):
            return "tv"

        return "mobile"

    def get_connected_devices(self) -> List[AndroidDevice]:
        """연결된 디바이스 목록을 가져옵니다."""
        try:
            result = subprocess.run(
                [get_adb_path(), "devices"], capture_output=True, text=True, check=True
            )

            devices = []
            for line in result.stdout.split("\n"):
                if line and not line.startswith("List of devices attached"):
                    parts = line.split("\t")
                    if parts and parts[0]:
                        device_id = parts[0]
                        devices.append(
                            AndroidDevice(
                                device_id=device_id, device_type=self._get_device_type(device_id)
                            )
                        )

            return devices

        except Exception as error:
            print("ADB 명령을 실행할 수 없습니다. ANDROID_HOME이 설정되지 않았을 수 있습니다.")
            return []
