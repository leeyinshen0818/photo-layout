"""Modal traditional crop editor for the EXIF-corrected working image."""

from __future__ import annotations

from math import hypot

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QResizeEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .crop import (
    MIN_CROP_FRACTION,
    CropState,
    constrained_crop_state,
    default_crop_state,
)
from .image_loader import LoadedPhoto
from .models import SizeMM


class CropCanvas(QWidget):
    state_changed = Signal(object)

    HANDLE_SIZE = 11.0
    HANDLE_HIT_RADIUS = 16.0
    MIN_FRAME_PIXELS = 30.0

    def __init__(self, photo: LoadedPhoto, target_size: SizeMM, parent=None) -> None:
        super().__init__(parent)
        self._photo = photo
        self._target = target_size
        self._state = default_crop_state(
            photo.width, photo.height, target_size.width, target_size.height
        )
        self._view_image_rect: QRectF | None = None
        self._last_mouse: QPointF | None = None
        self._interaction: str | None = None
        self._resize_direction = (1, 1)
        self._resize_opposite = QPointF()
        self.setMinimumSize(520, 440)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setAccessibleName("Interactive crop area")

    @property
    def crop_state(self) -> CropState:
        return self._state

    def set_crop_state(self, state: CropState) -> None:
        self._state = constrained_crop_state(
            state,
            self._photo.width,
            self._photo.height,
            self._target.width,
            self._target.height,
        )
        self._view_image_rect = None
        self.state_changed.emit(self._state)
        self.update()

    def reset_crop(self) -> None:
        self.set_crop_state(
            default_crop_state(
                self._photo.width,
                self._photo.height,
                self._target.width,
                self._target.height,
            )
        )

    def _fitted_image_rect(self) -> QRectF:
        margin = 34.0
        available_width = max(1.0, self.width() - margin * 2.0)
        available_height = max(1.0, self.height() - margin * 2.0)
        scale = min(
            available_width / self._photo.width,
            available_height / self._photo.height,
        )
        width = self._photo.width * scale
        height = self._photo.height * scale
        return QRectF(
            (self.width() - width) / 2.0,
            (self.height() - height) / 2.0,
            width,
            height,
        )

    def _image_rect(self) -> QRectF:
        return QRectF(self._view_image_rect or self._fitted_image_rect())

    def _crop_frame(self) -> QRectF:
        image = self._image_rect()
        state = constrained_crop_state(
            self._state,
            self._photo.width,
            self._photo.height,
            self._target.width,
            self._target.height,
        )
        return QRectF(
            image.left() + state.x * image.width(),
            image.top() + state.y * image.height(),
            state.width * image.width(),
            state.height * image.height(),
        )

    def _state_from_frame(self, frame: QRectF, image: QRectF) -> CropState:
        return constrained_crop_state(
            CropState(
                (frame.left() - image.left()) / image.width(),
                (frame.top() - image.top()) / image.height(),
                frame.width() / image.width(),
                frame.height() / image.height(),
            ),
            self._photo.width,
            self._photo.height,
            self._target.width,
            self._target.height,
        )

    def _handles(self) -> tuple[tuple[QPointF, tuple[int, int]], ...]:
        frame = self._crop_frame()
        return (
            (frame.topLeft(), (-1, -1)),
            (frame.topRight(), (1, -1)),
            (frame.bottomLeft(), (-1, 1)),
            (frame.bottomRight(), (1, 1)),
        )

    def _handle_at(self, position: QPointF) -> tuple[int, int] | None:
        for point, direction in self._handles():
            if hypot(position.x() - point.x(), position.y() - point.y()) <= self.HANDLE_HIT_RADIUS:
                return direction
        return None

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor("#15181d"))

        image = self._image_rect()
        frame = self._crop_frame()
        painter.drawImage(image, self._photo.image)

        shade = QColor(0, 0, 0, 160)
        painter.fillRect(QRectF(0, 0, self.width(), frame.top()), shade)
        painter.fillRect(
            QRectF(0, frame.bottom(), self.width(), self.height() - frame.bottom()), shade
        )
        painter.fillRect(QRectF(0, frame.top(), frame.left(), frame.height()), shade)
        painter.fillRect(
            QRectF(frame.right(), frame.top(), self.width() - frame.right(), frame.height()), shade
        )

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.drawRect(frame)
        painter.setPen(QPen(QColor(255, 255, 255, 105), 1))
        for fraction in (1.0 / 3.0, 2.0 / 3.0):
            x = frame.left() + frame.width() * fraction
            y = frame.top() + frame.height() * fraction
            painter.drawLine(QPointF(x, frame.top()), QPointF(x, frame.bottom()))
            painter.drawLine(QPointF(frame.left(), y), QPointF(frame.right(), y))

        painter.setPen(QPen(QColor("#ffffff"), 1))
        painter.setBrush(QColor("#246bfd"))
        half = self.HANDLE_SIZE / 2.0
        for point, _ in self._handles():
            painter.drawRect(
                QRectF(point.x() - half, point.y() - half, self.HANDLE_SIZE, self.HANDLE_SIZE)
            )

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() not in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            return super().mousePressEvent(event)

        self._last_mouse = event.position()
        handle = self._handle_at(event.position()) if event.button() == Qt.MouseButton.LeftButton else None
        frame = self._crop_frame()
        if handle:
            self._interaction = "resize_crop"
            self._resize_direction = handle
            self._resize_opposite = QPointF(
                frame.left() if handle[0] > 0 else frame.right(),
                frame.top() if handle[1] > 0 else frame.bottom(),
            )
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif event.button() == Qt.MouseButton.LeftButton and frame.contains(event.position()):
            self._interaction = "move_crop"
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        elif self._image_rect().contains(event.position()) or event.button() == Qt.MouseButton.RightButton:
            self._interaction = "pan_image"
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        else:
            self._last_mouse = None
            return super().mousePressEvent(event)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._last_mouse is None or self._interaction is None:
            self._update_cursor(event.position())
            return super().mouseMoveEvent(event)

        delta = event.position() - self._last_mouse
        image = self._image_rect()
        frame = self._crop_frame()
        if self._interaction == "move_crop":
            left = min(image.right() - frame.width(), max(image.left(), frame.left() + delta.x()))
            top = min(image.bottom() - frame.height(), max(image.top(), frame.top() + delta.y()))
            self._state = self._state_from_frame(
                QRectF(left, top, frame.width(), frame.height()), image
            )
        elif self._interaction == "pan_image":
            left = min(frame.left(), max(frame.right() - image.width(), image.left() + delta.x()))
            top = min(frame.top(), max(frame.bottom() - image.height(), image.top() + delta.y()))
            shifted = QRectF(left, top, image.width(), image.height())
            self._view_image_rect = shifted
            self._state = self._state_from_frame(frame, shifted)
        else:
            self._resize_to(event.position(), image)

        self._last_mouse = event.position()
        self.state_changed.emit(self._state)
        self.update()
        event.accept()

    def _resize_to(self, position: QPointF, image: QRectF) -> None:
        horizontal, vertical = self._resize_direction
        aspect = self._target.width / self._target.height
        proposed = max(
            abs(position.x() - self._resize_opposite.x()),
            abs(position.y() - self._resize_opposite.y()) * aspect,
        )
        max_horizontal = (
            image.right() - self._resize_opposite.x()
            if horizontal > 0
            else self._resize_opposite.x() - image.left()
        )
        max_vertical = (
            image.bottom() - self._resize_opposite.y()
            if vertical > 0
            else self._resize_opposite.y() - image.top()
        ) * aspect
        maximum = min(max_horizontal, max_vertical)
        minimum = min(maximum, max(self.MIN_FRAME_PIXELS, image.width() * MIN_CROP_FRACTION))
        width = min(maximum, max(minimum, proposed))
        height = width / aspect
        left = self._resize_opposite.x() if horizontal > 0 else self._resize_opposite.x() - width
        top = self._resize_opposite.y() if vertical > 0 else self._resize_opposite.y() - height
        self._state = self._state_from_frame(QRectF(left, top, width, height), image)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._last_mouse is not None:
            self._last_mouse = None
            self._interaction = None
            self._update_cursor(event.position())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _update_cursor(self, position: QPointF) -> None:
        if self._handle_at(position):
            cursor = Qt.CursorShape.SizeFDiagCursor
        elif self._crop_frame().contains(position):
            cursor = Qt.CursorShape.SizeAllCursor
        elif self._image_rect().contains(position):
            cursor = Qt.CursorShape.OpenHandCursor
        else:
            cursor = Qt.CursorShape.ArrowCursor
        self.setCursor(cursor)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._last_mouse is None:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().leaveEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        # Canonicalize only the editor view. The normalized crop composition is unchanged.
        self._view_image_rect = None
        super().resizeEvent(event)


class CropEditorDialog(QDialog):
    def __init__(
        self,
        photo: LoadedPhoto,
        target_size: SizeMM,
        initial_state: CropState,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Crop / Adjust")
        self.setModal(True)
        self.resize(820, 760)
        self.setMinimumSize(640, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        instruction = QLabel(
            "Drag inside the frame to move it · Drag blue corners to resize · "
            "Drag outside the frame or right-drag to move the image"
        )
        instruction.setWordWrap(True)
        layout.addWidget(instruction)

        self.canvas = CropCanvas(photo, target_size)
        layout.addWidget(self.canvas, 1)

        footer = QHBoxLayout()
        reset = QPushButton("Reset")
        reset.clicked.connect(self.reset_crop)
        footer.addWidget(reset)
        footer.addStretch()
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        footer.addWidget(buttons)
        layout.addLayout(footer)

        self.canvas.set_crop_state(initial_state)

    @property
    def crop_state(self) -> CropState:
        return self.canvas.crop_state

    def reset_crop(self) -> None:
        self.canvas.reset_crop()
