"""Main application window and control wiring."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .image_loader import ImageLoadError, LoadedPhoto, SUPPORTED_FILE_FILTER, load_photo
from .models import PAPER_SIZES, PHOTO_SIZES, LayoutSettings, Position, ResizeMode
from .preview import PreviewWidget


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._settings = LayoutSettings()
        self._photo: LoadedPhoto | None = None
        self._preferences = QSettings()

        self.setWindowTitle("Photo Print Layout Manager")
        self.resize(900, 700)
        self.setMinimumSize(760, 600)
        self._build_ui()
        self._apply_style()
        self._restore_window_geometry()

    def _build_ui(self) -> None:
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(20)

        controls = QFrame()
        controls.setObjectName("controlsPanel")
        controls.setFixedWidth(285)
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(20, 20, 20, 20)
        controls_layout.setSpacing(14)

        title = QLabel("Photo Print Layout")
        title.setObjectName("title")
        subtitle = QLabel("Prepare one photo for A3 printing")
        subtitle.setObjectName("subtitle")
        controls_layout.addWidget(title)
        controls_layout.addWidget(subtitle)

        controls_layout.addSpacing(8)
        controls_layout.addWidget(self._section_label("Photo"))
        open_button = QPushButton("Open Photo…")
        open_button.setObjectName("primaryButton")
        open_button.clicked.connect(self.open_photo)
        controls_layout.addWidget(open_button)

        self.photo_info = QLabel("No photo selected")
        self.photo_info.setObjectName("photoInfo")
        self.photo_info.setWordWrap(True)
        self.photo_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        controls_layout.addWidget(self.photo_info)

        form = QFormLayout()
        form.setContentsMargins(0, 5, 0, 0)
        form.setVerticalSpacing(13)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.paper_combo = QComboBox()
        for paper in PAPER_SIZES:
            self.paper_combo.addItem(paper.label, paper)
        self.paper_combo.currentIndexChanged.connect(self._controls_changed)
        form.addRow("Paper", self.paper_combo)

        self.photo_size_combo = QComboBox()
        for size in PHOTO_SIZES:
            self.photo_size_combo.addItem(size.label, size)
        form.addRow("Photo Size", self.photo_size_combo)

        self.position_combo = QComboBox()
        for position in Position:
            self.position_combo.addItem(position.value, position)
        self.position_combo.currentIndexChanged.connect(self._controls_changed)
        form.addRow("Position", self.position_combo)

        self.resize_combo = QComboBox()
        for mode in ResizeMode:
            self.resize_combo.addItem(mode.value, mode)
        self.resize_combo.currentIndexChanged.connect(self._controls_changed)
        form.addRow("Resize Mode", self.resize_combo)

        dpi_value = QLabel("300 DPI")
        dpi_value.setObjectName("fixedValue")
        form.addRow("Output", dpi_value)
        controls_layout.addLayout(form)
        controls_layout.addStretch()

        phase_note = QLabel("Phase 1 · Preview only\nPrinting and crop adjustment come next.")
        phase_note.setObjectName("phaseNote")
        phase_note.setWordWrap(True)
        controls_layout.addWidget(phase_note)

        preview_panel = QFrame()
        preview_panel.setObjectName("previewPanel")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(8)
        preview_heading = QLabel("Preview")
        preview_heading.setObjectName("previewHeading")
        preview_layout.addWidget(preview_heading)
        self.preview = PreviewWidget()
        preview_layout.addWidget(self.preview, 1)

        root.addWidget(controls)
        root.addWidget(preview_panel, 1)
        self.setCentralWidget(central)

        open_action = QAction("Open Photo", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_photo)
        self.addAction(open_action)

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    def _controls_changed(self) -> None:
        self._settings = replace(
            self._settings,
            paper=self.paper_combo.currentData(),
            photo_size=self.photo_size_combo.currentData(),
            position=self.position_combo.currentData(),
            resize_mode=self.resize_combo.currentData(),
        )
        self.preview.set_settings(self._settings)
        self.statusBar().showMessage(
            f"{self._settings.paper.label} · {self._settings.photo_size.label} · "
            f"{self._settings.position.value} · {self._settings.resize_mode.value}"
        )

    def open_photo(self) -> None:
        start_at = self._preferences.value("lastPhotoDirectory", "")
        path, _ = QFileDialog.getOpenFileName(self, "Open Photo", start_at, SUPPORTED_FILE_FILTER)
        if not path:
            return
        try:
            photo = load_photo(path, self._settings.photo_size)
        except ImageLoadError as exc:
            QMessageBox.warning(self, "Unable to Open Photo", str(exc))
            return

        self._photo = photo
        self.photo_info.setText(photo.summary)
        self.photo_info.setToolTip(str(photo.path))
        self.preview.set_photo(photo)
        self._preferences.setValue("lastPhotoDirectory", str(photo.path.parent))
        self.statusBar().showMessage(f"Loaded {photo.path.name}", 4000)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #f7f8fa; color: #20242b; }
            QFrame#controlsPanel { background: #ffffff; border: 1px solid #dfe3e8; border-radius: 10px; }
            QLabel#title { font-size: 21px; font-weight: 700; }
            QLabel#subtitle { color: #687180; font-size: 12px; }
            QLabel#sectionLabel, QLabel#previewHeading { font-size: 13px; font-weight: 700; }
            QLabel#previewHeading { font-size: 16px; }
            QLabel#photoInfo { background: #f4f6f8; border-radius: 6px; padding: 9px; color: #596273; }
            QLabel#fixedValue { padding: 5px 2px; color: #3e4652; }
            QLabel#phaseNote { color: #7b8492; font-size: 11px; }
            QPushButton#primaryButton { background: #246bfd; color: white; border: 0; border-radius: 6px; padding: 9px 12px; font-weight: 600; }
            QPushButton#primaryButton:hover { background: #1758d5; }
            QPushButton#primaryButton:pressed { background: #1248af; }
            QComboBox { background: white; border: 1px solid #cbd1d9; border-radius: 5px; padding: 6px 8px; min-width: 135px; }
            QComboBox:hover { border-color: #8e98a7; }
            QStatusBar { background: #ffffff; color: #687180; }
            """
        )

    def _restore_window_geometry(self) -> None:
        geometry = self._preferences.value("windowGeometry")
        if geometry:
            self.restoreGeometry(geometry)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self._preferences.setValue("windowGeometry", self.saveGeometry())
        super().closeEvent(event)
