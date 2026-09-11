"""Modal interactive crop editor for the normalized working image."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .crop import MAX_ZOOM, MIN_ZOOM, CropState, constrained_crop_state, crop_source_rect, pan_crop_state
from .image_loader import LoadedPhoto
from .models import PhotoSize


class CropCanvas(QWidget):
    state_changed = Signal(object)

    def __init__(self, photo: LoadedPhoto, target_size: PhotoSize, parent=None) -> None:
        super().__init__(parent)
        self._photo = photo
        self._target = target_size.size_mm
        self._state = CropState()
        self._last_mouse: QPointF | None = None
        self.setMinimumSize(520, 440)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
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
        self.state_changed.emit(self._state)
        self.update()

    def _crop_frame(self) -> QRectF:
        margin = 38.0
        available_width = max(1.0, self.width() - margin * 2.0)
        available_height = max(1.0, self.height() - margin * 2.0)
        scale = min(
            available_width / self._target.width,
            available_height / self._target.height,
        )
        width = self._target.width * scale
        height = self._target.height * scale
        return QRectF((self.width() - width) / 2.0, (self.height() - height) / 2.0, width, height)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor("#15181d"))

        frame = self._crop_frame()
        source = crop_source_rect(
            self._state,
            self._photo.width,
            self._photo.height,
            self._target.width,
            self._target.height,
        )
        scale = frame.width() / source.width
        image_rect = QRectF(
            frame.left() - source.x * scale,
            frame.top() - source.y * scale,
            self._photo.width * scale,
            self._photo.height * scale,
        )
        painter.drawImage(image_rect, self._photo.image)

        shade = QColor(0, 0, 0, 155)
        painter.fillRect(QRectF(0, 0, self.width(), frame.top()), shade)
        painter.fillRect(QRectF(0, frame.bottom(), self.width(), self.height() - frame.bottom()), shade)
        painter.fillRect(QRectF(0, frame.top(), frame.left(), frame.height()), shade)
        painter.fillRect(QRectF(frame.right(), frame.top(), self.width() - frame.right(), frame.height()), shade)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.drawRect(frame)
        painter.setPen(QPen(QColor(255, 255, 255, 105), 1))
        for fraction in (1.0 / 3.0, 2.0 / 3.0):
            x = frame.left() + frame.width() * fraction
            y = frame.top() + frame.height() * fraction
            painter.drawLine(QPointF(x, frame.top()), QPointF(x, frame.bottom()))
            painter.drawLine(QPointF(frame.left(), y), QPointF(frame.right(), y))

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._last_mouse = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._last_mouse is not None and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.position() - self._last_mouse
            frame = self._crop_frame()
            self._state = pan_crop_state(
                self._state,
                delta.x() / frame.width(),
                delta.y() / frame.height(),
                self._photo.width,
                self._photo.height,
                self._target.width,
                self._target.height,
            )
            self._last_mouse = event.position()
            self.state_changed.emit(self._state)
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._last_mouse = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        steps = event.angleDelta().y() / 120.0
        if steps:
            self.set_crop_state(
                CropState(self._state.zoom + steps * 0.1, self._state.center_x, self._state.center_y)
            )
            event.accept()
            return
        super().wheelEvent(event)


class CropEditorDialog(QDialog):
    def __init__(
        self,
        photo: LoadedPhoto,
        target_size: PhotoSize,
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
        instruction = QLabel("Drag the photo behind the fixed frame. Use zoom to refine the crop.")
        instruction.setObjectName("cropInstruction")
        layout.addWidget(instruction)

        self.canvas = CropCanvas(photo, target_size)
        layout.addWidget(self.canvas, 1)

        zoom_row = QHBoxLayout()
        zoom_out = QPushButton("−")
        zoom_out.setAccessibleName("Zoom out")
        zoom_out.setFixedWidth(38)
        zoom_in = QPushButton("+")
        zoom_in.setAccessibleName("Zoom in")
        zoom_in.setFixedWidth(38)
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(int(MIN_ZOOM * 100), int(MAX_ZOOM * 100))
        self.zoom_slider.setSingleStep(5)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setMinimumWidth(48)
        reset = QPushButton("Reset")

        zoom_row.addWidget(QLabel("Zoom"))
        zoom_row.addWidget(zoom_out)
        zoom_row.addWidget(self.zoom_slider, 1)
        zoom_row.addWidget(zoom_in)
        zoom_row.addWidget(self.zoom_label)
        zoom_row.addSpacing(12)
        zoom_row.addWidget(reset)
        layout.addLayout(zoom_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.zoom_slider.valueChanged.connect(self._zoom_changed)
        zoom_out.clicked.connect(lambda: self.zoom_slider.setValue(self.zoom_slider.value() - 10))
        zoom_in.clicked.connect(lambda: self.zoom_slider.setValue(self.zoom_slider.value() + 10))
        reset.clicked.connect(self.reset_crop)
        self.canvas.state_changed.connect(self._canvas_state_changed)
        self.canvas.set_crop_state(initial_state)

    @property
    def crop_state(self) -> CropState:
        return self.canvas.crop_state

    def reset_crop(self) -> None:
        self.canvas.set_crop_state(CropState())

    def _zoom_changed(self, value: int) -> None:
        current = self.canvas.crop_state
        self.canvas.set_crop_state(CropState(value / 100.0, current.center_x, current.center_y))

    def _canvas_state_changed(self, state: CropState) -> None:
        value = round(state.zoom * 100)
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(value)
        self.zoom_slider.blockSignals(False)
        self.zoom_label.setText(f"{value}%")

