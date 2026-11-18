"""Final-canvas preview backed by the authoritative render engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from PySide6.QtCore import QLineF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from .crop import CropState
from .image_loader import LoadedPhoto
from .layout import PhysicalLayout, calculate_layout
from .models import LayoutSettings, Unit
from .render_engine import RenderPlan, pillow_to_qimage, render_preview_image
from .rulers import (
    Tick,
    format_length,
    label_stride_for,
    layout_axis_labels,
    major_step_mm,
    photo_bands,
    ruler_ticks,
)


# Keep renders for two page sizes so toggling the rulers (which resizes the page)
# back and forth reuses them instead of resampling the photo again.
RENDER_CACHE_SIZE = 2
PAGE_MARGIN = 28.0

# Ruler metrics in unscaled logical pixels.
RULER_GAP = 6.0  # paper edge to ruler baseline; clears the page's 5 px drop shadow
RULER_MAJOR_TICK = 7.0
RULER_MINOR_TICK = 4.0
RULER_LABEL_PAD = 3.0
RULER_LABEL_GAP = 4.0  # minimum free space between neighbouring labels
# Labelled ticks need this many label-sizes of spacing, which keeps the rulers airy.
RULER_LABEL_SPACING = 2.0
RULER_FONT_PX = 10
RULER_MIN_FONT_PX = 8
# The widest label any ruler can show; reserving for it keeps the page from
# jumping when the unit changes.
RULER_WIDEST_LABELS = ("888.8 mm", "88.88 cm", "88.88 in")

RULER_LINE_COLOR = QColor("#b3bac5")
RULER_TEXT_COLOR = QColor("#8a93a1")
RULER_PAPER_TEXT_COLOR = QColor("#6b7482")
RULER_BAND_COLOR = QColor(36, 107, 253, 48)
RULER_BAND_TEXT_COLOR = QColor("#3b6fd8")
_LABEL_COLORS = {
    "tick": RULER_TEXT_COLOR,
    "paper": RULER_PAPER_TEXT_COLOR,
    "band": RULER_BAND_TEXT_COLOR,
}


@dataclass
class RulerDrawing:
    """Widget-space ruler primitives; computed separately so painting only draws."""

    lines: list[QLineF] = field(default_factory=list)
    bands: list[QRectF] = field(default_factory=list)
    labels: list[tuple[QRectF, str, str]] = field(default_factory=list)  # rect, text, kind

    def bounding_rect(self) -> QRectF:
        rect = QRectF()
        for line in self.lines:
            rect = rect.united(QRectF(line.p1(), line.p2()).normalized().adjusted(0, 0, 1, 1))
        for band in self.bands:
            rect = rect.united(band)
        for label_rect, _text, _kind in self.labels:
            rect = rect.united(label_rect)
        return rect


class PreviewWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = LayoutSettings()
        self._photo: LoadedPhoto | None = None
        self._crop_state = CropState()
        self._validation_error: str | None = None
        self._ui_scale = 1.0
        self._ruler_visible = True
        self._display_unit = Unit.INCHES
        self._render_cache: dict[tuple[object, ...], tuple[QImage, RenderPlan]] = {}
        self.setMinimumSize(440, 520)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName("Paper layout preview")

    def set_ui_scale(self, scale: float) -> None:
        self._ui_scale = max(0.5, scale)
        self._invalidate_render()
        self.update()

    def _invalidate_render(self) -> None:
        self._render_cache.clear()

    def set_settings(self, settings: LayoutSettings) -> None:
        self._settings = settings
        self._invalidate_render()
        self.update()

    def set_photo(self, photo: LoadedPhoto | None) -> None:
        self._photo = photo
        self._invalidate_render()
        self.update()

    def set_crop_state(self, crop_state: CropState) -> None:
        self._crop_state = crop_state
        self._invalidate_render()
        self.update()

    def set_validation_error(self, message: str | None) -> None:
        self._validation_error = message
        if message:
            self._invalidate_render()
        self.update()

    @property
    def ruler_visible(self) -> bool:
        return self._ruler_visible

    def set_ruler_visible(self, visible: bool) -> None:
        """Show or hide the rulers. Only repaints; cached renders are kept."""

        visible = bool(visible)
        if visible != self._ruler_visible:
            self._ruler_visible = visible
            self.update()

    def set_display_unit(self, unit: Unit) -> None:
        if unit is not self._display_unit:
            self._display_unit = unit
            self.update()

    def _layout(self) -> PhysicalLayout:
        if self._photo:
            return calculate_layout(
                self._settings,
                self._photo.width,
                self._photo.height,
                self._crop_state,
            )
        return calculate_layout(self._settings)

    def _rendered_page(self, width: int, height: int) -> tuple[QImage, RenderPlan]:
        assert self._photo is not None
        key = (id(self._photo), self._settings, self._crop_state, width, height)
        cached = self._render_cache.get(key)
        if cached is None:
            image, plan = render_preview_image(
                self._photo,
                self._settings,
                self._crop_state,
                (width, height),
            )
            cached = (pillow_to_qimage(image), plan)
            self._render_cache[key] = cached
            while len(self._render_cache) > RENDER_CACHE_SIZE:
                del self._render_cache[next(iter(self._render_cache))]
        return cached

    # -- Geometry ---------------------------------------------------------------

    def _ruler_font(self) -> QFont:
        font = QFont(self.font())
        font.setPixelSize(max(RULER_MIN_FONT_PX, round(RULER_FONT_PX * self._ui_scale)))
        return font

    def _ruler_reserve(self) -> tuple[float, float]:
        """Return (left, bottom) space kept free for the rulers; none when hidden."""

        if not self._ruler_visible:
            return 0.0, 0.0
        metrics = QFontMetricsF(self._ruler_font())
        depth = (RULER_GAP + RULER_MAJOR_TICK + RULER_LABEL_PAD) * self._ui_scale
        widest = max(metrics.horizontalAdvance(text) for text in RULER_WIDEST_LABELS)
        return depth + widest, depth + metrics.height()

    def _page_geometry(self, layout: PhysicalLayout) -> tuple[QRectF, float]:
        """Return the paper rectangle in widget pixels and the nominal px-per-mm scale."""

        margin = PAGE_MARGIN * self._ui_scale
        reserve_left, reserve_bottom = self._ruler_reserve()
        area = QRectF(
            margin + reserve_left,
            margin,
            max(1.0, self.width() - margin * 2 - reserve_left),
            max(1.0, self.height() - margin * 2 - reserve_bottom),
        )
        scale = min(area.width() / layout.paper.width, area.height() / layout.paper.height)
        page_width = max(1, round(layout.paper.width * scale))
        page_height = max(1, round(layout.paper.height * scale))
        return (
            QRectF(
                round(area.left() + (area.width() - page_width) / 2.0),
                round(area.top() + (area.height() - page_height) / 2.0),
                page_width,
                page_height,
            ),
            scale,
        )

    def _ticks_for(
        self, length_mm: float, px_per_mm: float, label_extent: Callable[[str], float]
    ) -> list[Tick]:
        unit = self._display_unit
        ticks = ruler_ticks(length_mm, unit)
        widest = max((label_extent(t.label) for t in ticks if t.label), default=0.0)
        stride = label_stride_for(major_step_mm(unit) * px_per_mm, widest * RULER_LABEL_SPACING)
        return ticks if stride == 1 else ruler_ticks(length_mm, unit, stride)

    def _ruler_drawing(self, layout: PhysicalLayout, page: QRectF) -> RulerDrawing | None:
        """Compute ruler primitives: left ruler counts down, bottom ruler counts right."""

        if not self._ruler_visible or self._photo is None or self._validation_error:
            return None
        s = self._ui_scale
        unit = self._display_unit
        metrics = QFontMetricsF(self._ruler_font())
        text_height = metrics.height()
        gap, pad, label_gap = RULER_GAP * s, RULER_LABEL_PAD * s, RULER_LABEL_GAP * s
        major, minor = RULER_MAJOR_TICK * s, RULER_MINOR_TICK * s
        paper = layout.paper
        px_x = page.width() / paper.width
        px_y = page.height() / paper.height
        horizontal_band, vertical_band = photo_bands(layout, unit)
        drawing = RulerDrawing()

        # Bottom ruler: origin at the paper's left edge, counting left to right.
        def x_at(mm: float) -> float:
            return page.left() + mm * px_x

        base_y = page.bottom() + gap
        drawing.bands.append(
            QRectF(
                x_at(horizontal_band.start_mm),
                base_y,
                (horizontal_band.end_mm - horizontal_band.start_mm) * px_x,
                major,
            )
        )
        drawing.lines.append(QLineF(x_at(0.0), base_y, x_at(paper.width), base_y))
        ticks = self._ticks_for(paper.width, px_x, metrics.horizontalAdvance)
        for tick in ticks:
            x = x_at(tick.position_mm)
            drawing.lines.append(QLineF(x, base_y, x, base_y + (major if tick.is_major else minor)))
        label_top = base_y + major + pad
        for label in layout_axis_labels(
            [(x_at(t.position_mm), t.label) for t in ticks if t.label],
            x_at(paper.width),
            format_length(paper.width, unit),
            (x_at(horizontal_band.end_mm), horizontal_band.label),
            metrics.horizontalAdvance,
            label_gap,
        ):
            drawing.labels.append(
                (QRectF(label.start, label_top, label.end - label.start, text_height), label.text, label.kind)
            )

        # Left ruler: origin at the paper's top edge, counting top to bottom.
        def y_at(mm: float) -> float:
            return page.top() + mm * px_y

        base_x = page.left() - gap
        drawing.bands.append(
            QRectF(
                base_x - major,
                y_at(vertical_band.start_mm),
                major,
                (vertical_band.end_mm - vertical_band.start_mm) * px_y,
            )
        )
        drawing.lines.append(QLineF(base_x, y_at(0.0), base_x, y_at(paper.height)))
        ticks = self._ticks_for(paper.height, px_y, lambda _text: text_height)
        for tick in ticks:
            y = y_at(tick.position_mm)
            drawing.lines.append(QLineF(base_x - (major if tick.is_major else minor), y, base_x, y))
        label_right = base_x - major - pad
        for label in layout_axis_labels(
            [(y_at(t.position_mm), t.label) for t in ticks if t.label],
            y_at(paper.height),
            format_length(paper.height, unit),
            (y_at(vertical_band.end_mm), vertical_band.label),
            lambda _text: text_height,
            label_gap / 2.0,
        ):
            width = metrics.horizontalAdvance(label.text)
            drawing.labels.append(
                (QRectF(label_right - width, label.start, width, label.end - label.start), label.text, label.kind)
            )
        return drawing

    # -- Painting ---------------------------------------------------------------

    def _draw_rulers(self, painter: QPainter, drawing: RulerDrawing) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)  # crisp 1 px lines
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(RULER_BAND_COLOR)
        for band in drawing.bands:
            painter.drawRect(band)
        pen = QPen(RULER_LINE_COLOR, 1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLines(drawing.lines)
        painter.setFont(self._ruler_font())
        for rect, text, kind in drawing.labels:
            painter.setPen(_LABEL_COLORS[kind])
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor("#eef1f5"))

        if self._validation_error:
            painter.setPen(QColor("#b42318"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._validation_error)
            return

        layout = self._layout()
        page_rect, scale = self._page_geometry(layout)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 28))
        painter.drawRoundedRect(
            page_rect.translated(4 * self._ui_scale, 5 * self._ui_scale),
            3 * self._ui_scale,
            3 * self._ui_scale,
        )
        painter.setBrush(QColor("#ffffff"))
        painter.drawRect(page_rect)

        if self._photo:
            rendered, plan = self._rendered_page(int(page_rect.width()), int(page_rect.height()))
            painter.drawImage(page_rect, rendered)
            target_rect = QRectF(
                page_rect.left() + plan.target.x,
                page_rect.top() + plan.target.y,
                plan.target.width,
                plan.target.height,
            )
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#596273"), 1))
            painter.drawRect(target_rect)
            drawing = self._ruler_drawing(layout, page_rect)
            if drawing is not None:
                self._draw_rulers(painter, drawing)
        else:
            target_rect = QRectF(
                page_rect.left() + layout.target.x * scale,
                page_rect.top() + layout.target.y * scale,
                layout.target.width * scale,
                layout.target.height * scale,
            )
            painter.setBrush(QColor("#f3f4f6"))
            painter.setPen(QPen(QColor("#aeb6c2"), 1, Qt.PenStyle.DashLine))
            painter.drawRect(target_rect)
            painter.setPen(QColor("#7b8492"))
            painter.drawText(
                target_rect,
                Qt.AlignmentFlag.AlignCenter,
                "Open a photo to preview",
            )
