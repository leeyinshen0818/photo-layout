"""The app-agnostic helpers in ui_scale: scale, sizing, sidebar, window limits, diagnostics; and the test audit."""

import unittest

from qt_test_support import (
    application,
    audit_widget_tree,
    configure_offscreen,
    real_fonts_configured,
    scroll_report,
    text_problems,
)

configure_offscreen()  # offscreen Qt with real system fonts, before any QApplication

from PySide6.QtCore import QSize
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from photo_print_layout.ui_scale import (
    ScaleConfig,
    UiMetrics,
    apply_size_limits,
    available_client_size,
    collect_diagnostics,
    combo_width_for,
    compute_scale,
    control_height,
    fit_to_screen,
    format_diagnostics,
    install_diagnostics,
    restore_geometry_safely,
    scrollable_sidebar,
    spin_width_for,
    text_height,
    text_width,
    title_bar_height,
)


CONFIG = ScaleConfig(reference_width=1536, reference_height=816, title_bar=23, status_bar=22)


class ScaleComputationTests(unittest.TestCase):
    def test_reference_screen_is_scale_one(self):
        self.assertEqual(compute_scale(1536, 816, CONFIG).used, 1.0)

    def test_chrome_is_subtracted_before_comparing_heights(self):
        result = compute_scale(1280, 672, CONFIG)
        self.assertAlmostEqual(result.raw, (672 - 45) / (816 - 45))
        self.assertLess(result.raw, 672 / 816)

    def test_width_or_height_whichever_is_tighter(self):
        self.assertAlmostEqual(compute_scale(1920, 1032, CONFIG).raw, 1920 / 1536)

    def test_clamped_to_min_and_max(self):
        low, high = compute_scale(800, 500, CONFIG), compute_scale(5000, 3000, CONFIG)
        self.assertEqual((low.used, high.used), (CONFIG.min_scale, CONFIG.max_scale))
        self.assertTrue(low.clamped and high.clamped)
        self.assertEqual(CONFIG.max_scale, 1.75)

    def test_degenerate_area_is_scale_one(self):
        self.assertEqual(compute_scale(0, 0, CONFIG).used, 1.0)

    def test_metrics_px_rounds_and_respects_minimum(self):
        metrics = UiMetrics(0.72)
        self.assertEqual(metrics.px(34), 24)
        self.assertEqual(metrics.px(10, 9), 9)


class QtTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = application("Fusion")  # setStyle only once per run


class SizingTests(QtTestCase):
    def test_real_fonts_are_used_offscreen(self):
        if not real_fonts_configured():
            self.skipTest("no system font folder on this platform")
        font = QFont("Segoe UI")
        font.setPixelSize(21)
        self.assertLess(text_width(font, "Photo Print Layout"), 200)  # boxes would be ~378

    def test_text_sizes_grow_with_the_font(self):
        small, large = QFont("Segoe UI"), QFont("Segoe UI")
        small.setPixelSize(10)
        large.setPixelSize(20)
        self.assertGreater(text_width(large, "mm"), text_width(small, "mm"))
        self.assertGreater(text_height(large), text_height(small))
        self.assertEqual(control_height(small, padding=4, minimum=100), 100)
        self.assertEqual(control_height(small, padding=4), text_height(small) + 10)

    def test_combo_and_spin_widths_fit_their_texts(self):
        combo = QComboBox()
        combo.addItems(["in", "cm", "mm"])
        combo.setFixedWidth(combo_width_for(combo))
        for index in range(3):
            combo.setCurrentIndex(index)
            self.assertEqual(text_problems(combo), [])
        spin = QDoubleSpinBox()
        spin.setRange(0, 1000)
        spin.setValue(888.88)
        spin.setFixedWidth(spin_width_for(spin, ["888.88"]))
        self.assertEqual(text_problems(spin), [])

    def test_fit_to_screen_never_exceeds_the_available_area(self):
        room = available_client_size(title_bar=23)
        fitted = fit_to_screen(QSize(100000, 100000), title_bar=23)
        self.assertEqual(fitted, room)
        self.assertEqual(fit_to_screen(QSize(10, 10)), QSize(10, 10))
        framed = available_client_size(title_bar=23, margin=8)
        self.assertEqual((room.width() - framed.width(), room.height() - framed.height()), (16, 16))


class PanelTests(QtTestCase):
    def _sidebar(self, rows: int):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        for index in range(rows):
            button = QPushButton(f"Row {index}")
            button.setFixedHeight(30)
            layout.addWidget(button)
        host = QWidget()
        host_layout = QVBoxLayout(host)
        sidebar = scrollable_sidebar(panel, 200, scrollbar_width=10)
        host_layout.addWidget(sidebar)
        host.resize(400, 300)
        host.show()
        QApplication.processEvents()
        return host, sidebar, panel

    def test_no_scrollbar_when_content_fits(self):
        host, sidebar, panel = self._sidebar(3)
        self.assertFalse(sidebar.scrollbar_visible)
        self.assertEqual((sidebar.width(), panel.width()), (200, 200))
        self.assertFalse(sidebar.horizontalScrollBar().isVisible())
        host.close()

    def test_vertical_scrollbar_only_when_taller_and_panel_width_kept(self):
        host, sidebar, panel = self._sidebar(20)
        self.assertTrue(sidebar.scrollbar_visible)
        self.assertEqual(panel.width(), 200)
        self.assertGreaterEqual(sidebar.width(), 210)
        self.assertGreaterEqual(sidebar.viewport().width(), 200)  # never narrower than the panel
        self.assertEqual(scroll_report(host)[0]["scrolling"], True)
        self.assertEqual(audit_widget_tree(host), [])
        host.close()


class AuditDetectsProblemsTests(QtTestCase):
    """The audit must report real defects, or a passing matrix proves nothing."""

    def _host(self):
        host = QWidget()
        host.resize(300, 200)
        return host

    def test_clipped_label_text(self):
        host = self._host()
        label = QLabel("A label that is much too long for its box", host)
        label.setGeometry(0, 0, 40, 30)
        host.show()
        self.assertTrue(any("text" in p for p in audit_widget_tree(host)))
        host.close()

    def test_elided_combo_item(self):
        host = self._host()
        combo = QComboBox(host)
        combo.addItems(["Short", "A much longer option text"])
        combo.setGeometry(0, 0, 60, 30)
        host.show()
        self.assertTrue(any("elided" in p for p in audit_widget_tree(host)))
        host.close()

    def test_overlap_and_outside_parent(self):
        host = self._host()
        QPushButton("A", host).setGeometry(0, 0, 80, 30)
        QPushButton("B", host).setGeometry(40, 10, 80, 30)
        QPushButton("C", host).setGeometry(280, 0, 80, 30)
        host.show()
        problems = audit_widget_tree(host)
        self.assertTrue(any(p.startswith("overlap") for p in problems))
        self.assertTrue(any("outside its parent" in p for p in problems))
        host.close()

    def test_squeezed_below_minimum_size_hint(self):
        host = self._host()
        button = QPushButton("Squeezed", host)
        button.setGeometry(0, 0, 80, 6)
        host.show()
        self.assertTrue(any("squeezed" in p or "tall" in p for p in audit_widget_tree(host)))
        host.close()

    def test_clean_tree_has_no_problems(self):
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.addWidget(QLabel("Fine"))
        layout.addWidget(QPushButton("Fine too"))
        host.resize(300, 200)
        host.show()
        QApplication.processEvents()
        self.assertEqual(audit_widget_tree(host), [])
        host.close()


class WindowTests(QtTestCase):
    def test_minimum_is_bounded_by_the_screen(self):
        window = QMainWindow()
        applied = apply_size_limits(window, QSize(100000, 100000), initial=QSize(100000, 100000))
        room = available_client_size(window.screen())
        self.assertEqual(applied, room)
        self.assertLessEqual(window.width(), room.width())
        window.close()

    def test_restored_geometry_always_ends_on_a_screen(self):
        window = QMainWindow()
        window.setGeometry(50000, 50000, 400, 300)  # saved on a monitor that is gone
        off_screen = window.saveGeometry()
        fresh = QMainWindow()
        fresh.setGeometry(10, 10, 300, 200)
        restore_geometry_safely(fresh, off_screen)
        available = fresh.screen().availableGeometry()
        self.assertTrue(available.intersects(fresh.geometry()))
        self.assertLessEqual(fresh.width(), available.width())
        self.assertFalse(restore_geometry_safely(fresh, None))
        window.close()
        fresh.close()


class DiagnosticsAndWatcherTests(QtTestCase):
    def test_diagnostics_rows_and_extra(self):
        window = QMainWindow()
        window.resize(400, 300)
        rows = dict(collect_diagnostics(window, extra=lambda: [("Custom", "42")]))
        for key in ("Physical resolution", "Device pixel ratio", "Available area", "System font"):
            self.assertIn(key, rows)
        self.assertEqual(rows["Custom"], "42")
        self.assertIn("Custom  42", format_diagnostics([("Custom", "42")]))
        overlay = install_diagnostics(window)
        window.show()
        overlay.shortcut.activated.emit()
        self.assertTrue(overlay.isVisible())
        overlay.copy()
        self.assertIn("Device pixel ratio", QGuiApplication.clipboard().text())
        window.close()

    def test_title_bar_allowance_comes_from_the_qt_style(self):
        self.assertGreater(title_bar_height(), 0)
        self.assertEqual(ScaleConfig(status_bar=22).chrome_height(), title_bar_height() + 22)


if __name__ == "__main__":
    unittest.main()
