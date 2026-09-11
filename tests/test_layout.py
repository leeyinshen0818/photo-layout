import unittest

from photo_print_layout.layout import calculate_layout
from photo_print_layout.models import LayoutSettings, Position, ResizeMode, SUPER_A3, SizeMM


class LayoutTests(unittest.TestCase):
    def test_default_target_is_top_left_and_uses_physical_size(self):
        layout = calculate_layout(LayoutSettings())
        self.assertEqual((layout.paper.width, layout.paper.height), (297.0, 420.0))
        self.assertAlmostEqual(layout.target.width, 279.4)
        self.assertAlmostEqual(layout.target.height, 355.6)
        self.assertEqual((layout.target.x, layout.target.y), (0.0, 0.0))

    def test_center_position_is_exact(self):
        settings = LayoutSettings(paper=SUPER_A3, position=Position.CENTER)
        layout = calculate_layout(settings)
        self.assertAlmostEqual(layout.target.x, (329.0 - 279.4) / 2)
        self.assertAlmostEqual(layout.target.y, (483.0 - 355.6) / 2)

    def test_landscape_source_is_center_cropped(self):
        layout = calculate_layout(LayoutSettings(resize_mode=ResizeMode.CROP), 4000, 2000)
        self.assertAlmostEqual(layout.source.height, 2000)
        self.assertLess(layout.source.width, 4000)
        self.assertAlmostEqual(layout.source.x, (4000 - layout.source.width) / 2)
        self.assertEqual(layout.image, layout.target)

    def test_fit_inside_keeps_full_source_and_centers_image(self):
        settings = LayoutSettings(resize_mode=ResizeMode.FIT)
        layout = calculate_layout(settings, 4000, 2000)
        self.assertEqual((layout.source.x, layout.source.y), (0.0, 0.0))
        self.assertEqual((layout.source.width, layout.source.height), (4000.0, 2000.0))
        self.assertAlmostEqual(layout.image.width, layout.target.width)
        self.assertLess(layout.image.height, layout.target.height)
        self.assertAlmostEqual(
            layout.image.y, layout.target.y + (layout.target.height - layout.image.height) / 2
        )

    def test_landscape_orientation_rotates_paper_and_photo_target(self):
        settings = LayoutSettings(photo_size_mm=SizeMM(14 * 25.4, 11 * 25.4))
        layout = calculate_layout(settings, 4000, 2000)
        self.assertEqual((layout.paper.width, layout.paper.height), (420.0, 297.0))
        self.assertAlmostEqual(layout.target.width, 14 * 25.4)
        self.assertAlmostEqual(layout.target.height, 11 * 25.4)
        self.assertGreater(layout.paper.width, layout.paper.height)
        self.assertAlmostEqual(layout.target.width / layout.target.height, 14 / 11)
        super_layout = calculate_layout(
            LayoutSettings(paper=SUPER_A3, photo_size_mm=SizeMM(14 * 25.4, 11 * 25.4))
        )
        self.assertEqual((super_layout.paper.width, super_layout.paper.height), (483.0, 329.0))


if __name__ == "__main__":
    unittest.main()
