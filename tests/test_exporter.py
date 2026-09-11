import hashlib
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage, QImageReader

from photo_print_layout.crop import CropState, constrained_crop_state
from photo_print_layout.exporter import (
    ExportError,
    ensure_jpeg_extension,
    export_jpeg,
    paper_pixel_size,
    render_paper_canvas,
    pixels_for_mm,
)
from photo_print_layout.image_loader import LoadedPhoto, load_photo
from photo_print_layout.layout import calculate_layout
from photo_print_layout.models import (
    LayoutSettings,
    Position,
    ResizeMode,
    SizeMM,
    SUPER_A3,
)


def colored_photo(width: int = 100, height: int = 200) -> LoadedPhoto:
    image = QImage(width, height, QImage.Format.Format_RGBA8888)
    image.fill(QColor("#d23b3b"))
    return LoadedPhoto(Path("memory.png"), width, height, image)


class ExporterTests(unittest.TestCase):
    def test_jpeg_extension_is_appended_or_replaced(self):
        self.assertEqual(ensure_jpeg_extension("layout"), Path("layout.jpg"))
        self.assertEqual(ensure_jpeg_extension("layout.png"), Path("layout.jpg"))
        self.assertEqual(ensure_jpeg_extension("layout.jpeg"), Path("layout.jpeg"))

    def test_300_dpi_dimensions_follow_true_physical_paper(self):
        self.assertEqual(paper_pixel_size(LayoutSettings()), (3508, 4961))
        self.assertEqual(
            paper_pixel_size(LayoutSettings(photo_size_mm=SizeMM(14 * 25.4, 11 * 25.4))),
            (4961, 3508),
        )
        self.assertEqual(
            paper_pixel_size(LayoutSettings(paper=SUPER_A3)),
            (3886, 5705),
        )

    def test_fit_export_uses_white_paper_and_center_position(self):
        settings = LayoutSettings(position=Position.CENTER, dpi=10)
        canvas = render_paper_canvas(colored_photo(), settings, CropState())
        self.assertEqual(canvas.pixelColor(0, 0), QColor("white"))
        self.assertNotEqual(
            canvas.pixelColor(canvas.width() // 2, canvas.height() // 2), QColor("white")
        )

    def test_custom_photo_size_converts_to_exact_300_dpi_target_pixels(self):
        settings = LayoutSettings(photo_size_mm=SizeMM(10 * 25.4, 12 * 25.4))
        layout = calculate_layout(settings, 100, 200)
        self.assertEqual(pixels_for_mm(layout.target.width, settings.dpi), 3000)
        self.assertEqual(pixels_for_mm(layout.target.height, settings.dpi), 3600)

    def test_crop_export_uses_selected_source_crop(self):
        photo = colored_photo()
        for y in range(photo.height):
            for x in range(photo.width // 2, photo.width):
                photo.image.setPixelColor(x, y, QColor("#2457c5"))
        settings = LayoutSettings(resize_mode=ResizeMode.CROP, dpi=10)
        crop = constrained_crop_state(
            CropState(0.55, 0.3, 0.4, 0.3), 100, 200, 11, 14
        )
        canvas = render_paper_canvas(photo, settings, crop)
        center = canvas.pixelColor(canvas.width() // 3, canvas.height() // 3)
        self.assertGreater(center.blue(), center.red())

    def test_export_writes_real_jpeg_at_300_dpi_without_touching_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.png"
            Image.new("RGB", (40, 80), "green").save(source)
            before = hashlib.sha256(source.read_bytes()).digest()
            photo = load_photo(source)
            output = export_jpeg(
                Path(directory) / "paper-layout",
                photo,
                LayoutSettings(),
                CropState(),
            )
            reader = QImageReader(str(output))
            self.assertEqual(reader.format().toLower(), b"jpeg")
            self.assertEqual(reader.size(), QSize(3508, 4961))
            reader.setFileName("")
            del reader
            self.assertEqual(before, hashlib.sha256(source.read_bytes()).digest())

    def test_export_refuses_to_overwrite_original_source(self):
        memory = colored_photo()
        photo = LoadedPhoto(Path("original.jpg"), memory.width, memory.height, memory.image)
        with self.assertRaises(ExportError):
            export_jpeg(photo.path, photo, LayoutSettings(dpi=10), CropState())


if __name__ == "__main__":
    unittest.main()
