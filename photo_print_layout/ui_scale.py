"""Shared logical-pixel sizing for a consistent, non-reflowing desktop UI."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QGuiApplication, QScreen


REFERENCE_WIDTH = 1536
# 1920 × 1080 at 125% is 1536 × 864 logical pixels; the Windows taskbar
# leaves roughly 816 logical pixels of available application height.
REFERENCE_HEIGHT = 816
MIN_UI_SCALE = 0.72
MAX_UI_SCALE = 1.25


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


def ui_scale_for_size(width: int, height: int) -> float:
    """Scale from available *logical* geometry; Qt handles device DPI itself."""

    if width < 1 or height < 1:
        return 1.0
    proportional = min(width / REFERENCE_WIDTH, height / REFERENCE_HEIGHT)
    return min(MAX_UI_SCALE, max(MIN_UI_SCALE, proportional))


def metrics_for_size(width: int, height: int) -> UiMetrics:
    return UiMetrics(ui_scale_for_size(width, height))


def metrics_for_screen(screen: QScreen | None = None) -> UiMetrics:
    active_screen = screen or QGuiApplication.primaryScreen()
    if active_screen is None:
        return UiMetrics(1.0)
    available = active_screen.availableGeometry().size()
    return metrics_for_size(available.width(), available.height())
