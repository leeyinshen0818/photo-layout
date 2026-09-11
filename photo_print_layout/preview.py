"""A widget that scales and renders the physical layout model."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from .crop import CropState
from .image_loader import LoadedPhoto
from .layout import PhysicalLayout, calculate_layout
from .models import LayoutSettings


class PreviewWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = LayoutSettings()
        self._photo: LoadedPhoto | None = None
        self._crop_state = CropState()
        self._validation_error: str | None = None
        self.setMinimumSize(440, 520)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName("Paper layout preview")

    def set_settings(self, settings: LayoutSettings) -> None:
        self._settings = settings
        self.update()

    def set_photo(self, photo: LoadedPhoto | None) -> None:
        self._photo = photo
        self.update()

    def set_crop_state(self, crop_state: CropState) -> None:
        self._crop_state = crop_state
        self.update()

    def set_validation_error(self, message: str | None) -> None:
        self._validation_error = message
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
        page_width = layout.paper.width * scale
        page_height = layout.paper.height * scale
        origin_x = (self.width() - page_width) / 2.0
        origin_y = (self.height() - page_height) / 2.0

        def screen_rect(rect) -> QRectF:
            return QRectF(
                origin_x + rect.x * scale,
                origin_y + rect.y * scale,
                rect.width * scale,
                rect.height * scale,
            )

        page_rect = screen_rect(layout.paper)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 28))
        painter.drawRoundedRect(page_rect.translated(4, 5), 3, 3)
        painter.setBrush(QColor("#ffffff"))
        painter.drawRect(page_rect)

        target_rect = screen_rect(layout.target)
        painter.setBrush(QColor("#f3f4f6"))
        painter.setPen(QPen(QColor("#aeb6c2"), 1, Qt.PenStyle.DashLine))
        painter.drawRect(target_rect)

        if self._photo and layout.image and layout.source:
            destination = screen_rect(layout.image)
            source = QRectF(layout.source.x, layout.source.y, layout.source.width, layout.source.height)
            painter.save()
            painter.setClipRect(target_rect)
            painter.drawImage(destination, self._photo.image, source)
            painter.restore()
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#596273"), 1))
            painter.drawRect(target_rect)
        else:
            painter.setPen(QColor("#7b8492"))
            painter.drawText(target_rect, Qt.AlignmentFlag.AlignCenter, "11 × 14\nOpen a photo to preview")
