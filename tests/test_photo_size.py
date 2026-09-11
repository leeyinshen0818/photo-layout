import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from photo_print_layout.crop import CropState, crop_source_rect
from photo_print_layout.layout import calculate_layout, photo_fits_on_paper
from photo_print_layout.main_window import MainWindow
from photo_print_layout.models import (
    LayoutSettings,
    Orientation,
    ResizeMode,
    SizeMM,
    SUPER_A3,
    Unit,
    from_millimetres,
    orientation_for_dimensions,
    to_millimetres,
)

from test_crop_ui import dummy_photo


class PhotoSizeModelTests(unittest.TestCase):
    def test_exact_unit_conversions(self):
        self.assertAlmostEqual(to_millimetres(11, Unit.INCHES), 279.4)
        self.assertAlmostEqual(to_millimetres(14, Unit.INCHES), 355.6)
        self.assertAlmostEqual(from_millimetres(279.4, Unit.CENTIMETRES), 27.94)
        self.assertAlmostEqual(from_millimetres(355.6, Unit.CENTIMETRES), 35.56)
        self.assertAlmostEqual(from_millimetres(279.4, Unit.MILLIMETRES), 279.4)

    def test_target_dimensions_are_orientation_source_of_truth(self):
        self.assertEqual(orientation_for_dimensions(8, 10), Orientation.PORTRAIT)
        self.assertEqual(orientation_for_dimensions(12, 10), Orientation.LANDSCAPE)
        self.assertEqual(orientation_for_dimensions(20, 20), Orientation.SQUARE)
        square = LayoutSettings(photo_size_mm=SizeMM(200, 200))
        self.assertEqual(square.target_orientation, Orientation.SQUARE)
        self.assertLess(square.paper_size_mm.width, square.paper_size_mm.height)

    def test_custom_sizes_drive_fit_crop_and_position_geometry(self):
        size = SizeMM(10 * 25.4, 12 * 25.4)
        fit = calculate_layout(LayoutSettings(photo_size_mm=size), 2000, 3000)
        crop = calculate_layout(
            LayoutSettings(photo_size_mm=size, resize_mode=ResizeMode.CROP),
            2000,
            3000,
            CropState(),
        )
        self.assertAlmostEqual(fit.target.width, 254.0)
        self.assertAlmostEqual(fit.target.height, 304.8)
        self.assertAlmostEqual(crop.target.width, 254.0)
        self.assertAlmostEqual(crop.target.height, 304.8)
        self.assertEqual(crop.image, crop.target)
        self.assertAlmostEqual(crop.source.width / crop.source.height, 10 / 12)

    def test_paper_fit_validation_rejects_oversized_target(self):
        self.assertTrue(photo_fits_on_paper(LayoutSettings(photo_size_mm=SizeMM(250, 300))))
        self.assertFalse(photo_fits_on_paper(LayoutSettings(photo_size_mm=SizeMM(300, 430))))
        self.assertFalse(photo_fits_on_paper(LayoutSettings(photo_size_mm=SizeMM(500, 400))))

    def test_a3_plus_accepts_exact_13_by_19_boundary_in_both_orientations(self):
        for size in (
            SizeMM(to_millimetres(13, Unit.INCHES), to_millimetres(19, Unit.INCHES)),
            SizeMM(to_millimetres(19, Unit.INCHES), to_millimetres(13, Unit.INCHES)),
            SizeMM(to_millimetres(33.02, Unit.CENTIMETRES), to_millimetres(48.26, Unit.CENTIMETRES)),
            SizeMM(330.2, 482.6),
        ):
            self.assertTrue(photo_fits_on_paper(LayoutSettings(paper=SUPER_A3, photo_size_mm=size)))

    def test_a3_plus_rejects_genuinely_oversized_targets(self):
        for width, height in ((13.01, 19), (13, 19.01), (13.1, 19)):
            size = SizeMM(
                to_millimetres(width, Unit.INCHES),
                to_millimetres(height, Unit.INCHES),
            )
            self.assertFalse(
                photo_fits_on_paper(LayoutSettings(paper=SUPER_A3, photo_size_mm=size))
            )
        self.assertFalse(
            photo_fits_on_paper(
                LayoutSettings(paper=SUPER_A3, photo_size_mm=SizeMM(331, 483))
            )
        )

    def test_standard_a3_exact_boundaries_and_small_tolerance(self):
        self.assertTrue(photo_fits_on_paper(LayoutSettings(photo_size_mm=SizeMM(297, 420))))
        self.assertTrue(photo_fits_on_paper(LayoutSettings(photo_size_mm=SizeMM(420, 297))))
        self.assertTrue(
            photo_fits_on_paper(LayoutSettings(photo_size_mm=SizeMM(297.0000005, 420)))
        )
        self.assertFalse(
            photo_fits_on_paper(LayoutSettings(photo_size_mm=SizeMM(297.00001, 420)))
        )

    def test_custom_crop_ratio_is_not_hard_coded(self):
        crop = crop_source_rect(CropState(), 2000, 3000, 8, 10)
        square = crop_source_rect(CropState(), 2000, 3000, 20, 20)
        self.assertAlmostEqual(crop.width / crop.height, 8 / 10)
        self.assertAlmostEqual(square.width / square.height, 1.0)


class PhotoSizeUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()

    def tearDown(self):
        self.window.close()

    def _select_unit(self, unit: Unit) -> None:
        self.window.unit_combo.setCurrentIndex(self.window.unit_combo.findData(unit))

    def test_no_image_defaults_to_11_by_14_inches(self):
        self.assertEqual(self.window.unit_combo.currentData(), Unit.INCHES)
        self.assertAlmostEqual(self.window.width_spin.value(), 11.0)
        self.assertAlmostEqual(self.window.height_spin.value(), 14.0)
        self.assertFalse(hasattr(self.window, "photo_size_combo"))
        self.assertEqual(self.window.width_label.text(), "Width")
        self.assertEqual(self.window.height_label.text(), "Height")
        self.assertEqual(self.window.max_size_label.text(), "Max: 11.69 × 16.54 in")

    def test_maximum_label_tracks_paper_orientation_and_unit(self):
        self.window.width_spin.setValue(14)
        self.window.height_spin.setValue(11)
        self.assertEqual(self.window.max_size_label.text(), "Max: 16.54 × 11.69 in")

        self.window.paper_combo.setCurrentIndex(self.window.paper_combo.findData(SUPER_A3))
        self.assertEqual(self.window.max_size_label.text(), "Max: 19 × 13 in")
        self._select_unit(Unit.CENTIMETRES)
        self.assertEqual(self.window.max_size_label.text(), "Max: 48.26 × 33.02 cm")

        self.window.width_spin.setValue(33.02)
        self.window.height_spin.setValue(48.26)
        self.assertEqual(self.window.max_size_label.text(), "Max: 33.02 × 48.26 cm")
        self._select_unit(Unit.MILLIMETRES)
        self.assertEqual(self.window.max_size_label.text(), "Max: 330.2 × 482.6 mm")

    def test_a3_plus_boundary_is_valid_in_each_display_unit(self):
        self.window.set_photo(dummy_photo())
        self.window.paper_combo.setCurrentIndex(self.window.paper_combo.findData(SUPER_A3))
        for unit, width, height in (
            (Unit.INCHES, 13, 19),
            (Unit.CENTIMETRES, 33.02, 48.26),
            (Unit.MILLIMETRES, 330.2, 482.6),
        ):
            self._select_unit(unit)
            self.window.width_spin.setValue(width)
            self.window.height_spin.setValue(height)
            self.assertTrue(photo_fits_on_paper(self.window._settings), unit.value)
            self.assertTrue(self.window.output_button.isEnabled(), unit.value)

    def test_loaded_image_orients_default_size_once(self):
        self.window.set_photo(dummy_photo("portrait.png", 200, 400))
        self.assertEqual((self.window.width_spin.value(), self.window.height_spin.value()), (11, 14))
        self.window.set_photo(dummy_photo("landscape.png", 400, 200))
        self.assertEqual((self.window.width_spin.value(), self.window.height_spin.value()), (14, 11))
        self.window.width_spin.setValue(10)
        self.window.height_spin.setValue(12)
        self.assertEqual(self.window._settings.target_orientation, Orientation.PORTRAIT)

    def test_unit_switch_preserves_physical_size_and_crop(self):
        self.window.set_photo(dummy_photo())
        crop = self.window._crop_state
        physical = self.window._settings.photo_size_mm
        self._select_unit(Unit.CENTIMETRES)
        self.assertAlmostEqual(self.window.width_spin.value(), 27.94)
        self.assertAlmostEqual(self.window.height_spin.value(), 35.56)
        self._select_unit(Unit.MILLIMETRES)
        self.assertAlmostEqual(self.window.width_spin.value(), 279.4)
        self.assertAlmostEqual(self.window.height_spin.value(), 355.6)
        self.assertEqual(self.window._settings.photo_size_mm, physical)
        self.assertIs(self.window._crop_state, crop)

    def test_custom_values_convert_to_canonical_millimetres(self):
        for unit, width, height, expected in (
            (Unit.INCHES, 8, 10, SizeMM(203.2, 254.0)),
            (Unit.INCHES, 10, 12, SizeMM(254.0, 304.8)),
            (Unit.CENTIMETRES, 25, 30, SizeMM(250.0, 300.0)),
            (Unit.MILLIMETRES, 200, 250, SizeMM(200.0, 250.0)),
        ):
            self._select_unit(unit)
            self.window.width_spin.setValue(width)
            self.window.height_spin.setValue(height)
            self.assertEqual(self.window._settings.photo_size_mm, expected)

    def test_aspect_change_resets_crop_but_proportional_change_preserves_it(self):
        self.window.set_photo(dummy_photo())
        original = self.window._crop_state
        self.window.width_spin.setValue(5.5)
        self.window.height_spin.setValue(7.0)
        self.assertIs(self.window._crop_state, original)

        self.window.width_spin.setValue(8.0)
        self.window.height_spin.setValue(10.0)
        QTest.qWait(300)
        self.assertIsNot(self.window._crop_state, original)
        self.assertAlmostEqual(self.window._crop_aspect_ratio, 8 / 10)

    def test_invalid_paper_fit_is_visible_and_disables_actions(self):
        self.window.set_photo(dummy_photo())
        self._select_unit(Unit.MILLIMETRES)
        self.window.width_spin.setValue(500)
        self.window.height_spin.setValue(400)
        self.assertFalse(self.window.size_error.isHidden())
        self.assertFalse(self.window.output_button.isEnabled())
        self.assertFalse(self.window.crop_button.isEnabled())
        self.assertIsNotNone(self.window.preview._validation_error)

    def test_clear_preserves_custom_size_and_unit(self):
        self.window.set_photo(dummy_photo())
        self._select_unit(Unit.CENTIMETRES)
        self.window.width_spin.setValue(25)
        self.window.height_spin.setValue(30)
        physical = self.window._settings.photo_size_mm
        self.window.clear_photo()
        self.assertEqual(self.window._settings.photo_size_mm, physical)
        self.assertEqual(self.window.unit_combo.currentData(), Unit.CENTIMETRES)
        self.assertEqual((self.window.width_spin.value(), self.window.height_spin.value()), (25, 30))


if __name__ == "__main__":
    unittest.main()
