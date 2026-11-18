"""A compact sliding on/off switch and a label that toggles it."""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    Property,
)
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QLabel, QSizePolicy, QWidget


TRACK_OFF = QColor("#cfd5dd")
TRACK_OFF_HOVER = QColor("#bcc4cf")
TRACK_ON = QColor("#246bfd")  # app blue
TRACK_ON_HOVER = QColor("#1758d5")  # app hover blue
FOCUS_RING = QColor("#6f9cff")  # app focus colour
KNOB = QColor("#ffffff")
KNOB_SHADOW = QColor(0, 0, 0, 38)
KNOB_BORDER = QColor(0, 0, 0, 22)
ANIMATION_MS = 150


def _blend(start: QColor, end: QColor, amount: float) -> QColor:
    amount = min(1.0, max(0.0, amount))
    return QColor(
        round(start.red() + (end.red() - start.red()) * amount),
        round(start.green() + (end.green() - start.green()) * amount),
        round(start.blue() + (end.blue() - start.blue()) * amount),
        round(start.alpha() + (end.alpha() - start.alpha()) * amount),
    )


class ToggleSwitch(QAbstractButton):
    """A checkable pill-shaped switch; the knob slides right when checked.

    User activation (click, Space, ``click()``) animates the knob. ``setChecked``
    from code places it immediately, so restored state never visibly slides.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)  # repaint on enter/leave
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._knob_position = 0.0  # 0 = off (left), 1 = on (right)
        self._animate_next_toggle = False
        self._track_size = QSize(34, 18)
        self._focus_margin = 3
        self._animation = QPropertyAnimation(self, b"knobPosition", self)
        self._animation.setDuration(ANIMATION_MS)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.toggled.connect(self._move_knob)
        self._apply_size()

    # -- Knob position (animated property) ---------------------------------------

    def _get_knob_position(self) -> float:
        return self._knob_position

    def _set_knob_position(self, value: float) -> None:
        self._knob_position = value
        self.update()

    knobPosition = Property(float, _get_knob_position, _set_knob_position)  # noqa: N815

    @property
    def animation(self) -> QPropertyAnimation:
        return self._animation

    def set_animation_duration(self, milliseconds: int) -> None:
        self._animation.setDuration(max(0, milliseconds))

    def nextCheckState(self) -> None:  # noqa: N802 - Qt API name
        # Only user activation reaches here; setChecked() from code does not.
        self._animate_next_toggle = True
        super().nextCheckState()

    def _move_knob(self, checked: bool) -> None:
        end = 1.0 if checked else 0.0
        animate = self._animate_next_toggle and self._animation.duration() > 0
        self._animate_next_toggle = False
        self._animation.stop()
        if animate:
            self._animation.setStartValue(self._knob_position)
            self._animation.setEndValue(end)
            self._animation.start()
        else:
            self._set_knob_position(end)

    # -- Size ---------------------------------------------------------------------

    def track_size(self) -> QSize:
        return QSize(self._track_size)

    def set_track_size(self, width: int, height: int, focus_margin: int) -> None:
        """Size the track in logical pixels; the focus ring uses the margin around it."""

        self._track_size = QSize(max(8, width), max(6, height))
        self._focus_margin = max(1, focus_margin)
        self._apply_size()

    def _apply_size(self) -> None:
        self.setFixedSize(self.sizeHint())
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API name
        margin = self._focus_margin * 2
        return QSize(self._track_size.width() + margin, self._track_size.height() + margin)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt API name
        return self.sizeHint()

    # -- Painting -----------------------------------------------------------------

    def _track_rect(self) -> QRectF:
        width, height = self._track_size.width(), self._track_size.height()
        return QRectF(
            (self.width() - width) / 2.0, (self.height() - height) / 2.0, width, height
        )

    def knob_rect(self) -> QRectF:
        track = self._track_rect()
        inset = max(1.5, track.height() / 9.0)  # 2 px at the 18 px reference height
        diameter = track.height() - inset * 2
        travel = track.width() - inset * 2 - diameter
        return QRectF(
            track.left() + inset + travel * self._knob_position,
            track.top() + inset,
            diameter,
            diameter,
        )

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API name
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.45)
        hover = self.underMouse() and self.isEnabled()
        off = TRACK_OFF_HOVER if hover else TRACK_OFF
        on = TRACK_ON_HOVER if hover else TRACK_ON
        track = self._track_rect()
        radius = track.height() / 2.0

        if self.hasFocus():
            ring_width = max(1.0, track.height() / 12.0)
            painter.setPen(QPen(FOCUS_RING, ring_width))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            spread = self._focus_margin - ring_width / 2.0
            painter.drawRoundedRect(
                track.adjusted(-spread, -spread, spread, spread), radius + spread, radius + spread
            )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_blend(off, on, self._knob_position))
        painter.drawRoundedRect(track, radius, radius)

        knob = self.knob_rect()
        lift = track.height() / 24.0
        painter.setBrush(KNOB_SHADOW)
        painter.drawEllipse(knob.translated(0, lift).adjusted(-0.4, -0.4, 0.4, 0.4))
        painter.setBrush(KNOB)
        painter.setPen(QPen(KNOB_BORDER, 0.75))
        painter.drawEllipse(knob)


class SwitchLabel(QLabel):
    """A text label that toggles its switch when clicked."""

    def __init__(self, text: str, switch: ToggleSwitch, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._switch = switch
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(switch.toolTip())

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API name
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()  # keep the release for this label
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API name
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
            and self._switch.isEnabled()
        ):
            self._switch.click()  # same path as clicking the switch, including the slide
            event.accept()
            return
        super().mouseReleaseEvent(event)
