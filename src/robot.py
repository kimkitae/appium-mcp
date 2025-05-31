from typing import Protocol, Optional, List, Literal
from dataclasses import dataclass


@dataclass
class Dimensions:
    width: int
    height: int


@dataclass
class ScreenSize(Dimensions):
    scale: float


@dataclass
class InstalledApp:
    package_name: str
    app_name: str


SwipeDirection = Literal["up", "down", "left", "right"]

Button = Literal[
    "HOME", "BACK", "VOLUME_UP", "VOLUME_DOWN", "ENTER",
    "DPAD_CENTER", "DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT"
]


@dataclass
class ScreenElementRect:
    x: int
    y: int
    width: int
    height: int


@dataclass
class ScreenElement:
    type: str
    rect: ScreenElementRect
    label: Optional[str] = None
    text: Optional[str] = None
    name: Optional[str] = None
    value: Optional[str] = None
    identifier: Optional[str] = None
    focused: Optional[bool] = None


class ActionableError(Exception):
    """사용자가 조치 가능한 오류"""
    pass


Orientation = Literal["portrait", "landscape"]


class Robot(Protocol):
    """모바일 기기 제어를 위한 공통 인터페이스"""
    
    async def get_screen_size(self) -> ScreenSize:
        """기기의 화면 크기를 픽셀 단위로 가져옵니다."""
        ...
    
    async def swipe(self, direction: SwipeDirection) -> None:
        """지정된 방향으로 스와이프합니다."""
        ...
    
    async def get_screenshot(self) -> bytes:
        """화면의 스크린샷을 가져옵니다. PNG 이미지가 포함된 bytes를 반환합니다."""
        ...
    
    async def list_apps(self) -> List[InstalledApp]:
        """기기에 설치된 모든 앱을 나열합니다."""
        ...
    
    async def launch_app(self, package_name: str) -> None:
        """앱을 실행합니다."""
        ...
    
    async def terminate_app(self, package_name: str) -> None:
        """앱을 종료합니다. 이미 종료된 경우 아무 작업도 수행하지 않습니다."""
        ...
    
    async def open_url(self, url: str) -> None:
        """기기의 웹 브라우저에서 URL을 엽니다."""
        ...
    
    async def send_keys(self, text: str) -> None:
        """키보드 입력을 시뮬레이션하여 기기에 키를 전송합니다."""
        ...
    
    async def press_button(self, button: Button) -> None:
        """물리적 버튼 누름을 시뮬레이션합니다."""
        ...
    
    async def tap(self, x: int, y: int) -> None:
        """화면의 특정 좌표를 탭합니다."""
        ...
    
    async def get_elements_on_screen(self) -> List[ScreenElement]:
        """화면의 모든 요소를 가져옵니다. 네이티브 앱에서만 작동합니다."""
        ...
    
    async def set_orientation(self, orientation: Orientation) -> None:
        """기기의 화면 방향을 변경합니다."""
        ...
    
    async def get_orientation(self) -> Orientation:
        """현재 화면 방향을 가져옵니다."""
        ... 