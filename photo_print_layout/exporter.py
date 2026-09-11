"""JPEG output backed by the authoritative final render engine."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtGui import QImage

from .crop import CropState
from .image_loader import LoadedPhoto
from .models import LayoutSettings
from .render_engine import (
    paper_pixel_size,
    pillow_to_qimage,
    pixels_for_mm,
    render_final_image,
)


class ExportError(Exception):
    pass


def ensure_jpeg_extension(path: str | Path) -> Path:
    output = Path(path)
    if output.suffix.lower() in (".jpg", ".jpeg"):
        return output
    if output.suffix:
        return output.with_suffix(".jpg")
    return output.with_suffix(".jpg")


def render_paper_canvas(
    photo: LoadedPhoto,
    settings: LayoutSettings,
    crop_state: CropState,
) -> QImage:
    """Render the complete physical paper at the configured output DPI."""

    try:
        canvas, _ = render_final_image(photo, settings, crop_state)
        return pillow_to_qimage(canvas, settings.dpi)
    except (MemoryError, OSError) as exc:
        raise ExportError("Not enough memory to create the output image") from exc


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
    try:
        canvas, _ = render_final_image(photo, settings, crop_state)
        canvas.save(output, format="JPEG", quality=quality, dpi=(settings.dpi, settings.dpi))
    except (MemoryError, OSError) as exc:
        raise ExportError(str(exc) or "The JPEG could not be written") from exc
    return output
