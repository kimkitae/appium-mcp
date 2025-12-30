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
from .ios import IosManager, IosRobot
from .iphone_simulator import SimctlManager
from .logger import error, trace
from .png import PNG
from .robot import ActionableError, Robot
from .image_utils import Image, is_scaling_available, get_max_image_width, get_jpeg_quality
from .robot import ScreenElement


def _format_element_compact(element: ScreenElement) -> Optional[Dict[str, Any]]:
    """요소를 컴팩트한 형식으로 변환합니다.

    토큰 사용량을 줄이기 위해:
    - 텍스트/라벨/identifier가 없는 요소는 제외
    - 빈 필드 제외
    - 좌표를 간단한 배열로 표현 [x, y, w, h]
    """
    # 유용한 정보가 있는 요소만 포함
    has_text = element.text and element.text.strip()
    has_label = element.label and element.label.strip()
    has_name = element.name and element.name.strip()
    has_identifier = element.identifier and element.identifier.strip()

    if not (has_text or has_label or has_name or has_identifier):
        return None

    # 컴팩트 딕셔너리 생성 - 빈 필드 제외
    elem = {"type": element.type}

    if has_text:
        elem["text"] = element.text.strip()
    if has_label and element.label.strip() != elem.get("text", ""):
        elem["label"] = element.label.strip()
    if has_name and element.name.strip() not in (elem.get("text", ""), elem.get("label", "")):
        elem["name"] = element.name.strip()
    if has_identifier:
        elem["id"] = element.identifier.strip()
    if element.value:
        elem["value"] = element.value
    if element.focused:
        elem["focused"] = True

    # 좌표를 배열로 [x, y, w, h] - 더 컴팩트
    elem["rect"] = [
        element.rect.x,
        element.rect.y,
        element.rect.width,
        element.rect.height
    ]

    return elem


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
                description="""List all available mobile devices connected to this computer.
Returns iOS simulators, physical iOS devices, and Android devices.
ALWAYS call this tool first before any other mobile operations to discover available devices.
DO NOT write code to interact with devices - use these MCP tools directly instead.""",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="mobile_use_device",
                description="""Select a specific device to control. You MUST call this before using any other mobile tools (except mobile_list_available_devices).
After calling mobile_list_available_devices, use this tool to select which device to interact with.
Example: To select an Android device with ID 'R3CN70RQZ2A', call with device='R3CN70RQZ2A' and deviceType='android'.
DO NOT write Python code - call this tool directly.""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "device": {"type": "string", "description": "Device ID or name from mobile_list_available_devices"},
                        "deviceType": {
                            "type": "string",
                            "enum": ["simulator", "ios", "android"],
                            "description": "Device type: 'simulator' for iOS Simulator, 'ios' for physical iPhone/iPad, 'android' for Android devices",
                        },
                    },
                    "required": ["device", "deviceType"],
                },
            ),
            Tool(
                name="mobile_list_apps",
                description="""List all installed apps on the selected device.
Returns app names and package identifiers (bundle ID for iOS, package name for Android).
Use this to find the correct packageName before launching or terminating an app.
Call this tool directly - do not write code.""",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="mobile_launch_app",
                description="""Launch/open an app on the device.
Use the packageName from mobile_list_apps.
Example Android: packageName='com.android.settings' to open Settings.
Example iOS: packageName='com.apple.Preferences' to open Settings.
This tool directly launches the app - no code needed.""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "packageName": {"type": "string", "description": "App package name (Android) or bundle ID (iOS)"}
                    },
                    "required": ["packageName"],
                },
            ),
            Tool(
                name="mobile_terminate_app",
                description="""Force stop and close an app on the device.
Use this to completely quit an app before relaunching it for a fresh start.
Example: terminate 'com.example.app' then launch it again for clean state.""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "packageName": {"type": "string", "description": "App package name to terminate"}
                    },
                    "required": ["packageName"],
                },
            ),
            Tool(
                name="mobile_install_app",
                description="""Install an APK (Android) or IPA (iOS) file to the device.
Provide the full local file path to the app package.""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Local file path to APK or IPA file"}
                    },
                    "required": ["path"],
                },
            ),
            Tool(
                name="mobile_uninstall_app",
                description="""Uninstall/remove an app from the device.
Use the packageName from mobile_list_apps.""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "packageName": {"type": "string", "description": "App package name (Android) or Bundle ID (iOS) to uninstall"}
                    },
                    "required": ["packageName"],
                },
            ),
            Tool(
                name="mobile_get_screen_size",
                description="""Get the screen dimensions of the device in logical pixels.
Returns width, height, and scale factor.
Coordinates from mobile_list_elements_on_screen use this same coordinate system.""",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="mobile_click_on_screen_at_coordinates",
                description="""Tap/click on a specific point on the screen.
Use coordinates from mobile_list_elements_on_screen or mobile_get_ui_state.
The coordinates use logical pixels (same as the resized screenshot).
Example: To tap a button at position (192, 450), call with x=192, y=450.
Call this tool directly - do not write code to tap.""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "x": {"type": "number", "description": "X coordinate (horizontal position from left)"},
                        "y": {"type": "number", "description": "Y coordinate (vertical position from top)"},
                    },
                    "required": ["x", "y"],
                },
            ),
            Tool(
                name="mobile_double_tap_on_screen",
                description="""Double-tap on a specific point on the screen.
Useful for zooming in on maps/images or quick selection actions.""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "x": {"type": "number", "description": "X coordinate to double-tap"},
                        "y": {"type": "number", "description": "Y coordinate to double-tap"},
                    },
                    "required": ["x", "y"],
                },
            ),
            Tool(
                name="mobile_long_press_on_screen_at_coordinates",
                description="""Long press (touch and hold) on a specific point.
Useful for triggering context menus or drag operations.""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "x": {"type": "number", "description": "X coordinate to long press"},
                        "y": {"type": "number", "description": "Y coordinate to long press"},
                        "duration": {"type": "number", "description": "Hold duration in milliseconds (default: 1000ms for Android, 500ms for iOS)"},
                    },
                    "required": ["x", "y"],
                },
            ),
            Tool(
                name="mobile_list_elements_on_screen",
                description="""Get all UI elements on screen - FAST and LOW COST (no image).
PREFER THIS over mobile_get_ui_state when you just need to find elements to tap/click.
Returns: element type, text, label, identifier, and rect [x, y, width, height].

When to use this tool:
- Finding a button/element to tap (most common case)
- Checking if a specific element exists
- After an action, to verify the screen changed

When to use mobile_get_ui_state instead:
- You need to visually verify complex UI (charts, images, colors)
- The element list alone is not enough to understand the screen

Cost: ~500 tokens vs ~2,000 tokens for get_ui_state with screenshot.""",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="mobile_press_button",
                description="""Press a physical or system button on the device.
Supported buttons: BACK (go back), HOME (go to home screen), VOLUME_UP, VOLUME_DOWN, ENTER (confirm/submit), DPAD_CENTER, DPAD_UP, DPAD_DOWN, DPAD_LEFT, DPAD_RIGHT.
Example: Press BACK to navigate back, HOME to exit app.""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "button": {
                            "type": "string",
                            "description": "Button name: BACK, HOME, VOLUME_UP, VOLUME_DOWN, ENTER, DPAD_CENTER, DPAD_UP, DPAD_DOWN, DPAD_LEFT, DPAD_RIGHT",
                        }
                    },
                    "required": ["button"],
                },
            ),
            Tool(
                name="mobile_open_url",
                description="""Open a URL in the device's default browser.
Example: open 'https://google.com' to launch browser with that page.""",
                inputSchema={
                    "type": "object",
                    "properties": {"url": {"type": "string", "description": "Full URL including https://"}},
                    "required": ["url"],
                },
            ),
            Tool(
                name="mobile_swipe_on_screen",
                description="""Perform a swipe gesture on the screen.
Use direction 'up' to scroll down (reveal content below), 'down' to scroll up.
If x,y provided, swipe starts from that point. Otherwise swipes from screen center.
Use this to scroll through lists, pages, or navigate carousels.""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "direction": {
                            "type": "string",
                            "enum": ["up", "down", "left", "right"],
                            "description": "Swipe direction: up/down for vertical scroll, left/right for horizontal",
                        },
                        "x": {"type": "number", "description": "Starting X coordinate (optional, defaults to center)"},
                        "y": {"type": "number", "description": "Starting Y coordinate (optional, defaults to center)"},
                        "distance": {"type": "number", "description": "Swipe distance in pixels (optional)"},
                    },
                    "required": ["direction"],
                },
            ),
            Tool(
                name="mobile_type_keys",
                description="""Type text into the currently focused input field.
First tap on an input field using mobile_click_on_screen_at_coordinates, then use this to type.
Set submit=true to press Enter after typing (useful for search fields or login forms).

IMPORTANT: After typing, the keyboard often covers buttons below!
Call mobile_hide_keyboard BEFORE tapping any button that might be hidden by the keyboard.
Example flow: tap email field → type email → tap password field → type password → HIDE KEYBOARD → tap login button.""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text to type"},
                        "submit": {"type": "boolean", "description": "Press Enter/Submit after typing (true/false)"},
                    },
                    "required": ["text", "submit"],
                },
            ),
            Tool(
                name="mobile_hide_keyboard",
                description="""Dismiss/hide the on-screen keyboard.
CRITICAL: Call this after typing text and BEFORE tapping buttons that may be hidden by the keyboard!
This prevents accidentally tapping keyboard keys instead of the intended button (e.g., Login button).

Common pattern:
1. Tap input field → type text
2. Tap another input field → type text
3. **mobile_hide_keyboard** ← CALL THIS
4. Tap submit/login button

Returns: true if keyboard was hidden, false if already hidden.""",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="mobile_clear_text_field",
                description="""Clear all text in the currently focused text field.
Use this BEFORE typing new text when the field may already contain text.

Common pattern:
1. Tap input field
2. **mobile_clear_text_field** ← CLEAR existing text
3. Type new text

This is essential for:
- Re-entering credentials after login failure
- Editing existing values
- Ensuring clean input without leftover characters""",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="mobile_take_screenshot",
                description="""Capture screenshot ONLY - no element list. Cost: ~1,500 tokens.
Use mobile_list_elements_on_screen instead if you need element coordinates.
Use mobile_get_ui_state if you need BOTH screenshot AND elements.

When to use this tool:
- Saving screenshot for documentation/report
- Pure visual verification (no interaction needed)
- User specifically asked to "show" or "see" the screen""",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="mobile_save_screenshot",
                description="""Save a screenshot to a local file.
Supports .png and .jpg formats based on file extension.""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path to save screenshot (.png or .jpg)"}
                    },
                    "required": ["path"],
                },
            ),
            Tool(
                name="mobile_get_ui_state",
                description="""Get screenshot AND UI elements together - use only when VISUAL VERIFICATION needed.
Returns both an image and element list. Higher cost (~2,000 tokens) due to image.

When to use this tool:
- First time seeing a new screen (need to understand layout)
- Verifying visual elements (images, charts, colors, animations)
- Element list alone is confusing or insufficient

PREFER mobile_list_elements_on_screen (~500 tokens) when:
- You just need to find a button/element to tap
- Checking if navigation succeeded (element exists = success)
- After simple actions like tap, type, swipe

This is more efficient than calling take_screenshot + list_elements separately.""",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="mobile_set_orientation",
                description="""Rotate the device screen orientation.
Use 'portrait' for vertical or 'landscape' for horizontal.""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "orientation": {
                            "type": "string",
                            "enum": ["portrait", "landscape"],
                            "description": "Screen orientation: portrait (vertical) or landscape (horizontal)",
                        }
                    },
                    "required": ["orientation"],
                },
            ),
            Tool(
                name="mobile_get_orientation",
                description="""Get the current screen orientation (portrait or landscape).""",
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

            elif name == "mobile_install_app":
                require_robot()
                path = arguments["path"]
                await robot.install_app(path)
                result = f"앱 설치됨: {path}"

            elif name == "mobile_uninstall_app":
                require_robot()
                package_name = arguments["packageName"]
                await robot.uninstall_app(package_name)
                result = f"앱 삭제됨: {package_name}"

            elif name == "mobile_get_screen_size":
                require_robot()
                screen_size = await robot.get_screen_size()
                result = f"화면 크기: {screen_size.width}x{screen_size.height} 픽셀"

            elif name == "mobile_click_on_screen_at_coordinates":
                require_robot()
                x = arguments["x"]
                y = arguments["y"]

                # 좌표는 포인트(논리적) 단위로 전달 - 리사이즈된 스크린샷 및 list_elements_on_screen과 동일한 좌표계
                tx = int(x)
                ty = int(y)

                await robot.tap(tx, ty)
                result = f"좌표 {tx}, {ty}에서 화면 클릭됨"

            elif name == "mobile_double_tap_on_screen":
                require_robot()
                x = arguments["x"]
                y = arguments["y"]
                tx = int(x)
                ty = int(y)
                await robot.double_tap(tx, ty)
                result = f"좌표 {tx}, {ty}에서 더블탭됨"

            elif name == "mobile_long_press_on_screen_at_coordinates":
                require_robot()
                x = arguments["x"]
                y = arguments["y"]
                duration = arguments.get("duration")
                tx = int(x)
                ty = int(y)
                await robot.long_press(tx, ty, int(duration) if duration else None)
                duration_text = f" ({int(duration)}ms)" if duration else ""
                result = f"좌표 {tx}, {ty}에서 길게 누름{duration_text}"

            elif name == "mobile_list_elements_on_screen":
                require_robot()
                elements = await robot.get_elements_on_screen()

                # 컴팩트 포맷으로 변환 (빈 요소 제외, 짧은 키 사용)
                # 좌표는 포인트(논리적) 단위 - rect: [x, y, width, height]
                element_list = []
                for element in elements:
                    elem = _format_element_compact(element)
                    if elem:
                        element_list.append(elem)

                result = f"Elements ({len(element_list)}): {json.dumps(element_list, ensure_ascii=False, separators=(',', ':'))}"

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

            elif name == "mobile_swipe_on_screen":
                require_robot()
                direction = arguments.get("direction")
                x = arguments.get("x")
                y = arguments.get("y")
                distance = arguments.get("distance")

                if x is not None and y is not None:
                    # 좌표 기반 스와이프
                    await robot.swipe_from_coordinate(
                        int(x), int(y), direction, int(distance) if distance else None
                    )
                    distance_text = f" {int(distance)} 픽셀" if distance else ""
                    result = f"좌표 ({int(x)}, {int(y)})에서 {direction} 방향으로{distance_text} 스와이프됨"
                else:
                    # 화면 중앙 스와이프
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

            elif name == "mobile_hide_keyboard":
                require_robot()
                hidden = await robot.hide_keyboard()
                if hidden:
                    result = "키보드가 숨겨졌습니다"
                else:
                    result = "키보드가 이미 숨겨져 있거나 표시되지 않았습니다"

            elif name == "mobile_clear_text_field":
                require_robot()
                await robot.clear_text_field()
                result = "텍스트 필드가 초기화되었습니다"

            elif name == "mobile_take_screenshot":
                require_robot()
                screen_size = await robot.get_screen_size()
                screenshot = await robot.get_screenshot()
                mime_type = "image/png"

                # PNG 유효성 검증
                png_image = PNG(screenshot)
                png_size = png_image.get_dimensions()
                if png_size.width <= 0 or png_size.height <= 0:
                    raise ActionableError("스크린샷이 유효하지 않습니다. 다시 시도하세요.")

                # 이미지 최적화 (토큰 비용 절감)
                if is_scaling_available():
                    before_size = len(screenshot)
                    # 논리적 해상도 계산
                    logical_width = int(png_size.width / screen_size.scale) if screen_size.scale > 1 else png_size.width
                    # 최대 너비 제한 적용 (Claude 타일 최적화)
                    max_width = get_max_image_width()
                    target_width = min(logical_width, max_width)
                    quality = get_jpeg_quality()

                    trace(f"이미지 최적화: {png_size.width}x{png_size.height} -> {target_width}px, quality={quality}")
                    img = Image.from_buffer(screenshot)
                    screenshot = img.resize(target_width).jpeg({"quality": quality}).to_buffer()
                    after_size = len(screenshot)
                    trace(f"스크린샷 리사이즈: {before_size} -> {after_size} 바이트 ({100*after_size//before_size}%)")
                    mime_type = "image/jpeg"

                screenshot_b64 = base64.b64encode(screenshot).decode("utf-8")
                trace(f"스크린샷 촬영됨: {len(screenshot)} 바이트")

                return [ImageContent(type="image", data=screenshot_b64, mimeType=mime_type)]

            elif name == "mobile_save_screenshot":
                require_robot()
                path = arguments["path"]
                screenshot = await robot.get_screenshot()

                # PNG 유효성 검증
                png_image = PNG(screenshot)
                png_size = png_image.get_dimensions()
                if png_size.width <= 0 or png_size.height <= 0:
                    raise ActionableError("스크린샷이 유효하지 않습니다. 다시 시도하세요.")

                # 파일 확장자에 따라 형식 결정
                if path.lower().endswith(".jpg") or path.lower().endswith(".jpeg"):
                    if is_scaling_available():
                        img = Image.from_buffer(screenshot)
                        screenshot = img.jpeg({"quality": 85}).to_buffer()

                with open(path, "wb") as f:
                    f.write(screenshot)

                result = f"스크린샷 저장됨: {path} ({len(screenshot)} 바이트)"

            elif name == "mobile_get_ui_state":
                require_robot()
                # 병렬로 정보 수집
                screen_size_task = asyncio.create_task(robot.get_screen_size())
                screenshot_task = asyncio.create_task(robot.get_screenshot())
                elements_task = asyncio.create_task(robot.get_elements_on_screen())

                screen_size = await screen_size_task
                screenshot = await screenshot_task
                elements = await elements_task
                mime_type = "image/png"

                png_image = PNG(screenshot)
                png_size = png_image.get_dimensions()
                if png_size.width <= 0 or png_size.height <= 0:
                    raise ActionableError("스크린샷이 유효하지 않습니다. 다시 시도하세요.")

                # 이미지 최적화 (토큰 비용 절감)
                if is_scaling_available():
                    before_size = len(screenshot)
                    logical_width = int(png_size.width / screen_size.scale) if screen_size.scale > 1 else png_size.width
                    max_width = get_max_image_width()
                    target_width = min(logical_width, max_width)
                    quality = get_jpeg_quality()

                    trace(f"이미지 최적화: {png_size.width}x{png_size.height} -> {target_width}px, quality={quality}")
                    img = Image.from_buffer(screenshot)
                    screenshot = img.resize(target_width).jpeg({"quality": quality}).to_buffer()
                    after_size = len(screenshot)
                    trace(f"스크린샷 리사이즈: {before_size} -> {after_size} 바이트 ({100*after_size//before_size}%)")
                    mime_type = "image/jpeg"

                screenshot_b64 = base64.b64encode(screenshot).decode("utf-8")
                trace(f"스크린샷 촬영됨: {len(screenshot)} 바이트")

                # 컴팩트 포맷으로 변환 (빈 요소 제외)
                # 좌표는 포인트(논리적) 단위 - rect: [x, y, width, height]
                element_list = []
                for element in elements:
                    elem = _format_element_compact(element)
                    if elem:
                        element_list.append(elem)

                result = f"Elements ({len(element_list)}): {json.dumps(element_list, ensure_ascii=False, separators=(',', ':'))}"

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
