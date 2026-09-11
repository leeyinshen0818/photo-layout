"""Non-destructive image loading with EXIF orientation support."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from PySide6.QtGui import QImage


SUPPORTED_FILE_FILTER = "Photos (*.jpg *.jpeg *.png *.tif *.tiff)"


class ImageLoadError(Exception):
    pass


@dataclass(frozen=True)
class LoadedPhoto:
    path: Path
    width: int
    height: int
    image: QImage

    @property
    def summary(self) -> str:
        return f"{self.path.name}  ·  {self.width} × {self.height} px"


def load_photo(path: str | Path) -> LoadedPhoto:
    """Read a source image into memory without writing to the source path."""

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
    return LoadedPhoto(source_path, width, height, image)

