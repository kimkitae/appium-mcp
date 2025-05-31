import asyncio
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    from ios import IosManager, IosRobot
except Exception:  # pragma: no cover - skip if dependencies missing
    IosManager = None  # type: ignore
    IosRobot = None  # type: ignore

class TestIOS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if IosManager is None:
            raise unittest.SkipTest("iOS dependencies missing")
        cls.manager = IosManager()
        cls.devices = asyncio.run(cls.manager.list_devices())
        cls.has_device = len(cls.devices) == 1
        cls.robot = IosRobot(cls.devices[0].device_id) if cls.has_device else None

    def setUp(self):
        if not self.has_device:
            self.skipTest("Requires exactly one iOS device")

    def test_get_screenshot(self):
        screenshot = asyncio.run(self.robot.get_screenshot())
        self.assertGreater(len(screenshot), 64 * 1024)

if __name__ == "__main__":
    unittest.main()
