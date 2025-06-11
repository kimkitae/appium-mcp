import asyncio
import base64
import json
from typing import Any, Callable, Dict, List, Optional

import aiohttp
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.types import ImageContent, TextContent, Tool
from pydantic import BaseModel, Field

from .__init__ import __version__
from .android import AndroidDeviceManager, AndroidRobot
from .image_utils import Image, is_imagemagick_installed
from .ios import IosManager, IosRobot
from .iphone_simulator import SimctlManager
from .logger import error, trace
from .png import PNG
from .robot import ActionableError, Robot


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

    # 도구 정의

    @server.list_tools()
    async def handle_list_tools() -> List[Tool]:
        """사용 가능한 도구 목록을 반환합니다."""
        return [
            Tool(
                name="mobile_list_available_devices",
                description="사용 가능한 모든 디바이스를 나열합니다. 물리적 디바이스와 시뮬레이터를 모두 포함합니다.",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="mobile_use_device",
                description="사용할 디바이스를 선택합니다. 시뮬레이터 또는 Android 디바이스일 수 있습니다.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "device": {"type": "string", "description": "선택할 디바이스의 이름"},
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
                name="swipe_on_screen",
                description="화면에서 스와이프합니다.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "direction": {
                            "type": "string",
                            "enum": ["up", "down", "left", "right"],
                            "description": "스와이프 방향",
                        }
                    },
                    "required": ["direction"],
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
                    },
                    "required": ["text", "submit"],
                },
            ),
            Tool(
                name="mobile_take_screenshot",
                description="모바일 디바이스의 스크린샷을 찍습니다. 이 결과를 캐시하지 마세요.",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="mobile_get_ui_state",
                description="페이지 소스와 스크린샷을 동시에 가져와 화면 구성과 이미지를 확인합니다.",
                inputSchema={
                    "type": "object",
                    "properties": {},
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
                devices = simulator_manager.list_booted_simulators()
                simulator_names = [d.name for d in devices]
                ios_devices_task = asyncio.create_task(ios_manager.list_devices())
                android_devices = android_manager.get_connected_devices()
                ios_devices = await ios_devices_task
                ios_device_names = [d.device_id for d in ios_devices]
                android_tv_devices = [d.device_id for d in android_devices if d.device_type == "tv"]
                android_mobile_devices = [
                    d.device_id for d in android_devices if d.device_type == "mobile"
                ]

                resp = ["발견된 디바이스:"]
                if simulator_names:
                    resp.append(f"iOS 시뮬레이터: [{', '.join(simulator_names)}]")
                if ios_devices:
                    resp.append(f"iOS 디바이스: [{', '.join(ios_device_names)}]")
                if android_mobile_devices:
                    resp.append(f"Android 디바이스: [{', '.join(android_mobile_devices)}]")
                if android_tv_devices:
                    resp.append(f"Android TV 디바이스: [{', '.join(android_tv_devices)}]")

                result = "\n".join(resp)

            elif name == "mobile_use_device":
                device = arguments["device"]
                device_type = arguments["deviceType"]

                if device_type == "simulator":
                    robot = simulator_manager.get_simulator(device)
                elif device_type == "ios":
                    robot = IosRobot(device)
                elif device_type == "android":
                    robot = AndroidRobot(device)

                result = f"선택된 디바이스: {device}"

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
                await robot.tap(x, y)
                result = f"좌표 {x}, {y}에서 화면 클릭됨"

            elif name == "mobile_list_elements_on_screen":
                require_robot()
                elements = await robot.get_elements_on_screen()

                element_list = []
                for element in elements:
                    elem_dict = {
                        "type": element.type,
                        "text": element.text,
                        "label": element.label,
                        "name": element.name,
                        "value": element.value,
                        "identifier": element.identifier,
                        "coordinates": {
                            "x": element.rect.x,
                            "y": element.rect.y,
                            "width": element.rect.width,
                            "height": element.rect.height,
                        },
                    }
                    if element.focused:
                        elem_dict["focused"] = True
                    element_list.append(elem_dict)

                result = f"화면에서 발견된 요소: {json.dumps(element_list)}"

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

            elif name == "swipe_on_screen":
                require_robot()
                direction = arguments["direction"]
                await robot.swipe(direction)
                result = f"화면에서 {direction} 방향으로 스와이프됨"

            elif name == "mobile_type_keys":
                require_robot()
                text = arguments["text"]
                submit = arguments["submit"]
                await robot.send_keys(text)

                if submit:
                    await robot.press_button("ENTER")

                result = f"텍스트 입력됨: {text}"

            elif name == "mobile_take_screenshot":
                require_robot()
                screen_size = await robot.get_screen_size()
                screenshot = await robot.get_screenshot()
                mime_type = "image/png"

                # PNG 유효성 검증
                image = PNG(screenshot)
                png_size = image.get_dimensions()
                if png_size.width <= 0 or png_size.height <= 0:
                    raise ActionableError("스크린샷이 유효하지 않습니다. 다시 시도하세요.")

                if is_imagemagick_installed():
                    trace("ImageMagick이 설치되어 있습니다. 스크린샷 크기 조정 중")
                    img = Image.from_buffer(screenshot)
                    before_size = len(screenshot)
                    screenshot = (
                        img.resize(int(png_size.width / screen_size.scale))
                        .jpeg({"quality": 75})
                        .to_buffer()
                    )
                    after_size = len(screenshot)
                    trace(f"스크린샷 크기 조정됨: {before_size} 바이트에서 {after_size} 바이트로")
                    mime_type = "image/jpeg"

                screenshot_b64 = base64.b64encode(screenshot).decode("utf-8")
                trace(f"스크린샷 촬영됨: {len(screenshot)} 바이트")

                return [ImageContent(type="image", data=screenshot_b64, mimeType=mime_type)]

            elif name == "mobile_get_ui_state":
                require_robot()
                screen_size_task = asyncio.create_task(robot.get_screen_size())
                screenshot_task = asyncio.create_task(robot.get_screenshot())
                elements_task = asyncio.create_task(robot.get_elements_on_screen())

                screen_size = await screen_size_task
                screenshot = await screenshot_task
                elements = await elements_task
                mime_type = "image/png"

                image = PNG(screenshot)
                png_size = image.get_dimensions()
                if png_size.width <= 0 or png_size.height <= 0:
                    raise ActionableError("스크린샷이 유효하지 않습니다. 다시 시도하세요.")

                if is_imagemagick_installed():
                    trace("ImageMagick이 설치되어 있습니다. 스크린샷 크기 조정 중")
                    img = Image.from_buffer(screenshot)
                    before_size = len(screenshot)
                    screenshot = (
                        img.resize(int(png_size.width / screen_size.scale))
                        .jpeg({"quality": 75})
                        .to_buffer()
                    )
                    after_size = len(screenshot)
                    trace(f"스크린샷 크기 조정됨: {before_size} 바이트에서 {after_size} 바이트로")
                    mime_type = "image/jpeg"

                screenshot_b64 = base64.b64encode(screenshot).decode("utf-8")
                trace(f"스크린샷 촬영됨: {len(screenshot)} 바이트")

                element_list = []
                for element in elements:
                    elem_dict = {
                        "type": element.type,
                        "text": element.text,
                        "label": element.label,
                        "name": element.name,
                        "value": element.value,
                        "identifier": element.identifier,
                        "coordinates": {
                            "x": element.rect.x,
                            "y": element.rect.y,
                            "width": element.rect.width,
                            "height": element.rect.height,
                        },
                    }
                    if element.focused:
                        elem_dict["focused"] = True
                    element_list.append(elem_dict)

                result = f"화면에서 발견된 요소: {json.dumps(element_list)}"

                return [
                    TextContent(type="text", text=result),
                    ImageContent(type="image", data=screenshot_b64, mimeType=mime_type),
                ]

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
