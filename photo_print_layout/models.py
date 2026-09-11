"""Physical layout definitions and application state."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


MM_PER_INCH = 25.4


@dataclass(frozen=True)
class SizeMM:
    width: float
    height: float


@dataclass(frozen=True)
class RectMM:
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class PaperSize:
    key: str
    label: str
    size_mm: SizeMM


@dataclass(frozen=True)
class PhotoSize:
    key: str
    label: str
    width_inches: float
    height_inches: float

    @property
    def size_mm(self) -> SizeMM:
        return SizeMM(self.width_inches * MM_PER_INCH, self.height_inches * MM_PER_INCH)


class Position(Enum):
    LEFT_TOP = "Left Top"
    CENTER = "Center"


class ResizeMode(Enum):
    CROP = "Crop to Size"
    FIT = "Fit Inside"


STANDARD_A3 = PaperSize("a3", "Standard A3", SizeMM(297.0, 420.0))
SUPER_A3 = PaperSize("a3_plus", "A3+ / Super A3", SizeMM(329.0, 483.0))
PAPER_SIZES = (STANDARD_A3, SUPER_A3)

PHOTO_11X14 = PhotoSize("11x14", "11 × 14 inches", 11.0, 14.0)
PHOTO_SIZES = (PHOTO_11X14,)


@dataclass(frozen=True)
class LayoutSettings:
    paper: PaperSize = STANDARD_A3
    photo_size: PhotoSize = PHOTO_11X14
    position: Position = Position.LEFT_TOP
    resize_mode: ResizeMode = ResizeMode.CROP
    dpi: int = 300

