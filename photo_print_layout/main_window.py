"""Main application window and control wiring."""

from __future__ import annotations

import os
from dataclasses import replace
from math import isclose
from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings, QSignalBlocker, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFontInfo, QKeySequence, QPalette, QScreen, QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from .crop import CropState, default_crop_state
from .crop_dialog import CropEditorDialog
from .exporter import ExportError, ensure_jpeg_extension, export_jpeg
from .image_loader import ImageLoadError, LoadedPhoto, SUPPORTED_FILE_FILTER, load_photo
from .layout import photo_fits_on_paper
from .models import (
    DEFAULT_PHOTO_SIZE_MM,
    PAPER_SIZES,
    PRESET_MATCH_TOLERANCE_MM,
    SIZE_PRESETS,
    STANDARD_A3,
    SUPER_A3,
    LayoutSettings,
    PaperSize,
    Position,
    ResizeMode,
    SizeMM,
    Unit,
    format_physical_value,
    from_millimetres,
    layout_orientation_for_dimensions,
    to_millimetres,
)
from .preview import PreviewWidget
from .toggle_switch import SwitchLabel, ToggleSwitch
from .ui_scale import (
    SCALE_CONFIG,
    UiMetrics,
    apply_size_limits,
    combo_width_for,
    control_height,
    install_diagnostics,
    metrics_for_screen,
    restore_geometry_safely,
    scale_result_for_screen,
    scrollable_sidebar,
    spin_width_for,
    text_height,
    title_bar_height,
)


PAPER_CHOICE_DEFAULT = "default"
PAPER_CHOICE_AUTO = "auto"
PAPER_CHOICE_USER = "user"
PAPER_AUTO_SWITCH_SUFFIX = " · switched to A3+"
RULER_VISIBLE_KEY = "preview/rulerVisible"
WINDOW_GEOMETRY_KEY = "windowGeometry"
SIZE_SAMPLE_TEXT = "888.88"  # widest value the size boxes must show unclipped


class PhysicalSizeSpinBox(QDoubleSpinBox):
    """Numeric input that omits unnecessary trailing zeroes."""

    def textFromValue(self, value: float) -> str:  # noqa: N802
        return f"{value:.{self.decimals()}f}".rstrip("0").rstrip(".")


class MainWindow(QMainWindow):
    def __init__(
        self,
        ui_metrics: UiMetrics | None = None,
        *,
        preferences: QSettings | None = None,
    ) -> None:
        super().__init__()
        self._ui_metrics_override = ui_metrics is not None
        self._ui_metrics = ui_metrics or metrics_for_screen()
        self._control_height = self._ui_metrics.control_height
        self._screen_signal_connected = False
        self._settings = LayoutSettings()
        self._photo: LoadedPhoto | None = None
        self._crop_state: CropState | None = None
        self._crop_aspect_ratio: float | None = None
        self._display_unit = Unit.INCHES
        # "default": app-chosen A3; "auto": upgraded to A3+ to fit the size (reverts);
        # "user": picked by the user (never changed automatically).
        self._paper_choice = PAPER_CHOICE_DEFAULT
        self._updating_size_controls = False
        self._crop_reset_timer = QTimer(self)
        self._crop_reset_timer.setSingleShot(True)
        self._crop_reset_timer.setInterval(250)
        self._crop_reset_timer.timeout.connect(self._commit_crop_aspect_change)
        # Injectable so tests can use an isolated settings file.
        self._preferences = preferences if preferences is not None else QSettings()

        self.setWindowTitle("Photo Print Layout Manager")
        self._build_ui()
        self.diagnostics = install_diagnostics(self, extra=self._diagnostic_rows)
        self._apply_ui_metrics(self._ui_metrics)

    def _build_ui(self) -> None:
        central = QWidget()
        root = QHBoxLayout(central)
        self._root_layout = root

        controls = QFrame()
        self._controls_panel = controls
        controls.setObjectName("controlsPanel")
        controls_layout = QVBoxLayout(controls)
        self._controls_layout = controls_layout

        title = QLabel("Photo Print Layout")
        title.setObjectName("title")
        subtitle = QLabel("Prepare one photo for A3 printing")
        subtitle.setObjectName("subtitle")
        controls_layout.addWidget(title)
        controls_layout.addWidget(subtitle)

        self._title_spacer = QSpacerItem(
            0,
            self._ui_metrics.compact_spacing,
            QSizePolicy.Policy.Minimum,
            QSizePolicy.Policy.Fixed,
        )
        controls_layout.addItem(self._title_spacer)
        controls_layout.addWidget(self._section_label("Photo"))
        self.open_button = QPushButton("Open Photo…")
        self.open_button.setObjectName("primaryButton")
        self.open_button.clicked.connect(self.open_photo)
        self.clear_button = QPushButton("Clear")
        self.clear_button.setEnabled(False)
        self.clear_button.clicked.connect(self.clear_photo)
        photo_buttons = QHBoxLayout()
        self._photo_buttons_layout = photo_buttons
        photo_buttons.addWidget(self.open_button, 1)
        photo_buttons.addWidget(self.clear_button)
        controls_layout.addLayout(photo_buttons)

        self.photo_info = QLabel("No photo selected")
        self.photo_info.setObjectName("photoInfo")
        self.photo_info.setWordWrap(True)
        self.photo_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        controls_layout.addWidget(self.photo_info)

        controls_layout.addWidget(self._section_label("Photo Size"))
        self.size_preset_combo = QComboBox()
        self.size_preset_combo.setObjectName("sizePresetCombo")
        self.size_preset_combo.setAccessibleName("Quick photo size")
        self.size_preset_combo.setPlaceholderText("Quick size…")
        for preset in SIZE_PRESETS:
            self.size_preset_combo.addItem(preset.label, preset)
        self.size_preset_combo.setCurrentIndex(-1)
        # activated fires only for user picks (including re-picking the shown preset),
        # never for the programmatic sync below.
        self.size_preset_combo.activated.connect(self._preset_selected)
        controls_layout.addWidget(self.size_preset_combo)
        size_grid = QGridLayout()
        self._size_grid = size_grid
        self.width_spin = PhysicalSizeSpinBox()
        self.width_spin.setAccessibleName("Photo width")
        self.width_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.height_spin = PhysicalSizeSpinBox()
        self.height_spin.setAccessibleName("Photo height")
        self.height_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.unit_combo = QComboBox()
        self.unit_combo.setObjectName("unitCombo")
        self.unit_combo.setAccessibleName("Photo size unit")
        for unit in Unit:
            self.unit_combo.addItem(unit.value, unit)
        self.width_label = QLabel("Width")
        self.width_label.setObjectName("dimensionLabel")
        self.height_label = QLabel("Height")
        self.height_label.setObjectName("dimensionLabel")
        unit_label = QLabel("Unit")
        unit_label.setObjectName("dimensionLabel")
        size_grid.addWidget(self.width_label, 0, 0)
        size_grid.addWidget(self.height_label, 0, 2)
        size_grid.addWidget(unit_label, 0, 3)
        size_grid.addWidget(self.width_spin, 1, 0)
        size_grid.addWidget(QLabel("×"), 1, 1)
        size_grid.addWidget(self.height_spin, 1, 2)
        size_grid.addWidget(self.unit_combo, 1, 3)
        controls_layout.addLayout(size_grid)
        # One status line: "Max: …" (info colour plus a suffix after an automatic switch
        # to A3+), replaced by the error row when the size does not fit.
        self.max_size_label = QLabel()
        self.max_size_label.setObjectName("maxSizeLabel")
        self.max_size_label.setProperty("autoSwitched", False)
        self.max_size_label.setWordWrap(True)
        controls_layout.addWidget(self.max_size_label)
        self.size_error = QLabel()
        self.size_error.setObjectName("sizeError")
        self.size_error.setWordWrap(True)  # wraps beside the button when space is short
        self.size_error.hide()
        self.switch_paper_button = QPushButton("Switch to A3+")
        self.switch_paper_button.setObjectName("switchPaperButton")
        self.switch_paper_button.hide()
        # A real combo change, so it is recorded as the user's own paper choice.
        self.switch_paper_button.clicked.connect(
            lambda: self.paper_combo.setCurrentIndex(self.paper_combo.findData(SUPER_A3))
        )
        size_status_row = QHBoxLayout()
        self._size_status_row = size_status_row
        size_status_row.setContentsMargins(0, 0, 0, 0)
        size_status_row.addWidget(self.size_error, 1)
        size_status_row.addWidget(
            self.switch_paper_button, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        controls_layout.addLayout(size_status_row)
        for spin in (self.width_spin, self.height_spin):
            spin.setProperty("sizeInvalid", False)
        self._configure_size_inputs(self._display_unit)
        self._set_size_controls_from_mm(self._settings.photo_size_mm)
        self._update_max_size_label()
        # Each box owns exactly one dimension; the other is never read back from a
        # rounded display value.
        self.width_spin.valueChanged.connect(lambda _value: self._photo_size_changed("width"))
        self.height_spin.valueChanged.connect(lambda _value: self._photo_size_changed("height"))
        self.unit_combo.currentIndexChanged.connect(self._unit_changed)

        form = QFormLayout()
        self._form_layout = form
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.paper_combo = QComboBox()
        for paper in PAPER_SIZES:
            self.paper_combo.addItem(paper.label, paper)
        self.paper_combo.currentIndexChanged.connect(self._paper_changed_by_user)
        form.addRow("Paper", self.paper_combo)

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
        self.output_button.setProperty("outputActive", False)
        self.output_button.setEnabled(False)
        self.output_button.clicked.connect(self.output_jpeg)
        controls_layout.addWidget(self.output_button)
        controls_layout.addStretch()

        phase_note = QLabel("Printing remains unavailable.")
        phase_note.setObjectName("phaseNote")
        phase_note.setWordWrap(True)
        controls_layout.addWidget(phase_note)

        preview_panel = QFrame()
        preview_panel.setObjectName("previewPanel")
        preview_layout = QVBoxLayout(preview_panel)
        self._preview_layout = preview_layout
        preview_heading = QLabel("Preview")
        preview_heading.setObjectName("previewHeading")
        self.preview_caption = QLabel()
        self.preview_caption.setObjectName("previewCaption")
        self.preview_caption.setProperty("sizeInvalid", False)
        self.preview_caption.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.preview_caption.setAccessibleName("Photo and paper size")
        self.ruler_button = ToggleSwitch()
        self.ruler_button.setObjectName("rulerToggle")
        self.ruler_button.setToolTip("Show/hide rulers")
        self.ruler_button.setAccessibleName("Ruler")
        self.ruler_label = SwitchLabel("Ruler", self.ruler_button)
        self.ruler_label.setObjectName("rulerLabel")
        ruler_row = QHBoxLayout()
        self._ruler_row = ruler_row
        ruler_row.setContentsMargins(0, 0, 0, 0)
        ruler_row.addWidget(self.ruler_label)
        ruler_row.addWidget(self.ruler_button)
        preview_header = QHBoxLayout()
        self._preview_header = preview_header
        preview_header.setContentsMargins(0, 0, 0, 0)
        preview_header.addWidget(preview_heading)
        preview_header.addStretch(1)
        preview_header.addLayout(ruler_row)
        preview_header.addWidget(self.preview_caption)
        preview_layout.addLayout(preview_header)
        self.preview = PreviewWidget()
        self.preview.set_display_unit(self._display_unit)
        preview_layout.addWidget(self.preview, 1)
        ruler_visible = self._preferences.value(RULER_VISIBLE_KEY, True, type=bool)
        self.ruler_button.setChecked(ruler_visible)
        self.preview.set_ruler_visible(ruler_visible)
        self.ruler_button.toggled.connect(self._ruler_toggled)

        # The panel keeps its fixed width; it scrolls only when a screen is too short.
        self._sidebar = scrollable_sidebar(controls, self._ui_metrics.sidebar_width)
        root.addWidget(self._sidebar)
        root.addWidget(preview_panel, 1)
        self.setCentralWidget(central)
        # Create the status bar now (not on the first message) so the window minimum
        # and the scale's chrome allowance always include it.
        self.statusBar()
        self._sync_preset_combo()
        self._refresh_size_labels()

        open_action = QAction("Open Photo", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_photo)
        self.addAction(open_action)

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    @property
    def ui_metrics(self) -> UiMetrics:
        return self._ui_metrics

    def _controls_changed(self) -> None:
        self._settings = replace(
            self._settings,
            paper=self.paper_combo.currentData(),
            position=self.position_combo.currentData(),
            resize_mode=self.resize_combo.currentData(),
        )
        self.preview.set_settings(self._settings)
        self._update_size_validity()
        self.statusBar().showMessage(
            f"{self._settings.paper.label} · {self._size_summary()} · "
            f"{self._settings.position.value} · {self._settings.resize_mode.value}"
        )

    def _paper_changed_by_user(self) -> None:
        # Code-driven changes are signal-blocked, so any change arriving here is the user's.
        self._paper_choice = PAPER_CHOICE_USER
        self._controls_changed()

    def _set_paper_programmatically(self, paper: PaperSize) -> None:
        with QSignalBlocker(self.paper_combo):
            self.paper_combo.setCurrentIndex(self.paper_combo.findData(paper))
        self._settings = replace(self._settings, paper=paper)

    def _reconcile_paper(self) -> None:
        """Pick the smallest fitting paper unless the user chose the paper."""

        if self._paper_choice == PAPER_CHOICE_USER:
            return
        if photo_fits_on_paper(replace(self._settings, paper=STANDARD_A3)):
            if self._paper_choice == PAPER_CHOICE_AUTO:
                self._set_paper_programmatically(STANDARD_A3)
                self._paper_choice = PAPER_CHOICE_DEFAULT
        elif photo_fits_on_paper(replace(self._settings, paper=SUPER_A3)):
            if self._settings.paper != SUPER_A3:
                self._set_paper_programmatically(SUPER_A3)
            self._paper_choice = PAPER_CHOICE_AUTO
        # Too large even for A3+: leave the paper alone; validation shows the error.

    def _size_problem_message(self) -> str | None:
        """Return the oversize error for the current size, or None when it fits."""

        if photo_fits_on_paper(self._settings):
            return None
        if photo_fits_on_paper(replace(self._settings, paper=SUPER_A3)):
            limit = self._settings.paper  # a smaller paper the user chose
        else:
            limit = SUPER_A3
        maximum = limit.size_mm.for_orientation(self._settings.layout_orientation)
        return f"Too large for {limit.short_name} (max {self._format_size(maximum)})"

    def _configure_size_inputs(self, unit: Unit) -> None:
        decimals = 1 if unit is Unit.MILLIMETRES else 2
        step = {Unit.INCHES: 0.25, Unit.CENTIMETRES: 0.1, Unit.MILLIMETRES: 1.0}[unit]
        minimum = max(10 ** -decimals, from_millimetres(0.1, unit))
        maximum = from_millimetres(1000.0, unit)
        for spin in (self.width_spin, self.height_spin):
            spin.setDecimals(decimals)
            spin.setRange(minimum, maximum)
            spin.setSingleStep(step)

    def _ruler_toggled(self, checked: bool) -> None:
        """Show or hide the preview rulers; no layout, crop, or paper state changes."""

        self.preview.set_ruler_visible(checked)
        self._preferences.setValue(RULER_VISIBLE_KEY, checked)

    def _set_size_controls_from_mm(self, size: SizeMM) -> None:
        self._updating_size_controls = True
        try:
            self.width_spin.setValue(from_millimetres(size.width, self._display_unit))
            self.height_spin.setValue(from_millimetres(size.height, self._display_unit))
        finally:
            self._updating_size_controls = False

    def _unit_changed(self) -> None:
        unit = self.unit_combo.currentData()
        if unit is None or unit is self._display_unit:
            return
        self._updating_size_controls = True
        try:
            self._display_unit = unit
            self._configure_size_inputs(unit)
            self.width_spin.setValue(from_millimetres(self._settings.photo_size_mm.width, unit))
            self.height_spin.setValue(from_millimetres(self._settings.photo_size_mm.height, unit))
        finally:
            self._updating_size_controls = False
        self.preview.set_display_unit(unit)
        self.statusBar().showMessage(f"Photo size shown in {unit.value}", 2500)
        self._refresh_size_labels()

    def _photo_size_changed(self, dimension: str) -> None:
        """Apply one edited size box without re-reading the other (rounded) box."""

        if self._updating_size_controls:
            return
        current = self._settings.photo_size_mm
        if dimension == "width":
            size = SizeMM(to_millimetres(self.width_spin.value(), self._display_unit), current.height)
        else:
            size = SizeMM(current.width, to_millimetres(self.height_spin.value(), self._display_unit))
        self._apply_photo_size(size, immediate_crop=False)

    def _apply_photo_size(self, size: SizeMM, *, immediate_crop: bool) -> None:
        """Install an exact millimetre photo size and update dependent state.

        ``immediate_crop`` commits an aspect-ratio crop reset now (discrete actions
        such as presets) instead of after the typing debounce.
        """

        self._settings = replace(self._settings, photo_size_mm=size)
        self._reconcile_paper()
        self._sync_preset_combo()
        self.preview.set_settings(self._settings)

        if self._photo is not None:
            ratio = size.width / size.height
            if self._crop_aspect_ratio is not None and isclose(
                ratio, self._crop_aspect_ratio, rel_tol=1e-9, abs_tol=1e-9
            ):
                if self._crop_state is not None:
                    self.preview.set_crop_state(self._crop_state)
                self._crop_reset_timer.stop()
            elif immediate_crop:
                self._crop_reset_timer.stop()
                self._commit_crop_aspect_change()
            else:
                self.preview.set_crop_state(self._default_crop_for_current_size())
                self._crop_reset_timer.start()
        self._update_size_validity()

    def _preset_selected(self, index: int) -> None:
        """Apply a preset's exact size, oriented like the photo; the unit is unchanged."""

        preset = self.size_preset_combo.itemData(index) if index >= 0 else None
        if preset is None:
            return
        if self._photo is not None:
            orientation = layout_orientation_for_dimensions(self._photo.width, self._photo.height)
        else:
            orientation = self._settings.layout_orientation
        size = preset.size_mm.for_orientation(orientation)
        self._apply_photo_size(size, immediate_crop=True)
        self._set_size_controls_from_mm(size)

    def _sync_preset_combo(self) -> None:
        """Show the preset matching the current size, or the placeholder if none does."""

        current = sorted((self._settings.photo_size_mm.width, self._settings.photo_size_mm.height))
        match = -1
        for index, preset in enumerate(SIZE_PRESETS):
            candidate = sorted((preset.size_mm.width, preset.size_mm.height))
            if all(
                abs(actual - expected) <= PRESET_MATCH_TOLERANCE_MM
                for actual, expected in zip(current, candidate)
            ):
                match = index
                break
        with QSignalBlocker(self.size_preset_combo):
            self.size_preset_combo.setCurrentIndex(match)

    def _commit_crop_aspect_change(self) -> None:
        if self._photo is None:
            return
        ratio = self._settings.photo_size_mm.width / self._settings.photo_size_mm.height
        if self._crop_aspect_ratio is None or not isclose(
            ratio, self._crop_aspect_ratio, rel_tol=1e-9, abs_tol=1e-9
        ):
            self._crop_state = self._default_crop_for_current_size()
            self._crop_aspect_ratio = ratio
            self.preview.set_crop_state(self._crop_state)

    def _default_crop_for_current_size(self) -> CropState:
        assert self._photo is not None
        target = self._settings.photo_size_mm
        return default_crop_state(
            self._photo.width,
            self._photo.height,
            target.width,
            target.height,
        )

    def _effective_crop_state(self) -> CropState:
        if self._photo is None:
            return CropState()
        ratio = self._settings.photo_size_mm.width / self._settings.photo_size_mm.height
        if (
            self._crop_state is not None
            and self._crop_aspect_ratio is not None
            and isclose(ratio, self._crop_aspect_ratio, rel_tol=1e-9, abs_tol=1e-9)
        ):
            return self._crop_state
        return self._default_crop_for_current_size()

    def _update_size_validity(self) -> None:
        """Show the fit state: fits, auto-switched to A3+, too large for A3, too large for A3+."""

        self._refresh_size_labels()
        valid = photo_fits_on_paper(self._settings)
        fits_super_a3 = photo_fits_on_paper(replace(self._settings, paper=SUPER_A3))
        self.switch_paper_button.setVisible(not valid and fits_super_a3)
        for spin in (self.width_spin, self.height_spin):
            self._set_style_flag(spin, "sizeInvalid", not valid)
        self.clear_button.setEnabled(self._photo is not None)
        output_enabled = self._photo is not None and valid
        self.output_button.setEnabled(output_enabled)
        self.output_button.setProperty("outputActive", output_enabled)
        self.output_button.style().unpolish(self.output_button)
        self.output_button.style().polish(self.output_button)
        self._update_crop_button()

    def _format_size(self, size: SizeMM) -> str:
        """Format an exact millimetre size in the current display unit."""

        unit = self._display_unit
        width = format_physical_value(from_millimetres(size.width, unit), unit)
        height = format_physical_value(from_millimetres(size.height, unit), unit)
        return f"{width} × {height} {unit.value}"

    def _update_max_size_label(self) -> None:
        auto_switched = self._paper_choice == PAPER_CHOICE_AUTO and photo_fits_on_paper(
            self._settings
        )
        text = f"Max: {self._format_size(self._settings.paper_size_mm)}"
        self.max_size_label.setText(text + (PAPER_AUTO_SWITCH_SUFFIX if auto_switched else ""))
        self._set_style_flag(self.max_size_label, "autoSwitched", auto_switched)

    def _refresh_size_labels(self) -> None:
        """Refresh every size readout that depends on the display unit."""

        self._update_max_size_label()
        message = self._size_problem_message()
        fits = message is None
        self.size_error.setText(message or "")
        self.size_error.setVisible(not fits)
        # The error states the same maximum, so the Max line gives way to the error row.
        self.max_size_label.setVisible(fits)
        self.preview.set_validation_error(message)
        self.preview_caption.setText(
            f"Photo {self._format_size(self._settings.photo_size_mm)} · "
            f"{self._settings.paper.short_name} paper"
        )
        self._set_style_flag(self.preview_caption, "sizeInvalid", not fits)

    @staticmethod
    def _set_style_flag(widget: QWidget, name: str, value: bool) -> None:
        """Set a stylesheet-driven property and re-polish only when it changes."""

        if widget.property(name) == value:
            return
        widget.setProperty(name, value)
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _size_summary(self) -> str:
        return (
            f"{self.width_spin.text()} × {self.height_spin.text()} "
            f"{self._display_unit.value}"
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
        self._crop_reset_timer.stop()
        self._reset_resize_mode()
        orientation = layout_orientation_for_dimensions(photo.width, photo.height)
        default_size = DEFAULT_PHOTO_SIZE_MM.for_orientation(orientation)
        self._settings = replace(self._settings, photo_size_mm=default_size)
        self._reconcile_paper()
        self._sync_preset_combo()
        self._set_size_controls_from_mm(default_size)
        target = self._settings.photo_size_mm
        self._crop_state = default_crop_state(
            photo.width, photo.height, target.width, target.height
        )
        self._crop_aspect_ratio = target.width / target.height
        self.photo_info.setText(photo.summary)
        self.photo_info.setToolTip(str(photo.path))
        self.preview.set_photo(photo)
        self.preview.set_settings(self._settings)
        self.preview.set_crop_state(self._crop_state)
        self._update_size_validity()

    def _reset_resize_mode(self) -> None:
        """Return Resize Mode to Fit Inside without triggering control signals."""

        with QSignalBlocker(self.resize_combo):
            self.resize_combo.setCurrentIndex(self.resize_combo.findData(ResizeMode.FIT))
        self._settings = replace(self._settings, resize_mode=ResizeMode.FIT)

    def clear_photo(self) -> None:
        """Clear image-specific state and Resize Mode, preserving other selections."""

        self._photo = None
        self._crop_state = None
        self._crop_aspect_ratio = None
        self._crop_reset_timer.stop()
        self._reset_resize_mode()
        self._sync_preset_combo()
        self.photo_info.setText("No photo selected")
        self.photo_info.setToolTip("")
        self.preview.set_photo(None)
        self.preview.set_settings(self._settings)
        self.preview.set_crop_state(CropState())
        self._update_size_validity()
        self.statusBar().showMessage("Image cleared", 3000)

    def output_jpeg(self) -> None:
        if self._photo is None:
            return
        if not photo_fits_on_paper(self._settings):
            QMessageBox.warning(
                self, "Unable to Export JPEG", "Photo size is larger than the selected paper."
            )
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
                self._effective_crop_state(),
            )
        except (ExportError, OSError, ValueError) as exc:
            QMessageBox.warning(self, "Unable to Export JPEG", str(exc))
            return

        self._preferences.setValue("lastOutputDirectory", str(written.parent))
        QMessageBox.information(self, "Output Complete", "JPEG exported successfully.")

    def open_crop_editor(self) -> None:
        if (
            self._photo is None
            or self._settings.resize_mode is not ResizeMode.CROP
            or not photo_fits_on_paper(self._settings)
        ):
            return
        dialog = CropEditorDialog(
            self._photo,
            self._settings.photo_size_mm,
            self._effective_crop_state(),
            self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._crop_state = dialog.crop_state
            self._crop_aspect_ratio = (
                self._settings.photo_size_mm.width / self._settings.photo_size_mm.height
            )
            self.preview.set_crop_state(self._crop_state)

    def _update_crop_button(self) -> None:
        enabled = (
            self._photo is not None
            and self._settings.resize_mode is ResizeMode.CROP
            and photo_fits_on_paper(self._settings)
        )
        self.crop_button.setEnabled(enabled)
        self.crop_button.setProperty("cropActive", enabled)
        self.crop_button.style().unpolish(self.crop_button)
        self.crop_button.style().polish(self.crop_button)
        self.crop_button.setToolTip(
            "Adjust the crop composition" if enabled else "Select Crop to Size after opening a photo"
        )

    def _apply_ui_metrics(self, metrics: UiMetrics, *, resize_window: bool = True) -> None:
        """Apply one proportional metric set without changing layout structure."""

        self._ui_metrics = metrics
        px = metrics.px
        # Style first: every size measured from text below uses the styled fonts.
        self._apply_style()
        self._root_layout.setContentsMargins(
            metrics.outer_margin,
            metrics.outer_margin,
            metrics.outer_margin,
            metrics.outer_margin,
        )
        self._root_layout.setSpacing(metrics.outer_margin)
        self._sidebar.set_scrollbar_width(px(10, 8))
        self._sidebar.set_content_width(metrics.sidebar_width)
        self._controls_layout.setContentsMargins(
            metrics.panel_padding,
            metrics.panel_padding,
            metrics.panel_padding,
            metrics.panel_padding,
        )
        self._controls_layout.setSpacing(metrics.section_spacing)
        self._title_spacer.changeSize(
            0,
            metrics.compact_spacing,
            QSizePolicy.Policy.Minimum,
            QSizePolicy.Policy.Fixed,
        )
        self._photo_buttons_layout.setSpacing(metrics.compact_spacing)
        self._size_grid.setHorizontalSpacing(px(6))
        self._size_grid.setVerticalSpacing(px(3))
        self._form_layout.setContentsMargins(0, px(5), 0, 0)
        self._form_layout.setVerticalSpacing(px(8))
        self._size_status_row.setSpacing(metrics.compact_spacing)
        self._preview_layout.setContentsMargins(0, 0, 0, 0)
        self._preview_layout.setSpacing(metrics.compact_spacing)
        self.preview.setMinimumSize(px(440), px(520))
        self.preview.set_ui_scale(metrics.scale)
        self._preview_header.setSpacing(metrics.compact_spacing)
        # A compact switch, deliberately smaller than control_height, in the heading row.
        self._ruler_row.setSpacing(px(4))
        self.ruler_button.set_track_size(px(34, 26), px(18, 14), px(3, 2))

        # Sizes from real text, never smaller than the scaled design sizes.
        self._control_height = control_height(
            self.paper_combo, padding=px(6, 4), minimum=metrics.control_height
        )
        for widget in self._app_controls():
            widget.setFixedHeight(self._control_height)
        for spin in (self.width_spin, self.height_spin):
            spin.setFixedWidth(max(px(70), spin_width_for(spin, [SIZE_SAMPLE_TEXT])))
        self.unit_combo.setFixedWidth(
            max(px(58), combo_width_for(self.unit_combo, [unit.value for unit in Unit]))
        )
        self.photo_info.setMinimumHeight(text_height(self.photo_info) + 2 * px(9) + 2)

        for combo in self.findChildren(QComboBox):
            combo.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            combo.setMinimumContentsLength(4)
            if combo is not self.unit_combo:
                texts = [combo.itemText(i) for i in range(combo.count())]
                combo.setMinimumWidth(combo_width_for(combo, texts + [combo.placeholderText()]))
                combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self._style_combo_popup(combo)

        # Window limits never exceed the screen; the sidebar scrolls instead of squeezing.
        apply_size_limits(
            self,
            QSize(px(785), px(600)),
            initial=QSize(px(900), px(700)) if resize_window else None,
        )

    def _style_combo_popup(self, combo: QComboBox) -> None:
        """Force a light popup palette even when Windows uses a dark menu theme."""

        view = combo.view()
        palette = view.palette()
        palette.setColor(QPalette.ColorRole.Base, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Window, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.black)
        palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.black)
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#e7efff"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#173b7a"))
        view.setPalette(palette)
        view.setStyleSheet(
            f"""
            QAbstractItemView {{
                background: #ffffff;
                color: #20242b;
                border: 1px solid #cbd1d9;
                outline: 0;
                padding: {self._ui_metrics.px(4)}px;
                selection-background-color: #e7efff;
                selection-color: #173b7a;
            }}
            QAbstractItemView::item {{
                min-height: {self._ui_metrics.px(28, 22)}px;
                padding: 0 {self._ui_metrics.px(7)}px;
                border-radius: {self._ui_metrics.px(4)}px;
            }}
            QAbstractItemView::item:hover {{ background: #f1f5fb; }}
            QAbstractItemView::item:selected {{ background: #e7efff; color: #173b7a; }}
            """
        )

    def _apply_style(self) -> None:
        metrics = self._ui_metrics
        px = metrics.px
        arrow_url = (Path(__file__).with_name("assets") / "chevron-down.svg").as_posix()
        self.setStyleSheet(
            f"""
            QMainWindow, QWidget {{ background: #f7f8fa; color: #20242b; font-family: 'Segoe UI'; font-size: {px(12, 9)}px; }}
            QFrame#controlsPanel {{ background: #ffffff; border: 1px solid #dfe3e8; border-radius: {px(10)}px; }}
            QLabel {{ background: transparent; }}
            QLabel#title {{ font-size: {px(21, 15)}px; font-weight: 700; }}
            QLabel#subtitle {{ color: #687180; font-size: {px(12, 9)}px; }}
            QLabel#sectionLabel, QLabel#previewHeading {{ font-size: {px(13, 10)}px; font-weight: 700; }}
            QLabel#previewHeading {{ font-size: {px(16, 12)}px; }}
            QLabel#previewCaption {{ color: #596273; font-size: {px(12, 9)}px; font-weight: 600; }}
            QLabel#previewCaption[sizeInvalid="true"] {{ color: #b42318; }}
            QLabel#rulerLabel {{ color: #687180; font-size: {px(12, 9)}px; font-weight: 600; }}
            QLabel#photoInfo {{ background: #f4f6f8; border-radius: {metrics.radius}px; padding: {px(9)}px; color: #596273; }}
            QLabel#fixedValue {{ padding: {px(5)}px {px(2)}px; color: #3e4652; }}
            QLabel#phaseNote {{ color: #7b8492; font-size: {px(11, 9)}px; }}
            QLabel#sizeError {{ color: #b42318; font-size: {px(11, 9)}px; }}
            QLabel#dimensionLabel {{ color: #687180; font-size: {px(10, 9)}px; }}
            QLabel#maxSizeLabel {{ color: #687180; font-size: {px(11, 9)}px; }}
            QPushButton {{ background: #ffffff; color: #3e4652; border: 1px solid #cbd1d9; border-radius: {metrics.radius}px; padding: 0 {px(10)}px; font-weight: 600; }}
            QPushButton:hover {{ background: #f4f6f8; border-color: #9aa4b2; }}
            QPushButton:focus {{ border-color: #6f9cff; }}
            QPushButton:disabled {{ background: #eef0f3; color: #9aa1ab; border-color: #dde1e6; }}
            QPushButton#primaryButton {{ background: #246bfd; color: white; border: 1px solid #246bfd; border-radius: {metrics.radius}px; padding: 0 {px(12)}px; font-weight: 700; }}
            QPushButton#primaryButton:hover {{ background: #1758d5; }}
            QPushButton#primaryButton:pressed {{ background: #1248af; }}
            QPushButton#cropButton {{ background: #eef0f3; color: #9aa1ab; border: 1px solid #dde1e6; border-radius: {metrics.radius}px; padding: 0 {px(10)}px; font-weight: 600; }}
            QPushButton#cropButton[cropActive="true"]:enabled {{ background: #246bfd; color: white; border-color: #246bfd; }}
            QPushButton#cropButton[cropActive="true"]:enabled:hover {{ background: #1758d5; }}
            QPushButton#outputButton {{ background: #eef0f3; color: #9aa1ab; border: 1px solid #dde1e6; border-radius: {metrics.radius}px; padding: 0 {px(12)}px; font-weight: 700; }}
            QPushButton#outputButton[outputActive="true"]:enabled {{ background: #246bfd; color: white; border-color: #246bfd; }}
            QPushButton#outputButton[outputActive="true"]:enabled:hover {{ background: #1758d5; }}
            QPushButton#outputButton[outputActive="true"]:enabled:pressed {{ background: #1248af; }}
            QComboBox, QDoubleSpinBox {{ background: white; color: #20242b; border: 1px solid #cbd1d9; border-radius: {px(5)}px; padding: 0 {px(8)}px; selection-background-color: #dce8ff; selection-color: #173b7a; }}
            QComboBox {{ padding-right: {px(28)}px; }}
            QComboBox:hover {{ border-color: #8e98a7; }}
            QComboBox:focus {{ border-color: #6f9cff; }}
            QComboBox:disabled, QDoubleSpinBox:disabled {{ background: #eef0f3; color: #9aa1ab; border-color: #dde1e6; }}
            QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: top right; width: {px(26)}px; border: 0; border-left: 1px solid #e1e5ea; }}
            QComboBox::down-arrow {{ image: url("{arrow_url}"); width: {px(10)}px; height: {px(6)}px; }}
            QComboBox#unitCombo {{ min-width: 0; padding-left: {px(6)}px; padding-right: {px(20)}px; }}
            QDoubleSpinBox:focus {{ border-color: #246bfd; }}
            QDoubleSpinBox[sizeInvalid="true"] {{ border-color: #b42318; }}
            QDoubleSpinBox[sizeInvalid="true"]:focus {{ border-color: #b42318; }}
            QLabel#maxSizeLabel[autoSwitched="true"] {{ color: #1d4f9e; }}
            QAbstractItemView {{ background: #ffffff; color: #20242b; border: 1px solid #cbd1d9; selection-background-color: #e7efff; selection-color: #173b7a; outline: 0; }}
            QStatusBar {{ background: #ffffff; color: #687180; font-size: {px(11, 9)}px; }}
            """
        )

    def _app_controls(self) -> list[QWidget]:
        """Buttons, combos, and spin boxes of the app (the diagnostics overlay sizes itself)."""

        controls = (
            self.findChildren(QPushButton)
            + self.findChildren(QComboBox)
            + self.findChildren(QDoubleSpinBox)
        )
        return [widget for widget in controls if not self.diagnostics.isAncestorOf(widget)]

    @property
    def control_height(self) -> int:
        """Height of every push button, combo, and spin box (design size or text, larger)."""

        return self._control_height

    def _screen_changed(self, screen: QScreen | None) -> None:
        """Re-apply metrics for the window's screen (on show and when moved to another monitor)."""

        if not self._ui_metrics_override:
            self._apply_ui_metrics(metrics_for_screen(screen), resize_window=False)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 - Qt API name
        super().showEvent(event)
        handle = self.windowHandle()
        if handle and not self._screen_signal_connected:
            handle.screenChanged.connect(self._screen_changed)
            self._screen_signal_connected = True
        if handle and not self._ui_metrics_override:
            self._screen_changed(handle.screen())

    def saved_geometry(self) -> QByteArray | None:
        geometry = self._preferences.value(WINDOW_GEOMETRY_KEY)
        return geometry if geometry else None

    def _restore_window_geometry(self) -> bool:
        """Restore the saved geometry only if it still fits a connected screen."""

        return restore_geometry_safely(self, self.saved_geometry())

    def _diagnostic_rows(self) -> list[tuple[str, str]]:
        """App-specific lines for the Ctrl+Shift+D overlay."""

        result = scale_result_for_screen(self.screen())
        metrics = self._ui_metrics
        panel = self._controls_panel
        rendered = QFontInfo(self.paper_combo.font())
        sidebar = (
            f"{panel.minimumSizeHint().height()} / {self._sidebar.viewport().height()} px"
            + (" (scrolling)" if self._sidebar.scrollbar_visible else "")
        )
        return [
            (
                "UI scale raw / used",
                f"{result.raw:.3f} / {result.used:.3f}" + (" (clamped)" if result.clamped else ""),
            ),
            (
                "UI scale in use",
                f"{metrics.scale:.3f}" + (" (fixed by caller)" if self._ui_metrics_override else ""),
            ),
            (
                "Chrome allowance",
                f"title {title_bar_height()} + status {SCALE_CONFIG.status_bar} px (Qt style metric)",
            ),
            ("Stylesheet font", f"Segoe UI {metrics.px(12, 9)} px (title {metrics.px(21, 15)} px)"),
            ("Rendered font", f"{rendered.family()} {rendered.pixelSize()} px"),
            ("Control height", f"{self._control_height} px (design {metrics.control_height} px)"),
            ("Sidebar width", f"{panel.width()} px"),
            ("Sidebar height need / have", sidebar),
        ]

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self._preferences.setValue(WINDOW_GEOMETRY_KEY, self.saveGeometry())
        super().closeEvent(event)
