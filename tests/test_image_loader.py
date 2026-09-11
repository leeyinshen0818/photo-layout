import hashlib
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from photo_print_layout.image_loader import load_photo


class ImageLoaderTests(unittest.TestCase):
    def test_exif_orientation_is_applied_without_modifying_source(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "oriented.jpg"
            image = Image.new("RGB", (40, 20), "red")
            exif = Image.Exif()
            exif[274] = 6  # Rotate 90 degrees clockwise for display.
            image.save(path, exif=exif)

            before = hashlib.sha256(path.read_bytes()).digest()
            loaded = load_photo(path)
            after = hashlib.sha256(path.read_bytes()).digest()

            self.assertEqual((loaded.width, loaded.height), (20, 40))
            self.assertFalse(loaded.image.isNull())
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
