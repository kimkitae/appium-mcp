import json
import subprocess
import platform
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

from .webdriver_agent import WebDriverAgent
from typing import Optional as OptionalType
from .robot import (
    ActionableError, Button, InstalledApp, Robot, ScreenElement,
    ScreenSize, SwipeDirection, Orientation
)


@dataclass
class Simulator:
    """시뮬레이터 정보"""
    name: str
    uuid: str
    state: str


@dataclass
class AppInfo:
    """앱 정보"""
    application_type: str
    bundle: str
    cf_bundle_display_name: str
    cf_bundle_executable: str
    cf_bundle_identifier: str
    cf_bundle_name: str
    cf_bundle_version: str
    data_container: str
    path: str


TIMEOUT = 30
WDA_PORT = 8100
MAX_BUFFER_SIZE = 4 * 1024 * 1024  # 4MB


class ParseState(Enum):
    """파싱 상태"""
    LOOKING_FOR_APP = 1
    IN_APP = 2
    IN_PROPERTY = 3


class Simctl(Robot):
    """iPhone 시뮬레이터 제어 구현"""
    
    def __init__(self, simulator_uuid: str):
        self.simulator_uuid = simulator_uuid
    
    async def _wda(self) -> WebDriverAgent:
        """WebDriverAgent 인스턴스를 반환합니다."""
        wda = WebDriverAgent("localhost", WDA_PORT)
        
        if not await wda.is_running():
            raise ActionableError(
                "WebDriverAgent가 시뮬레이터에서 실행되고 있지 않습니다. "
                "https://github.com/mobile-next/mobile-mcp/wiki/ 를 참조하세요."
            )
        
        return wda
    
    def _simctl(self, *args: str) -> bytes:
        """simctl 명령을 실행합니다."""
        cmd = ["xcrun", "simctl"] + list(args)
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=TIMEOUT,
            check=True
        )
        
        return result.stdout
    
    async def get_screenshot(self) -> bytes:
        """스크린샷을 가져옵니다."""
        return self._simctl("io", self.simulator_uuid, "screenshot", "-")
    
    async def open_url(self, url: str) -> None:
        """URL을 엽니다."""
        wda = await self._wda()
        await wda.open_url(url)
        # 대안: self._simctl("openurl", self.simulator_uuid, url)
    
    async def launch_app(self, package_name: str) -> None:
        """앱을 실행합니다."""
        self._simctl("launch", self.simulator_uuid, package_name)
    
    async def terminate_app(self, package_name: str) -> None:
        """앱을 종료합니다."""
        self._simctl("terminate", self.simulator_uuid, package_name)
    
    @staticmethod
    def parse_ios_app_data(input_text: str) -> List[AppInfo]:
        """iOS 앱 데이터를 파싱합니다."""
        result: List[AppInfo] = []
        
        state = ParseState.LOOKING_FOR_APP
        current_app: Dict[str, Any] = {}
        app_identifier = ""
        
        lines = input_text.split("\n")
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if state == ParseState.LOOKING_FOR_APP:
                # 앱 식별자 패턴 찾기: "com.example.app" = {
                import re
                app_match = re.match(r'^"?([^"=]+)"?\s*=\s*\{', line)
                if app_match:
                    app_identifier = app_match.group(1).strip()
                    current_app = {"CFBundleIdentifier": app_identifier}
                    state = ParseState.IN_APP
            
            elif state == ParseState.IN_APP:
                if line == "};":
                    # 앱 정보 완성
                    if all(key in current_app for key in [
                        "CFBundleIdentifier", "CFBundleDisplayName"
                    ]):
                        result.append(AppInfo(
                            application_type=current_app.get("ApplicationType", ""),
                            bundle=current_app.get("Bundle", ""),
                            cf_bundle_display_name=current_app.get("CFBundleDisplayName", ""),
                            cf_bundle_executable=current_app.get("CFBundleExecutable", ""),
                            cf_bundle_identifier=current_app.get("CFBundleIdentifier", ""),
                            cf_bundle_name=current_app.get("CFBundleName", ""),
                            cf_bundle_version=current_app.get("CFBundleVersion", ""),
                            data_container=current_app.get("DataContainer", ""),
                            path=current_app.get("Path", "")
                        ))
                    current_app = {}
                    state = ParseState.LOOKING_FOR_APP
                else:
                    # 속성 찾기: PropertyName = Value;
                    import re
                    property_match = re.match(r'^([^=]+)\s*=\s*(.+?);\s*$', line)
                    if property_match:
                        prop_name = property_match.group(1).strip()
                        prop_value = property_match.group(2).strip()
                        
                        # 따옴표 제거
                        if prop_value.startswith('"') and prop_value.endswith('"'):
                            prop_value = prop_value[1:-1]
                        
                        current_app[prop_name] = prop_value
                    elif line.endswith("{"):
                        # 중첩된 속성
                        state = ParseState.IN_PROPERTY
            
            elif state == ParseState.IN_PROPERTY:
                if line == "};":
                    # 중첩된 속성 끝
                    state = ParseState.IN_APP
                # 중첩된 속성 내용은 건너뛰기
        
        return result
    
    async def list_apps(self) -> List[InstalledApp]:
        """설치된 앱 목록을 가져옵니다."""
        text = self._simctl("listapps", self.simulator_uuid).decode('utf-8')
        apps = self.parse_ios_app_data(text)
        
        return [
            InstalledApp(
                package_name=app.cf_bundle_identifier,
                app_name=app.cf_bundle_display_name
            )
            for app in apps
        ]
    
    async def get_screen_size(self) -> ScreenSize:
        """화면 크기를 가져옵니다."""
        wda = await self._wda()
        return await wda.get_screen_size()
    
    async def send_keys(self, text: str) -> None:
        """키 입력을 전송합니다."""
        wda = await self._wda()
        await wda.send_keys(text)
    
    async def swipe(self, direction: SwipeDirection) -> None:
        """스와이프합니다."""
        wda = await self._wda()
        await wda.swipe(direction)

    async def swipe_between_points(
        self, start_x: int, start_y: int, end_x: int, end_y: int
    ) -> None:
        """지정된 좌표에서 다른 좌표까지 스와이프합니다."""
        wda = await self._wda()
        await wda.swipe_between_points(start_x, start_y, end_x, end_y)

    async def swipe_from_coordinate(
        self, x: int, y: int, direction: SwipeDirection, distance: OptionalType[int] = None
    ) -> None:
        """지정된 좌표에서 특정 방향으로 스와이프합니다."""
        wda = await self._wda()
        await wda.swipe_from_coordinate(x, y, direction, distance)

    async def tap(self, x: int, y: int) -> None:
        """지정된 좌표를 탭합니다."""
        wda = await self._wda()
        await wda.tap(x, y)
    
    async def press_button(self, button: Button) -> None:
        """버튼을 누릅니다."""
        wda = await self._wda()
        await wda.press_button(button)
    
    async def get_elements_on_screen(self) -> List[ScreenElement]:
        """화면의 모든 요소를 가져옵니다."""
        wda = await self._wda()
        return await wda.get_elements_on_screen()
    
    async def set_orientation(self, orientation: Orientation) -> None:
        """화면 방향을 설정합니다."""
        wda = await self._wda()
        await wda.set_orientation(orientation)
    
    async def get_orientation(self) -> Orientation:
        """현재 화면 방향을 가져옵니다."""
        wda = await self._wda()
        return await wda.get_orientation()

    async def hide_keyboard(self) -> bool:
        """키보드를 숨깁니다."""
        wda = await self._wda()
        return await wda.hide_keyboard()

    async def clear_text_field(self) -> None:
        """현재 포커스된 텍스트 필드의 내용을 모두 삭제합니다."""
        wda = await self._wda()
        await wda.clear_text_field()


class SimctlManager:
    """시뮬레이터 관리자"""
    
    def list_simulators(self) -> List[Simulator]:
        """시뮬레이터 목록을 가져옵니다."""
        # macOS가 아니면 빈 목록 반환
        if platform.system() != "Darwin":
            return []
        
        try:
            result = subprocess.run(
                ["xcrun", "simctl", "list", "devices", "-j"],
                capture_output=True,
                text=True,
                check=True
            )
            
            data = json.loads(result.stdout)
            simulators = []
            
            for runtime, devices in data.get("devices", {}).items():
                for device in devices:
                    simulators.append(Simulator(
                        name=device["name"],
                        uuid=device["udid"],
                        state=device["state"]
                    ))
            
            return simulators
            
        except Exception as error:
            print(f"시뮬레이터 목록 조회 오류: {error}")
            return []
    
    def list_booted_simulators(self) -> List[Simulator]:
        """부팅된 시뮬레이터 목록을 가져옵니다."""
        return [
            sim for sim in self.list_simulators()
            if sim.state == "Booted"
        ]
    
    def get_simulator(self, uuid: str) -> Simctl:
        """시뮬레이터 인스턴스를 가져옵니다."""
        return Simctl(uuid) 
