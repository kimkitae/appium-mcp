import unittest
from unittest.mock import patch

from src.iphone_simulator import SimctlManager, Simulator
from src.robot import ActionableError


class TestSimctlManager(unittest.TestCase):
    def test_get_simulator_with_name(self):
        manager = SimctlManager()
        simulators = [
            Simulator(name="iPhone 16", uuid="udid-1", state="Booted"),
            Simulator(name="iPhone 15", uuid="udid-2", state="Shutdown"),
        ]

        with patch.object(manager, "list_simulators", return_value=simulators):
            robot = manager.get_simulator("iPhone 16")
            self.assertEqual(robot.simulator_uuid, "udid-1")

    def test_get_simulator_with_duplicate_name_raises(self):
        manager = SimctlManager()
        simulators = [
            Simulator(name="iPhone", uuid="udid-1", state="Booted"),
            Simulator(name="iPhone", uuid="udid-2", state="Shutdown"),
        ]

        with patch.object(manager, "list_simulators", return_value=simulators):
            with self.assertRaises(ActionableError):
                manager.get_simulator("iPhone")


if __name__ == "__main__":
    unittest.main()
