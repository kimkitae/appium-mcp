import os
import json
import socket
import tempfile
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import secrets

from .webdriver_agent import WebDriverAgent
from typing import Optional as OptionalType
from .robot import (
    ActionableError, Button, InstalledApp, Robot, ScreenSize,
    SwipeDirection, ScreenElement, Orientation
)


WDA_PORT = 8100
IOS_TUNNEL_PORT = 60105


@dataclass
class IosDevice:
    """iOS 디바이스 정보"""
    device_id: str
    device_name: str


@dataclass
class ListCommandOutput:
    """list 명령 출력"""
    device_list: List[str]


@dataclass
class VersionCommandOutput:
    """version 명령 출력"""
    version: str


@dataclass
class InfoCommandOutput:
    """info 명령 출력"""
    device_class: str
    device_name: str
    product_name: str
    product_type: str
    product_version: str
    phone_number: str
    time_zone: str


def get_go_ios_path() -> str:
    """go-ios 실행 파일 경로를 반환합니다."""
    if go_ios_path := os.environ.get("GO_IOS_PATH"):
        return go_ios_path
    
    # PATH에서 go-ios 찾기 (npm install -g go-ios로 설치된 경우)
    return "ios"


class IosRobot(Robot):
    """iOS 디바이스 제어 구현"""
    
    def __init__(self, device_id: str):
        self.device_id = device_id
    
    async def _is_listening_on_port(self, port: int) -> bool:
        """특정 포트가 열려있는지 확인합니다."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            result = sock.connect_ex(('localhost', port))
            return result == 0
        finally:
            sock.close()
    
    async def _is_tunnel_running(self) -> bool:
        """iOS 터널이 실행 중인지 확인합니다."""
        return await self._is_listening_on_port(IOS_TUNNEL_PORT)
    
    async def _is_wda_forward_running(self) -> bool:
        """WDA 포트 포워딩이 실행 중인지 확인합니다."""
        return await self._is_listening_on_port(WDA_PORT)
    
    async def _assert_tunnel_running(self) -> None:
        """터널이 실행 중인지 확인하고 아니면 예외를 발생시킵니다."""
        if await self._is_tunnel_required():
            if not await self._is_tunnel_running():
                raise ActionableError(
                    "iOS 터널이 실행되고 있지 않습니다. "
                    "https://github.com/mobile-next/mobile-mcp/wiki/ 를 참조하세요."
                )
    
    async def _wda(self) -> WebDriverAgent:
        """WebDriverAgent 인스턴스를 반환합니다."""
        await self._assert_tunnel_running()
        
        if not await self._is_wda_forward_running():
            raise ActionableError(
                "WebDriverAgent 포트 포워딩이 실행되고 있지 않습니다 (터널은 정상). "
                "https://github.com/mobile-next/mobile-mcp/wiki/ 를 참조하세요."
            )
        
        wda = WebDriverAgent("localhost", WDA_PORT)
        
        if not await wda.is_running():
            raise ActionableError(
                "WebDriverAgent가 디바이스에서 실행되고 있지 않습니다 (터널 정상, 포트 포워딩 정상). "
                "https://github.com/mobile-next/mobile-mcp/wiki/ 를 참조하세요."
            )
        
        return wda
    
    async def _ios(self, *args: str) -> str:
        """go-ios 명령을 실행합니다."""
        cmd = [get_go_ios_path(), "--udid", self.device_id] + list(args)
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        return result.stdout
    
    async def get_ios_version(self) -> str:
        """iOS 버전을 가져옵니다."""
        output = await self._ios("info")
        data = json.loads(output)
        return data["ProductVersion"]
    
    async def _is_tunnel_required(self) -> bool:
        """터널이 필요한지 확인합니다."""
        version = await self.get_ios_version()
        major_version = int(version.split(".")[0])
        return major_version >= 17
    
    async def get_screen_size(self) -> ScreenSize:
        """화면 크기를 가져옵니다."""
        wda = await self._wda()
        return await wda.get_screen_size()
    
    async def swipe(self, direction: SwipeDirection) -> None:
        """스와이프합니다."""
        wda = await self._wda()
        await wda.swipe(direction)

    async def swipe_between_points(
        self, start_x: int, start_y: int, end_x: int, end_y: int
    ) -> None:
        """지정된 좌표에서 다른 좌표까지 스와이프합니다. 좌표는 포인트(논리적) 단위."""
        wda = await self._wda()
        await wda.swipe_between_points(start_x, start_y, end_x, end_y)

    async def swipe_from_coordinate(
        self, x: int, y: int, direction: SwipeDirection, distance: OptionalType[int] = None
    ) -> None:
        """지정된 좌표에서 특정 방향으로 스와이프합니다. 좌표는 포인트(논리적) 단위."""
        wda = await self._wda()
        await wda.swipe_from_coordinate(x, y, direction, distance)

    async def list_apps(self) -> List[InstalledApp]:
        """설치된 앱 목록을 가져옵니다."""
        await self._assert_tunnel_running()
        
        output = await self._ios("apps", "--all", "--list")
        apps = []
        
        for line in output.strip().split('\n'):
            if line:
                parts = line.split(' ', 1)
                if len(parts) >= 2:
                    package_name, app_name = parts
                    apps.append(InstalledApp(
                        package_name=package_name,
                        app_name=app_name
                    ))
        
        return apps
    
    async def launch_app(self, package_name: str) -> None:
        """앱을 실행합니다."""
        await self._assert_tunnel_running()
        await self._ios("launch", package_name)
    
    async def terminate_app(self, package_name: str) -> None:
        """앱을 종료합니다."""
        await self._assert_tunnel_running()
        await self._ios("kill", package_name)
    
    async def open_url(self, url: str) -> None:
        """URL을 엽니다."""
        wda = await self._wda()
        await wda.open_url(url)
    
    async def send_keys(self, text: str) -> None:
        """키 입력을 전송합니다."""
        wda = await self._wda()
        await wda.send_keys(text)
    
    async def press_button(self, button: Button) -> None:
        """버튼을 누릅니다."""
        wda = await self._wda()
        await wda.press_button(button)
    
    async def tap(self, x: int, y: int) -> None:
        """지정된 좌표를 탭합니다. 좌표는 포인트(논리적) 단위."""
        wda = await self._wda()
        await wda.tap(x, y)

    async def double_tap(self, x: int, y: int) -> None:
        """지정된 좌표를 더블탭합니다. 좌표는 포인트(논리적) 단위."""
        wda = await self._wda()
        await wda.double_tap(x, y)

    async def long_press(self, x: int, y: int, duration: OptionalType[int] = None) -> None:
        """지정된 좌표를 길게 누릅니다. 좌표는 포인트(논리적) 단위."""
        wda = await self._wda()
        await wda.long_press(x, y, duration)

    async def install_app(self, path: str) -> None:
        """IPA 파일을 설치합니다."""
        await self._assert_tunnel_running()
        try:
            await self._ios("install", "--path", path)
        except subprocess.CalledProcessError as e:
            stdout = e.stdout if e.stdout else ""
            stderr = e.stderr if e.stderr else ""
            output = (stdout + stderr).strip()
            raise ActionableError(output or str(e))

    async def uninstall_app(self, bundle_id: str) -> None:
        """앱을 삭제합니다."""
        await self._assert_tunnel_running()
        try:
            await self._ios("uninstall", "--bundleid", bundle_id)
        except subprocess.CalledProcessError as e:
            stdout = e.stdout if e.stdout else ""
            stderr = e.stderr if e.stderr else ""
            output = (stdout + stderr).strip()
            raise ActionableError(output or str(e))

    async def get_elements_on_screen(self) -> List[ScreenElement]:
        """화면의 모든 요소를 가져옵니다."""
        wda = await self._wda()
        return await wda.get_elements_on_screen()
    
    async def get_screenshot(self) -> bytes:
        """스크린샷을 가져옵니다."""
        await self._assert_tunnel_running()
        
        # 임시 파일 생성
        with tempfile.NamedTemporaryFile(
            suffix='.png', 
            prefix=f'screenshot-{secrets.token_hex(8)}-',
            delete=False
        ) as tmp_file:
            tmp_filename = tmp_file.name
        
        try:
            await self._ios("screenshot", "--output", tmp_filename)
            
            with open(tmp_filename, 'rb') as f:
                return f.read()
        finally:
            # 임시 파일 삭제
            Path(tmp_filename).unlink(missing_ok=True)
    
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


class IosManager:
    """iOS 디바이스 관리자"""
    
    async def is_go_ios_installed(self) -> bool:
        """go-ios가 설치되어 있는지 확인합니다."""
        try:
            result = subprocess.run(
                [get_go_ios_path(), "version"],
                capture_output=True,
                text=True,
                check=True
            )
            
            data = json.loads(result.stdout)
            version = data.get("version", "")
            return version and (version.startswith("v") or version == "local-build")
            
        except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
            return False
    
    async def get_device_name(self, device_id: str) -> str:
        """디바이스 이름을 가져옵니다."""
        result = subprocess.run(
            [get_go_ios_path(), "info", "--udid", device_id],
            capture_output=True,
            text=True,
            check=True
        )
        
        data = json.loads(result.stdout)
        return data["DeviceName"]
    
    async def list_devices(self) -> List[IosDevice]:
        """연결된 디바이스 목록을 가져옵니다."""
        if not await self.is_go_ios_installed():
            print("go-ios가 설치되어 있지 않습니다. 물리적 iOS 디바이스를 감지할 수 없습니다.")
            return []
        
        result = subprocess.run(
            [get_go_ios_path(), "list"],
            capture_output=True,
            text=True,
            check=True
        )
        
        data = json.loads(result.stdout)
        devices = []
        
        for device_id in data.get("deviceList", []):
            device_name = await self.get_device_name(device_id)
            devices.append(IosDevice(
                device_id=device_id,
                device_name=device_name
            ))
        
        return devices 
