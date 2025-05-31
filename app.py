from mcp.server.fastmcp import FastMCP
from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.options.ios import XCUITestOptions

mcp = FastMCP(
    "자동화",
    instructions="이 MCP는 Appium을 사용하여 모바일 장치를 제어합니다."
)

driver = None

@mcp.tool()
async def connect(platform: str, deviceName: str, udid: str, appPackage: str = "", appActivity: str = "", bundleId: str = ""):
    global driver
    if platform.lower() == "android":
        options = UiAutomator2Options().load_capabilities({
            "platformName": "Android",
            "automationName": "UiAutomator2",
            "deviceName": deviceName,
            "udid": udid,
            "appPackage": appPackage,
            "appActivity": appActivity,
            "newCommandTimeout": 60
        })
    elif platform.lower() == "ios":
        options = XCUITestOptions().load_capabilities({
            "platformName": "iOS",
            "automationName": "XCUITest",
            "deviceName": deviceName,
            "udid": udid,
            "bundleId": bundleId,
            "newCommandTimeout": 60
        })
    else:
        return "지원하지 않는 플랫폼입니다."

    driver = webdriver.Remote("http://localhost:4723", options=options)
    return f"{platform} device 연결 완료"

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
    global driver
    if driver:
        driver.quit()
        driver = None
    return "장치 연결 해제됨"

if __name__ == "__main__":
    mcp.run(transport="stdio")
