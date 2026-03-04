import asyncio
import base64
import json
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from mcp.server import Server
from mcp.types import ImageContent, TextContent, Tool

from .__init__ import __version__
from .android import AndroidDeviceManager, AndroidRobot
from .image_utils import Image, is_scaling_available
from .ios import IosManager, IosRobot
from .iphone_simulator import SimctlManager
from .logger import error, trace
from .png import PNG
from .robot import ActionableError, Robot, ScreenElement


def get_agent_version() -> str:
    """에이전트 버전을 가져옵니다."""
    return __version__


async def get_latest_agent_version() -> str:
    """최신 에이전트 버전을 가져옵니다."""
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://api.github.com/repos/mobile-next/mobile-mcp/tags?per_page=1"
        ) as response:
            data = await response.json()
            return data[0]["name"]


async def check_for_latest_agent_version() -> None:
    """최신 버전 확인을 수행합니다."""
    try:
        latest_version = await get_latest_agent_version()
        current_version = get_agent_version()
        if latest_version != current_version:
            trace(
                f"이전 버전의 에이전트를 실행 중입니다. "
                f"최신 버전으로 업데이트하세요: {latest_version}."
            )
    except Exception:
        # 무시
        pass


def create_mcp_server() -> Server:
    """MCP 서버를 생성합니다."""

    server = Server("mobile-mcp")

    # 전역 상태
    robot: Optional[Robot] = None
    simulator_manager = SimctlManager()

    def require_robot() -> None:
        """로봇이 선택되었는지 확인합니다."""
        if not robot:
            raise ActionableError(
                "선택된 디바이스가 없습니다. "
                "mobile_use_device 도구를 사용하여 디바이스를 선택하세요."
            )

    def serialize_elements(elements: List[Any], scale: float) -> str:
        """화면 요소를 토큰 효율적인 형태로 직렬화합니다."""
        output = []
        for element in elements:
            item: Dict[str, Any] = {
                "type": element.type,
                "coordinates": {
                    "x": int(element.rect.x * scale),
                    "y": int(element.rect.y * scale),
                    "width": int(element.rect.width * scale),
                    "height": int(element.rect.height * scale),
                },
            }

            if element.text:
                item["text"] = element.text
            if element.label:
                item["label"] = element.label
            if element.name:
                item["name"] = element.name
            if element.value:
                item["value"] = element.value
            if element.identifier:
                item["identifier"] = element.identifier
            if element.focused:
                item["focused"] = True

            output.append(item)

        return json.dumps(output, ensure_ascii=False, separators=(",", ":"))

    def element_search_fields(element: ScreenElement) -> List[str]:
        fields: List[str] = []
        for value in (
            element.identifier,
            element.text,
            element.label,
            element.name,
            element.value,
            element.type,
        ):
            if value:
                fields.append(str(value))
        return fields

    def find_element_by_query(
        elements: List[ScreenElement], query: str, index: int = 0, exact_match: bool = False
    ) -> ScreenElement:
        query_text = query.strip().lower()
        if not query_text:
            raise ActionableError("엘리먼트 검색어가 비어 있습니다.")

        ranked: List[Tuple[int, ScreenElement]] = []
        for element in elements:
            fields = element_search_fields(element)
            best_score = -1

            for field in fields:
                lowered = field.lower()
                if exact_match:
                    if lowered == query_text:
                        best_score = max(best_score, 1000)
                else:
                    if lowered == query_text:
                        best_score = max(best_score, 1000)
                    elif lowered.startswith(query_text):
                        best_score = max(best_score, 700)
                    elif query_text in lowered:
                        best_score = max(best_score, 500)

            if best_score >= 0:
                area = max(1, element.rect.width * element.rect.height)
                ranked.append((best_score * 10 + min(area, 999), element))

        ranked.sort(key=lambda item: item[0], reverse=True)
        if not ranked:
            raise ActionableError(
                f'검색어 "{query}"와 일치하는 엘리먼트를 찾을 수 없습니다. '
                "먼저 mobile_list_elements_on_screen으로 값을 확인하세요."
            )

        if index < 0 or index >= len(ranked):
            raise ActionableError(
                f'검색어 "{query}"에 대한 index {index}가 범위를 벗어났습니다. '
                f"일치 개수: {len(ranked)}"
            )

        return ranked[index][1]

    def get_center_coordinates(element: ScreenElement, scale: float) -> Tuple[int, int]:
        center_x = int((element.rect.x + (element.rect.width / 2)) * scale)
        center_y = int((element.rect.y + (element.rect.height / 2)) * scale)
        return center_x, center_y

    def describe_element(element: ScreenElement) -> str:
        for value in (
            element.identifier,
            element.text,
            element.label,
            element.name,
            element.value,
            element.type,
        ):
            if value:
                return str(value)
        return element.type

    def compress_screenshot(screenshot: bytes, quality: int = 70) -> Tuple[bytes, str]:
        """스크린샷을 압축 가능한 경우 JPEG로 변환합니다."""
        image = PNG(screenshot)
        png_size = image.get_dimensions()
        if png_size.width <= 0 or png_size.height <= 0:
            raise ActionableError("스크린샷이 유효하지 않습니다. 다시 시도하세요.")

        if not is_scaling_available():
            return screenshot, "image/png"

        safe_quality = max(40, min(int(quality), 95))
        try:
            compressed = Image.from_buffer(screenshot).jpeg({"quality": safe_quality}).to_buffer()
            return compressed, "image/jpeg"
        except Exception:
            # 압축 도구 오류 시 원본 이미지로 폴백
            return screenshot, "image/png"

    # 도구 정의

    @server.list_tools()
    async def handle_list_tools() -> List[Tool]:
        """사용 가능한 도구 목록을 반환합니다."""
        return [
            Tool(
                name="mobile_list_available_devices",
                description="사용 가능한 iOS/Android 디바이스를 나열합니다. 실기기, 시뮬레이터, 에뮬레이터를 모두 포함합니다.",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="mobile_use_device",
                description="사용할 디바이스를 선택합니다. device에는 디바이스 ID(권장) 또는 이름을 넣습니다.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "device": {"type": "string", "description": "선택할 디바이스 ID 또는 이름"},
                        "deviceType": {
                            "type": "string",
                            "enum": ["simulator", "ios", "android"],
                            "description": "선택할 디바이스의 유형",
                        },
                    },
                    "required": ["device", "deviceType"],
                },
            ),
            Tool(
                name="mobile_list_apps",
                description="디바이스에 설치된 모든 앱을 나열합니다.",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="mobile_launch_app",
                description="모바일 디바이스에서 앱을 실행합니다.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "packageName": {"type": "string", "description": "실행할 앱의 패키지 이름"}
                    },
                    "required": ["packageName"],
                },
            ),
            Tool(
                name="mobile_terminate_app",
                description="모바일 디바이스에서 앱을 중지하고 종료합니다.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "packageName": {"type": "string", "description": "종료할 앱의 패키지 이름"}
                    },
                    "required": ["packageName"],
                },
            ),
            Tool(
                name="mobile_get_screen_size",
                description="모바일 디바이스의 화면 크기를 픽셀 단위로 가져옵니다.",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="mobile_click_on_screen_at_coordinates",
                description="주어진 x,y 좌표에서 화면을 클릭합니다.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "x": {"type": "number", "description": "화면에서 클릭할 x 좌표 (픽셀)"},
                        "y": {"type": "number", "description": "화면에서 클릭할 y 좌표 (픽셀)"},
                    },
                    "required": ["x", "y"],
                },
            ),
            Tool(
                name="mobile_list_elements_on_screen",
                description="화면의 요소와 좌표를 나열합니다. 이 결과를 캐시하지 마세요.",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="mobile_press_button",
                description="디바이스의 버튼을 누릅니다.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "button": {
                            "type": "string",
                            "description": "누를 버튼. 지원되는 버튼: BACK, HOME, VOLUME_UP, VOLUME_DOWN, ENTER, DPAD_CENTER, DPAD_UP, DPAD_DOWN, DPAD_LEFT, DPAD_RIGHT",
                        }
                    },
                    "required": ["button"],
                },
            ),
            Tool(
                name="mobile_open_url",
                description="디바이스의 브라우저에서 URL을 엽니다.",
                inputSchema={
                    "type": "object",
                    "properties": {"url": {"type": "string", "description": "열 URL"}},
                    "required": ["url"],
                },
            ),
            Tool(
                name="mobile_swipe_on_screen",
                description="화면에서 스와이프합니다. 좌표 시작점(x,y)을 주면 특정 위치에서 스와이프합니다.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "direction": {
                            "type": "string",
                            "enum": ["up", "down", "left", "right"],
                            "description": "스와이프 방향",
                        },
                        "x": {
                            "type": "number",
                            "description": "스와이프 시작 X 좌표. y와 함께 사용합니다.",
                        },
                        "y": {
                            "type": "number",
                            "description": "스와이프 시작 Y 좌표. x와 함께 사용합니다.",
                        },
                        "distance": {
                            "type": "number",
                            "description": "스와이프 거리(px). 미지정 시 기본 거리 사용",
                        },
                        "start_x": {"type": "integer", "description": "시작 X 좌표"},
                        "start_y": {"type": "integer", "description": "시작 Y 좌표"},
                        "end_x": {"type": "integer", "description": "끝 X 좌표"},
                        "end_y": {"type": "integer", "description": "끝 Y 좌표"},
                    },
                    "required": [],
                },
            ),
            Tool(
                name="swipe_on_screen",
                description="(호환용) 화면에서 스와이프합니다. mobile_swipe_on_screen 사용을 권장합니다.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "direction": {
                            "type": "string",
                            "enum": ["up", "down", "left", "right"],
                            "description": "스와이프 방향",
                        },
                        "x": {"type": "number", "description": "스와이프 시작 X 좌표"},
                        "y": {"type": "number", "description": "스와이프 시작 Y 좌표"},
                        "distance": {"type": "number", "description": "스와이프 거리(px)"},
                        "start_x": {"type": "integer", "description": "시작 X 좌표"},
                        "start_y": {"type": "integer", "description": "시작 Y 좌표"},
                        "end_x": {"type": "integer", "description": "끝 X 좌표"},
                        "end_y": {"type": "integer", "description": "끝 Y 좌표"},
                    },
                    "required": [],
                },
            ),
            Tool(
                name="mobile_drag_and_drop",
                description="출발 엘리먼트에서 도착 엘리먼트로 드래그 앤 드롭합니다. 좌표 대신 엘리먼트 검색어를 사용합니다.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "sourceElement": {
                            "type": "string",
                            "description": "출발 엘리먼트 검색어 (text/label/name/identifier 중 하나)",
                        },
                        "targetElement": {
                            "type": "string",
                            "description": "도착 엘리먼트 검색어 (text/label/name/identifier 중 하나)",
                        },
                        "sourceIndex": {
                            "type": "integer",
                            "description": "동일 검색 결과가 여러 개인 경우 출발 엘리먼트 인덱스(기본 0)",
                        },
                        "targetIndex": {
                            "type": "integer",
                            "description": "동일 검색 결과가 여러 개인 경우 도착 엘리먼트 인덱스(기본 0)",
                        },
                        "exactMatch": {
                            "type": "boolean",
                            "description": "검색어를 정확히 일치시킬지 여부 (기본 false)",
                        },
                        "holdMs": {
                            "type": "integer",
                            "minimum": 0,
                            "description": "드래그 시작점에서 누르고 있을 시간(ms, 기본 250)",
                        },
                        "moveMs": {
                            "type": "integer",
                            "minimum": 100,
                            "description": "드래그 이동 시간(ms, 기본 850)",
                        },
                    },
                    "required": ["sourceElement", "targetElement"],
                },
            ),
            Tool(
                name="mobile_type_keys",
                description="포커스된 요소에 텍스트를 입력합니다.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "입력할 텍스트"},
                        "submit": {"type": "boolean", "description": "텍스트를 제출할지 여부"},
                        "clearBeforeTyping": {
                            "type": "boolean",
                            "description": "입력 전에 현재 포커스된 입력값을 먼저 지울지 여부",
                        },
                    },
                    "required": ["text", "submit"],
                },
            ),
            Tool(
                name="mobile_take_screenshot",
                description="모바일 디바이스의 스크린샷을 찍습니다. 기본적으로 JPEG 압축을 적용합니다. 이 결과를 캐시하지 마세요.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "quality": {
                            "type": "integer",
                            "minimum": 40,
                            "maximum": 95,
                            "description": "JPEG 품질(40~95). 기본값 70",
                        }
                    },
                },
            ),
            Tool(
                name="mobile_get_ui_state",
                description="기본적으로 화면 요소만 반환합니다. 필요할 때만 includeScreenshot=true로 이미지를 포함해 비용을 줄이세요.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "includeElements": {
                            "type": "boolean",
                            "description": "화면 요소 목록 포함 여부 (기본 true)",
                        },
                        "includeScreenshot": {
                            "type": "boolean",
                            "description": "스크린샷 이미지 포함 여부 (기본 false)",
                        },
                        "quality": {
                            "type": "integer",
                            "minimum": 40,
                            "maximum": 95,
                            "description": "includeScreenshot=true 일 때 JPEG 품질(기본 70)",
                        },
                    },
                },
            ),
            Tool(
                name="mobile_set_orientation",
                description="디바이스의 화면 방향을 변경합니다.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "orientation": {
                            "type": "string",
                            "enum": ["portrait", "landscape"],
                            "description": "원하는 방향",
                        }
                    },
                    "required": ["orientation"],
                },
            ),
            Tool(
                name="mobile_get_orientation",
                description="디바이스의 현재 화면 방향을 가져옵니다.",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
        ]

    @server.call_tool()
    async def handle_call_tool(
        name: str, arguments: Dict[str, Any]
    ) -> List[TextContent | ImageContent]:
        """도구 호출을 처리합니다."""
        nonlocal robot

        try:
            trace(f"{name} 호출, 인자: {json.dumps(arguments)}")

            if name == "mobile_list_available_devices":
                ios_manager = IosManager()
                android_manager = AndroidDeviceManager()
                simulators = simulator_manager.list_simulators()
                ios_devices_task = asyncio.create_task(ios_manager.list_devices())
                android_devices = android_manager.get_connected_devices()
                ios_devices = await ios_devices_task
                devices_payload: List[Dict[str, Any]] = []

                for sim in simulators:
                    devices_payload.append(
                        {
                            "id": sim.uuid,
                            "name": sim.name,
                            "platform": "ios",
                            "type": "simulator",
                            "state": sim.state.lower(),
                            "runtime": sim.runtime,
                        }
                    )

                for device in ios_devices:
                    devices_payload.append(
                        {
                            "id": device.device_id,
                            "name": device.device_name,
                            "platform": "ios",
                            "type": "real",
                            "state": "online",
                        }
                    )

                for device in android_devices:
                    devices_payload.append(
                        {
                            "id": device.device_id,
                            "name": device.device_name or device.device_id,
                            "platform": "android",
                            "type": device.connection_type,
                            "deviceCategory": device.device_type,
                            "version": device.os_version or "unknown",
                            "state": "online",
                        }
                    )

                result = json.dumps({"devices": devices_payload}, ensure_ascii=False)

            elif name == "mobile_use_device":
                device = arguments["device"]
                device_type = arguments["deviceType"]

                if device_type == "simulator":
                    robot = simulator_manager.get_simulator(device)
                elif device_type == "ios":
                    robot = IosRobot(device)
                elif device_type == "android":
                    robot = AndroidRobot(device)
                else:
                    raise ActionableError(f"지원하지 않는 deviceType: {device_type}")

                result = f"선택된 디바이스: {device} ({device_type})"

            elif name == "mobile_list_apps":
                require_robot()
                apps = await robot.list_apps()
                app_list = [f"{app.app_name} ({app.package_name})" for app in apps]
                result = f"디바이스에서 발견된 앱: {', '.join(app_list)}"

            elif name == "mobile_launch_app":
                require_robot()
                package_name = arguments["packageName"]
                await robot.launch_app(package_name)
                result = f"앱 실행됨: {package_name}"

            elif name == "mobile_terminate_app":
                require_robot()
                package_name = arguments["packageName"]
                await robot.terminate_app(package_name)
                result = f"앱 종료됨: {package_name}"

            elif name == "mobile_get_screen_size":
                require_robot()
                screen_size = await robot.get_screen_size()
                result = f"화면 크기: {screen_size.width}x{screen_size.height} 픽셀"

            elif name == "mobile_click_on_screen_at_coordinates":
                require_robot()
                x = arguments["x"]
                y = arguments["y"]

                # 스크린샷을 원본 크기로 전송하므로, 전달받은 좌표는 그대로 사용합니다
                tx = int(x)
                ty = int(y)

                await robot.tap(tx, ty)
                result = f"좌표 {tx}, {ty}에서 화면 클릭됨"

            elif name == "mobile_list_elements_on_screen":
                require_robot()
                screen_size = await robot.get_screen_size()
                scale = screen_size.scale if screen_size else 1
                elements = await robot.get_elements_on_screen()
                serialized = serialize_elements(elements, scale)
                result = f"화면에서 발견된 요소: {serialized}"

            elif name == "mobile_press_button":
                require_robot()
                button = arguments["button"]
                await robot.press_button(button)
                result = f"버튼 눌림: {button}"

            elif name == "mobile_open_url":
                require_robot()
                url = arguments["url"]
                await robot.open_url(url)
                result = f"URL 열림: {url}"

            elif name in ("swipe_on_screen", "mobile_swipe_on_screen"):
                require_robot()
                if all(
                    key in arguments for key in ("start_x", "start_y", "end_x", "end_y")
                ):
                    start_x = int(arguments["start_x"])
                    start_y = int(arguments["start_y"])
                    end_x = int(arguments["end_x"])
                    end_y = int(arguments["end_y"])
                    await robot.swipe_between_points(start_x, start_y, end_x, end_y)
                    result = (
                        f"화면에서 ({start_x},{start_y}) -> ({end_x},{end_y}) 로 스와이프됨"
                    )
                elif "direction" in arguments and "x" in arguments and "y" in arguments:
                    direction = arguments["direction"]
                    x = int(arguments["x"])
                    y = int(arguments["y"])
                    distance = arguments.get("distance")
                    swipe_distance = int(distance) if distance is not None else None
                    await robot.swipe_from_coordinate(x, y, direction, swipe_distance)
                    distance_text = f", 거리 {swipe_distance}px" if swipe_distance else ""
                    result = (
                        f"화면에서 ({x},{y}) 시작 {direction} 스와이프 실행됨{distance_text}"
                    )
                elif "direction" in arguments:
                    direction = arguments["direction"]
                    await robot.swipe(direction)
                    result = f"화면에서 {direction} 방향으로 스와이프됨"
                else:
                    raise ActionableError(
                        "direction 또는 (start_x,start_y,end_x,end_y) 또는 (direction,x,y) 인자가 필요합니다."
                    )

            elif name == "mobile_drag_and_drop":
                require_robot()
                source_query = arguments["sourceElement"]
                target_query = arguments["targetElement"]
                source_index = int(arguments.get("sourceIndex", 0))
                target_index = int(arguments.get("targetIndex", 0))
                exact_match = bool(arguments.get("exactMatch", False))
                hold_ms = arguments.get("holdMs")
                move_ms = arguments.get("moveMs")
                hold_ms_int = int(hold_ms) if hold_ms is not None else None
                move_ms_int = int(move_ms) if move_ms is not None else None

                screen_size = await robot.get_screen_size()
                scale = screen_size.scale if screen_size else 1
                elements = await robot.get_elements_on_screen()

                source_element = find_element_by_query(
                    elements, source_query, index=source_index, exact_match=exact_match
                )
                target_element = find_element_by_query(
                    elements, target_query, index=target_index, exact_match=exact_match
                )

                start_x, start_y = get_center_coordinates(source_element, scale)
                end_x, end_y = get_center_coordinates(target_element, scale)

                await robot.drag_between_points(
                    start_x,
                    start_y,
                    end_x,
                    end_y,
                    hold_ms=hold_ms_int,
                    move_ms=move_ms_int,
                )

                source_name = describe_element(source_element)
                target_name = describe_element(target_element)
                result = (
                    f'드래그 앤 드롭 실행됨: "{source_name}" -> "{target_name}" '
                    f"(index: {source_index}->{target_index})"
                )

            elif name == "mobile_type_keys":
                require_robot()
                text = arguments["text"]
                submit = arguments["submit"]
                clear_before_typing = bool(arguments.get("clearBeforeTyping", False))

                if clear_before_typing:
                    await robot.clear_focused_input()

                await robot.send_keys(text)

                if submit:
                    await robot.press_button("ENTER")

                cleared_text = " (기존 입력 삭제 후)" if clear_before_typing else ""
                result = f"텍스트 입력됨{cleared_text}: {text}"

            elif name == "mobile_take_screenshot":
                require_robot()
                screenshot = await robot.get_screenshot()
                quality = int(arguments.get("quality", 70))
                screenshot, mime_type = compress_screenshot(screenshot, quality)
                screenshot_b64 = base64.b64encode(screenshot).decode("utf-8")
                trace(
                    f"스크린샷 촬영됨: {len(screenshot)} 바이트, mime={mime_type}, quality={quality}"
                )

                return [ImageContent(type="image", data=screenshot_b64, mimeType=mime_type)]

            elif name == "mobile_get_ui_state":
                require_robot()
                include_elements = bool(arguments.get("includeElements", True))
                include_screenshot = bool(arguments.get("includeScreenshot", False))
                quality = int(arguments.get("quality", 70))

                if not include_elements and not include_screenshot:
                    raise ActionableError(
                        "includeElements와 includeScreenshot이 모두 false 입니다. 하나 이상 true여야 합니다."
                    )

                content: List[TextContent | ImageContent] = []

                screen_size: Optional[Any] = None
                if include_elements:
                    screen_size = await robot.get_screen_size()
                    scale = screen_size.scale if screen_size else 1
                    elements = await robot.get_elements_on_screen()
                    serialized = serialize_elements(elements, scale)
                    result = f"화면에서 발견된 요소: {serialized}"
                    content.append(TextContent(type="text", text=result))

                if include_screenshot:
                    screenshot = await robot.get_screenshot()
                    screenshot, mime_type = compress_screenshot(screenshot, quality)
                    screenshot_b64 = base64.b64encode(screenshot).decode("utf-8")
                    trace(
                        f"UI 상태 스크린샷 포함: {len(screenshot)} 바이트, mime={mime_type}, quality={quality}"
                    )
                    content.append(
                        ImageContent(type="image", data=screenshot_b64, mimeType=mime_type)
                    )

                return content

            elif name == "mobile_set_orientation":
                require_robot()
                orientation = arguments["orientation"]
                await robot.set_orientation(orientation)
                result = f"디바이스 방향이 {orientation}으로 변경됨"

            elif name == "mobile_get_orientation":
                require_robot()
                orientation = await robot.get_orientation()
                result = f"현재 디바이스 방향: {orientation}"

            else:
                raise ValueError(f"알 수 없는 도구: {name}")

            trace(f"=> {result}")
            return [TextContent(type="text", text=result)]

        except ActionableError as e:
            return [TextContent(type="text", text=f"{e}. 문제를 해결하고 다시 시도하세요.")]
        except Exception as e:
            error(f"도구 '{name}' 실패: {str(e)}")
            return [TextContent(type="text", text=f"오류: {str(e)}")]

    # 최신 버전 확인 (비동기)
    # asyncio.create_task(check_for_latest_agent_version())

    return server
