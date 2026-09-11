import os
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QDialog

from photo_print_layout.crop import CropState, crop_source_rect
from photo_print_layout.crop_dialog import CropEditorDialog
from photo_print_layout.image_loader import LoadedPhoto
from photo_print_layout.main_window import MainWindow
from photo_print_layout.models import LayoutSettings, ResizeMode


def dummy_photo(name: str = "photo.png") -> LoadedPhoto:
    image = QImage(200, 400, QImage.Format.Format_RGBA8888)
    image.fill(0xFFFFFFFF)
    return LoadedPhoto(Path(name), 200, 400, image)


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

    def test_crop_control_requires_crop_mode_and_photo(self):
        self.window.set_photo(dummy_photo())
        self.assertFalse(self.window.crop_button.isEnabled())
        self._select_mode(ResizeMode.CROP)
        self.assertTrue(self.window.crop_button.isEnabled())
        self._select_mode(ResizeMode.FIT)
        self.assertFalse(self.window.crop_button.isEnabled())

    def test_confirmed_crop_survives_mode_switch_and_reopen(self):
        confirmed = CropState(2.0, 0.4, 0.6)
        seen_initial_states = []

        class AcceptedDialog:
            def __init__(dialog_self, photo, target, initial, parent):
                del photo, target, parent
                seen_initial_states.append(initial)
                dialog_self.crop_state = confirmed

            def exec(dialog_self):
                return QDialog.DialogCode.Accepted

        self.window.set_photo(dummy_photo())
        self._select_mode(ResizeMode.CROP)
        with patch("photo_print_layout.main_window.CropEditorDialog", AcceptedDialog):
            self.window.open_crop_editor()
            self._select_mode(ResizeMode.FIT)
            self._select_mode(ResizeMode.CROP)
            self.window.open_crop_editor()

        self.assertEqual(self.window._crop_state, confirmed)
        self.assertEqual(seen_initial_states, [CropState(), confirmed])
        expected = crop_source_rect(confirmed, 200, 400, 11, 14)
        self.assertEqual(self.window.preview._layout().source, expected)

    def test_cancel_does_not_replace_confirmed_crop(self):
        confirmed = CropState(1.8, 0.45, 0.55)

        class RejectedDialog:
            def __init__(dialog_self, *args):
                dialog_self.crop_state = CropState(3.0, 0.2, 0.8)

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
        self.window._crop_state = CropState(2.0, 0.4, 0.6)
        self.window.set_photo(dummy_photo("second.png"))
        self.assertEqual(self.window._crop_state, CropState())

    def test_dialog_reset_returns_to_centered_minimum_cover(self):
        dialog = CropEditorDialog(
            dummy_photo(),
            self.window._settings.photo_size,
            CropState(2.5, 0.3, 0.7),
        )
        dialog.reset_crop()
        self.assertEqual(dialog.crop_state, CropState())
        dialog.close()


if __name__ == "__main__":
    unittest.main()
