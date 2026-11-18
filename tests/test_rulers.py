"""Preview rulers: pure tick/label/band geometry, widget layout, and the toggle."""

import tempfile
import unittest
from itertools import combinations, product
from pathlib import Path

from qt_test_support import configure_offscreen

configure_offscreen()  # offscreen Qt with real system fonts, before any QApplication

from PySide6.QtCore import QAbstractAnimation, QSettings, QSize, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from photo_print_layout.crop import CropState
from photo_print_layout.layout import calculate_layout
from photo_print_layout.main_window import RULER_VISIBLE_KEY, MainWindow
from photo_print_layout.models import (
    STANDARD_A3,
    SUPER_A3,
    LayoutSettings,
    Position,
    ResizeMode,
    SizeMM,
    Unit,
)
from photo_print_layout.preview import PreviewWidget
from photo_print_layout.rulers import (
    AxisLabel,
    format_length,
    label_stride_for,
    layout_axis_labels,
    photo_bands,
    ruler_ticks,
)
from photo_print_layout.toggle_switch import SwitchLabel, ToggleSwitch
from photo_print_layout.ui_scale import UiMetrics

from test_crop_ui import dummy_photo


PORTRAIT_11X14 = SizeMM(279.4, 355.6)
LANDSCAPE_14X11 = SizeMM(355.6, 279.4)


def _labels(ticks):
    return [tick.label for tick in ticks if tick.label is not None]


class RulerTickTests(unittest.TestCase):
    def test_inch_ticks_every_half_inch_with_major_labels(self):
        ticks = ruler_ticks(420.0, Unit.INCHES)  # A3 long side, 16.54 in
        self.assertEqual(len(ticks), 34)  # 0 … 16.5 in
        for index, tick in enumerate(ticks):
            self.assertAlmostEqual(tick.position_mm, index * 12.7, places=6)
            self.assertEqual(tick.is_major, index % 2 == 0)
            if not tick.is_major:
                self.assertIsNone(tick.label)
        self.assertEqual(_labels(ticks), [str(n) for n in range(17)])

    def test_centimetre_ticks_every_half_centimetre(self):
        ticks = ruler_ticks(297.0, Unit.CENTIMETRES)  # 29.7 cm
        self.assertEqual(len(ticks), 60)
        self.assertAlmostEqual(ticks[1].position_mm, 5.0)
        self.assertAlmostEqual(ticks[-1].position_mm, 295.0)
        self.assertEqual(_labels(ticks), [str(n) for n in range(30)])

    def test_millimetre_ticks_major_ten_minor_five(self):
        ticks = ruler_ticks(330.2, Unit.MILLIMETRES)
        self.assertEqual(len(ticks), 67)
        self.assertEqual([t.position_mm for t in ticks[:3]], [0.0, 5.0, 10.0])
        self.assertEqual([t.is_major for t in ticks[:3]], [True, False, True])
        self.assertEqual(_labels(ticks), [str(n) for n in range(0, 331, 10)])

    def test_tick_on_exact_paper_end_is_included(self):
        last = ruler_ticks(482.6, Unit.INCHES)[-1]  # A3+ 19 in
        self.assertAlmostEqual(last.position_mm, 482.6)
        self.assertEqual(last.label, "19")

    def test_label_stride_thins_major_labels_but_keeps_every_tick(self):
        all_ticks = ruler_ticks(420.0, Unit.INCHES)
        every_second = ruler_ticks(420.0, Unit.INCHES, label_stride=2)
        every_fifth = ruler_ticks(420.0, Unit.INCHES, label_stride=5)
        self.assertEqual(len(every_second), len(all_ticks))
        self.assertEqual(_labels(every_second), [str(n) for n in range(0, 17, 2)])
        self.assertEqual(_labels(every_fifth), ["0", "5", "10", "15"])

    def test_label_stride_for_crowding(self):
        self.assertEqual(label_stride_for(30, 25), 1)
        self.assertEqual(label_stride_for(13, 25), 2)
        self.assertEqual(label_stride_for(10, 25), 5)
        self.assertEqual(label_stride_for(1, 1000), 50)

    def test_invalid_arguments(self):
        with self.assertRaises(ValueError):
            ruler_ticks(0, Unit.INCHES)
        with self.assertRaises(ValueError):
            ruler_ticks(100, Unit.INCHES, label_stride=0)

    def test_paper_length_labels(self):
        self.assertEqual(format_length(420.0, Unit.INCHES), "16.54 in")
        self.assertEqual(format_length(420.0, Unit.CENTIMETRES), "42 cm")
        self.assertEqual(format_length(482.6, Unit.MILLIMETRES), "482.6 mm")
        self.assertEqual(format_length(482.6, Unit.INCHES), "19 in")


class RulerBandTests(unittest.TestCase):
    def _bands(self, size, position, unit=Unit.INCHES, **kwargs):
        layout = calculate_layout(LayoutSettings(photo_size_mm=size, position=position), **kwargs)
        return photo_bands(layout, unit)

    def _assert_band(self, band, start, end, label):
        self.assertAlmostEqual(band.start_mm, start, places=6)
        self.assertAlmostEqual(band.end_mm, end, places=6)
        self.assertEqual(band.label, label)

    def test_left_top_portrait(self):
        horizontal, vertical = self._bands(PORTRAIT_11X14, Position.LEFT_TOP)
        self._assert_band(horizontal, 0.0, 279.4, "11 in")
        self._assert_band(vertical, 0.0, 355.6, "14 in")

    def test_center_portrait(self):
        horizontal, vertical = self._bands(PORTRAIT_11X14, Position.CENTER)
        self._assert_band(horizontal, 8.8, 288.2, "11 in")  # (297 - 279.4) / 2
        self._assert_band(vertical, 32.2, 387.8, "14 in")  # (420 - 355.6) / 2

    def test_left_top_landscape_uses_rotated_paper(self):
        horizontal, vertical = self._bands(LANDSCAPE_14X11, Position.LEFT_TOP)
        self._assert_band(horizontal, 0.0, 355.6, "14 in")
        self._assert_band(vertical, 0.0, 279.4, "11 in")

    def test_center_landscape(self):
        horizontal, vertical = self._bands(LANDSCAPE_14X11, Position.CENTER, Unit.CENTIMETRES)
        self._assert_band(horizontal, 32.2, 387.8, "35.56 cm")
        self._assert_band(vertical, 8.8, 288.2, "27.94 cm")

    def test_band_is_photo_size_box_not_fit_inside_image(self):
        layout = calculate_layout(
            LayoutSettings(photo_size_mm=PORTRAIT_11X14, resize_mode=ResizeMode.FIT),
            400,
            100,  # very wide source: the fitted image is letterboxed
        )
        self.assertLess(layout.image.height, layout.target.height)
        _horizontal, vertical = photo_bands(layout, Unit.INCHES)
        self._assert_band(vertical, 0.0, 355.6, "14 in")


class AxisLabelTests(unittest.TestCase):
    @staticmethod
    def extent(text):
        return len(text) * 6.0

    def _place(self, ticks, band, paper_end=200.0, paper_label="16.54 in"):
        return layout_axis_labels(ticks, paper_end, paper_label, band, self.extent, 2.0)

    def test_paper_label_is_end_aligned_and_ticks_are_centred(self):
        labels = self._place([(0.0, "0"), (50.0, "1")], None)
        self.assertIn(AxisLabel("16.54 in", 152.0, 200.0, "paper"), labels)
        self.assertIn(AxisLabel("1", 47.0, 53.0, "tick"), labels)

    def test_band_label_is_end_aligned_at_band_end(self):
        labels = self._place([], (100.0, "11 in"))
        self.assertIn(AxisLabel("11 in", 70.0, 100.0, "band"), labels)

    def test_band_label_near_paper_end_is_nudged_clear(self):
        labels = self._place([], (190.0, "16 in"))
        band = next(label for label in labels if label.kind == "band")
        paper = next(label for label in labels if label.kind == "paper")
        self.assertLessEqual(band.end + 2.0, paper.start)

    def test_full_length_band_shares_one_label(self):
        labels = self._place([], (200.0, "16.54 in"))
        self.assertEqual([label.kind for label in labels], ["band"])

    def test_colliding_tick_labels_are_dropped(self):
        # Paper label spans 152–200 and the band label 72–102 (gap 2).
        labels = self._place(
            [(120.0, "12"), (150.0, "15"), (196.0, "16"), (100.0, "10")], (102.0, "10 in")
        )
        texts = [label.text for label in labels if label.kind == "tick"]
        self.assertEqual(texts, ["12"])  # "15" and "16" hit the paper label, "10" the band


class PreviewRulerWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _preview(self, scale=1.0, size=(600, 700), settings=None, unit=Unit.INCHES):
        preview = PreviewWidget()
        preview.set_ui_scale(scale)
        preview.resize(*size)
        preview.set_settings(settings or LayoutSettings())
        preview.set_display_unit(unit)
        preview.set_photo(dummy_photo())
        return preview

    def _drawing(self, preview):
        layout = preview._layout()
        page, _scale = preview._page_geometry(layout)
        return page, preview._ruler_drawing(layout, page)

    def test_rulers_on_by_default_and_reserve_margin_only_when_visible(self):
        preview = self._preview()
        self.assertTrue(preview.ruler_visible)
        page_on, drawing = self._drawing(preview)
        self.assertIsNotNone(drawing)
        preview.set_ruler_visible(False)
        page_off, drawing_off = self._drawing(preview)
        self.assertIsNone(drawing_off)
        self.assertEqual(preview._ruler_reserve(), (0.0, 0.0))
        self.assertGreaterEqual(page_off.width(), page_on.width())
        self.assertGreaterEqual(page_off.height(), page_on.height())
        self.assertGreater(page_off.width() * page_off.height(), page_on.width() * page_on.height())

    def test_no_rulers_without_photo_or_in_error_state(self):
        preview = self._preview()
        preview.set_validation_error("Too large for A3+")
        self.assertIsNone(self._drawing(preview)[1])
        preview.set_validation_error(None)
        preview.set_photo(None)
        self.assertIsNone(self._drawing(preview)[1])
        self.assertTrue(preview.ruler_visible)

    def test_rulers_sit_left_and_below_the_paper(self):
        page, drawing = self._drawing(self._preview())
        for line in drawing.lines:
            self.assertTrue(
                max(line.x1(), line.x2()) <= page.left() or min(line.y1(), line.y2()) >= page.bottom()
            )
        texts = [text for _rect, text, _kind in drawing.labels]
        self.assertIn("16.54 in", texts)  # paper height (left ruler)
        self.assertIn("11.69 in", texts)  # paper width (bottom ruler)
        self.assertIn("14 in", texts)
        self.assertIn("11 in", texts)

    def test_band_maps_physical_position_to_widget_pixels(self):
        settings = LayoutSettings(photo_size_mm=PORTRAIT_11X14, position=Position.CENTER)
        page, drawing = self._drawing(self._preview(settings=settings))
        horizontal, vertical = drawing.bands
        px = page.width() / 297.0
        self.assertAlmostEqual(horizontal.left(), page.left() + 8.8 * px, places=4)
        self.assertAlmostEqual(horizontal.width(), 279.4 * px, places=4)
        self.assertAlmostEqual(vertical.top(), page.top() + 32.2 * page.height() / 420.0, places=4)

    def test_labels_follow_display_unit(self):
        preview = self._preview(unit=Unit.CENTIMETRES)
        texts = [text for _rect, text, _kind in self._drawing(preview)[1].labels]
        self.assertIn("42 cm", texts)
        self.assertIn("29.7 cm", texts)

    def test_nothing_clips_or_overlaps_at_minimum_size(self):
        cases = product(
            (0.72, 1.0, 1.25),
            (Unit.INCHES, Unit.CENTIMETRES, Unit.MILLIMETRES),
            (STANDARD_A3, SUPER_A3),
            (PORTRAIT_11X14, LANDSCAPE_14X11, SizeMM(297.0, 420.0)),
            (Position.LEFT_TOP, Position.CENTER),
        )
        for scale, unit, paper, size, position in cases:
            with self.subTest(scale=scale, unit=unit, paper=paper.key, size=size, position=position):
                metrics = UiMetrics(scale)
                settings = LayoutSettings(paper=paper, photo_size_mm=size, position=position)
                preview = self._preview(
                    scale, (metrics.px(440), metrics.px(520)), settings, unit
                )
                _page, drawing = self._drawing(preview)
                self.assertTrue(preview.rect().toRectF().contains(drawing.bounding_rect()))
                for (first, *_), (second, *_) in combinations(drawing.labels, 2):
                    self.assertFalse(first.intersects(second))


class RulerToggleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._directory = tempfile.TemporaryDirectory()
        self._path = str(Path(self._directory.name) / "preferences.ini")
        self.window = self._window()

    def tearDown(self):
        self.window.close()
        self._directory.cleanup()

    def _window(self, scale=1.0):
        preferences = QSettings(self._path, QSettings.Format.IniFormat)
        return MainWindow(UiMetrics(scale), preferences=preferences)

    def test_switch_defaults_on_and_sits_label_switch_caption(self):
        window = self.window
        switch = window.ruler_button
        self.assertIsInstance(switch, ToggleSwitch)
        self.assertTrue(switch.isCheckable())
        self.assertTrue(switch.isChecked())
        self.assertEqual(switch.knobPosition, 1.0)  # restored state is placed, not animated
        self.assertTrue(window.preview.ruler_visible)
        self.assertEqual(window.ruler_label.text(), "Ruler")
        self.assertEqual(switch.accessibleName(), "Ruler")
        self.assertEqual(switch.toolTip(), "Show/hide rulers")

        window.resize(1200, 800)
        window.show()
        self.app.processEvents()
        label, caption = window.ruler_label, window.preview_caption
        left = lambda widget: widget.mapTo(window, widget.rect().topLeft()).x()
        centre_y = lambda widget: widget.mapTo(window, widget.rect().center()).y()
        self.assertLess(left(label) + label.width(), left(switch) + 1)
        self.assertLess(left(switch) + switch.width(), left(caption) + 1)
        self.assertLessEqual(abs(centre_y(switch) - centre_y(caption)), 1)
        self.assertLessEqual(abs(centre_y(label) - centre_y(caption)), 1)

    def test_toggle_only_repaints_without_touching_layout_state(self):
        window = self.window
        window.set_photo(dummy_photo())
        window.resize_combo.setCurrentIndex(window.resize_combo.findData(ResizeMode.CROP))
        window.preview._rendered_page(240, 340)
        cached_keys = set(window.preview._render_cache)
        before = (window._settings, window._crop_state, window._paper_choice, window.preview._settings)

        window.ruler_button.click()

        self.assertFalse(window.preview.ruler_visible)
        self.assertEqual(
            before,
            (window._settings, window._crop_state, window._paper_choice, window.preview._settings),
        )
        self.assertIs(window._crop_state, before[1])
        self.assertTrue(cached_keys <= set(window.preview._render_cache))

    def test_state_persists_in_settings(self):
        self.window.ruler_button.click()
        self.window.close()
        stored = QSettings(self._path, QSettings.Format.IniFormat)
        self.assertFalse(stored.value(RULER_VISIBLE_KEY, True, type=bool))

        self.window = self._window()
        self.assertFalse(self.window.ruler_button.isChecked())
        self.assertFalse(self.window.preview.ruler_visible)
        self.window.ruler_button.click()
        self.assertTrue(self.window.preview.ruler_visible)
        self.window.close()
        self.window = self._window()
        self.assertTrue(self.window.ruler_button.isChecked())

    def test_display_unit_reaches_preview(self):
        self.window.unit_combo.setCurrentIndex(self.window.unit_combo.findData(Unit.CENTIMETRES))
        self.assertIs(self.window.preview._display_unit, Unit.CENTIMETRES)

    def test_clicking_the_label_toggles_rulers_and_persists(self):
        self.window.ruler_button.set_animation_duration(0)
        QTest.mouseClick(self.window.ruler_label, Qt.MouseButton.LeftButton)
        self.assertFalse(self.window.ruler_button.isChecked())
        self.assertFalse(self.window.preview.ruler_visible)
        self.window.close()
        self.window = self._window()
        self.assertFalse(self.window.ruler_button.isChecked())
        self.assertEqual(self.window.ruler_button.knobPosition, 0.0)

    def test_switch_scales_with_ui_metrics(self):
        for scale in (0.72, 1.0):
            metrics = UiMetrics(scale)
            window = self._window(scale)
            try:
                switch = window.ruler_button
                self.assertEqual(
                    switch.track_size(), QSize(metrics.px(34, 26), metrics.px(18, 14))
                )
                margin = metrics.px(3, 2) * 2
                self.assertEqual(
                    switch.size(),
                    QSize(metrics.px(34, 26) + margin, metrics.px(18, 14) + margin),
                )
            finally:
                window.close()


class ToggleSwitchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.switch = ToggleSwitch()
        self.switch.setToolTip("Show/hide rulers")
        self.label = SwitchLabel("Ruler", self.switch)

    def _settle(self, timeout_ms=2000):
        """Wait for the slide to finish (PySide6 has no QTest.qWaitFor)."""

        waited = 0
        while self.switch.animation.state() != QAbstractAnimation.State.Stopped:
            self.assertLess(waited, timeout_ms, "knob animation did not finish")
            QTest.qWait(10)
            waited += 10

    def test_checkable_off_by_default_with_pointer_cursor(self):
        self.assertTrue(self.switch.isCheckable())
        self.assertFalse(self.switch.isChecked())
        self.assertEqual(self.switch.knobPosition, 0.0)
        self.assertEqual(self.switch.cursor().shape(), Qt.CursorShape.PointingHandCursor)
        self.assertEqual(self.label.cursor().shape(), Qt.CursorShape.PointingHandCursor)
        self.assertEqual(self.label.toolTip(), "Show/hide rulers")

    def test_click_toggles_and_slides_knob(self):
        QTest.mouseClick(self.switch, Qt.MouseButton.LeftButton)
        self.assertTrue(self.switch.isChecked())
        self.assertEqual(self.switch.animation.state(), QAbstractAnimation.State.Running)
        self.assertLess(self.switch.knobPosition, 1.0)
        self._settle()
        self.assertEqual(self.switch.knobPosition, 1.0)

        QTest.mouseClick(self.switch, Qt.MouseButton.LeftButton)
        self.assertFalse(self.switch.isChecked())
        self._settle()
        self.assertEqual(self.switch.knobPosition, 0.0)

    def test_knob_moves_right_when_on(self):
        self.switch.set_animation_duration(0)
        off_left = self.switch.knob_rect().left()
        self.switch.click()
        self.assertGreater(self.switch.knob_rect().left(), off_left)

    def test_space_key_toggles(self):
        self.switch.set_animation_duration(0)
        QTest.keyClick(self.switch, Qt.Key.Key_Space)
        self.assertTrue(self.switch.isChecked())
        self.assertEqual(self.switch.knobPosition, 1.0)
        QTest.keyClick(self.switch, Qt.Key.Key_Space)
        self.assertFalse(self.switch.isChecked())

    def test_set_checked_from_code_places_knob_without_animating(self):
        self.switch.setChecked(True)
        self.assertEqual(self.switch.animation.state(), QAbstractAnimation.State.Stopped)
        self.assertEqual(self.switch.knobPosition, 1.0)
        self.switch.setChecked(False)
        self.assertEqual(self.switch.knobPosition, 0.0)

    def test_clicking_label_toggles_switch(self):
        self.switch.set_animation_duration(0)
        QTest.mouseClick(self.label, Qt.MouseButton.LeftButton)
        self.assertTrue(self.switch.isChecked())
        QTest.mouseClick(self.label, Qt.MouseButton.RightButton)
        self.assertTrue(self.switch.isChecked())  # only the primary button toggles

    def test_track_size_sets_fixed_widget_size(self):
        self.switch.set_track_size(34, 18, 3)
        self.assertEqual(self.switch.size(), QSize(40, 24))
        self.assertEqual(self.switch.track_size(), QSize(34, 18))


if __name__ == "__main__":
    unittest.main()
