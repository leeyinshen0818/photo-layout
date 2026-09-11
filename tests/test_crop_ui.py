import os
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from photo_print_layout.crop import CropState, crop_source_rect, default_crop_state
from photo_print_layout.crop_dialog import CropEditorDialog
from photo_print_layout.exporter import ExportError
from photo_print_layout.image_loader import LoadedPhoto
from photo_print_layout.main_window import MainWindow
from photo_print_layout.models import LayoutSettings, Position, ResizeMode, SUPER_A3


def dummy_photo(name: str = "photo.png", width: int = 200, height: int = 400) -> LoadedPhoto:
    image = QImage(width, height, QImage.Format.Format_RGBA8888)
    image.fill(0xFFFFFFFF)
    return LoadedPhoto(Path(name), width, height, image)


def smaller_crop(width: int = 200, height: int = 400) -> CropState:
    base = default_crop_state(width, height, 11, 14)
    new_width = base.width * 0.6
    new_height = base.height * 0.6
    return CropState(
        0.5 - new_width / 2,
        0.5 - new_height / 2,
        new_width,
        new_height,
    )


class CropUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()

    def tearDown(self):
        self.window.close()

    def _select_mode(self, mode: ResizeMode) -> None:
        self.window.resize_combo.setCurrentIndex(self.window.resize_combo.findData(mode))

    def test_fit_inside_is_default_and_crop_control_is_disabled(self):
        self.assertEqual(LayoutSettings().resize_mode, ResizeMode.FIT)
        self.assertEqual(self.window.resize_combo.currentData(), ResizeMode.FIT)
        self.assertFalse(self.window.crop_button.isEnabled())
        self.assertFalse(self.window.clear_button.isEnabled())
        self.assertFalse(self.window.output_button.isEnabled())

    def test_crop_control_requires_crop_mode_and_photo(self):
        self.window.set_photo(dummy_photo())
        self.assertTrue(self.window.clear_button.isEnabled())
        self.assertTrue(self.window.output_button.isEnabled())
        self.assertFalse(self.window.crop_button.isEnabled())
        self._select_mode(ResizeMode.CROP)
        self.assertTrue(self.window.crop_button.isEnabled())
        self.assertTrue(self.window.crop_button.property("cropActive"))
        self._select_mode(ResizeMode.FIT)
        self.assertFalse(self.window.crop_button.isEnabled())
        self.assertFalse(self.window.crop_button.property("cropActive"))

    def test_confirmed_crop_survives_mode_switch_and_reopen(self):
        confirmed = smaller_crop()
        seen_initial_states = []

        class AcceptedDialog:
            def __init__(dialog_self, photo, target, initial, parent):
                del photo, target, parent
                seen_initial_states.append(initial)
                dialog_self.crop_state = confirmed

            def exec(dialog_self):
                return QDialog.DialogCode.Accepted

        self.window.set_photo(dummy_photo())
        initial = self.window._crop_state
        self._select_mode(ResizeMode.CROP)
        with patch("photo_print_layout.main_window.CropEditorDialog", AcceptedDialog):
            self.window.open_crop_editor()
            self._select_mode(ResizeMode.FIT)
            self._select_mode(ResizeMode.CROP)
            self.window.open_crop_editor()

        self.assertEqual(self.window._crop_state, confirmed)
        self.assertEqual(seen_initial_states, [initial, confirmed])
        expected = crop_source_rect(confirmed, 200, 400, 11, 14)
        self.assertEqual(self.window.preview._layout().source, expected)

    def test_cancel_does_not_replace_confirmed_crop(self):
        confirmed = smaller_crop()

        class RejectedDialog:
            def __init__(dialog_self, *args):
                dialog_self.crop_state = CropState(0.1, 0.1, 0.2, 0.2)

            def exec(dialog_self):
                return QDialog.DialogCode.Rejected

        self.window.set_photo(dummy_photo())
        self.window._crop_state = confirmed
        self._select_mode(ResizeMode.CROP)
        with patch("photo_print_layout.main_window.CropEditorDialog", RejectedDialog):
            self.window.open_crop_editor()
        self.assertEqual(self.window._crop_state, confirmed)

    def test_new_photo_resets_crop_state(self):
        self.window.set_photo(dummy_photo("first.png"))
        self.window._crop_state = smaller_crop()
        self.window.set_photo(dummy_photo("second.png"))
        self.assertEqual(self.window._crop_state, default_crop_state(200, 400, 11, 14))

    def test_dialog_has_no_zoom_controls_and_reset_restores_default(self):
        dialog = CropEditorDialog(
            dummy_photo(), self.window._settings.photo_size_mm, smaller_crop()
        )
        self.assertFalse(hasattr(dialog, "zoom_slider"))
        dialog.reset_crop()
        self.assertEqual(dialog.crop_state, default_crop_state(200, 400, 11, 14))
        dialog.close()

    def test_crop_frame_can_move_resize_and_image_can_pan(self):
        dialog = CropEditorDialog(
            dummy_photo(), self.window._settings.photo_size_mm, smaller_crop()
        )
        dialog.show()
        self.app.processEvents()
        canvas = dialog.canvas

        before_move = canvas.crop_state
        center = canvas._crop_frame().center().toPoint()
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=center)
        QTest.mouseMove(canvas, center + QPoint(20, 12), 10)
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=center + QPoint(20, 12))
        self.assertNotEqual(canvas.crop_state, before_move)

        before_resize = canvas.crop_state
        handle = canvas._crop_frame().bottomRight().toPoint()
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=handle)
        QTest.mouseMove(canvas, handle - QPoint(45, 35), 10)
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=handle - QPoint(45, 35))
        self.assertLess(canvas.crop_state.width, before_resize.width)
        source = crop_source_rect(canvas.crop_state, 200, 400, 11, 14)
        self.assertAlmostEqual(source.width / source.height, 11 / 14)

        before_pan = canvas.crop_state
        fixed_frame = canvas._crop_frame()
        pan_at = fixed_frame.center().toPoint()
        QTest.mousePress(canvas, Qt.MouseButton.RightButton, pos=pan_at)
        QTest.mouseMove(canvas, pan_at + QPoint(15, 8), 10)
        QTest.mouseRelease(canvas, Qt.MouseButton.RightButton, pos=pan_at + QPoint(15, 8))
        self.assertNotEqual(canvas.crop_state, before_pan)
        self.assertAlmostEqual(canvas._crop_frame().left(), fixed_frame.left(), places=4)
        self.assertAlmostEqual(canvas._crop_frame().top(), fixed_frame.top(), places=4)
        dialog.close()

    def test_new_photo_updates_paper_target_and_crop_frame_orientation(self):
        self.window.set_photo(dummy_photo("landscape.png", 400, 200))
        layout = self.window.preview._layout()
        self.assertGreater(layout.paper.width, layout.paper.height)
        self.assertAlmostEqual(layout.target.width / layout.target.height, 14 / 11)
        dialog = CropEditorDialog(
            self.window._photo, self.window._settings.photo_size_mm, self.window._crop_state
        )
        frame = dialog.canvas._crop_frame()
        self.assertAlmostEqual(frame.width() / frame.height(), 14 / 11)
        dialog.close()

    def test_clear_removes_image_state_but_preserves_layout_selections(self):
        self.window.paper_combo.setCurrentIndex(self.window.paper_combo.findData(SUPER_A3))
        self.window.position_combo.setCurrentIndex(self.window.position_combo.findData(Position.CENTER))
        self._select_mode(ResizeMode.CROP)
        self.window.set_photo(dummy_photo())
        preserved = (
            self.window._settings.paper,
            self.window._settings.photo_size,
            self.window._settings.position,
            self.window._settings.resize_mode,
            self.window._settings.dpi,
        )
        self.window.clear_photo()
        self.assertIsNone(self.window._photo)
        self.assertIsNone(self.window.preview._photo)
        self.assertIsNone(self.window._crop_state)
        self.assertEqual(self.window.photo_info.text(), "No photo selected")
        self.assertFalse(self.window.clear_button.isEnabled())
        self.assertFalse(self.window.output_button.isEnabled())
        self.assertEqual(
            preserved,
            (
                self.window._settings.paper,
                self.window._settings.photo_size,
                self.window._settings.position,
                self.window._settings.resize_mode,
                self.window._settings.dpi,
            ),
        )

    def test_output_uses_save_as_appends_jpg_and_reports_success(self):
        self.window.set_photo(dummy_photo())
        with (
            patch(
                "photo_print_layout.main_window.QFileDialog.getSaveFileName",
                return_value=("chosen-layout", "JPEG Image (*.jpg *.jpeg)"),
            ) as save_dialog,
            patch(
                "photo_print_layout.main_window.export_jpeg",
                return_value=Path("chosen-layout.jpg"),
            ) as export,
            patch("photo_print_layout.main_window.QMessageBox.information") as information,
        ):
            self.window.output_jpeg()
        save_dialog.assert_called_once()
        self.assertEqual(export.call_args.args[0], Path("chosen-layout.jpg"))
        information.assert_called_once()

    def test_output_failure_is_reported_without_crashing(self):
        self.window.set_photo(dummy_photo())
        with (
            patch(
                "photo_print_layout.main_window.QFileDialog.getSaveFileName",
                return_value=("bad-path.jpg", "JPEG Image (*.jpg *.jpeg)"),
            ),
            patch(
                "photo_print_layout.main_window.export_jpeg",
                side_effect=ExportError("write failed"),
            ),
            patch("photo_print_layout.main_window.QMessageBox.warning") as warning,
        ):
            self.window.output_jpeg()
        self.assertIn("write failed", warning.call_args.args[2])


if __name__ == "__main__":
    unittest.main()
