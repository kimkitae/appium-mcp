from mcp.server.fastmcp import FastMCP
from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.options.ios import XCUITestOptions
import subprocess

mcp = FastMCP(
    "자동화",
    instructions="이 MCP는 Appium을 사용하여 모바일 장치를 제어합니다."
)

driver = None
current_device = None

@mcp.tool()
async def connect(platform: str, deviceName: str = "", udid: str = "", appPackage: str = "", appActivity: str = "", bundleId: str = ""):
    """Connect to a mobile device.

    If no ``udid`` is provided this function tries to automatically detect a
    connected device for the given ``platform``. When multiple devices are
    available a list of serial numbers is returned so the caller can invoke
    this function again with the desired ``udid``.
    """
    global driver, current_device

    platform_lower = platform.lower()

    if platform_lower == "android":
        if not udid:
            try:
                result = subprocess.run(["adb", "devices", "-l"], capture_output=True, text=True)
            except FileNotFoundError:
                return "adb 명령을 찾을 수 없습니다."
            devices = []
            for line in result.stdout.splitlines():
                line = line.strip()
                if not line or line.startswith("List of devices"):
                    continue
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "device":
                    serial = parts[0]
                    model = ""
                    for p in parts[2:]:
                        if p.startswith("model:"):
                            model = p.split(":", 1)[1]
                            break
                    devices.append((serial, model))
            if not devices:
                return "연결된 Android 장치가 없습니다."
            if len(devices) > 1:
                info = "\n".join([f"{d[0]} ({d[1]})" for d in devices])
                return (
                    "여러 Android 장치가 연결되어 있습니다:\n"
                    f"{info}\n"
                    "connect 명령을 시리얼 번호와 함께 다시 호출해주세요."
                )
            udid, deviceName = devices[0]

        os_version = ""
        try:
            res = subprocess.run(
                ["adb", "-s", udid, "shell", "getprop", "ro.build.version.release"],
                capture_output=True,
                text=True,
            )
            os_version = res.stdout.strip()
        except Exception:
            pass

        options = UiAutomator2Options().load_capabilities(
            {
                "platformName": "Android",
                "automationName": "UiAutomator2",
                "deviceName": deviceName,
                "udid": udid,
                "appPackage": appPackage,
                "appActivity": appActivity,
                "newCommandTimeout": 60,
            }
        )

    elif platform_lower == "ios":
        if not udid:
            try:
                result = subprocess.run(["idevice_id", "-l"], capture_output=True, text=True)
            except FileNotFoundError:
                return "idevice_id 명령을 찾을 수 없습니다."
            ids = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            if not ids:
                return "연결된 iOS 장치가 없습니다."
            if len(ids) > 1:
                info = "\n".join(ids)
                return (
                    "여러 iOS 장치가 연결되어 있습니다:\n"
                    f"{info}\n"
                    "connect 명령을 시리얼 번호와 함께 다시 호출해주세요."
                )
            udid = ids[0]

        if not deviceName:
            try:
                name_res = subprocess.run(
                    ["ideviceinfo", "-u", udid, "-k", "DeviceName"],
                    capture_output=True,
                    text=True,
                )
                deviceName = name_res.stdout.strip()
            except Exception:
                deviceName = ""

        os_version = ""
        try:
            os_res = subprocess.run(
                ["ideviceinfo", "-u", udid, "-k", "ProductVersion"],
                capture_output=True,
                text=True,
            )
            os_version = os_res.stdout.strip()
        except Exception:
            pass

        options = XCUITestOptions().load_capabilities(
            {
                "platformName": "iOS",
                "automationName": "XCUITest",
                "deviceName": deviceName,
                "udid": udid,
                "bundleId": bundleId,
                "newCommandTimeout": 60,
            }
        )

    else:
        return "지원하지 않는 플랫폼입니다."

    driver = webdriver.Remote("http://localhost:4723", options=options)
    current_device = {
        "udid": udid,
        "deviceName": deviceName,
        "platform": platform,
        "osVersion": os_version,
    }
    return f"{platform} device 연결 완료"


@mcp.tool()
async def current_device_info():
    """Return information about the currently connected device."""
    global current_device
    if not current_device:
        return "현재 연결된 장치가 없습니다."
    return (
        f"시리얼: {current_device['udid']}, "
        f"이름: {current_device['deviceName']}, "
        f"OS 버전: {current_device['osVersion']}"
    )

@mcp.tool()
async def screenshot():
    global driver
    return driver.get_screenshot_as_base64()

@mcp.tool()
async def click(by: str, value: str):
    global driver
    element = driver.find_element(by, value)
    element.click()
    return "클릭 성공"

@mcp.tool()
async def swipe(start_x: int, start_y: int, end_x: int, end_y: int, duration: int = 800):
    global driver
    driver.swipe(start_x, start_y, end_x, end_y, duration)
    return "스와이프 성공"

@mcp.tool()
async def is_displayed(by: str, value: str):
    global driver
    element = driver.find_element(by, value)
    return element.is_displayed()

@mcp.tool()
async def get_attribute(by: str, value: str, attribute: str):
    global driver
    element = driver.find_element(by, value)
    return element.get_attribute(attribute)

@mcp.tool()
async def get_page_source():
    global driver
    return driver.page_source

@mcp.tool()
async def long_press(by: str, value: str, duration: int = 2000):
    global driver
    element = driver.find_element(by, value)
    action = webdriver.common.touch_action.TouchAction(driver)
    action.long_press(element, duration=duration).release().perform()
    return "길게 누르기 성공"

@mcp.tool()
async def disconnect():
    global driver, current_device
    if driver:
        driver.quit()
        driver = None
    current_device = None
    return "장치 연결 해제됨"

if __name__ == "__main__":
    mcp.run(transport="stdio")
