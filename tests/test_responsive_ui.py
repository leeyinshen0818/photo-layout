import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage, QPalette
from PySide6.QtWidgets import QApplication, QComboBox, QDoubleSpinBox, QPushButton

from photo_print_layout.crop import CropState
from photo_print_layout.crop_dialog import CropEditorDialog
from photo_print_layout.image_loader import LoadedPhoto
from photo_print_layout.main_window import MainWindow
from photo_print_layout.models import SizeMM
from photo_print_layout.ui_scale import (
    MAX_UI_SCALE,
    MIN_UI_SCALE,
    UiMetrics,
    metrics_for_size,
    ui_scale_for_size,
)


class ResponsiveScaleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")

    def test_requested_resolution_and_scaling_matrix(self):
        cases = (
            # Physical resolution, Windows scale, available logical dimensions.
            (1366, 768, 1.00, 1366, 768, 8 / 9),
            (1366, 768, 1.25, 1093, 614, MIN_UI_SCALE),
            (1920, 1080, 1.25, 1536, 864, 1.0),
            (1920, 1080, 1.00, 1920, 1080, MAX_UI_SCALE),
            (2560, 1440, 1.50, 1707, 960, 10 / 9),
            (2560, 1440, 1.25, 2048, 1152, MAX_UI_SCALE),
            (2560, 1440, 1.00, 2560, 1440, MAX_UI_SCALE),
        )
        for physical_width, physical_height, dpi_scale, width, height, expected in cases:
            with self.subTest(
                resolution=(physical_width, physical_height), windows_scale=dpi_scale
            ):
                self.assertAlmostEqual(ui_scale_for_size(width, height), expected, places=3)

    def test_metrics_scale_as_one_design_system(self):
        small = UiMetrics(MIN_UI_SCALE)
        preferred = UiMetrics(1.0)
        large = UiMetrics(MAX_UI_SCALE)
        self.assertLess(small.sidebar_width, preferred.sidebar_width)
        self.assertLess(preferred.sidebar_width, large.sidebar_width)
        self.assertLess(small.control_height, preferred.control_height)
        self.assertLess(preferred.control_height, large.control_height)
        self.assertEqual(preferred.sidebar_width, 285)
        self.assertEqual(preferred.control_height, 34)

    def test_two_column_structure_and_preview_dominance_are_preserved(self):
        for width, height in ((1093, 614), (1536, 864), (1920, 1080), (2560, 1440)):
            metrics = metrics_for_size(width, height)
            window = MainWindow(metrics)
            try:
                self.assertEqual(window._root_layout.count(), 2)
                self.assertEqual(window._controls_panel.width(), metrics.sidebar_width)
                expected_preview_minimum = metrics.px(440)
                self.assertEqual(window.preview.minimumWidth(), expected_preview_minimum)
                available_preview = (
                    width
                    - metrics.sidebar_width
                    - metrics.outer_margin * 3
                )
                self.assertGreater(available_preview, metrics.sidebar_width)
            finally:
                window.close()

    def test_controls_share_height_and_scaled_widths(self):
        for scale in (MIN_UI_SCALE, 1.0, MAX_UI_SCALE):
            metrics = UiMetrics(scale)
            window = MainWindow(metrics)
            try:
                controls = (
                    window.findChildren(QPushButton)
                    + window.findChildren(QComboBox)
                    + window.findChildren(QDoubleSpinBox)
                )
                self.assertTrue(controls)
                self.assertTrue(
                    all(control.height() == metrics.control_height for control in controls)
                )
                self.assertEqual(window.width_spin.width(), metrics.px(70))
                self.assertEqual(window.height_spin.width(), metrics.px(70))
                self.assertEqual(window.unit_combo.width(), metrics.px(58))
            finally:
                window.close()

    def test_combo_popups_have_an_explicit_light_palette_and_states(self):
        window = MainWindow(UiMetrics(1.0))
        try:
            for combo in window.findChildren(QComboBox):
                palette = combo.view().palette()
                self.assertEqual(palette.color(QPalette.ColorRole.Base), QColor("white"))
                self.assertEqual(
                    palette.color(QPalette.ColorRole.Highlight), QColor("#e7efff")
                )
                popup_style = combo.view().styleSheet()
                self.assertIn("background: #ffffff", popup_style)
                self.assertIn("item:hover", popup_style)
                self.assertIn("item:selected", popup_style)
        finally:
            window.close()

    def test_reapplying_metrics_scales_without_reflowing_or_changing_state(self):
        window = MainWindow(UiMetrics(1.0))
        try:
            settings = window._settings
            first_widgets = tuple(
                window._root_layout.itemAt(index).widget()
                for index in range(window._root_layout.count())
            )
            window._apply_ui_metrics(UiMetrics(MIN_UI_SCALE), resize_window=False)
            self.assertEqual(window._controls_panel.width(), UiMetrics(MIN_UI_SCALE).sidebar_width)
            self.assertEqual(window._settings, settings)
            self.assertEqual(
                first_widgets,
                tuple(
                    window._root_layout.itemAt(index).widget()
                    for index in range(window._root_layout.count())
                ),
            )
        finally:
            window.close()

    def test_crop_editor_uses_the_same_scaled_control_and_canvas_metrics(self):
        metrics = UiMetrics(MIN_UI_SCALE)
        window = MainWindow(metrics)
        image = QImage(200, 400, QImage.Format.Format_RGBA8888)
        image.fill(QColor("white"))
        photo = LoadedPhoto(Path("responsive.png"), 200, 400, image)
        dialog = CropEditorDialog(
            photo,
            SizeMM(279.4, 355.6),
            CropState(),
            window,
        )
        try:
            self.assertEqual(dialog.minimumWidth(), metrics.px(640))
            self.assertEqual(dialog.minimumHeight(), metrics.px(600))
            self.assertEqual(dialog.canvas.minimumWidth(), metrics.px(520))
            self.assertEqual(dialog.canvas.minimumHeight(), metrics.px(440))
            self.assertTrue(
                all(
                    button.height() == metrics.control_height
                    for button in dialog.findChildren(QPushButton)
                )
            )
        finally:
            dialog.close()
            window.close()


if __name__ == "__main__":
    unittest.main()
