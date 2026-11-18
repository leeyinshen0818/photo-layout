import unittest
from pathlib import Path

from qt_test_support import application, configure_offscreen

configure_offscreen()

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPalette
from PySide6.QtWidgets import QApplication, QComboBox, QDoubleSpinBox, QPushButton, QScrollArea

from qt_test_support import audit_widget_tree, text_problems
from photo_print_layout.crop import CropState
from photo_print_layout.crop_dialog import CropEditorDialog
from photo_print_layout.image_loader import LoadedPhoto
from photo_print_layout.main_window import MainWindow
from photo_print_layout.models import SizeMM
from photo_print_layout.ui_scale import (
    MAX_UI_SCALE,
    MIN_UI_SCALE,
    REFERENCE_HEIGHT,
    SCALE_CONFIG,
    ScrollableSidebar,
    UiMetrics,
    available_client_size,
    metrics_for_size,
    text_height,
    text_width,
    ui_scale_for_size,
)


def _height_scale(available_height: int) -> float:
    chrome = SCALE_CONFIG.chrome_height()
    return (available_height - chrome) / (REFERENCE_HEIGHT - chrome)


class ResponsiveScaleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application("Fusion")  # setStyle only once per run

    def test_requested_resolution_and_scaling_matrix(self):
        cases = (
            # Physical resolution, Windows scale -> available area (Windows 11 taskbar 48 px).
            (1366, 768, 1.00, 1366, 720, min(1366 / 1536, _height_scale(720))),
            (1366, 768, 1.25, 1093, 566, MIN_UI_SCALE),
            (1920, 1080, 1.25, 1536, 816, 1.0),
            (1920, 1080, 1.00, 1920, 1032, 1.25),  # width-limited
            (1280, 720, 1.00, 1280, 672, _height_scale(672)),
            (2560, 1440, 1.50, 1707, 912, 1707 / 1536),
            (2560, 1440, 1.25, 2048, 1104, 2048 / 1536),
            (2560, 1440, 1.00, 2560, 1392, 2560 / 1536),
            (3840, 2160, 1.00, 3840, 2112, MAX_UI_SCALE),
        )
        for physical_width, physical_height, dpi_scale, width, height, expected in cases:
            with self.subTest(
                resolution=(physical_width, physical_height), windows_scale=dpi_scale
            ):
                self.assertAlmostEqual(ui_scale_for_size(width, height), expected, places=3)

    def test_non_scaling_chrome_is_excluded_from_the_height_comparison(self):
        # Without subtracting title + status bar, 672 px would give 672 / 816 = 0.824.
        self.assertLess(ui_scale_for_size(1280, 672), 672 / REFERENCE_HEIGHT)
        self.assertEqual(MAX_UI_SCALE, 1.75)
        self.assertEqual(MIN_UI_SCALE, 0.72)

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
        for width, height in ((1093, 566), (1536, 816), (1920, 1032), (2560, 1392)):
            metrics = metrics_for_size(width, height)
            window = MainWindow(metrics)
            try:
                self.assertEqual(window._root_layout.count(), 2)
                self.assertIsInstance(window._root_layout.itemAt(0).widget(), ScrollableSidebar)
                self.assertIs(window._sidebar.widget(), window._controls_panel)
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

    def test_controls_share_height_and_fit_their_text(self):
        for scale in (MIN_UI_SCALE, 1.0, MAX_UI_SCALE):
            metrics = UiMetrics(scale)
            window = MainWindow(metrics)
            try:
                controls = window._app_controls()
                self.assertTrue(controls)
                self.assertGreaterEqual(window.control_height, metrics.control_height)
                self.assertTrue(all(control.height() == window.control_height for control in controls))
                for spin in (window.width_spin, window.height_spin):
                    self.assertGreaterEqual(spin.width(), metrics.px(70))
                    self.assertGreaterEqual(spin.width(), text_width(spin, "888.88"))
                self.assertGreaterEqual(window.unit_combo.width(), metrics.px(58))
                for unit_index in range(window.unit_combo.count()):
                    window.unit_combo.setCurrentIndex(unit_index)
                    self.assertEqual(text_problems(window.unit_combo), [], window.unit_combo.currentText())
                for spin in (window.width_spin, window.height_spin):
                    spin.setValue(888.88 if spin.decimals() == 2 else 888.8)
                    self.assertEqual(text_problems(spin), [])
                self.assertGreaterEqual(  # one line of text plus its stylesheet padding
                    window.photo_info.minimumHeight(),
                    text_height(window.photo_info) + 2 * metrics.px(9),
                )
            finally:
                window.close()

    def test_sidebar_scrolls_only_when_the_window_is_too_short(self):
        window = MainWindow(UiMetrics(1.0))
        try:
            window.show()
            window.resize(1536, 793)  # baseline maximized client area
            window.statusBar().showMessage("Ready")
            QApplication.processEvents()
            sidebar = window._sidebar
            self.assertFalse(sidebar.scrollbar_visible)
            self.assertEqual(sidebar.horizontalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.assertEqual(sidebar.frameShape(), QScrollArea.Shape.NoFrame)
            self.assertEqual(sidebar.width(), window.ui_metrics.sidebar_width)
            self.assertEqual(audit_widget_tree(window), [])

            window.resize(1536, window.minimumHeight())  # shortest the window may become
            QApplication.processEvents()
            self.assertLess(window._sidebar.viewport().height(), window._controls_panel.minimumSizeHint().height())
            self.assertTrue(sidebar.scrollbar_visible)
            self.assertEqual(window._controls_panel.width(), window.ui_metrics.sidebar_width)
            self.assertGreater(sidebar.width(), window.ui_metrics.sidebar_width)  # bar added
            self.assertEqual(audit_widget_tree(window), [])  # scrolls instead of squeezing
        finally:
            window.close()

    def test_window_minimum_never_exceeds_the_screen(self):
        window = MainWindow(UiMetrics(MAX_UI_SCALE))
        try:
            room = available_client_size(window.screen())
            self.assertLessEqual(window.minimumWidth(), room.width())
            self.assertLessEqual(window.minimumHeight(), room.height())
            small = MainWindow(UiMetrics(1.0))
            try:
                self.assertLess(small.minimumHeight(), UiMetrics(1.0).px(735))  # no longer the sidebar
                self.assertGreaterEqual(small.width(), small.minimumWidth())
                self.assertGreaterEqual(small.height(), small.minimumHeight())
            finally:
                small.close()
        finally:
            window.close()

    def test_diagnostics_overlay_toggles_and_copies(self):
        window = MainWindow(UiMetrics(1.0))
        try:
            window.show()
            QApplication.processEvents()
            overlay = window.diagnostics
            self.assertFalse(overlay.isVisible())
            overlay.shortcut.activated.emit()  # Ctrl+Shift+D
            self.assertTrue(overlay.isVisible())
            text = overlay.text.text()
            for needle in (
                "Screen", "Physical resolution", "Logical size", "Available area",
                "Device pixel ratio", "Logical / physical DPI", "UI scale raw / used",
                "System font", "Stylesheet font", "Sidebar height need / have",
                "Window size", "Qt / PySide",
            ):
                self.assertIn(needle, text)
            self.assertEqual(overlay.shortcut.key().toString(), "Ctrl+Shift+D")
            overlay.copy()
            self.assertEqual(QGuiApplication.clipboard().text(), overlay.report())
            overlay.shortcut.activated.emit()
            self.assertFalse(overlay.isVisible())
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
