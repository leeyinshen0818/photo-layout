"""Application bootstrap."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Photo Print Layout Manager")
    app.setOrganizationName("Photo Print Layout Manager")
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()
    return app.exec()

