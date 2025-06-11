import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from src.android import AndroidRobot, ScreenSize
from src.webdriver_agent import ScreenSize as WdaScreenSize
from src.webdriver_agent import WebDriverAgent


class DummySession:
    def __init__(self, posts):
        self.posts = posts

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def post(self, url, json=None):
        self.posts.append((url, json))

        class Resp:
            async def json(self_inner):
                return {}

        return Resp()


class TestSwipeGestures(unittest.TestCase):
    def test_android_swipe_left(self):
        robot = AndroidRobot("serial")
        mock_size = ScreenSize(width=1000, height=2000, scale=1)
        with patch.object(
            robot, "get_screen_size", AsyncMock(return_value=mock_size)
        ), patch.object(robot, "adb") as mock_adb:
            asyncio.run(robot.swipe("left"))
            args = mock_adb.call_args[0]
            self.assertEqual(args[0], "shell")
            self.assertEqual(args[1], "input")
            self.assertEqual(args[2], "swipe")
            self.assertEqual(args[3:], ("800", "1000", "200", "1000", "1000"))

    def test_android_swipe_between_points(self):
        robot = AndroidRobot("serial")
        with patch.object(robot, "adb") as mock_adb:
            asyncio.run(robot.swipe_between_points(10, 20, 30, 40))
            args = mock_adb.call_args[0]
            self.assertEqual(args[0], "shell")
            self.assertEqual(args[1], "input")
            self.assertEqual(args[2], "swipe")
            self.assertEqual(args[3:], ("10", "20", "30", "40", "1000"))

    def test_wda_swipe_right(self):
        wda = WebDriverAgent("localhost", 8100)
        posts = []
        with patch.object(
            wda,
            "get_screen_size",
            AsyncMock(return_value=WdaScreenSize(width=1000, height=1000, scale=1)),
        ), patch.object(
            wda, "within_session", side_effect=lambda fn: fn("http://localhost:8100/session/1")
        ), patch(
            "aiohttp.ClientSession", lambda: DummySession(posts)
        ):
            asyncio.run(wda.swipe("right"))
            self.assertEqual(posts[0][0], "http://localhost:8100/session/1/actions")
            actions = posts[0][1]["actions"][0]["actions"]
            self.assertEqual(actions[0]["x"], 200)
            self.assertEqual(actions[0]["y"], 500)
            self.assertEqual(actions[2]["x"], 800)
            self.assertEqual(actions[2]["y"], 500)

    def test_wda_swipe_between_points(self):
        wda = WebDriverAgent("localhost", 8100)
        posts = []
        with patch.object(
            wda, "within_session", side_effect=lambda fn: fn("http://localhost:8100/session/1")
        ), patch(
            "aiohttp.ClientSession", lambda: DummySession(posts)
        ):
            asyncio.run(wda.swipe_between_points(1, 2, 3, 4))
            self.assertEqual(posts[0][0], "http://localhost:8100/session/1/actions")
            actions = posts[0][1]["actions"][0]["actions"]
            self.assertEqual(actions[0]["x"], 1)
            self.assertEqual(actions[0]["y"], 2)
            self.assertEqual(actions[2]["x"], 3)
            self.assertEqual(actions[2]["y"], 4)


if __name__ == "__main__":
    unittest.main()
