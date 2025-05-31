import base64
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from png import PNG

class TestPNG(unittest.TestCase):
    def test_parse_png(self):
        buffer = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAAD0lEQVR4nGNgYAAAAAMAAWgmWQ0AAAAASUVORK5CYII="
        )
        png = PNG(base64.b64decode(buffer))
        dims = png.get_dimensions()
        self.assertEqual(dims.width, 1)
        self.assertEqual(dims.height, 1)

    def test_invalid_png(self):
        with self.assertRaises(ValueError):
            PNG(b"IAMADUCK").get_dimensions()

if __name__ == "__main__":
    unittest.main()
