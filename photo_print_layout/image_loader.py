"""Non-destructive image loading with EXIF orientation correction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from PySide6.QtGui import QImage

from .models import Orientation, orientation_for_dimensions


SUPPORTED_FILE_FILTER = "Photos (*.jpg *.jpeg *.png *.tif *.tiff)"


class ImageLoadError(Exception):
    pass


ImageOrientation = Orientation


def image_orientation(width: float, height: float) -> ImageOrientation:
    """Return the EXIF-corrected image orientation."""

    return orientation_for_dimensions(width, height)


@dataclass(frozen=True)
class LoadedPhoto:
    """The shared, EXIF-corrected in-memory image in its natural orientation."""

    path: Path
    width: int
    height: int
    image: QImage
    layout_rotation_degrees: int = 0

    @property
    def summary(self) -> str:
        return f"{self.path.name}  ·  {self.width} × {self.height} px"


def load_photo(path: str | Path) -> LoadedPhoto:
    """Create the EXIF-corrected working image without changing its orientation."""

    source_path = Path(path)
    try:
        with Image.open(source_path) as opened:
            oriented = ImageOps.exif_transpose(opened)
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
        layout_rotation_degrees=0,
    )
