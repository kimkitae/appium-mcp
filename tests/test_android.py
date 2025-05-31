import asyncio
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.android import AndroidRobot, AndroidDeviceManager
from src.png import PNG

class TestAndroid(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manager = AndroidDeviceManager()
        cls.devices = manager.get_connected_devices()
        cls.has_device = len(cls.devices) == 1
        cls.android = AndroidRobot(cls.devices[0].device_id) if cls.has_device else None

    def setUp(self):
        if not self.has_device:
            self.skipTest("Requires exactly one Android device")

    def test_get_screen_size(self):
        screen_size = asyncio.run(self.android.get_screen_size())
        self.assertGreater(screen_size.width, 1024)
        self.assertGreater(screen_size.height, 1024)
        self.assertEqual(screen_size.scale, 1)
        self.assertEqual(len(screen_size.__dict__), 3)

    def test_take_screenshot(self):
        screen_size = asyncio.run(self.android.get_screen_size())
        screenshot = asyncio.run(self.android.get_screenshot())
        self.assertGreater(len(screenshot), 64 * 1024)
        image = PNG(screenshot)
        png_size = image.get_dimensions()
        self.assertEqual(png_size.width, screen_size.width)
        self.assertEqual(png_size.height, screen_size.height)

    def test_list_apps(self):
        apps = asyncio.run(self.android.list_apps())
        packages = [app.package_name for app in apps]
        self.assertIn("com.android.settings", packages)

if __name__ == "__main__":
    unittest.main()
