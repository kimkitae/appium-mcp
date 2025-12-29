import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.ios import IosRobot
from src.robot import ScreenSize


class TestIosCoordinateScaling(unittest.TestCase):
    """iOS 좌표는 point(논리적) 단위로 직접 전달됩니다 (스케일 변환 없음)."""

    def test_tap_passes_coordinates_directly(self):
        """tap은 좌표를 스케일 변환 없이 그대로 WDA에 전달해야 합니다."""
        robot = IosRobot("serial")
        mock_wda = MagicMock()
        mock_wda.tap = AsyncMock()
        with patch.object(robot, "_wda", AsyncMock(return_value=mock_wda)):
            asyncio.run(robot.tap(40, 60))
            mock_wda.tap.assert_awaited_with(40, 60)

    def test_swipe_between_points_passes_coordinates_directly(self):
        """swipe_between_points는 좌표를 스케일 변환 없이 그대로 WDA에 전달해야 합니다."""
        robot = IosRobot("serial")
        mock_wda = MagicMock()
        mock_wda.swipe_between_points = AsyncMock()
        with patch.object(robot, "_wda", AsyncMock(return_value=mock_wda)):
            asyncio.run(robot.swipe_between_points(40, 60, 80, 120))
            mock_wda.swipe_between_points.assert_awaited_with(40, 60, 80, 120)


if __name__ == "__main__":
    unittest.main()
