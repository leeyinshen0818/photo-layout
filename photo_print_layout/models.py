"""Physical layout definitions and application state."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


MM_PER_INCH = 25.4


@dataclass(frozen=True)
class SizeMM:
    width: float
    height: float

    def for_orientation(self, orientation: "Orientation") -> "SizeMM":
        """Return this portrait-defined size in the requested layout orientation."""

        short, long = sorted((self.width, self.height))
        if orientation is Orientation.LANDSCAPE:
            return SizeMM(long, short)
        return SizeMM(short, long)


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


class Position(Enum):
    LEFT_TOP = "Left Top"
    CENTER = "Center"


class ResizeMode(Enum):
    FIT = "Fit Inside"
    CROP = "Crop to Size"


class Orientation(Enum):
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"
    SQUARE = "square"


class Unit(Enum):
    INCHES = "in"
    CENTIMETRES = "cm"
    MILLIMETRES = "mm"


def to_millimetres(value: float, unit: Unit) -> float:
    if unit is Unit.INCHES:
        return round(value * MM_PER_INCH, 10)
    if unit is Unit.CENTIMETRES:
        return round(value * 10.0, 10)
    return round(value, 10)


def from_millimetres(value_mm: float, unit: Unit) -> float:
    if unit is Unit.INCHES:
        return round(value_mm / MM_PER_INCH, 10)
    if unit is Unit.CENTIMETRES:
        return round(value_mm / 10.0, 10)
    return round(value_mm, 10)


def orientation_for_dimensions(width: float, height: float) -> Orientation:
    if width <= 0 or height <= 0:
        raise ValueError("Dimensions must be positive")
    if width == height:
        return Orientation.SQUARE
    return Orientation.LANDSCAPE if width > height else Orientation.PORTRAIT


def layout_orientation_for_dimensions(width: float, height: float) -> Orientation:
    """Map image dimensions to a paper orientation; square safely uses portrait."""

    orientation = orientation_for_dimensions(width, height)
    return Orientation.PORTRAIT if orientation is Orientation.SQUARE else orientation


STANDARD_A3 = PaperSize("a3", "Standard A3", SizeMM(297.0, 420.0))
SUPER_A3 = PaperSize("a3_plus", "A3+ / Super A3", SizeMM(329.0, 483.0))
PAPER_SIZES = (STANDARD_A3, SUPER_A3)

DEFAULT_PHOTO_SIZE_MM = SizeMM(279.4, 355.6)


@dataclass(frozen=True)
class LayoutSettings:
    paper: PaperSize = STANDARD_A3
    photo_size_mm: SizeMM = DEFAULT_PHOTO_SIZE_MM
    position: Position = Position.LEFT_TOP
    resize_mode: ResizeMode = ResizeMode.FIT
    dpi: int = 300

    @property
    def target_orientation(self) -> Orientation:
        return orientation_for_dimensions(self.photo_size_mm.width, self.photo_size_mm.height)

    @property
    def layout_orientation(self) -> Orientation:
        orientation = self.target_orientation
        return Orientation.PORTRAIT if orientation is Orientation.SQUARE else orientation

    @property
    def paper_size_mm(self) -> SizeMM:
        return self.paper.size_mm.for_orientation(self.layout_orientation)
