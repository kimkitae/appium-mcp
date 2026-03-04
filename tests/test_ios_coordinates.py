import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.ios import IosRobot
from src.robot import ScreenSize


class TestIosCoordinateScaling(unittest.TestCase):
    def test_tap_scales_coordinates(self):
        robot = IosRobot("serial")
        mock_wda = MagicMock()
        mock_wda.get_screen_size = AsyncMock(return_value=ScreenSize(width=100, height=200, scale=2))
        mock_wda.tap = AsyncMock()
        with patch.object(robot, "_wda", AsyncMock(return_value=mock_wda)):
            asyncio.run(robot.tap(40, 60))
            mock_wda.tap.assert_awaited_with(20, 30)

    def test_swipe_between_points_scales_coordinates(self):
        robot = IosRobot("serial")
        mock_wda = MagicMock()
        mock_wda.get_screen_size = AsyncMock(return_value=ScreenSize(width=100, height=200, scale=2))
        mock_wda.swipe_between_points = AsyncMock()
        with patch.object(robot, "_wda", AsyncMock(return_value=mock_wda)):
            asyncio.run(robot.swipe_between_points(40, 60, 80, 120))
            mock_wda.swipe_between_points.assert_awaited_with(20, 30, 40, 60)

    def test_swipe_from_coordinate_scales_coordinates_and_distance(self):
        robot = IosRobot("serial")
        mock_wda = MagicMock()
        mock_wda.get_screen_size = AsyncMock(return_value=ScreenSize(width=100, height=200, scale=2))
        mock_wda.swipe_from_coordinate = AsyncMock()
        with patch.object(robot, "_wda", AsyncMock(return_value=mock_wda)):
            asyncio.run(robot.swipe_from_coordinate(40, 60, "up", 80))
            mock_wda.swipe_from_coordinate.assert_awaited_with(20, 30, "up", 40)

    def test_drag_between_points_scales_coordinates(self):
        robot = IosRobot("serial")
        mock_wda = MagicMock()
        mock_wda.get_screen_size = AsyncMock(return_value=ScreenSize(width=100, height=200, scale=2))
        mock_wda.drag_between_points = AsyncMock()
        with patch.object(robot, "_wda", AsyncMock(return_value=mock_wda)):
            asyncio.run(robot.drag_between_points(40, 60, 100, 140, hold_ms=100, move_ms=800))
            mock_wda.drag_between_points.assert_awaited_with(
                20, 30, 50, 70, hold_ms=100, move_ms=800
            )


if __name__ == "__main__":
    unittest.main()
