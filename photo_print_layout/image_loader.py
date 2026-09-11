"""Non-destructive image loading and working-image normalization."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isclose
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from PySide6.QtGui import QImage

from .models import PHOTO_11X14, PhotoSize


SUPPORTED_FILE_FILTER = "Photos (*.jpg *.jpeg *.png *.tif *.tiff)"


class ImageLoadError(Exception):
    pass


class ImageOrientation(Enum):
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"
    SQUARE = "square"


def image_orientation(width: float, height: float) -> ImageOrientation:
    """Return an orientation while treating effectively square sizes safely."""

    if width <= 0 or height <= 0:
        raise ValueError("Image dimensions must be positive")
    if isclose(width, height):
        return ImageOrientation.SQUARE
    return ImageOrientation.LANDSCAPE if width > height else ImageOrientation.PORTRAIT


def needs_layout_rotation(
    source_width: float,
    source_height: float,
    target_width: float,
    target_height: float,
) -> bool:
    """Whether a quarter turn is needed to match source and target orientation."""

    source = image_orientation(source_width, source_height)
    target = image_orientation(target_width, target_height)
    return (
        source is not ImageOrientation.SQUARE
        and target is not ImageOrientation.SQUARE
        and source is not target
    )


@dataclass(frozen=True)
class LoadedPhoto:
    """The shared, EXIF-corrected and target-normalized in-memory image."""

    path: Path
    width: int
    height: int
    image: QImage
    layout_rotation_degrees: int = 0

    @property
    def summary(self) -> str:
        return f"{self.path.name}  ·  {self.width} × {self.height} px"


def load_photo(path: str | Path, target_size: PhotoSize = PHOTO_11X14) -> LoadedPhoto:
    """Create the normalized working image without writing to the source path.

    EXIF orientation is applied exactly once. A deterministic clockwise quarter
    turn is then applied only when the corrected source and target orientations
    differ. Square sources or targets never trigger a layout rotation.
    """

    source_path = Path(path)
    try:
        with Image.open(source_path) as opened:
            oriented = ImageOps.exif_transpose(opened)
            target = target_size.size_mm
            rotate_for_layout = needs_layout_rotation(
                oriented.width, oriented.height, target.width, target.height
            )
            if rotate_for_layout:
                oriented = oriented.transpose(Image.Transpose.ROTATE_270)
            rgba = oriented.convert("RGBA")
            width, height = rgba.size
            raw = rgba.tobytes("raw", "RGBA")
    except (OSError, ValueError, UnidentifiedImageError) as exc:
        raise ImageLoadError(f"Could not open this image: {exc}") from exc

    # copy() detaches QImage from the temporary Python bytes buffer.
    image = QImage(raw, width, height, width * 4, QImage.Format.Format_RGBA8888).copy()
    if image.isNull():
        raise ImageLoadError("Could not convert this image for display")
    return LoadedPhoto(
        source_path,
        width,
        height,
        image,
        layout_rotation_degrees=90 if rotate_for_layout else 0,
    )
