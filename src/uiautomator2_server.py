"""
UiAutomator2 Server Client for Android

Appium UiAutomator2 서버와 HTTP로 통신하여 Android 디바이스를 제어합니다.
기존 adb + uiautomator dump 방식보다 빠르고 안정적입니다.

기본 포트:
- 디바이스 포트: 6790
- 호스트 포트: 8200 (adb forward)

참고: https://github.com/appium/appium-uiautomator2-server
"""

import asyncio
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import aiohttp

from .robot import (
    ActionableError,
    Orientation,
    ScreenElement,
    ScreenElementRect,
    ScreenSize,
    SwipeDirection,
)


# UiAutomator2 서버 기본 설정
DEFAULT_DEVICE_PORT = 6790
DEFAULT_HOST_PORT = 8200


@dataclass
class UiAutomator2Element:
    """UiAutomator2 요소"""

    class_name: str
    text: Optional[str] = None
    content_desc: Optional[str] = None
    resource_id: Optional[str] = None
    package: Optional[str] = None
    bounds: Optional[Dict[str, int]] = None
    clickable: bool = False
    enabled: bool = True
    focused: bool = False
    scrollable: bool = False
    children: Optional[List["UiAutomator2Element"]] = None


def get_adb_path() -> str:
    """ADB 실행 파일 경로를 반환합니다."""
    executable = "adb"
    android_home = os.environ.get("ANDROID_HOME")

    if android_home:
        executable = os.path.join(android_home, "platform-tools", "adb")

    return executable


class UiAutomator2Server:
    """UiAutomator2 서버 클라이언트

    Appium UiAutomator2 서버에 HTTP 요청을 보내 Android 디바이스를 제어합니다.
    """

    # 클래스 레벨 커넥터 (connection pool 재사용)
    _connector: Optional[aiohttp.TCPConnector] = None

    # APK 패키지명
    SERVER_PACKAGE = "io.appium.uiautomator2.server"
    SERVER_TEST_PACKAGE = "io.appium.uiautomator2.server.test"

    def __init__(
        self,
        device_id: str,
        host: str = "localhost",
        host_port: int = DEFAULT_HOST_PORT,
        device_port: int = DEFAULT_DEVICE_PORT,
    ):
        self.device_id = device_id
        self.host = host
        self.host_port = host_port
        self.device_port = device_port
        self.base_url = f"http://{host}:{host_port}"
        self._session_id: Optional[str] = None
        self._server_process: Optional[subprocess.Popen] = None

    @classmethod
    def _get_connector(cls) -> aiohttp.TCPConnector:
        """재사용 가능한 TCP 커넥터를 반환합니다."""
        if cls._connector is None or cls._connector.closed:
            cls._connector = aiohttp.TCPConnector(
                limit=10,
                ttl_dns_cache=300,
                keepalive_timeout=30,
            )
        return cls._connector

    def _create_session(self) -> aiohttp.ClientSession:
        """재사용 가능한 커넥터를 사용하는 세션을 생성합니다."""
        timeout = aiohttp.ClientTimeout(total=30)
        return aiohttp.ClientSession(
            connector=self._get_connector(),
            connector_owner=False,
            timeout=timeout,
        )

    def _adb(self, *args: str) -> bytes:
        """ADB 명령을 실행합니다."""
        cmd = [get_adb_path(), "-s", self.device_id] + list(args)
        result = subprocess.run(cmd, capture_output=True, timeout=30, check=True)
        return result.stdout

    def is_server_installed(self) -> bool:
        """UiAutomator2 서버 APK가 설치되어 있는지 확인합니다."""
        try:
            output = self._adb("shell", "pm", "list", "packages", self.SERVER_PACKAGE)
            return self.SERVER_PACKAGE in output.decode("utf-8")
        except Exception:
            return False

    def setup_port_forward(self) -> None:
        """ADB 포트 포워딩을 설정합니다."""
        try:
            self._adb("forward", f"tcp:{self.host_port}", f"tcp:{self.device_port}")
        except subprocess.CalledProcessError as e:
            raise ActionableError(f"포트 포워딩 실패: {e}")

    def remove_port_forward(self) -> None:
        """ADB 포트 포워딩을 제거합니다."""
        try:
            self._adb("forward", "--remove", f"tcp:{self.host_port}")
        except Exception:
            pass

    def start_server(self) -> None:
        """UiAutomator2 서버를 시작합니다."""
        # 이미 실행 중인지 확인
        if self._server_process is not None:
            return

        # 포트 포워딩 설정
        self.setup_port_forward()

        # 서버 시작 (백그라운드)
        cmd = [
            get_adb_path(), "-s", self.device_id,
            "shell", "am", "instrument", "-w",
            f"{self.SERVER_TEST_PACKAGE}/androidx.test.runner.AndroidJUnitRunner"
        ]

        self._server_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def stop_server(self) -> None:
        """UiAutomator2 서버를 중지합니다."""
        if self._server_process is not None:
            self._server_process.terminate()
            self._server_process = None

        # 포트 포워딩 제거
        self.remove_port_forward()

        # 서버 프로세스 강제 종료
        try:
            self._adb("shell", "am", "force-stop", self.SERVER_PACKAGE)
        except Exception:
            pass

    async def is_running(self) -> bool:
        """서버가 실행 중인지 확인합니다."""
        url = f"{self.base_url}/status"
        try:
            async with self._create_session() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    return response.status == 200
        except Exception:
            return False

    async def wait_for_server(self, timeout: int = 30) -> bool:
        """서버가 준비될 때까지 대기합니다."""
        for _ in range(timeout):
            if await self.is_running():
                return True
            await asyncio.sleep(1)
        return False

    async def create_session(self) -> str:
        """새 세션을 생성합니다."""
        url = f"{self.base_url}/session"

        async with self._create_session() as session:
            async with session.post(
                url,
                json={"capabilities": {"alwaysMatch": {"platformName": "Android"}}}
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ActionableError(f"세션 생성 실패: {error_text}")
                data = await response.json()
                self._session_id = data.get("sessionId") or data.get("value", {}).get("sessionId")
                return self._session_id

    async def delete_session(self) -> None:
        """현재 세션을 삭제합니다."""
        if not self._session_id:
            return

        url = f"{self.base_url}/session/{self._session_id}"

        try:
            async with self._create_session() as session:
                await session.delete(url)
        except Exception:
            pass
        finally:
            self._session_id = None

    async def ensure_session(self) -> str:
        """세션이 있으면 반환하고, 없으면 생성합니다."""
        if self._session_id:
            return self._session_id
        return await self.create_session()

    async def get_page_source(self) -> str:
        """페이지 소스(XML)를 가져옵니다."""
        session_id = await self.ensure_session()
        url = f"{self.base_url}/session/{session_id}/source"

        async with self._create_session() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ActionableError(f"페이지 소스 가져오기 실패: {error_text}")
                data = await response.json()
                return data.get("value", "")

    async def get_screen_size(self) -> ScreenSize:
        """화면 크기를 가져옵니다."""
        session_id = await self.ensure_session()
        url = f"{self.base_url}/session/{session_id}/window/current/size"

        async with self._create_session() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ActionableError(f"화면 크기 가져오기 실패: {error_text}")
                data = await response.json()
                value = data.get("value", {})
                return ScreenSize(
                    width=value.get("width", 0),
                    height=value.get("height", 0),
                    scale=1.0,  # UiAutomator2는 논리적 좌표 반환
                )

    async def get_screenshot(self) -> bytes:
        """스크린샷을 가져옵니다."""
        session_id = await self.ensure_session()
        url = f"{self.base_url}/session/{session_id}/screenshot"

        async with self._create_session() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ActionableError(f"스크린샷 가져오기 실패: {error_text}")
                data = await response.json()
                import base64
                return base64.b64decode(data.get("value", ""))

    async def tap(self, x: int, y: int) -> None:
        """지정된 좌표를 탭합니다."""
        session_id = await self.ensure_session()
        url = f"{self.base_url}/session/{session_id}/actions"

        actions = {
            "actions": [
                {
                    "type": "pointer",
                    "id": "finger1",
                    "parameters": {"pointerType": "touch"},
                    "actions": [
                        {"type": "pointerMove", "duration": 0, "x": x, "y": y},
                        {"type": "pointerDown", "button": 0},
                        {"type": "pause", "duration": 100},
                        {"type": "pointerUp", "button": 0},
                    ],
                }
            ]
        }

        async with self._create_session() as session:
            async with session.post(url, json=actions) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ActionableError(f"탭 실패: {error_text}")

    async def double_tap(self, x: int, y: int) -> None:
        """지정된 좌표를 더블탭합니다."""
        session_id = await self.ensure_session()
        url = f"{self.base_url}/session/{session_id}/actions"

        actions = {
            "actions": [
                {
                    "type": "pointer",
                    "id": "finger1",
                    "parameters": {"pointerType": "touch"},
                    "actions": [
                        {"type": "pointerMove", "duration": 0, "x": x, "y": y},
                        {"type": "pointerDown", "button": 0},
                        {"type": "pause", "duration": 50},
                        {"type": "pointerUp", "button": 0},
                        {"type": "pause", "duration": 100},
                        {"type": "pointerDown", "button": 0},
                        {"type": "pause", "duration": 50},
                        {"type": "pointerUp", "button": 0},
                    ],
                }
            ]
        }

        async with self._create_session() as session:
            async with session.post(url, json=actions) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ActionableError(f"더블탭 실패: {error_text}")

    async def long_press(self, x: int, y: int, duration: Optional[int] = None) -> None:
        """지정된 좌표를 길게 누릅니다."""
        session_id = await self.ensure_session()
        url = f"{self.base_url}/session/{session_id}/actions"
        press_duration = duration if duration else 1000

        actions = {
            "actions": [
                {
                    "type": "pointer",
                    "id": "finger1",
                    "parameters": {"pointerType": "touch"},
                    "actions": [
                        {"type": "pointerMove", "duration": 0, "x": x, "y": y},
                        {"type": "pointerDown", "button": 0},
                        {"type": "pause", "duration": press_duration},
                        {"type": "pointerUp", "button": 0},
                    ],
                }
            ]
        }

        async with self._create_session() as session:
            async with session.post(url, json=actions) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ActionableError(f"롱프레스 실패: {error_text}")

    async def swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration: int = 1000,
    ) -> None:
        """스와이프합니다."""
        session_id = await self.ensure_session()
        url = f"{self.base_url}/session/{session_id}/actions"

        actions = {
            "actions": [
                {
                    "type": "pointer",
                    "id": "finger1",
                    "parameters": {"pointerType": "touch"},
                    "actions": [
                        {"type": "pointerMove", "duration": 0, "x": start_x, "y": start_y},
                        {"type": "pointerDown", "button": 0},
                        {"type": "pointerMove", "duration": duration, "x": end_x, "y": end_y},
                        {"type": "pointerUp", "button": 0},
                    ],
                }
            ]
        }

        async with self._create_session() as session:
            async with session.post(url, json=actions) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ActionableError(f"스와이프 실패: {error_text}")

    async def send_keys(self, text: str) -> None:
        """키 입력을 전송합니다."""
        session_id = await self.ensure_session()
        url = f"{self.base_url}/session/{session_id}/keys"

        async with self._create_session() as session:
            async with session.post(url, json={"value": list(text)}) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ActionableError(f"키 입력 실패: {error_text}")

    async def press_keycode(self, keycode: int) -> None:
        """키코드를 누릅니다."""
        session_id = await self.ensure_session()
        url = f"{self.base_url}/session/{session_id}/appium/device/press_keycode"

        async with self._create_session() as session:
            async with session.post(url, json={"keycode": keycode}) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ActionableError(f"키코드 입력 실패: {error_text}")

    async def back(self) -> None:
        """뒤로 가기"""
        session_id = await self.ensure_session()
        url = f"{self.base_url}/session/{session_id}/back"

        async with self._create_session() as session:
            await session.post(url, json={})

    async def get_orientation(self) -> Orientation:
        """화면 방향을 가져옵니다."""
        session_id = await self.ensure_session()
        url = f"{self.base_url}/session/{session_id}/orientation"

        async with self._create_session() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ActionableError(f"방향 가져오기 실패: {error_text}")
                data = await response.json()
                value = data.get("value", "PORTRAIT").lower()
                return "portrait" if value == "portrait" else "landscape"

    async def set_orientation(self, orientation: Orientation) -> None:
        """화면 방향을 설정합니다."""
        session_id = await self.ensure_session()
        url = f"{self.base_url}/session/{session_id}/orientation"

        async with self._create_session() as session:
            async with session.post(url, json={"orientation": orientation.upper()}) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ActionableError(f"방향 설정 실패: {error_text}")

    def _parse_xml_elements(self, xml_str: str) -> List[ScreenElement]:
        """XML 페이지 소스에서 요소를 파싱합니다."""
        import xml.etree.ElementTree as ET

        elements: List[ScreenElement] = []

        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError:
            return elements

        def parse_node(node: ET.Element) -> None:
            text = node.get("text")
            content_desc = node.get("content-desc")
            resource_id = node.get("resource-id")

            if text or content_desc:
                bounds = node.get("bounds", "")
                match = re.match(r"^\[(\d+),(\d+)\]\[(\d+),(\d+)\]$", bounds)

                if match:
                    left, top, right, bottom = map(int, match.groups())

                    element = ScreenElement(
                        type=node.get("class", "text"),
                        text=text,
                        label=content_desc or "",
                        rect=ScreenElementRect(
                            x=left,
                            y=top,
                            width=right - left,
                            height=bottom - top,
                        ),
                    )

                    if node.get("focused") == "true":
                        element.focused = True

                    if resource_id:
                        element.identifier = resource_id

                    elements.append(element)

            for child in node:
                parse_node(child)

        parse_node(root)
        return elements

    async def get_elements_on_screen(self) -> List[ScreenElement]:
        """화면의 모든 요소를 가져옵니다."""
        xml_source = await self.get_page_source()
        return self._parse_xml_elements(xml_source)

    async def find_element(self, strategy: str, selector: str) -> Optional[str]:
        """요소를 찾습니다. element ID를 반환합니다."""
        session_id = await self.ensure_session()
        url = f"{self.base_url}/session/{session_id}/element"

        async with self._create_session() as session:
            async with session.post(
                url,
                json={"using": strategy, "value": selector}
            ) as response:
                if response.status != 200:
                    return None
                data = await response.json()
                value = data.get("value", {})
                # W3C 형식: {"element-6066-11e4-a52e-4f735466cecf": "xxx"}
                for key in value:
                    if "element" in key.lower():
                        return value[key]
                return value.get("ELEMENT")

    async def find_elements(self, strategy: str, selector: str) -> List[str]:
        """여러 요소를 찾습니다. element ID 목록을 반환합니다."""
        session_id = await self.ensure_session()
        url = f"{self.base_url}/session/{session_id}/elements"

        async with self._create_session() as session:
            async with session.post(
                url,
                json={"using": strategy, "value": selector}
            ) as response:
                if response.status != 200:
                    return []
                data = await response.json()
                values = data.get("value", [])

                element_ids = []
                for value in values:
                    for key in value:
                        if "element" in key.lower():
                            element_ids.append(value[key])
                            break
                    else:
                        if "ELEMENT" in value:
                            element_ids.append(value["ELEMENT"])

                return element_ids

    async def click_element(self, element_id: str) -> None:
        """요소를 클릭합니다."""
        session_id = await self.ensure_session()
        url = f"{self.base_url}/session/{session_id}/element/{element_id}/click"

        async with self._create_session() as session:
            async with session.post(url, json={}) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ActionableError(f"요소 클릭 실패: {error_text}")

    async def get_element_text(self, element_id: str) -> str:
        """요소의 텍스트를 가져옵니다."""
        session_id = await self.ensure_session()
        url = f"{self.base_url}/session/{session_id}/element/{element_id}/text"

        async with self._create_session() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return ""
                data = await response.json()
                return data.get("value", "")

    async def get_element_rect(self, element_id: str) -> ScreenElementRect:
        """요소의 위치/크기를 가져옵니다."""
        session_id = await self.ensure_session()
        url = f"{self.base_url}/session/{session_id}/element/{element_id}/rect"

        async with self._create_session() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return ScreenElementRect(x=0, y=0, width=0, height=0)
                data = await response.json()
                value = data.get("value", {})
                return ScreenElementRect(
                    x=int(value.get("x", 0)),
                    y=int(value.get("y", 0)),
                    width=int(value.get("width", 0)),
                    height=int(value.get("height", 0)),
                )
