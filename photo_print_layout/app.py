"""Application bootstrap."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow
from .release_smoke import run_release_smoke_test


def main() -> int:
    # Qt 6 is high-DPI aware by default. Pass-through keeps 125% and 150%
    # fractional scaling sharp without applying a second manual DPI multiplier.
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("Photo Print Layout Manager")
    app.setOrganizationName("Photo Print Layout Manager")
    app.setStyle("Fusion")

    if "--release-smoke-test" in sys.argv:
        return run_release_smoke_test()

    window = MainWindow()
    window.showMaximized()
    return app.exec()
