"""Photo-size workflow: unit precision, paper selection, presets, and caption."""

import unittest
from unittest.mock import patch

from qt_test_support import configure_offscreen

configure_offscreen()  # offscreen Qt with real system fonts, before any QApplication

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from photo_print_layout.crop import default_crop_state
from photo_print_layout.main_window import MainWindow
from photo_print_layout.models import (
    SIZE_PRESETS,
    STANDARD_A3,
    SUPER_A3,
    ResizeMode,
    SizeMM,
    Unit,
)

from test_crop_ui import dummy_photo


class SizeWorkflowTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()

    def tearDown(self):
        self.window.close()

    def _select_unit(self, unit: Unit) -> None:
        self.window.unit_combo.setCurrentIndex(self.window.unit_combo.findData(unit))

    def _set_size(self, width: float, height: float, unit: Unit) -> None:
        self._select_unit(unit)
        self.window.width_spin.setValue(width)
        self.window.height_spin.setValue(height)


class UnitPrecisionTests(SizeWorkflowTestCase):
    def test_editing_height_in_inches_keeps_exact_millimetre_width(self):
        self._set_size(297, 420, Unit.MILLIMETRES)
        self._select_unit(Unit.INCHES)
        self.assertAlmostEqual(self.window.width_spin.value(), 11.69)  # rounded display only

        self.window.height_spin.setValue(16)

        self.assertEqual(self.window._settings.photo_size_mm, SizeMM(297.0, 406.4))

    def test_editing_width_keeps_exact_millimetre_height(self):
        self._set_size(297, 420, Unit.MILLIMETRES)
        self._select_unit(Unit.INCHES)
        self.assertAlmostEqual(self.window.height_spin.value(), 16.54)  # 420.116 mm if read back
        self.window.width_spin.setValue(11)
        self.assertEqual(self.window._settings.photo_size_mm, SizeMM(279.4, 420.0))

    def test_inch_round_trip_back_to_original_ratio_keeps_confirmed_crop(self):
        self.window.set_photo(dummy_photo())
        self._set_size(297, 420, Unit.MILLIMETRES)
        QTest.qWait(300)  # commit the crop for the 297 × 420 ratio
        confirmed = self.window._crop_state
        self.assertAlmostEqual(self.window._crop_aspect_ratio, 297 / 420)

        self._select_unit(Unit.INCHES)
        self.window.height_spin.setValue(16)
        self._select_unit(Unit.MILLIMETRES)
        self.window.height_spin.setValue(420)
        QTest.qWait(300)

        # The width was never replaced by its rounded 11.69 in display value, so the
        # ratio returns exactly and the confirmed crop survives.
        self.assertEqual(self.window._settings.photo_size_mm, SizeMM(297.0, 420.0))
        self.assertIs(self.window._crop_state, confirmed)


class PaperStateMachineTests(SizeWorkflowTestCase):
    def setUp(self):
        super().setUp()
        self.window.set_photo(dummy_photo())  # portrait, 11 × 14 in on A3

    def _select_paper(self, paper) -> None:
        self.window.paper_combo.setCurrentIndex(self.window.paper_combo.findData(paper))

    def _assert_paper(self, paper, choice: str) -> None:
        self.assertEqual(self.window._settings.paper, paper)
        self.assertEqual(self.window.paper_combo.currentData(), paper)
        self.assertEqual(self.window.preview._settings.paper, paper)
        self.assertEqual(self.window._paper_choice, choice)

    def _assert_invalid(self, message: str, *, switch_visible: bool) -> None:
        window = self.window
        self.assertFalse(window.size_error.isHidden())
        self.assertEqual(window.size_error.text(), message)
        self.assertEqual(window.preview._validation_error, message)
        self.assertTrue(window.width_spin.property("sizeInvalid"))
        self.assertTrue(window.height_spin.property("sizeInvalid"))
        self.assertEqual(not window.switch_paper_button.isHidden(), switch_visible)
        self.assertTrue(window.max_size_label.isHidden())  # the error states the maximum
        self.assertFalse(window.output_button.isEnabled())
        self.assertFalse(window.crop_button.isEnabled())

    def _assert_error_and_button_share_a_row(self) -> None:
        window = self.window
        window.resize(1200, 800)
        window.show()
        QApplication.processEvents()
        error, button = window.size_error, window.switch_paper_button
        centre = lambda widget: widget.mapTo(window, widget.rect().center())
        self.assertLessEqual(abs(centre(error).y() - centre(button).y()), 1)
        self.assertLess(centre(error).x(), centre(button).x())  # button on the right

    def _assert_valid(self) -> None:
        window = self.window
        self.assertTrue(window.size_error.isHidden())
        self.assertIsNone(window.preview._validation_error)
        self.assertFalse(window.width_spin.property("sizeInvalid"))
        self.assertFalse(window.height_spin.property("sizeInvalid"))
        self.assertTrue(window.switch_paper_button.isHidden())
        self.assertFalse(window.max_size_label.isHidden())
        self.assertTrue(window.output_button.isEnabled())

    def _auto_note_shown(self) -> bool:
        label = self.window.max_size_label
        shown = bool(label.property("autoSwitched")) and label.text().endswith(" · switched to A3+")
        self.assertEqual(shown, bool(label.property("autoSwitched")))
        return shown

    def test_size_that_fits_only_a3_plus_auto_switches_with_info_note(self):
        self._set_size(12, 16, Unit.INCHES)
        self._assert_paper(SUPER_A3, "auto")
        self._assert_valid()
        self.assertTrue(self._auto_note_shown())  # merged into the Max line, info colour
        self.assertEqual(self.window.max_size_label.text(), "Max: 13 × 19 in · switched to A3+")

    def test_reducing_size_reverts_only_an_auto_switch(self):
        self._set_size(12, 16, Unit.INCHES)
        self.window.width_spin.setValue(11)
        self._assert_paper(STANDARD_A3, "default")
        self._assert_valid()
        self.assertFalse(self._auto_note_shown())
        self.assertEqual(self.window.max_size_label.text(), "Max: 11.69 × 16.54 in")

        self._select_paper(SUPER_A3)  # explicit choice is never reverted
        self._assert_paper(SUPER_A3, "user")
        self.window.width_spin.setValue(8)
        self._assert_paper(SUPER_A3, "user")
        self.assertFalse(self._auto_note_shown())

    def test_new_photo_size_reset_reverts_auto_switch(self):
        self._set_size(12, 16, Unit.INCHES)
        self.window.set_photo(dummy_photo("second.png"))
        self._assert_paper(STANDARD_A3, "default")
        self.assertFalse(self._auto_note_shown())

    def test_user_chosen_a3_shows_error_and_switch_button(self):
        self._select_paper(SUPER_A3)
        self._select_paper(STANDARD_A3)
        self.window.resize_combo.setCurrentIndex(self.window.resize_combo.findData(ResizeMode.CROP))
        self._set_size(12, 16, Unit.INCHES)

        self._assert_paper(STANDARD_A3, "user")
        self._assert_invalid("Too large for A3 (max 11.69 × 16.54 in)", switch_visible=True)
        self.assertTrue(self.window.preview_caption.property("sizeInvalid"))
        self._assert_error_and_button_share_a_row()

        self.window.switch_paper_button.click()
        self._assert_paper(SUPER_A3, "user")
        self._assert_valid()
        self.assertTrue(self.window.crop_button.isEnabled())
        self.assertFalse(self._auto_note_shown())  # not an automatic switch

        self._set_size(8, 10, Unit.INCHES)
        self._assert_paper(SUPER_A3, "user")

    def test_too_large_for_a3_plus_shows_error_without_switch_button(self):
        self._set_size(14, 20, Unit.INCHES)
        self._assert_paper(STANDARD_A3, "default")
        self._assert_invalid("Too large for A3+ (max 13 × 19 in)", switch_visible=False)

        self._select_unit(Unit.CENTIMETRES)  # message follows the display unit
        self._assert_invalid("Too large for A3+ (max 33.02 × 48.26 cm)", switch_visible=False)

    def test_auto_switched_paper_stays_until_size_fits_a3_again(self):
        self._set_size(12, 16, Unit.INCHES)
        self.window.height_spin.setValue(20)
        self._assert_paper(SUPER_A3, "auto")
        self._assert_invalid("Too large for A3+ (max 13 × 19 in)", switch_visible=False)

        self._set_size(11, 14, Unit.INCHES)
        self._assert_paper(STANDARD_A3, "default")
        self._assert_valid()

    def test_landscape_19_by_13_auto_switches_to_landscape_a3_plus(self):
        self.window.set_photo(dummy_photo("landscape.png", 400, 200))  # 14 × 11 in
        self._set_size(19, 13, Unit.INCHES)
        self._assert_paper(SUPER_A3, "auto")
        self._assert_valid()
        self.assertEqual(self.window.max_size_label.text(), "Max: 19 × 13 in · switched to A3+")
        self.assertEqual(self.window.preview_caption.text(), "Photo 19 × 13 in · A3+ paper")

    def test_auto_switch_also_works_without_a_photo(self):
        self.window.clear_photo()
        self._set_size(12, 15, Unit.INCHES)
        self._assert_paper(SUPER_A3, "auto")
        self.assertTrue(self._auto_note_shown())


class SizePresetTests(SizeWorkflowTestCase):
    EXPECTED = (
        ("11 × 14 in", SizeMM(279.4, 355.6)),
        ("12 × 15 in", SizeMM(304.8, 381.0)),
        ("12 × 16 in", SizeMM(304.8, 406.4)),
        ("13 × 16 in", SizeMM(330.2, 406.4)),
        ("A3 (11.69 × 16.54 in)", SizeMM(297.0, 420.0)),
        ("A3+ (13 × 19 in)", SizeMM(330.2, 482.6)),
    )

    def _pick(self, key: str) -> None:
        """Simulate a user pick: Qt sets the index, then emits activated."""

        combo = self.window.size_preset_combo
        index = next(i for i, preset in enumerate(SIZE_PRESETS) if preset.key == key)
        combo.setCurrentIndex(index)
        combo.activated.emit(index)

    def _shown_preset(self):
        return self.window.size_preset_combo.currentData()

    def test_preset_list_is_exact_and_has_no_custom_or_13r_entry(self):
        combo = self.window.size_preset_combo
        self.assertEqual(
            tuple((combo.itemText(i), combo.itemData(i).size_mm) for i in range(combo.count())),
            self.EXPECTED,
        )
        self.assertEqual(combo.placeholderText(), "Quick size…")
        for preset in SIZE_PRESETS[:4]:  # inch presets convert exactly
            width_in, height_in = (float(v) for v in preset.key.split("x"))
            self.assertAlmostEqual(preset.size_mm.width, width_in * 25.4, places=9)
            self.assertAlmostEqual(preset.size_mm.height, height_in * 25.4, places=9)

    def test_each_preset_writes_exact_millimetres_without_changing_unit(self):
        self.window.set_photo(dummy_photo())  # portrait
        self._select_unit(Unit.CENTIMETRES)
        for preset in SIZE_PRESETS:
            with self.subTest(preset=preset.key):
                self._pick(preset.key)
                self.assertEqual(self.window._settings.photo_size_mm, preset.size_mm)
                self.assertEqual(self._shown_preset(), preset)
                self.assertEqual(self.window.unit_combo.currentData(), Unit.CENTIMETRES)
                self.assertAlmostEqual(self.window.width_spin.value(), preset.size_mm.width / 10)

    def test_preset_follows_photo_orientation(self):
        self.window.set_photo(dummy_photo("landscape.png", 400, 200))
        self._pick("12x15")
        self.assertEqual(self.window._settings.photo_size_mm, SizeMM(381.0, 304.8))
        self.assertEqual((self.window.width_spin.value(), self.window.height_spin.value()), (15, 12))

        self.window.set_photo(dummy_photo("square.png", 300, 300))
        self._pick("12x15")
        self.assertEqual(self.window._settings.photo_size_mm, SizeMM(304.8, 381.0))

    def test_preset_without_photo_keeps_current_size_orientation(self):
        self._set_size(14, 11, Unit.INCHES)
        self._pick("a3")
        self.assertEqual(self.window._settings.photo_size_mm, SizeMM(420.0, 297.0))

    def test_combo_shows_matching_preset_or_placeholder(self):
        combo = self.window.size_preset_combo
        self.assertEqual(self._shown_preset().key, "11x14")  # startup default
        self._set_size(16, 12, Unit.INCHES)  # landscape still matches
        self.assertEqual(self._shown_preset().key, "12x16")
        self._set_size(12, 17, Unit.INCHES)
        self.assertEqual(combo.currentIndex(), -1)
        self._set_size(29.7, 42, Unit.CENTIMETRES)
        self.assertEqual(self._shown_preset().key, "a3")
        self.window.clear_photo()
        self.assertEqual(self._shown_preset().key, "a3")
        self.window.set_photo(dummy_photo())
        self.assertEqual(self._shown_preset().key, "11x14")

    def test_a3_preset_in_inches_then_editing_width_keeps_exact_height(self):
        self._pick("a3")
        self.assertEqual(
            (self.window.width_spin.value(), self.window.height_spin.value()), (11.69, 16.54)
        )
        self.window.width_spin.setValue(11)
        self.assertEqual(self.window._settings.photo_size_mm, SizeMM(279.4, 420.0))
        self.assertEqual(self.window._settings.paper, STANDARD_A3)  # 420 mm still fits A3

    def test_preset_paper_follows_smallest_fit_unless_user_chose(self):
        self._pick("12x16")
        self.assertEqual(self.window._settings.paper, SUPER_A3)
        self.assertEqual(self.window._paper_choice, "auto")
        self._pick("a3")
        self.assertEqual(self.window._settings.paper, STANDARD_A3)
        self.assertEqual(self.window._paper_choice, "default")

        self.window.paper_combo.setCurrentIndex(self.window.paper_combo.findData(SUPER_A3))
        self.window.paper_combo.setCurrentIndex(self.window.paper_combo.findData(STANDARD_A3))
        self._pick("a3_plus")
        self.assertEqual(self.window._settings.paper, STANDARD_A3)
        self.assertEqual(self.window.size_error.text(), "Too large for A3 (max 11.69 × 16.54 in)")
        self.assertFalse(self.window.switch_paper_button.isHidden())

    def test_preset_commits_crop_immediately_and_same_ratio_keeps_crop(self):
        self.window.set_photo(dummy_photo())
        self._pick("12x16")
        self.assertAlmostEqual(self.window._crop_aspect_ratio, 12 / 16)
        self.assertEqual(
            self.window._crop_state, default_crop_state(200, 400, 304.8, 406.4)
        )
        self.assertEqual(self.window.preview._crop_state, self.window._crop_state)

        confirmed = self.window._crop_state
        self._pick("12x16")  # re-picking the shown preset keeps the composition
        self.assertIs(self.window._crop_state, confirmed)

    def test_placeholder_selection_does_nothing(self):
        before = self.window._settings
        self.window.size_preset_combo.activated.emit(-1)
        self.assertEqual(self.window._settings, before)


class PreviewCaptionTests(SizeWorkflowTestCase):
    def _caption(self) -> str:
        return self.window.preview_caption.text()

    def test_default_caption_and_heading_row(self):
        self.assertEqual(self._caption(), "Photo 11 × 14 in · A3 paper")
        self.assertFalse(self.window.preview_caption.property("sizeInvalid"))
        self.assertTrue(
            self.window.preview_caption.alignment() & Qt.AlignmentFlag.AlignRight
        )

    def test_caption_follows_unit_size_and_paper(self):
        self._select_unit(Unit.CENTIMETRES)
        self.assertEqual(self._caption(), "Photo 27.94 × 35.56 cm · A3 paper")

        self._set_size(8, 10, Unit.INCHES)
        self.assertEqual(self._caption(), "Photo 8 × 10 in · A3 paper")

        self.window.paper_combo.setCurrentIndex(self.window.paper_combo.findData(SUPER_A3))
        self.assertEqual(self._caption(), "Photo 8 × 10 in · A3+ paper")

    def test_caption_formats_exact_model_size_not_box_text(self):
        self._set_size(297, 420, Unit.MILLIMETRES)
        self._select_unit(Unit.INCHES)
        self.assertEqual(self._caption(), "Photo 11.69 × 16.54 in · A3 paper")
        self._select_unit(Unit.MILLIMETRES)
        self.assertEqual(self._caption(), "Photo 297 × 420 mm · A3 paper")

    def test_caption_turns_red_when_size_does_not_fit(self):
        self._set_size(500, 400, Unit.MILLIMETRES)
        self.assertTrue(self.window.preview_caption.property("sizeInvalid"))
        self.assertIn("500 × 400 mm", self._caption())
        self._set_size(200, 250, Unit.MILLIMETRES)
        self.assertFalse(self.window.preview_caption.property("sizeInvalid"))

    def test_placeholder_has_no_hard_coded_size(self):
        drawn = []

        class RecordingPainter(QPainter):
            def drawText(self, *args):  # noqa: N802 - Qt API name
                drawn.append(args[-1])
                return super().drawText(*args)

        self._set_size(8, 10, Unit.INCHES)
        with patch("photo_print_layout.preview.QPainter", RecordingPainter):
            self.window.preview.grab()
        self.assertEqual(drawn, ["Open a photo to preview"])


if __name__ == "__main__":
    unittest.main()
