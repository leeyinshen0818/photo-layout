import unittest

from photo_print_layout.crop import (
    MAX_ZOOM,
    CropState,
    constrained_crop_state,
    crop_source_rect,
    pan_crop_state,
)
from photo_print_layout.layout import calculate_layout
from photo_print_layout.models import LayoutSettings, Position, ResizeMode, SUPER_A3


class CropStateTests(unittest.TestCase):
    def test_default_crop_is_centered_minimum_cover(self):
        rect = crop_source_rect(CropState(), 2000, 4000, 11, 14)
        self.assertAlmostEqual(rect.x, 0.0)
        self.assertAlmostEqual(rect.width, 2000.0)
        self.assertAlmostEqual(rect.y, (4000.0 - rect.height) / 2.0)
        self.assertAlmostEqual((rect.x + rect.width / 2.0) / 2000.0, 0.5)
        self.assertAlmostEqual((rect.y + rect.height / 2.0) / 4000.0, 0.5)

    def test_zoom_shrinks_source_rect_but_keeps_target_ratio(self):
        base = crop_source_rect(CropState(), 2000, 4000, 11, 14)
        zoomed = crop_source_rect(CropState(zoom=2.0), 2000, 4000, 11, 14)
        self.assertAlmostEqual(zoomed.width, base.width / 2.0)
        self.assertAlmostEqual(zoomed.height, base.height / 2.0)
        self.assertAlmostEqual(zoomed.width / zoomed.height, 11 / 14)

    def test_pan_is_constrained_to_image_edges(self):
        state = pan_crop_state(CropState(zoom=2.0), 100, -100, 2000, 4000, 11, 14)
        rect = crop_source_rect(state, 2000, 4000, 11, 14)
        self.assertGreaterEqual(rect.x, 0.0)
        self.assertGreaterEqual(rect.y, 0.0)
        self.assertLessEqual(rect.x + rect.width, 2000.0)
        self.assertLessEqual(rect.y + rect.height, 4000.0)

    def test_reset_state_is_centered_minimum_cover(self):
        changed = CropState(zoom=3.2, center_x=0.2, center_y=0.8)
        reset = CropState()
        self.assertNotEqual(changed, reset)
        self.assertEqual(reset, CropState(zoom=1.0, center_x=0.5, center_y=0.5))

    def test_state_is_logical_and_clamps_zoom(self):
        state = constrained_crop_state(CropState(99.0, -10.0, 10.0), 2000, 4000, 11, 14)
        self.assertEqual(state.zoom, MAX_ZOOM)
        self.assertGreaterEqual(state.center_x, 0.0)
        self.assertLessEqual(state.center_y, 1.0)
        self.assertEqual(set(state.__dataclass_fields__), {"zoom", "center_x", "center_y"})

    def test_source_crop_is_independent_of_paper_and_position(self):
        crop = CropState(2.25, 0.4, 0.62)
        first = calculate_layout(
            LayoutSettings(resize_mode=ResizeMode.CROP), 2000, 4000, crop
        )
        second = calculate_layout(
            LayoutSettings(
                paper=SUPER_A3,
                position=Position.CENTER,
                resize_mode=ResizeMode.CROP,
            ),
            2000,
            4000,
            crop,
        )
        self.assertEqual(first.source, second.source)


if __name__ == "__main__":
    unittest.main()
