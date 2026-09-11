"""Main application window and control wiring."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
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

from .crop import CropState, default_crop_state
from .crop_dialog import CropEditorDialog
from .exporter import ExportError, ensure_jpeg_extension, export_jpeg
from .image_loader import ImageLoadError, LoadedPhoto, SUPPORTED_FILE_FILTER, load_photo
from .models import (
    PAPER_SIZES,
    PHOTO_SIZES,
    LayoutSettings,
    Position,
    Orientation,
    ResizeMode,
    layout_orientation_for_dimensions,
)
from .preview import PreviewWidget


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._settings = LayoutSettings()
        self._photo: LoadedPhoto | None = None
        self._crop_state: CropState | None = None
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
        self.clear_button = QPushButton("Clear")
        self.clear_button.setEnabled(False)
        self.clear_button.clicked.connect(self.clear_photo)
        photo_buttons = QHBoxLayout()
        photo_buttons.setSpacing(8)
        photo_buttons.addWidget(open_button, 1)
        photo_buttons.addWidget(self.clear_button)
        controls_layout.addLayout(photo_buttons)

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

        self.crop_button = QPushButton("Crop / Adjust…")
        self.crop_button.setObjectName("cropButton")
        self.crop_button.setProperty("cropActive", False)
        self.crop_button.clicked.connect(self.open_crop_editor)
        self.crop_button.setEnabled(False)
        form.addRow("", self.crop_button)

        dpi_value = QLabel("300 DPI")
        dpi_value.setObjectName("fixedValue")
        form.addRow("Resolution", dpi_value)
        controls_layout.addLayout(form)

        self.output_button = QPushButton("Output JPEG…")
        self.output_button.setObjectName("outputButton")
        self.output_button.setEnabled(False)
        self.output_button.clicked.connect(self.output_jpeg)
        controls_layout.addWidget(self.output_button)
        controls_layout.addStretch()

        phase_note = QLabel("Phase 2.2 · JPEG layout output\nPrinting remains unavailable.")
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
        self._update_crop_button()
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
            photo = load_photo(path)
        except ImageLoadError as exc:
            QMessageBox.warning(self, "Unable to Open Photo", str(exc))
            return

        self.set_photo(photo)
        self._preferences.setValue("lastPhotoDirectory", str(photo.path.parent))
        self.statusBar().showMessage(f"Loaded {photo.path.name}", 4000)

    def set_photo(self, photo: LoadedPhoto) -> None:
        """Install a new working photo and initialize its crop composition."""

        self._photo = photo
        self._settings = replace(
            self._settings,
            orientation=layout_orientation_for_dimensions(photo.width, photo.height),
        )
        target = self._settings.photo_size_mm
        self._crop_state = default_crop_state(
            photo.width, photo.height, target.width, target.height
        )
        self.photo_info.setText(photo.summary)
        self.photo_info.setToolTip(str(photo.path))
        self.preview.set_photo(photo)
        self.preview.set_settings(self._settings)
        self.preview.set_crop_state(self._crop_state)
        self.clear_button.setEnabled(True)
        self.output_button.setEnabled(True)
        self._update_crop_button()

    def clear_photo(self) -> None:
        """Clear only image-specific state, preserving user layout selections."""

        self._photo = None
        self._crop_state = None
        self._settings = replace(
            self._settings,
            orientation=Orientation.PORTRAIT,
        )
        self.photo_info.setText("No photo selected")
        self.photo_info.setToolTip("")
        self.preview.set_photo(None)
        self.preview.set_settings(self._settings)
        self.preview.set_crop_state(CropState())
        self.clear_button.setEnabled(False)
        self.output_button.setEnabled(False)
        self._update_crop_button()
        self.statusBar().showMessage("Image cleared", 3000)

    def output_jpeg(self) -> None:
        if self._photo is None:
            return
        last_directory = self._preferences.value(
            "lastOutputDirectory", str(self._photo.path.parent)
        )
        suggested = str(Path(last_directory) / f"{self._photo.path.stem}_layout.jpg")
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Output JPEG",
            suggested,
            "JPEG Image (*.jpg *.jpeg)",
        )
        if not selected:
            return

        output = ensure_jpeg_extension(selected)
        if os.path.normcase(os.path.abspath(output)) == os.path.normcase(
            os.path.abspath(self._photo.path)
        ):
            QMessageBox.warning(
                self,
                "Unable to Export JPEG",
                "Choose a different filename so the original photo remains unchanged.",
            )
            return
        try:
            written = export_jpeg(
                output,
                self._photo,
                self._settings,
                self._crop_state
                or default_crop_state(
                    self._photo.width,
                    self._photo.height,
                    self._settings.photo_size_mm.width,
                    self._settings.photo_size_mm.height,
                ),
            )
        except (ExportError, OSError, ValueError) as exc:
            QMessageBox.warning(self, "Unable to Export JPEG", str(exc))
            return

        self._preferences.setValue("lastOutputDirectory", str(written.parent))
        QMessageBox.information(self, "Output Complete", "JPEG exported successfully.")

    def open_crop_editor(self) -> None:
        if self._photo is None or self._settings.resize_mode is not ResizeMode.CROP:
            return
        dialog = CropEditorDialog(
            self._photo,
            self._settings.photo_size_mm,
            self._crop_state
            or default_crop_state(
                self._photo.width,
                self._photo.height,
                self._settings.photo_size_mm.width,
                self._settings.photo_size_mm.height,
            ),
            self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._crop_state = dialog.crop_state
            self.preview.set_crop_state(self._crop_state)

    def _update_crop_button(self) -> None:
        enabled = self._photo is not None and self._settings.resize_mode is ResizeMode.CROP
        self.crop_button.setEnabled(enabled)
        self.crop_button.setProperty("cropActive", enabled)
        self.crop_button.style().unpolish(self.crop_button)
        self.crop_button.style().polish(self.crop_button)
        self.crop_button.setToolTip(
            "Adjust the crop composition" if enabled else "Select Crop to Size after opening a photo"
        )

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
            QPushButton#cropButton { background: #e8ebef; color: #9299a4; border: 1px solid #d8dde4; border-radius: 6px; padding: 7px 10px; font-weight: 600; }
            QPushButton#cropButton[cropActive="true"]:enabled { background: #246bfd; color: white; border-color: #246bfd; }
            QPushButton#cropButton[cropActive="true"]:enabled:hover { background: #1758d5; }
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
