import os
import json
import asyncio
from threading import Lock, Thread
from subprocess import Popen, DEVNULL
import time
import requests
from flask import Flask, request, jsonify
from appium import webdriver
from appium.webdriver.common.appiumby import AppiumBy
from appium.options.android import UiAutomator2Options
from appium.options.ios import XCUITestOptions
import websockets

app = Flask(__name__)

driver = None
appium_process = None
driver_lock = Lock()

APPIUM_HOST = os.environ.get("APPIUM_HOST", "localhost")
APPIUM_PORT = int(os.environ.get("APPIUM_PORT", "4723"))
APPIUM_START = os.environ.get("APPIUM_START_SERVER", "true").lower() == "true"
APPIUM_SERVER_URL = f"http://{APPIUM_HOST}:{APPIUM_PORT}"


def start_appium():
    global appium_process
    if not APPIUM_START:
        return
    if appium_process is None:
        appium_process = Popen([
            "appium", "server",
            "--session-override",
            "--relaxed-security",
            "--log-level", "warn"
        ], stdout=DEVNULL, stderr=DEVNULL)
        wait_for_appium_ready()


def wait_for_appium_ready(timeout=10):
    url = f"{APPIUM_SERVER_URL}/status"
    for _ in range(timeout * 10):
        try:
            response = requests.get(url)
            if response.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.1)
    raise RuntimeError("Appium server failed to start")


def stop_appium():
    global appium_process
    if appium_process:
        appium_process.terminate()
        appium_process.wait()
        appium_process = None


# Internal command functions -------------------------------------------------

def connect_driver(capabilities):
    global driver
    platform = capabilities.get("platformName", "").lower()
    start_appium()
    if platform == "android":
        options = UiAutomator2Options().load_capabilities(capabilities)
    elif platform == "ios":
        options = XCUITestOptions().load_capabilities(capabilities)
    else:
        return {"status": "error", "reason": "Unsupported platform"}
    with driver_lock:
        if driver:
            driver.quit()
        driver = webdriver.Remote(APPIUM_SERVER_URL, options=options)
    return {"status": "connected"}


def disconnect_driver():
    global driver
    with driver_lock:
        if driver:
            driver.quit()
            driver = None
        stop_appium()
    return {"status": "disconnected"}


def click_element(data):
    global driver
    with driver_lock:
        el = driver.find_element(getattr(AppiumBy, data['by'].upper()), data['value'])
        el.click()
    return {"status": "clicked"}


def swipe_screen(data):
    global driver
    with driver_lock:
        driver.swipe(data['start_x'], data['start_y'], data['end_x'], data['end_y'], data.get('duration', 800))
    return {"status": "swiped"}


def element_displayed(data):
    global driver
    with driver_lock:
        el = driver.find_element(getattr(AppiumBy, data['by'].upper()), data['value'])
        return {"status": "success", "is_displayed": el.is_displayed()}


def get_attribute_value(data):
    global driver
    with driver_lock:
        el = driver.find_element(getattr(AppiumBy, data['by'].upper()), data['value'])
        value = el.get_attribute(data['attribute'])
        return {"status": "success", "attribute": value}


def get_source():
    global driver
    with driver_lock:
        return {"status": "success", "page_source": driver.page_source}


def take_screenshot():
    global driver
    with driver_lock:
        screenshot_base64 = driver.get_screenshot_as_base64()
        return {"status": "success", "screenshot": screenshot_base64}


def long_press(data):
    global driver
    with driver_lock:
        el = driver.find_element(getattr(AppiumBy, data['by'].upper()), data['value'])
        action = webdriver.common.touch_action.TouchAction(driver)
        action.long_press(el, duration=data.get('duration', 2000)).release().perform()
    return {"status": "long_pressed"}


def status_info():
    return {
        "appium_running": appium_process is not None,
        "driver_active": driver is not None
    }

# Flask routes ---------------------------------------------------------------

@app.route('/connect', methods=['POST'])
def http_connect():
    result = connect_driver(request.json)
    return jsonify(result), (400 if result.get('status') == 'error' else 200)


@app.route('/disconnect', methods=['POST'])
def http_disconnect():
    return jsonify(disconnect_driver())


@app.route('/click', methods=['POST'])
def http_click():
    try:
        result = click_element(request.json)
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "failed", "reason": str(e)}), 500


@app.route('/swipe', methods=['POST'])
def http_swipe():
    try:
        return jsonify(swipe_screen(request.json))
    except Exception as e:
        return jsonify({"status": "failed", "reason": str(e)}), 500


@app.route('/is_displayed', methods=['POST'])
def http_is_displayed():
    try:
        return jsonify(element_displayed(request.json))
    except Exception as e:
        return jsonify({"status": "failed", "reason": str(e)}), 500


@app.route('/get_attribute', methods=['POST'])
def http_get_attribute():
    try:
        return jsonify(get_attribute_value(request.json))
    except Exception as e:
        return jsonify({"status": "failed", "reason": str(e)}), 500


@app.route('/get_page_source', methods=['GET'])
def http_get_page_source():
    try:
        return jsonify(get_source())
    except Exception as e:
        return jsonify({"status": "failed", "reason": str(e)}), 500


@app.route('/screenshot', methods=['GET'])
def http_screenshot():
    try:
        return jsonify(take_screenshot())
    except Exception as e:
        return jsonify({"status": "failed", "reason": str(e)}), 500


@app.route('/long_press', methods=['POST'])
def http_long_press():
    try:
        return jsonify(long_press(request.json))
    except Exception as e:
        return jsonify({"status": "failed", "reason": str(e)}), 500


@app.route('/status', methods=['GET'])
def http_status():
    return jsonify(status_info())


# WebSocket server -----------------------------------------------------------

async def websocket_handler(websocket):
    while True:
        try:
            message = await websocket.recv()
        except websockets.ConnectionClosed:
            break
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            await websocket.send(json.dumps({"status": "error", "reason": "invalid json"}))
            continue
        cmd = data.get("command")
        try:
            if cmd == "connect":
                result = connect_driver(data.get("capabilities", {}))
            elif cmd == "disconnect":
                result = disconnect_driver()
            elif cmd == "click":
                result = click_element(data)
            elif cmd == "swipe":
                result = swipe_screen(data)
            elif cmd == "is_displayed":
                result = element_displayed(data)
            elif cmd == "get_attribute":
                result = get_attribute_value(data)
            elif cmd == "get_page_source":
                result = get_source()
            elif cmd == "screenshot":
                result = take_screenshot()
            elif cmd == "long_press":
                result = long_press(data)
            elif cmd == "status":
                result = status_info()
            else:
                result = {"status": "error", "reason": "unknown command"}
        except Exception as e:
            result = {"status": "failed", "reason": str(e)}
        await websocket.send(json.dumps(result))


def start_websocket_server():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    server = websockets.serve(websocket_handler, "0.0.0.0", 8765)
    loop.run_until_complete(server)
    loop.run_forever()


if __name__ == '__main__':
    ws_thread = Thread(target=start_websocket_server, daemon=True)
    ws_thread.start()
    app.run(host='0.0.0.0', port=6000, debug=True, threaded=True)
