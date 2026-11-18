"""Test support: offscreen Qt with real fonts, and an automatic layout audit.

Qt's offscreen platform ships no fonts on Windows, so every glyph is a wide
placeholder box and text-fitting checks are meaningless; ``configure_offscreen``
points ``QT_QPA_FONTDIR`` at the system font folder. Call it before the first
QApplication. ``audit_widget_tree(root)`` reports clipped text, widgets squeezed
below their minimum size hint, overlaps, and widgets outside their parent or
window (content inside a scroll area is checked against the scrolled content).
"""


from __future__ import annotations

import os
import sys
from pathlib import Path


def system_fonts_dir() -> Path | None:
    """The Windows fonts folder, or None on platforms without one."""

    if sys.platform != "win32":
        return None
    folder = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    return folder if folder.is_dir() else None


def configure_offscreen(*, real_fonts: bool = True) -> bool:
    """Use the offscreen platform with real fonts when available.

    Returns True when real fonts are configured; elsewhere tests still run but
    text measurements use Qt's fallback font.
    """

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if not real_fonts:
        return False
    if os.environ.get("QT_QPA_FONTDIR"):
        return True
    folder = system_fonts_dir()
    if folder is None:
        return False
    os.environ["QT_QPA_FONTDIR"] = str(folder)
    return True


def real_fonts_configured() -> bool:
    return bool(os.environ.get("QT_QPA_FONTDIR"))


def application(style: str | None = "Fusion"):
    """The shared QApplication, created once; the style is set only if it differs.

    ``setStyle`` re-polishes every existing widget, which gets very slow once a
    test run has created many windows, so never call it repeatedly.
    """

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    if style and app.style().name().lower() != style.lower():
        app.setStyle(style)
    return app




from itertools import combinations
from pathlib import Path

from PySide6.QtCore import QRect, QSize
from PySide6.QtGui import QFontMetricsF
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractScrollArea,
    QAbstractSpinBox,
    QComboBox,
    QLabel,
    QPushButton,
    QScrollArea,
    QStyle,
    QStyleOptionButton,
    QStyleOptionComboBox,
    QStyleOptionSpinBox,
    QWidget,
)

TEXT_TYPES = (QLabel, QAbstractButton, QComboBox, QAbstractSpinBox)
TOLERANCE = 0.5


def describe(widget: QWidget) -> str:
    text = ""
    if isinstance(widget, (QLabel, QAbstractButton)):
        text = widget.text().replace("\n", " ")[:32]
    elif isinstance(widget, QComboBox):
        text = widget.currentText()[:32]
    return f"{type(widget).__name__}#{widget.objectName() or '-'}({text!r})"


def _is_internal(widget: QWidget, root: QWidget) -> bool:
    parent = widget.parentWidget()
    while parent is not None and parent is not root:
        if isinstance(parent, (QComboBox, QAbstractSpinBox)):
            return True
        parent = parent.parentWidget()
    return False


def visible_leaves(root: QWidget) -> list[QWidget]:
    """Visible text-bearing controls under ``root`` (internals of combos/spin boxes excluded)."""

    window = root.window()
    return [
        widget
        for widget in root.findChildren(QWidget)
        if isinstance(widget, TEXT_TYPES)
        and widget.isVisibleTo(window)
        and not _is_internal(widget, root)
    ]


def rect_in(widget: QWidget, ancestor: QWidget) -> QRect:
    return QRect(widget.mapTo(ancestor, widget.rect().topLeft()), widget.size())


def container_of(widget: QWidget, root: QWidget) -> QWidget:
    """The scroll content widget holding ``widget``, or ``root``."""

    parent = widget.parentWidget()
    while parent is not None and parent is not root:
        grand = parent.parentWidget()
        if grand is not None and isinstance(grand.parentWidget(), QAbstractScrollArea):
            if grand is grand.parentWidget().viewport():
                return parent
        parent = grand
    return root


def text_problems(widget: QWidget) -> list[str]:
    """Clipping found by comparing font metrics with the widget's text area."""

    problems: list[str] = []
    metrics = QFontMetricsF(widget.font())
    style = widget.style()
    if isinstance(widget, QLabel):
        text = widget.text()
        if not text or not widget.pixmap().isNull():
            return problems
        area = widget.contentsRect()
        if widget.wordWrap():
            need = widget.heightForWidth(widget.width())
            if need > widget.height() + TOLERANCE:
                problems.append(f"wrapped text needs {need}px height, has {widget.height()}px")
        else:
            lines = text.split("\n")
            width = max(metrics.horizontalAdvance(line) for line in lines)
            height = metrics.height() * len(lines)
            if width > area.width() + TOLERANCE:
                problems.append(f"text {width:.0f}px wide > {area.width()}px")
            if height > area.height() + TOLERANCE:
                problems.append(f"text {height:.0f}px tall > {area.height()}px")
    elif isinstance(widget, QPushButton):
        option = QStyleOptionButton()
        widget.initStyleOption(option)
        area = style.subElementRect(QStyle.SubElement.SE_PushButtonContents, option, widget)
        width = metrics.horizontalAdvance(widget.text())
        if width > area.width() + TOLERANCE:
            problems.append(f"button text {width:.0f}px > {area.width()}px")
        if metrics.height() > area.height() + TOLERANCE:
            problems.append(f"button text {metrics.height():.0f}px tall > {area.height()}px")
    elif isinstance(widget, QComboBox):
        option = QStyleOptionComboBox()
        widget.initStyleOption(option)
        area = style.subControlRect(
            QStyle.ComplexControl.CC_ComboBox, option, QStyle.SubControl.SC_ComboBoxEditField, widget
        )
        texts = [widget.itemText(i) for i in range(widget.count())] + [widget.placeholderText()]
        for text in texts:
            width = metrics.horizontalAdvance(text)
            if text and width > area.width() + TOLERANCE:
                problems.append(f"item {text!r} {width:.0f}px > {area.width()}px (elided)")
        if metrics.height() > area.height() + TOLERANCE:
            problems.append(f"combo text {metrics.height():.0f}px tall > {area.height()}px")
    elif isinstance(widget, QAbstractSpinBox):
        option = QStyleOptionSpinBox()
        widget.initStyleOption(option)
        area = style.subControlRect(
            QStyle.ComplexControl.CC_SpinBox, option, QStyle.SubControl.SC_SpinBoxEditField, widget
        )
        width = metrics.horizontalAdvance(widget.text())
        if width > area.width() + TOLERANCE:
            problems.append(f"value {widget.text()!r} {width:.0f}px > {area.width()}px")
        if metrics.height() > area.height() + TOLERANCE:
            problems.append(f"spin text {metrics.height():.0f}px tall > {area.height()}px")
    return problems


def audit_widget_tree(root: QWidget, *, min_overlap: int = 2) -> list[str]:
    """Return every clipping, squeeze, overlap, and overflow problem under ``root``."""

    problems: list[str] = []
    window = root.window()
    leaves = visible_leaves(root)
    by_container: dict[int, list[tuple[QWidget, QRect]]] = {}

    for widget in leaves:
        name = describe(widget)
        problems += [f"{name}: {issue}" for issue in text_problems(widget)]
        hint = widget.minimumSizeHint()
        fixed_height = widget.minimumHeight() == widget.maximumHeight()
        if hint.isValid() and not fixed_height and widget.height() + TOLERANCE < hint.height():
            problems.append(f"{name}: squeezed to {widget.height()}px < minimum {hint.height()}px")
        if (
            hint.isValid()
            and isinstance(widget, (QPushButton, QAbstractSpinBox))
            and widget.width() + TOLERANCE < hint.width()
        ):
            problems.append(f"{name}: squeezed to {widget.width()}px wide < minimum {hint.width()}px")
        parent = widget.parentWidget()
        if parent is not None and not parent.rect().contains(widget.geometry()):
            problems.append(f"{name}: extends outside its parent {describe(parent)}")
        container = container_of(widget, root)
        rect = rect_in(widget, container)
        if not container.rect().contains(rect):
            where = "window" if container is root else "scroll content"
            problems.append(f"{name}: extends outside the {where}")
        by_container.setdefault(id(container), []).append((widget, rect))

    for members in by_container.values():
        for (a, rect_a), (b, rect_b) in combinations(members, 2):
            if a.isAncestorOf(b) or b.isAncestorOf(a):
                continue
            overlap = rect_a.intersected(rect_b)
            if overlap.width() >= min_overlap and overlap.height() >= min_overlap:
                problems.append(
                    f"overlap {describe(a)} / {describe(b)} ({overlap.width()}×{overlap.height()}px)"
                )

    for widget in [root, *root.findChildren(QWidget)]:
        if widget.layout() is None or not widget.isVisibleTo(window) or _is_internal(widget, root):
            continue
        need = widget.minimumSizeHint()
        if need.isValid() and widget.height() + TOLERANCE < need.height():
            problems.append(
                f"{describe(widget)}: container {widget.height()}px tall < layout minimum {need.height()}px"
            )
    return problems


def scroll_report(root: QWidget) -> list[dict]:
    """Which scroll areas under ``root`` are scrolling, with content vs viewport heights."""

    report = []
    for area in root.findChildren(QScrollArea):
        if not area.isVisibleTo(root.window()) or area.widget() is None:
            continue
        report.append(
            {
                "name": area.objectName() or type(area).__name__,
                "scrolling": area.verticalScrollBar().maximum() > 0,
                "content_height": area.widget().minimumSizeHint().height(),
                "viewport_height": area.viewport().height(),
            }
        )
    return report


def window_fits(window: QWidget, available: QSize) -> list[str]:
    if window.width() > available.width() or window.height() > available.height():
        return [
            f"window {window.width()}×{window.height()} exceeds the available "
            f"{available.width()}×{available.height()}"
        ]
    return []


def save_render(widget: QWidget, path: str | Path) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    widget.grab().save(str(path))
    return str(path)
