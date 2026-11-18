"""Resolution- and DPI-independent sizing.

The first part is app-agnostic (imports only PySide6, uses only Qt APIs, no
platform calls) so it can be extracted for other apps:

- proportional scale from the screen's *available* area, minus non-scaling
  window chrome (title bar + status bar)
- sizes from real font metrics, and sizes limited to the available screen
- a frameless, vertically scrolling fixed-width sidebar
- window size limits and safe geometry restore
- a small Ctrl+Shift+D diagnostics overlay with a Copy button

The last part is this app's design system and reference screen.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass
from math import ceil
from typing import Callable, Iterable

from PySide6 import __version__ as PYSIDE_VERSION
from PySide6.QtCore import QByteArray, QCoreApplication, QRect, QSize, Qt, QTimer, qVersion
from PySide6.QtGui import QFont, QFontInfo, QFontMetricsF, QGuiApplication, QKeySequence, QScreen, QShortcut
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStyle,
    QStyleOptionComboBox,
    QStyleOptionSpinBox,
    QVBoxLayout,
    QWidget,
)


# ---------------------------------------------------------------------------
# Generic: proportional scale
# ---------------------------------------------------------------------------

DEFAULT_TITLE_BAR = 30  # logical px when no QApplication/style is available


def title_bar_height() -> int:
    """Title bar allowance from the application style (Qt only, no platform calls)."""

    app = QApplication.instance()
    if app is not None:
        value = app.style().pixelMetric(QStyle.PixelMetric.PM_TitleBarHeight)
        if value > 0:
            return value
    return DEFAULT_TITLE_BAR


@dataclass(frozen=True)
class ScaleConfig:
    """Reference screen and limits for one design system."""

    reference_width: int = 1536
    reference_height: int = 816  # available height on the reference screen (taskbar excluded)
    min_scale: float = 0.72
    max_scale: float = 1.75
    title_bar: int | None = None  # None: from the application style
    status_bar: int = 0

    def chrome_height(self) -> int:
        """Window chrome that does not scale with the UI (title bar + status bar)."""

        title = self.title_bar if self.title_bar is not None else title_bar_height()
        return title + self.status_bar


@dataclass(frozen=True)
class ScaleResult:
    raw: float
    used: float

    @property
    def clamped(self) -> bool:
        return abs(self.raw - self.used) > 1e-9


def compute_scale(
    available_width: float, available_height: float, config: ScaleConfig = ScaleConfig()
) -> ScaleResult:
    """Scale for an available screen area; heights are compared without the chrome."""

    chrome = config.chrome_height()
    usable_height = available_height - chrome
    reference_usable = max(1.0, config.reference_height - chrome)
    if available_width < 1 or usable_height < 1:
        return ScaleResult(1.0, 1.0)
    raw = min(available_width / config.reference_width, usable_height / reference_usable)
    return ScaleResult(raw, min(config.max_scale, max(config.min_scale, raw)))


def scale_for_screen(screen: QScreen | None, config: ScaleConfig = ScaleConfig()) -> ScaleResult:
    screen = screen or QGuiApplication.primaryScreen()
    if screen is None:
        return ScaleResult(1.0, 1.0)
    available = screen.availableGeometry()  # already excludes the taskbar
    return compute_scale(available.width(), available.height(), config)


# ---------------------------------------------------------------------------
# Generic: sizes from font metrics and the available screen
# ---------------------------------------------------------------------------

_TRIAL_WIDTH = 1000


def font_of(target: QWidget | QFont) -> QFont:
    """The effective font, including a stylesheet font once the widget is polished."""

    if isinstance(target, QFont):
        return target
    target.ensurePolished()
    return target.font()


def text_width(target: QWidget | QFont, *texts: str) -> int:
    metrics = QFontMetricsF(font_of(target))
    return ceil(max((metrics.horizontalAdvance(text) for text in texts), default=0.0))


def text_height(target: QWidget | QFont, lines: int = 1) -> int:
    metrics = QFontMetricsF(font_of(target))
    return ceil(metrics.height() + metrics.lineSpacing() * max(0, lines - 1))


def control_height(target: QWidget | QFont, *, padding: int, border: int = 1, minimum: int = 0) -> int:
    """Height for a single-line control: text height plus vertical padding and borders."""

    return max(minimum, text_height(target) + 2 * (padding + border))


def combo_width_for(combo: QComboBox, texts: Iterable[str] | None = None, slack: int = 2) -> int:
    """Smallest combo width that shows every text unelided, using the style's own geometry."""

    combo.ensurePolished()
    if texts is None:
        texts = [combo.itemText(index) for index in range(combo.count())]
    option = QStyleOptionComboBox()
    combo.initStyleOption(option)
    option.rect = QRect(0, 0, _TRIAL_WIDTH, max(combo.height(), 24))
    field = combo.style().subControlRect(
        QStyle.ComplexControl.CC_ComboBox, option, QStyle.SubControl.SC_ComboBoxEditField, combo
    )
    return text_width(combo, *texts) + (_TRIAL_WIDTH - field.width()) + slack


def spin_width_for(spin: QAbstractSpinBox, texts: Iterable[str], slack: int = 4) -> int:
    """Smallest spin box width that shows every text (the editor adds its own margins)."""

    spin.ensurePolished()
    option = QStyleOptionSpinBox()
    spin.initStyleOption(option)
    option.rect = QRect(0, 0, _TRIAL_WIDTH, max(spin.height(), 24))
    field = spin.style().subControlRect(
        QStyle.ComplexControl.CC_SpinBox, option, QStyle.SubControl.SC_SpinBoxEditField, spin
    )
    return text_width(spin, *texts) + (_TRIAL_WIDTH - field.width()) + slack


def available_client_size(
    screen: QScreen | None = None, *, title_bar: int | None = None, margin: int = 0
) -> QSize:
    """Room for a window's client area on ``screen`` (taskbar and title bar excluded)."""

    screen = screen or QGuiApplication.primaryScreen()
    if screen is None:
        return QSize(16777215, 16777215)
    available = screen.availableGeometry()
    caption = title_bar_height() if title_bar is None else title_bar
    return QSize(
        max(1, available.width() - 2 * margin), max(1, available.height() - caption - 2 * margin)
    )


def fit_to_screen(
    size: QSize, screen: QScreen | None = None, *, title_bar: int | None = None, margin: int = 0
) -> QSize:
    """``size`` reduced, if necessary, so the window fits the available screen area."""

    return size.boundedTo(available_client_size(screen, title_bar=title_bar, margin=margin))


# ---------------------------------------------------------------------------
# Generic: scrollable sidebar
# ---------------------------------------------------------------------------


class ScrollableSidebar(QScrollArea):
    """Frameless scroll area around a fixed-width panel.

    The inner widget keeps exactly ``content_width``; the area widens by the
    scrollbar only while it is shown, so the content never reflows.
    """

    def __init__(self, widget: QWidget, content_width: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("scrollableSidebar")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setWidgetResizable(True)  # the panel fills the height when it fits
        self.setWidget(widget)
        self._content_width = content_width
        self._scrollbar_width = 10
        self.verticalScrollBar().rangeChanged.connect(self._update_width)
        self.set_content_width(content_width)

    @property
    def scrollbar_visible(self) -> bool:
        return self.verticalScrollBar().maximum() > 0

    def set_content_width(self, width: int) -> None:
        self._content_width = width
        self.widget().setFixedWidth(width)
        self._update_width()

    def set_scrollbar_width(self, width: int) -> None:
        self._scrollbar_width = max(4, width)
        radius = max(2, self._scrollbar_width // 2 - 1)
        bar = "QScrollArea#scrollableSidebar > QWidget > QScrollBar"
        self.setStyleSheet(
            f"""
            QScrollArea#scrollableSidebar {{ border: 0; background: transparent; }}
            {bar}:vertical {{ background: transparent; width: {self._scrollbar_width}px; margin: 0; }}
            {bar}::handle:vertical {{ background: #c4cad3; border-radius: {radius}px; min-height: 24px; margin: 1px; }}
            {bar}::handle:vertical:hover {{ background: #9aa4b2; }}
            {bar}::add-line:vertical, {bar}::sub-line:vertical {{ height: 0; }}
            {bar}::add-page:vertical, {bar}::sub-page:vertical {{ background: none; }}
            """
        )
        self._update_width()

    def _update_width(self, *_args) -> None:
        # The bar's real width, so the viewport is never narrower than the panel.
        bar = self.verticalScrollBar()
        extra = max(self._scrollbar_width, bar.sizeHint().width()) if self.scrollbar_visible else 0
        self.setFixedWidth(self._content_width + extra)


def scrollable_sidebar(widget: QWidget, width: int, *, scrollbar_width: int = 10) -> ScrollableSidebar:
    sidebar = ScrollableSidebar(widget, width)
    sidebar.set_scrollbar_width(scrollbar_width)
    return sidebar


# ---------------------------------------------------------------------------
# Generic: window limits and geometry restore
# ---------------------------------------------------------------------------


def apply_size_limits(
    window: QWidget, minimum: QSize, *, initial: QSize | None = None, screen: QScreen | None = None
) -> QSize:
    """Minimum covering the layout's needs but never larger than the screen; returns it."""

    room = available_client_size(screen or window.screen())
    layout_minimum = window.minimumSizeHint()
    wanted = minimum.expandedTo(layout_minimum) if layout_minimum.isValid() else minimum
    applied = wanted.boundedTo(room)
    window.setMinimumSize(applied)
    if initial is not None:
        window.resize(initial.expandedTo(applied).boundedTo(room))
    return applied


def _fits_some_screen(window: QWidget) -> bool:
    frame = window.frameGeometry() if window.isVisible() else window.geometry()
    for screen in QGuiApplication.screens():
        available = screen.availableGeometry()
        overlap = available.intersected(frame)
        if (
            frame.width() <= available.width()
            and frame.height() <= available.height()
            and overlap.width() >= frame.width() * 0.5
            and overlap.height() >= frame.height() * 0.5
        ):
            return True
    return False


def restore_geometry_safely(window: QWidget, saved: QByteArray | bytes | None) -> bool:
    """Restore saved geometry only if it still fits a connected screen."""

    if not saved:
        return False
    before = window.saveGeometry()
    if not window.restoreGeometry(QByteArray(saved)):
        return False
    if window.isMaximized() or _fits_some_screen(window):
        return True
    window.restoreGeometry(before)  # saved on another monitor or scale: ignore it
    return False


# ---------------------------------------------------------------------------
# Generic: diagnostics overlay (Ctrl+Shift+D)
# ---------------------------------------------------------------------------

Rows = Iterable[tuple[str, str]]


def collect_diagnostics(window: QWidget, extra: Callable[[], Rows] | None = None) -> list[tuple[str, str]]:
    app = QCoreApplication.instance()
    rows = [
        ("Application", f"{app.applicationName() or '?'} {app.applicationVersion() or ''}".strip()),
        ("Qt / PySide", f"{qVersion()} / {PYSIDE_VERSION}"),
        ("Platform", f"{QGuiApplication.platformName()} · {platform.platform()}"),
    ]
    screen = window.screen()
    if screen is not None:
        geometry, available, ratio = screen.geometry(), screen.availableGeometry(), screen.devicePixelRatio()
        rows += [
            ("Screen", screen.name() or "?"),
            ("Physical resolution", f"{round(geometry.width() * ratio)} × {round(geometry.height() * ratio)}"),
            ("Windows scale", f"{round(ratio * 100)}%"),
            ("Logical size", f"{geometry.width()} × {geometry.height()}"),
            ("Available area", f"{available.width()} × {available.height()} at ({available.x()}, {available.y()})"),
            ("Device pixel ratio", f"{ratio:g}"),
            ("Logical / physical DPI", f"{screen.logicalDotsPerInch():.1f} / {screen.physicalDotsPerInch():.1f}"),
        ]
    state = "maximized" if window.isMaximized() else "normal"
    system_font = QGuiApplication.font()
    rows += [
        ("Window size", f"{window.width()} × {window.height()} ({state})"),
        ("System font", f"{system_font.family()} {system_font.pointSizeF():g} pt / {QFontInfo(system_font).pixelSize()} px"),
    ]
    if extra is not None:
        rows += list(extra())
    return rows


def format_diagnostics(rows: Rows) -> str:
    rows = list(rows)
    width = max((len(name) for name, _value in rows), default=0)
    return "\n".join(f"{name.ljust(width)}  {value}" for name, value in rows)


class DiagnosticsOverlay(QFrame):
    """A small card over the window's top-left corner with Copy and Close buttons."""

    def __init__(self, window: QWidget, extra: Callable[[], Rows] | None = None) -> None:
        super().__init__(window)
        self._target = window
        self._extra = extra
        self.setObjectName("diagnosticsOverlay")
        self.setStyleSheet(
            """
            QFrame#diagnosticsOverlay { background: #ffffff; border: 1px solid #9aa4b2; border-radius: 6px; }
            QLabel { background: transparent; color: #20242b; }
            QLabel#diagnosticsTitle { font: bold 13px 'Segoe UI'; }
            QLabel#diagnosticsText { font: 12px 'Consolas', 'Courier New', monospace; }
            QPushButton { font: 12px 'Segoe UI'; min-height: 26px; padding: 0 12px; }
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        title = QLabel("Display diagnostics (Ctrl+Shift+D to close)")
        title.setObjectName("diagnosticsTitle")
        self.text = QLabel()
        self.text.setObjectName("diagnosticsText")
        self.text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.copy_button = QPushButton("Copy")
        self.copy_button.clicked.connect(self.copy)
        close = QPushButton("Close")
        close.clicked.connect(self.hide)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.copy_button)
        buttons.addWidget(close)
        layout.addWidget(title)
        layout.addWidget(self.text)
        layout.addLayout(buttons)
        self.hide()

    def report(self) -> str:
        return format_diagnostics(collect_diagnostics(self._target, self._extra))

    def toggle(self) -> None:
        if self.isVisible():
            self.hide()
            return
        self.text.setText(self.report())
        self.adjustSize()
        self.move(12, 12)
        self.raise_()
        self.show()

    def copy(self) -> None:
        QGuiApplication.clipboard().setText(self.report())
        self.copy_button.setText("Copied")
        QTimer.singleShot(1500, lambda: self.copy_button.setText("Copy"))


def install_diagnostics(
    window: QWidget, shortcut: str = "Ctrl+Shift+D", extra: Callable[[], Rows] | None = None
) -> DiagnosticsOverlay:
    """Add a toggleable diagnostics overlay to ``window`` and return it."""

    overlay = DiagnosticsOverlay(window, extra)
    action = QShortcut(QKeySequence(shortcut), window)
    action.setContext(Qt.ShortcutContext.WindowShortcut)
    action.activated.connect(overlay.toggle)
    overlay.shortcut = action
    return overlay


# ---------------------------------------------------------------------------
# This app's design system
# ---------------------------------------------------------------------------

# Baseline: 1920 × 1080 at 125% = 1536 × 864 logical; the Windows 11 taskbar
# leaves 1536 × 816 of available area.
REFERENCE_WIDTH = 1536
REFERENCE_HEIGHT = 816
MIN_UI_SCALE = 0.72
MAX_UI_SCALE = 1.75
STATUS_BAR_HEIGHT = 22  # this window's status bar at the baseline (non-scaling chrome)

SCALE_CONFIG = ScaleConfig(
    reference_width=REFERENCE_WIDTH,
    reference_height=REFERENCE_HEIGHT,
    min_scale=MIN_UI_SCALE,
    max_scale=MAX_UI_SCALE,
    status_bar=STATUS_BAR_HEIGHT,
)


@dataclass(frozen=True)
class UiMetrics:
    """A compact design system expressed in Qt device-independent pixels."""

    scale: float

    def px(self, value: float, minimum: int = 1) -> int:
        return max(minimum, round(value * self.scale))

    @property
    def outer_margin(self) -> int:
        return self.px(20)

    @property
    def panel_padding(self) -> int:
        return self.px(20)

    @property
    def section_spacing(self) -> int:
        return self.px(14)

    @property
    def compact_spacing(self) -> int:
        return self.px(8)

    @property
    def sidebar_width(self) -> int:
        return self.px(285)

    @property
    def control_height(self) -> int:
        return self.px(34, 24)

    @property
    def radius(self) -> int:
        return self.px(6, 4)


def scale_result_for_size(width: int, height: int) -> ScaleResult:
    """Raw and clamped scale for an *available* screen area (taskbar excluded)."""

    return compute_scale(width, height, SCALE_CONFIG)


def ui_scale_for_size(width: int, height: int) -> float:
    return scale_result_for_size(width, height).used


def metrics_for_size(width: int, height: int) -> UiMetrics:
    return UiMetrics(ui_scale_for_size(width, height))


def scale_result_for_screen(screen: QScreen | None = None) -> ScaleResult:
    return scale_for_screen(screen, SCALE_CONFIG)


def metrics_for_screen(screen: QScreen | None = None) -> UiMetrics:
    return UiMetrics(scale_result_for_screen(screen).used)
