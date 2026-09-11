"""Final-canvas preview backed by the authoritative render engine."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from .crop import CropState
from .image_loader import LoadedPhoto
from .layout import PhysicalLayout, calculate_layout
from .models import LayoutSettings
from .render_engine import RenderPlan, pillow_to_qimage, render_preview_image


class PreviewWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = LayoutSettings()
        self._photo: LoadedPhoto | None = None
        self._crop_state = CropState()
        self._validation_error: str | None = None
        self._render_cache_key: tuple[object, ...] | None = None
        self._render_cache: tuple[QImage, RenderPlan] | None = None
        self.setMinimumSize(440, 520)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName("Paper layout preview")

    def _invalidate_render(self) -> None:
        self._render_cache_key = None
        self._render_cache = None

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
        if key != self._render_cache_key or self._render_cache is None:
            image, plan = render_preview_image(
                self._photo,
                self._settings,
                self._crop_state,
                (width, height),
            )
            self._render_cache = pillow_to_qimage(image), plan
            self._render_cache_key = key
        return self._render_cache

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
        margin = 28.0
        available_width = max(1.0, self.width() - margin * 2)
        available_height = max(1.0, self.height() - margin * 2)
        scale = min(available_width / layout.paper.width, available_height / layout.paper.height)
        page_width = max(1, round(layout.paper.width * scale))
        page_height = max(1, round(layout.paper.height * scale))
        origin_x = (self.width() - page_width) / 2.0
        origin_y = (self.height() - page_height) / 2.0
        page_rect = QRectF(origin_x, origin_y, page_width, page_height)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 28))
        painter.drawRoundedRect(page_rect.translated(4, 5), 3, 3)
        painter.setBrush(QColor("#ffffff"))
        painter.drawRect(page_rect)

        if self._photo:
            rendered, plan = self._rendered_page(page_width, page_height)
            painter.drawImage(page_rect, rendered)
            target_rect = QRectF(
                origin_x + plan.target.x,
                origin_y + plan.target.y,
                plan.target.width,
                plan.target.height,
            )
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#596273"), 1))
            painter.drawRect(target_rect)
        else:
            target_rect = QRectF(
                origin_x + layout.target.x * scale,
                origin_y + layout.target.y * scale,
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
                "11 × 14\nOpen a photo to preview",
            )
