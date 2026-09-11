import hashlib
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from photo_print_layout.image_loader import (
    ImageOrientation,
    image_orientation,
    load_photo,
)
from photo_print_layout.layout import calculate_layout
from photo_print_layout.models import (
    LayoutSettings,
    Orientation,
    ResizeMode,
    SizeMM,
    layout_orientation_for_dimensions,
)


class ImageLoaderTests(unittest.TestCase):
    def test_orientation_helper_handles_portrait_landscape_and_square(self):
        self.assertEqual(image_orientation(20, 40), ImageOrientation.PORTRAIT)
        self.assertEqual(image_orientation(40, 20), ImageOrientation.LANDSCAPE)
        self.assertEqual(image_orientation(20, 20), ImageOrientation.SQUARE)
        self.assertEqual(layout_orientation_for_dimensions(20, 40), Orientation.PORTRAIT)
        self.assertEqual(layout_orientation_for_dimensions(40, 20), Orientation.LANDSCAPE)
        self.assertEqual(layout_orientation_for_dimensions(20, 20), Orientation.PORTRAIT)

    def test_portrait_source_for_portrait_target_is_not_rotated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "portrait.png"
            Image.new("RGB", (20, 40), "blue").save(path)

            loaded = load_photo(path)

            self.assertEqual((loaded.width, loaded.height), (20, 40))
            self.assertEqual(loaded.layout_rotation_degrees, 0)

    def test_landscape_source_keeps_orientation_and_source_is_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "landscape.png"
            Image.new("RGB", (40, 20), "green").save(path)
            before = hashlib.sha256(path.read_bytes()).digest()

            loaded = load_photo(path)

            self.assertEqual((loaded.width, loaded.height), (40, 20))
            self.assertEqual(loaded.layout_rotation_degrees, 0)
            self.assertEqual(before, hashlib.sha256(path.read_bytes()).digest())

    def test_crop_and_fit_both_use_normalized_working_dimensions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "landscape.png"
            Image.new("RGB", (40, 20), "green").save(path)
            loaded = load_photo(path)
            orientation = layout_orientation_for_dimensions(loaded.width, loaded.height)
            self.assertEqual(orientation, Orientation.LANDSCAPE)
            landscape_target = SizeMM(14 * 25.4, 11 * 25.4)

            crop = calculate_layout(
                LayoutSettings(resize_mode=ResizeMode.CROP, photo_size_mm=landscape_target),
                loaded.width,
                loaded.height,
            )
            fit = calculate_layout(
                LayoutSettings(resize_mode=ResizeMode.FIT, photo_size_mm=landscape_target),
                loaded.width,
                loaded.height,
            )

            self.assertEqual(crop.source.height, 20.0)
            self.assertLess(crop.source.width, 40.0)
            self.assertEqual((fit.source.width, fit.source.height), (40.0, 20.0))
            self.assertAlmostEqual(fit.image.width, fit.target.width)
            self.assertLess(fit.image.height, fit.target.height)

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
            self.assertEqual(loaded.layout_rotation_degrees, 0)
            self.assertFalse(loaded.image.isNull())
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
