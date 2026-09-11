import unittest

from photo_print_layout.crop import (
    CropState,
    constrained_crop_state,
    crop_source_rect,
    default_crop_state,
    move_crop_state,
    resize_crop_state,
)
from photo_print_layout.layout import calculate_layout
from photo_print_layout.models import LayoutSettings, Position, ResizeMode, SUPER_A3


class CropStateTests(unittest.TestCase):
    def test_default_crop_is_largest_centered_fixed_ratio(self):
        state = default_crop_state(2000, 4000, 11, 14)
        rect = crop_source_rect(state, 2000, 4000, 11, 14)
        self.assertAlmostEqual(rect.width / rect.height, 11 / 14)
        self.assertAlmostEqual(state.x + state.width / 2, 0.5)
        self.assertAlmostEqual(state.y + state.height / 2, 0.5)
        self.assertTrue(state.width == 1.0 or state.height == 1.0)

    def test_portrait_and_landscape_crop_ratios(self):
        portrait = crop_source_rect(CropState(), 2000, 4000, 11, 14)
        landscape = crop_source_rect(CropState(), 4000, 2000, 14, 11)
        self.assertAlmostEqual(portrait.width / portrait.height, 11 / 14)
        self.assertAlmostEqual(landscape.width / landscape.height, 14 / 11)

    def test_move_updates_crop_and_clamps_inside_source(self):
        initial = constrained_crop_state(CropState(0.2, 0.2, 0.5, 0.5), 2000, 4000, 11, 14)
        moved = move_crop_state(initial, 0.1, 0.05, 2000, 4000, 11, 14)
        self.assertGreater(moved.x, initial.x)
        self.assertGreater(moved.y, initial.y)
        clamped = move_crop_state(moved, 10, -10, 2000, 4000, 11, 14)
        self.assertGreaterEqual(clamped.x, 0.0)
        self.assertGreaterEqual(clamped.y, 0.0)
        self.assertLessEqual(clamped.x + clamped.width, 1.0)
        self.assertLessEqual(clamped.y + clamped.height, 1.0)

    def test_corner_resize_preserves_ratio_anchor_and_bounds(self):
        initial = default_crop_state(4000, 2000, 14, 11)
        resized = resize_crop_state(
            initial, 0.5, initial.x, initial.y, 1, 1, 4000, 2000, 14, 11
        )
        rect = crop_source_rect(resized, 4000, 2000, 14, 11)
        self.assertAlmostEqual(rect.width / rect.height, 14 / 11)
        self.assertAlmostEqual(resized.x, initial.x)
        self.assertAlmostEqual(resized.y, initial.y)
        self.assertGreater(resized.width, 0)
        self.assertLessEqual(resized.x + resized.width, 1.0)
        self.assertLessEqual(resized.y + resized.height, 1.0)

    def test_reset_returns_default_crop(self):
        changed = CropState(0.2, 0.2, 0.4, 0.4)
        reset = default_crop_state(2000, 4000, 11, 14)
        self.assertNotEqual(changed, reset)
        self.assertEqual(reset, default_crop_state(2000, 4000, 11, 14))

    def test_source_crop_is_independent_of_paper_and_position(self):
        crop = constrained_crop_state(CropState(0.1, 0.2, 0.6, 0.4), 2000, 4000, 11, 14)
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
