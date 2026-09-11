"""Full-resolution JPEG rendering using the shared physical layout model."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QImageWriter, QPainter

from .crop import CropState
from .image_loader import LoadedPhoto
from .layout import calculate_layout
from .models import MM_PER_INCH, LayoutSettings


class ExportError(Exception):
    pass


def pixels_for_mm(length_mm: float, dpi: int) -> int:
    if length_mm <= 0 or dpi <= 0:
        raise ValueError("Physical length and DPI must be positive")
    return round(length_mm / MM_PER_INCH * dpi)


def ensure_jpeg_extension(path: str | Path) -> Path:
    output = Path(path)
    if output.suffix.lower() in (".jpg", ".jpeg"):
        return output
    if output.suffix:
        return output.with_suffix(".jpg")
    return output.with_suffix(".jpg")


def paper_pixel_size(settings: LayoutSettings) -> tuple[int, int]:
    paper = settings.paper_size_mm
    return pixels_for_mm(paper.width, settings.dpi), pixels_for_mm(paper.height, settings.dpi)


def render_paper_canvas(
    photo: LoadedPhoto,
    settings: LayoutSettings,
    crop_state: CropState,
) -> QImage:
    """Render the complete physical paper at the configured output DPI."""

    layout = calculate_layout(settings, photo.width, photo.height, crop_state)
    width, height = paper_pixel_size(settings)
    canvas = QImage(width, height, QImage.Format.Format_RGB32)
    if canvas.isNull():
        raise ExportError("Not enough memory to create the output image")
    canvas.fill(QColor("white"))
    dots_per_meter = round(settings.dpi / 0.0254)
    canvas.setDotsPerMeterX(dots_per_meter)
    canvas.setDotsPerMeterY(dots_per_meter)

    if layout.image and layout.source:
        x_scale = width / layout.paper.width
        y_scale = height / layout.paper.height
        destination = QRectF(
            layout.image.x * x_scale,
            layout.image.y * y_scale,
            layout.image.width * x_scale,
            layout.image.height * y_scale,
        )
        source = QRectF(
            layout.source.x,
            layout.source.y,
            layout.source.width,
            layout.source.height,
        )
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(destination, photo.image, source)
        painter.end()
    return canvas


def export_jpeg(
    path: str | Path,
    photo: LoadedPhoto,
    settings: LayoutSettings,
    crop_state: CropState,
    quality: int = 95,
) -> Path:
    """Write a newly rendered paper canvas as a high-quality JPEG."""

    output = ensure_jpeg_extension(path)
    if os.path.normcase(os.path.abspath(output)) == os.path.normcase(
        os.path.abspath(photo.path)
    ):
        raise ExportError("The output path must be different from the original photo")
    canvas = render_paper_canvas(photo, settings, crop_state)
    writer = QImageWriter(str(output), b"jpeg")
    writer.setQuality(quality)
    if not writer.write(canvas):
        raise ExportError(writer.errorString() or "The JPEG could not be written")
    return output
