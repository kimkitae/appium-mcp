from mcp.server.fastmcp import FastMCP
from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.options.ios import XCUITestOptions
import subprocess
import json
import os
import time
import logging
from typing import Optional, Dict, Any

# 설정 파일 로드
CONFIG_FILE = "config.json"
config = {}
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config = json.load(f)

# 로깅 설정
logging.basicConfig(level=getattr(logging, config.get('logging', {}).get('level', 'INFO')))
logger = logging.getLogger(__name__)

mcp = FastMCP(
    "자동화",
    instructions=(
        "이 MCP는 Appium을 사용하여 모바일 장치를 제어합니다. "
        "자동 연결 및 서버 관리 기능은 물론 화면 분석과 좌표 기반 클릭을 지원합니다. "
        "요청에 빠르게 응답하도록 최적화되었습니다."
    ),
)

driver = None
current_device = None
appium_process = None

def is_appium_server_running() -> bool:
    """Appium 서버가 실행 중인지 확인"""
    try:
        import requests
        response = requests.get(f"{config.get('appium', {}).get('server_url', 'http://localhost:4723')}/status", timeout=5)
        return response.status_code == 200
    except Exception:
        return False

def start_appium_server():
    """Appium 서버 자동 시작"""
    global appium_process
    
    if is_appium_server_running():
        logger.info("Appium 서버가 이미 실행 중입니다.")
        return True
    
    try:
        logger.info("Appium 서버를 시작합니다...")
        appium_process = subprocess.Popen(
            ["appium"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # 서버 시작 대기
        for _ in range(30):  # 30초 대기
            if is_appium_server_running():
                logger.info("Appium 서버가 성공적으로 시작되었습니다.")
                return True
            time.sleep(1)
        
        logger.error("Appium 서버 시작 실패")
        return False
    except FileNotFoundError:
        logger.error("Appium이 설치되지 않았습니다. 'npm install -g appium' 명령으로 설치해주세요.")
        return False
    except Exception as e:
        logger.error(f"Appium 서버 시작 중 오류: {e}")
        return False

def stop_appium_server():
    """Appium 서버 중지"""
    global appium_process
    
    if appium_process:
        appium_process.terminate()
        appium_process.wait()
        appium_process = None
        logger.info("Appium 서버가 중지되었습니다.")

def detect_devices() -> Dict[str, Any]:
    """연결된 모든 디바이스 자동 검색"""
    devices = {"android": [], "ios": []}
    
    # Android 디바이스 검색
    try:
        result = subprocess.run(["adb", "devices", "-l"], capture_output=True, text=True)
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
                devices["android"].append({"serial": serial, "model": model})
    except FileNotFoundError:
        logger.warning("adb 명령을 찾을 수 없습니다.")
    
    # iOS 디바이스 검색
    try:
        result = subprocess.run(["idevice_id", "-l"], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            udid = line.strip()
            if udid:
                device_name = ""
                try:
                    name_res = subprocess.run(
                        ["ideviceinfo", "-u", udid, "-k", "DeviceName"],
                        capture_output=True, text=True
                    )
                    device_name = name_res.stdout.strip()
                except Exception:
                    pass
                devices["ios"].append({"udid": udid, "name": device_name})
    except FileNotFoundError:
        logger.warning("idevice_id 명령을 찾을 수 없습니다.")
    
    return devices

@mcp.tool()
async def auto_setup():
    """자동으로 Appium 서버를 시작하고 첫 번째 사용 가능한 디바이스에 연결"""
    logger.info("자동 설정을 시작합니다...")
    
    # 1. Appium 서버 자동 시작
    if config.get('appium', {}).get('auto_start', True):
        if not start_appium_server():
            return "Appium 서버 시작에 실패했습니다."
    
    # 2. 디바이스 자동 검색
    devices = detect_devices()
    
    # 3. 자동 연결 시도
    android_config = config.get('android', {})
    ios_config = config.get('ios', {})
    
    # Android 우선 연결 시도
    if android_config.get('auto_connect', True) and devices['android']:
        preferred = android_config.get('preferred_device')
        target_device = None
        
        if preferred:
            target_device = next((d for d in devices['android'] if d['serial'] == preferred), None)
        
        if not target_device:
            target_device = devices['android'][0]
        
        result = await connect(
            platform="android",
            udid=target_device['serial'],
            appPackage=android_config.get('default_app_package', ''),
            appActivity=android_config.get('default_app_activity', '')
        )
        return f"Android 자동 연결 완료: {result}"
    
    # iOS 연결 시도
    elif ios_config.get('auto_connect', True) and devices['ios']:
        preferred = ios_config.get('preferred_device')
        target_device = None
        
        if preferred:
            target_device = next((d for d in devices['ios'] if d['udid'] == preferred), None)
        
        if not target_device:
            target_device = devices['ios'][0]
        
        result = await connect(
            platform="ios",
            udid=target_device['udid'],
            bundleId=ios_config.get('default_bundle_id', '')
        )
        return f"iOS 자동 연결 완료: {result}"
    
    return "연결 가능한 디바이스가 없습니다."

@mcp.tool()
async def list_available_devices():
    """사용 가능한 모든 디바이스 목록 조회"""
    devices = detect_devices()
    
    result = "=== 사용 가능한 디바이스 ===\n"
    
    if devices['android']:
        result += "\n📱 Android 디바이스:\n"
        for device in devices['android']:
            result += f"  - {device['serial']} ({device['model']})\n"
    
    if devices['ios']:
        result += "\n📱 iOS 디바이스:\n"  
        for device in devices['ios']:
            result += f"  - {device['udid']} ({device['name']})\n"
    
    if not devices['android'] and not devices['ios']:
        result += "연결된 디바이스가 없습니다."
    
    return result

@mcp.tool()
async def check_connection_status():
    """현재 연결 상태 및 서버 상태 확인"""
    status = {
        "appium_server": "실행 중" if is_appium_server_running() else "중지됨",
        "device_connected": bool(current_device),
        "device_info": current_device
    }
    
    result = f"🔧 Appium 서버: {status['appium_server']}\n"
    result += f"📱 디바이스 연결: {'✅ 연결됨' if status['device_connected'] else '❌ 연결 안됨'}\n"
    
    if status['device_info']:
        result += f"📋 디바이스 정보: {status['device_info']['deviceName']} ({status['device_info']['platform']}, {status['device_info']['osVersion']})"
    
    return result

@mcp.tool()
async def restart_connection():
    """현재 연결을 끊고 자동으로 다시 연결"""
    logger.info("연결을 재시작합니다...")
    
    # 기존 연결 해제
    await disconnect()
    
    # 잠시 대기
    time.sleep(2)
    
    # 자동 재연결
    return await auto_setup()

@mcp.tool()
async def connect(platform: str, deviceName: str = "", udid: str = "", appPackage: str = "", appActivity: str = "", bundleId: str = ""):
    """Connect to a mobile device.

    If no ``udid`` is provided this function tries to automatically detect a
    connected device for the given ``platform``. When multiple devices are
    available a list of serial numbers is returned so the caller can invoke
    this function again with the desired ``udid``.
    """
    global driver, current_device

    # Appium 서버 상태 확인 및 자동 시작
    if not is_appium_server_running():
        logger.info("Appium 서버가 실행되지 않았습니다. 자동 시작을 시도합니다...")
        if not start_appium_server():
            return "Appium 서버를 시작할 수 없습니다. 수동으로 Appium 서버를 시작해주세요."

    platform_lower = platform.lower()

    if platform_lower == "android":
        if not udid:
            try:
                result = subprocess.run(["adb", "devices", "-l"], capture_output=True, text=True)
            except FileNotFoundError:
                return "adb 명령을 찾을 수 없습니다. Android SDK를 설치하고 PATH에 추가해주세요."
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
                return "연결된 Android 장치가 없습니다. USB 디버깅이 활성화되어 있는지 확인해주세요."
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
                "newCommandTimeout": config.get('appium', {}).get('timeout', 60),
                "noReset": True,
                "autoGrantPermissions": True,
                "ignoreUnimportantViews": config.get('performance', {}).get('ignore_unimportant_views', True),
            }
        )

    elif platform_lower == "ios":
        if not udid:
            try:
                result = subprocess.run(["idevice_id", "-l"], capture_output=True, text=True)
            except FileNotFoundError:
                return "idevice_id 명령을 찾을 수 없습니다. libimobiledevice를 설치해주세요."
            ids = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            if not ids:
                return "연결된 iOS 장치가 없습니다. 신뢰할 수 있는 컴퓨터로 설정되어 있는지 확인해주세요."
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
                "newCommandTimeout": config.get('appium', {}).get('timeout', 60),
                "noReset": True,
                "useJSONSource": config.get('performance', {}).get('use_json_source', True),
            }
        )

    else:
        return "지원하지 않는 플랫폼입니다. 'android' 또는 'ios'를 사용해주세요."

    try:
        server_url = config.get('appium', {}).get('server_url', 'http://localhost:4723')
        driver = webdriver.Remote(server_url, options=options)
        current_device = {
            "udid": udid,
            "deviceName": deviceName,
            "platform": platform,
            "osVersion": os_version,
        }
        logger.info(f"{platform} 디바이스 연결 성공: {deviceName}")
        return f"✅ {platform} device 연결 완료: {deviceName} (OS: {os_version})"
    except Exception as e:
        logger.error(f"디바이스 연결 실패: {e}")
        return f"❌ 디바이스 연결 실패: {str(e)}"

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
async def screen_analysis(detailed: bool = False):
    """빠른 화면 분석을 위해 스크린샷과 페이지 소스를 함께 반환"""
    global driver
    return {
        "screenshot": driver.get_screenshot_as_base64(),
        "page_source": await get_page_source(detailed=detailed),
    }

@mcp.tool()
async def click_coordinates(x: int, y: int):
    """지정한 좌표를 탭합니다"""
    global driver
    action = webdriver.common.touch_action.TouchAction(driver)
    action.tap(x=x, y=y).perform()
    return "클릭 성공"

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
async def get_page_source(detailed: bool = False):
    """페이지 소스를 가져옵니다. 간단 모드에서는 플랫폼별 설정을 활용합니다."""
    global driver, current_device
    if not detailed:
        platform = (current_device or {}).get("platform", "").lower()
        if platform == "ios" and config.get("performance", {}).get("use_json_source", False):
            try:
                return driver.execute_script("mobile: source", {"format": "json"})
            except Exception:
                pass
        elif platform == "android" and config.get("performance", {}).get("ignore_unimportant_views", False):
            try:
                driver.update_settings({"ignoreUnimportantViews": True})
                source = driver.page_source
                driver.update_settings({"ignoreUnimportantViews": False})
                return source
            except Exception:
                pass
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
    """현재 연결된 디바이스와의 연결을 해제하고 선택적으로 Appium 서버를 중지"""
    global driver, current_device
    
    device_info = ""
    if current_device:
        device_info = f" ({current_device['deviceName']})"
    
    if driver:
        try:
            driver.quit()
            logger.info(f"디바이스 연결 해제됨{device_info}")
        except Exception as e:
            logger.warning(f"드라이버 종료 중 오류: {e}")
        driver = None
    
    current_device = None
    
    # 설정에 따라 Appium 서버도 중지
    auto_stop = config.get('appium', {}).get('auto_stop_on_disconnect', False)
    if auto_stop:
        stop_appium_server()
        return f"✅ 장치 연결 해제 및 Appium 서버 중지 완료{device_info}"
    
    return f"✅ 장치 연결 해제됨{device_info}"

if __name__ == "__main__":
    mcp.run(transport="stdio")
