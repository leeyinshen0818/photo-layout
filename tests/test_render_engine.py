import unittest
from pathlib import Path

from PySide6.QtGui import QColor, QImage

from photo_print_layout.crop import CropState, crop_source_rect
from photo_print_layout.image_loader import LoadedPhoto
from photo_print_layout.models import LayoutSettings, Position, ResizeMode, SizeMM, SUPER_A3
from photo_print_layout.render_engine import (
    build_render_plan,
    paper_pixel_size,
    pixels_for_mm,
    render_plan,
)


def split_photo(width: int = 100, height: int = 100) -> LoadedPhoto:
    image = QImage(width, height, QImage.Format.Format_RGBA8888)
    image.fill(QColor("red"))
    for y in range(height):
        for x in range(width // 2, width):
            image.setPixelColor(x, y, QColor("blue"))
    return LoadedPhoto(Path("split.png"), width, height, image)


class RenderEngineTests(unittest.TestCase):
    def test_physical_conversions_and_paper_dimensions(self):
        self.assertEqual(pixels_for_mm(25.4, 300), 300)
        self.assertEqual(pixels_for_mm(8 * 25.4, 300), 2400)
        self.assertEqual(pixels_for_mm(10 * 25.4, 300), 3000)
        self.assertEqual(pixels_for_mm(12 * 25.4, 300), 3600)
        self.assertEqual(pixels_for_mm(250.0, 300), 2953)
        self.assertEqual(paper_pixel_size(LayoutSettings()), (3508, 4961))
        self.assertEqual(
            paper_pixel_size(LayoutSettings(photo_size_mm=SizeMM(14 * 25.4, 11 * 25.4))),
            (4961, 3508),
        )
        self.assertEqual(paper_pixel_size(LayoutSettings(paper=SUPER_A3)), (3900, 5700))
        self.assertEqual(
            paper_pixel_size(
                LayoutSettings(paper=SUPER_A3, photo_size_mm=SizeMM(19 * 25.4, 13 * 25.4))
            ),
            (5700, 3900),
        )

    def test_custom_target_is_exact_and_positioned_from_physical_geometry(self):
        size = SizeMM(10 * 25.4, 12 * 25.4)
        left = build_render_plan(LayoutSettings(photo_size_mm=size), 100, 100, CropState())
        self.assertEqual((left.target.x, left.target.y), (0, 0))
        self.assertEqual((left.target.width, left.target.height), (3000, 3600))

        landscape = build_render_plan(
            LayoutSettings(photo_size_mm=SizeMM(12 * 25.4, 10 * 25.4)),
            100,
            100,
            CropState(),
        )
        self.assertEqual((landscape.target.width, landscape.target.height), (3600, 3000))
        self.assertGreater(landscape.canvas_width, landscape.canvas_height)

        center = build_render_plan(
            LayoutSettings(photo_size_mm=size, position=Position.CENTER),
            100,
            100,
            CropState(),
        )
        self.assertLessEqual(
            abs((center.canvas_width - center.target.width) - 2 * center.target.x), 1
        )
        self.assertLessEqual(
            abs((center.canvas_height - center.target.height) - 2 * center.target.y), 1
        )

    def test_crop_plan_preserves_saved_source_rectangle_and_fills_target(self):
        photo = split_photo()
        crop = CropState(0.5, 0.25, 0.5, 0.5)
        settings = LayoutSettings(
            photo_size_mm=SizeMM(25.4, 25.4),
            resize_mode=ResizeMode.CROP,
            dpi=10,
        )
        plan = build_render_plan(settings, photo.width, photo.height, crop)
        self.assertEqual(
            plan.source,
            crop_source_rect(crop, photo.width, photo.height, 25.4, 25.4),
        )
        self.assertEqual((plan.image.width, plan.image.height), (10, 10))
        canvas = render_plan(photo, plan)
        self.assertGreater(canvas.getpixel((5, 5))[2], canvas.getpixel((5, 5))[0])

    def test_fit_uses_full_source_and_leaves_internal_white_space(self):
        photo = split_photo(100, 50)
        settings = LayoutSettings(photo_size_mm=SizeMM(25.4, 25.4), dpi=10)
        plan = build_render_plan(settings, photo.width, photo.height, CropState())
        self.assertEqual((plan.source.x, plan.source.y), (0.0, 0.0))
        self.assertEqual((plan.source.width, plan.source.height), (100.0, 50.0))
        self.assertEqual((plan.target.width, plan.target.height), (10, 10))
        self.assertEqual((plan.image.width, plan.image.height), (10, 5))
        canvas = render_plan(photo, plan)
        self.assertEqual(canvas.getpixel((5, 0)), (255, 255, 255))
        self.assertNotEqual(canvas.getpixel((5, plan.image.y + 2)), (255, 255, 255))

    def test_preview_and_final_plans_share_physical_and_crop_geometry(self):
        settings = LayoutSettings(
            photo_size_mm=SizeMM(203.2, 254.0),
            position=Position.CENTER,
            resize_mode=ResizeMode.CROP,
        )
        crop = CropState(0.1, 0.1, 0.8, 0.8)
        final = build_render_plan(settings, 800, 1000, crop)
        preview = build_render_plan(
            settings, 800, 1000, crop, canvas_size=(350, 495)
        )
        self.assertEqual(preview.layout, final.layout)
        self.assertEqual(preview.source, final.source)
        self.assertAlmostEqual(
            preview.target.x / preview.canvas_width,
            final.target.x / final.canvas_width,
            delta=1 / preview.canvas_width,
        )
        self.assertAlmostEqual(
            preview.target.width / preview.canvas_width,
            final.target.width / final.canvas_width,
            delta=1 / preview.canvas_width,
        )

    def test_invalid_layout_cannot_build_a_render_plan(self):
        with self.assertRaises(ValueError):
            build_render_plan(
                LayoutSettings(photo_size_mm=SizeMM(500, 500)),
                100,
                100,
                CropState(),
            )


if __name__ == "__main__":
    unittest.main()
