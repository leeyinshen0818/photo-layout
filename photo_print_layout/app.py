"""Application bootstrap."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow
from .release_smoke import run_release_smoke_test


def _resolve_icon_path() -> Path:
    """Return the path to the application icon.

    Inside a PyInstaller one-file bundle ``sys._MEIPASS`` points to the
    temporary extraction directory.  During normal development the icon
    lives in the ``logo/`` folder relative to the project root (i.e. one
    level above *this* package).
    """
    base: Path
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent.parent

    return base / "logo" / "Photo_Layout.ico"


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

    icon_path = _resolve_icon_path()
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    if "--release-smoke-test" in sys.argv:
        return run_release_smoke_test()

    window = MainWindow()
    window.showMaximized()
    return app.exec()
