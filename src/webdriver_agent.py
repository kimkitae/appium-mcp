import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

import aiohttp

from .robot import (
    ActionableError,
    Orientation,
    ScreenElement,
    ScreenElementRect,
    ScreenSize,
    SwipeDirection,
)


@dataclass
class SourceTreeElementRect:
    """소스 트리 요소의 위치 정보"""

    x: int
    y: int
    width: int
    height: int


@dataclass
class SourceTreeElement:
    """소스 트리 요소"""

    type: str
    rect: SourceTreeElementRect
    label: Optional[str] = None
    name: Optional[str] = None
    value: Optional[str] = None
    raw_identifier: Optional[str] = None
    is_visible: Optional[str] = None  # "0" or "1"
    children: Optional[List["SourceTreeElement"]] = None


@dataclass
class SourceTree:
    """소스 트리 루트"""

    value: SourceTreeElement


class WebDriverAgent:
    """iOS WebDriverAgent 클라이언트"""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"

    async def is_running(self) -> bool:
        """WebDriverAgent가 실행 중인지 확인합니다."""
        url = f"{self.base_url}/status"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    return response.status == 200
        except Exception as error:
            print(f"WebDriverAgent 연결 실패: {error}")
            return False

    async def create_session(self) -> str:
        """새 세션을 생성하고 세션 ID를 반환합니다."""
        url = f"{self.base_url}/session"

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json={"capabilities": {"alwaysMatch": {"platformName": "iOS"}}}
            ) as response:
                data = await response.json()
                return data["value"]["sessionId"]

    async def delete_session(self, session_id: str) -> Dict[str, Any]:
        """세션을 삭제합니다."""
        url = f"{self.base_url}/session/{session_id}"

        async with aiohttp.ClientSession() as session:
            async with session.delete(url) as response:
                return await response.json()

    async def within_session(self, fn: Callable[[str], Awaitable[Any]]) -> Any:
        """세션 내에서 작업을 수행합니다."""
        session_id = await self.create_session()
        session_url = f"{self.base_url}/session/{session_id}"
        try:
            result = await fn(session_url)
            return result
        finally:
            await self.delete_session(session_id)

    async def get_screen_size(self) -> ScreenSize:
        """화면 크기를 가져옵니다."""

        async def _get_size(session_url: str) -> ScreenSize:
            url = f"{session_url}/wda/screen"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    data = await response.json()
                    value = data["value"]
                    return ScreenSize(
                        width=value["screenSize"]["width"],
                        height=value["screenSize"]["height"],
                        scale=value.get("scale", 1),
                    )

        return await self.within_session(_get_size)

    async def send_keys(self, keys: str) -> None:
        """키 입력을 전송합니다."""

        async def _send(session_url: str) -> None:
            url = f"{session_url}/wda/keys"
            async with aiohttp.ClientSession() as session:
                await session.post(url, json={"value": [keys]})

        await self.within_session(_send)

    async def press_button(self, button: str) -> None:
        """버튼을 누릅니다."""
        button_map = {
            "HOME": "home",
            "VOLUME_UP": "volumeup",
            "VOLUME_DOWN": "volumedown",
        }

        if button == "ENTER":
            await self.send_keys("\n")
            return

        if button not in button_map:
            raise ActionableError(f'버튼 "{button}"은 지원되지 않습니다')

        async def _press(session_url: str) -> Dict[str, Any]:
            url = f"{session_url}/wda/pressButton"
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json={"name": button_map[button]}) as response:
                    return await response.json()

        await self.within_session(_press)

    async def tap(self, x: int, y: int) -> None:
        """지정된 좌표를 탭합니다."""

        async def _tap(session_url: str) -> None:
            url = f"{session_url}/actions"
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

            async with aiohttp.ClientSession() as session:
                await session.post(url, json=actions)

        await self.within_session(_tap)

    def _is_visible(self, rect: SourceTreeElementRect) -> bool:
        """요소가 화면에 보이는지 확인합니다."""
        return rect.x >= 0 and rect.y >= 0

    def _filter_source_elements(self, source: SourceTreeElement) -> List[ScreenElement]:
        """소스 트리에서 화면 요소를 필터링합니다."""
        output: List[ScreenElement] = []

        accepted_types = [
            "TextField",
            "Button",
            "Switch",
            "Icon",
            "SearchField",
            "StaticText",
            "Image",
        ]

        if source.type in accepted_types:
            if source.is_visible == "1" and self._is_visible(source.rect):
                if source.label or source.name or source.raw_identifier:
                    output.append(
                        ScreenElement(
                            type=source.type,
                            label=source.label,
                            name=source.name,
                            value=source.value,
                            identifier=source.raw_identifier,
                            rect=ScreenElementRect(
                                x=source.rect.x,
                                y=source.rect.y,
                                width=source.rect.width,
                                height=source.rect.height,
                            ),
                        )
                    )

        if source.children:
            for child in source.children:
                output.extend(self._filter_source_elements(child))

        return output

    async def get_page_source(self) -> SourceTree:
        """페이지 소스를 가져옵니다."""
        url = f"{self.base_url}/source/?format=json"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                return self._parse_source_tree(data)

    def _parse_source_tree(self, data: Dict[str, Any]) -> SourceTree:
        """JSON 데이터를 SourceTree로 파싱합니다."""

        def parse_element(elem_data: Dict[str, Any]) -> SourceTreeElement:
            rect_data = elem_data.get("rect", {})
            rect = SourceTreeElementRect(
                x=rect_data.get("x", 0),
                y=rect_data.get("y", 0),
                width=rect_data.get("width", 0),
                height=rect_data.get("height", 0),
            )

            children = None
            if "children" in elem_data:
                children = [parse_element(child) for child in elem_data["children"]]

            return SourceTreeElement(
                type=elem_data.get("type", ""),
                rect=rect,
                label=elem_data.get("label"),
                name=elem_data.get("name"),
                value=elem_data.get("value"),
                raw_identifier=elem_data.get("rawIdentifier"),
                is_visible=elem_data.get("isVisible"),
                children=children,
            )

        return SourceTree(value=parse_element(data["value"]))

    async def get_elements_on_screen(self) -> List[ScreenElement]:
        """화면의 모든 요소를 가져옵니다."""
        source = await self.get_page_source()
        return self._filter_source_elements(source.value)

    async def open_url(self, url: str) -> None:
        """URL을 엽니다."""

        async def _open(session_url: str) -> None:
            target_url = f"{session_url}/url"
            async with aiohttp.ClientSession() as session:
                await session.post(target_url, json={"url": url})

        await self.within_session(_open)

    async def swipe(self, direction: SwipeDirection) -> None:
        """스와이프합니다."""
        screen_size = await self.get_screen_size()

        async def _swipe(session_url: str) -> None:
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

            url = f"{session_url}/actions"
            actions = {
                "actions": [
                    {
                        "type": "pointer",
                        "id": "finger1",
                        "parameters": {"pointerType": "touch"},
                        "actions": [
                            {"type": "pointerMove", "duration": 0, "x": x0, "y": y0},
                            {"type": "pointerDown", "button": 0},
                            {"type": "pointerMove", "duration": 0, "x": x1, "y": y1},
                            {"type": "pause", "duration": 1000},
                            {"type": "pointerUp", "button": 0},
                        ],
                    }
                ]
            }

            async with aiohttp.ClientSession() as session:
                await session.post(url, json=actions)

        await self.within_session(_swipe)

    async def swipe_between_points(
        self, start_x: int, start_y: int, end_x: int, end_y: int
    ) -> None:
        """지정된 좌표에서 다른 좌표까지 스와이프합니다."""

        async def _swipe(session_url: str) -> None:
            url = f"{session_url}/actions"
            actions = {
                "actions": [
                    {
                        "type": "pointer",
                        "id": "finger1",
                        "parameters": {"pointerType": "touch"},
                        "actions": [
                            {
                                "type": "pointerMove",
                                "duration": 0,
                                "x": start_x,
                                "y": start_y,
                            },
                            {"type": "pointerDown", "button": 0},
                            {
                                "type": "pointerMove",
                                "duration": 0,
                                "x": end_x,
                                "y": end_y,
                            },
                            {"type": "pause", "duration": 1000},
                            {"type": "pointerUp", "button": 0},
                        ],
                    }
                ]
            }

            async with aiohttp.ClientSession() as session:
                await session.post(url, json=actions)

        await self.within_session(_swipe)

    async def set_orientation(self, orientation: Orientation) -> None:
        """화면 방향을 설정합니다."""

        async def _set(session_url: str) -> None:
            url = f"{session_url}/orientation"
            async with aiohttp.ClientSession() as session:
                await session.post(url, json={"orientation": orientation.upper()})

        await self.within_session(_set)

    async def get_orientation(self) -> Orientation:
        """현재 화면 방향을 가져옵니다."""

        async def _get(session_url: str) -> Orientation:
            url = f"{session_url}/orientation"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    data = await response.json()
                    return data["value"].lower()

        return await self.within_session(_get)
