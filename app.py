from flask import Flask, request, jsonify
from appium import webdriver
from appium.webdriver.common.appiumby import AppiumBy
from appium.options.android import UiAutomator2Options
from appium.options.ios import XCUITestOptions
from subprocess import Popen, DEVNULL
import time
import requests
from threading import Lock

app = Flask(__name__)

driver = None
appium_process = None
driver_lock = Lock()

def start_appium():
    global appium_process
    if appium_process is None:
        appium_process = Popen([
            "appium", "server",
            "--session-override",
            "--relaxed-security",
            "--log-level", "warn"
        ], stdout=DEVNULL, stderr=DEVNULL)
        wait_for_appium_ready()

def wait_for_appium_ready(timeout=10):
    url = "http://localhost:4723/status"
    for _ in range(timeout * 10):
        try:
            response = requests.get(url)
            if response.status_code == 200:
                return
        except:
            pass
        time.sleep(0.1)
    raise RuntimeError("Appium 서버 실행 실패")

def stop_appium():
    global appium_process
    if appium_process:
        appium_process.terminate()
        appium_process.wait()
        appium_process = None

@app.route('/connect', methods=['POST'])
def connect():
    global driver
    capabilities = request.json
    platform = capabilities.get("platformName", "").lower()

    start_appium()

    if platform == "android":
        options = UiAutomator2Options().load_capabilities(capabilities)
    elif platform == "ios":
        options = XCUITestOptions().load_capabilities(capabilities)
    else:
        return jsonify({"status": "error", "reason": "Unsupported platform"}), 400

    with driver_lock:
        if driver:
            driver.quit()
        driver = webdriver.Remote("http://localhost:4723", options=options)

    return jsonify({"status": "connected"})

@app.route('/click', methods=['POST'])
def click_element():
    global driver
    locator = request.json
    with driver_lock:
        try:
            el = driver.find_element(
                getattr(AppiumBy, locator['by'].upper()), locator['value']
            )
            el.click()
            return jsonify({"status": "clicked"})
        except Exception as e:
            return jsonify({"status": "failed", "reason": str(e)}), 500

@app.route('/disconnect', methods=['POST'])
def disconnect():
    global driver
    with driver_lock:
        if driver:
            driver.quit()
            driver = None
        stop_appium()

    return jsonify({"status": "disconnected"})

@app.route('/status', methods=['GET'])
def status():
    appium_running = appium_process is not None
    driver_active = driver is not None
    return jsonify({
        "appium_running": appium_running,
        "driver_active": driver_active
    })

@app.route('/screenshot', methods=['GET'])
def screenshot():
    global driver
    with driver_lock:
        try:
            screenshot_base64 = driver.get_screenshot_as_base64()
            return jsonify({"status": "success", "screenshot": screenshot_base64})
        except Exception as e:
            return jsonify({"status": "failed", "reason": str(e)}), 500

@app.route('/swipe', methods=['POST'])
def swipe():
    global driver
    data = request.json
    with driver_lock:
        try:
            driver.swipe(data['start_x'], data['start_y'], data['end_x'], data['end_y'], data.get('duration', 800))
            return jsonify({"status": "swiped"})
        except Exception as e:
            return jsonify({"status": "failed", "reason": str(e)}), 500

@app.route('/is_displayed', methods=['POST'])
def is_displayed():
    global driver
    locator = request.json
    with driver_lock:
        try:
            el = driver.find_element(getattr(AppiumBy, locator['by'].upper()), locator['value'])
            return jsonify({"status": "success", "is_displayed": el.is_displayed()})
        except Exception as e:
            return jsonify({"status": "failed", "reason": str(e)}), 500

@app.route('/get_attribute', methods=['POST'])
def get_attribute():
    global driver
    data = request.json
    with driver_lock:
        try:
            el = driver.find_element(getattr(AppiumBy, data['by'].upper()), data['value'])
            attribute_value = el.get_attribute(data['attribute'])
            return jsonify({"status": "success", "attribute": attribute_value})
        except Exception as e:
            return jsonify({"status": "failed", "reason": str(e)}), 500

@app.route('/get_page_source', methods=['GET'])
def get_page_source():
    global driver
    with driver_lock:
        try:
            source = driver.page_source
            return jsonify({"status": "success", "page_source": source})
        except Exception as e:
            return jsonify({"status": "failed", "reason": str(e)}), 500

@app.route('/long_press', methods=['POST'])
def long_press():
    global driver
    data = request.json
    with driver_lock:
        try:
            el = driver.find_element(getattr(AppiumBy, data['by'].upper()), data['value'])
            action = webdriver.common.touch_action.TouchAction(driver)
            action.long_press(el, duration=data.get('duration', 2000)).release().perform()
            return jsonify({"status": "long_pressed"})
        except Exception as e:
            return jsonify({"status": "failed", "reason": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=6000, debug=True, threaded=True)