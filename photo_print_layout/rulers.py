"""Qt-free ruler geometry for the preview: ticks, labels, and the photo band.

All physical positions are millimetres from the paper's top-left corner. Label
placement works on one screen axis in pixels so the widget only has to draw.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import Callable, Sequence

from .layout import PhysicalLayout
from .models import Unit, format_physical_value, from_millimetres, to_millimetres


# (major, minor) tick spacing in display units.
RULER_STEPS = {
    Unit.INCHES: (1.0, 0.5),
    Unit.CENTIMETRES: (1.0, 0.5),
    Unit.MILLIMETRES: (10.0, 5.0),
}
# Label every Nth major tick when labels would otherwise crowd.
LABEL_STRIDES = (1, 2, 5, 10, 20, 50)
_EPSILON = 1e-9
# Band labels within this many pixels of the paper end count as the same position.
_SAME_POSITION_PX = 0.5


@dataclass(frozen=True)
class Tick:
    position_mm: float
    is_major: bool
    label: str | None


@dataclass(frozen=True)
class RulerBand:
    """The photo-size box's extent along one ruler."""

    start_mm: float
    end_mm: float
    label: str


@dataclass(frozen=True)
class AxisLabel:
    """A label occupying [start, end] pixels along one ruler axis."""

    text: str
    start: float
    end: float
    kind: str  # "tick", "paper" or "band"


def format_length(length_mm: float, unit: Unit) -> str:
    """Format a physical length with its unit, e.g. ``16.54 in``."""

    return f"{format_physical_value(from_millimetres(length_mm, unit), unit)} {unit.value}"


def major_step_mm(unit: Unit) -> float:
    return to_millimetres(RULER_STEPS[unit][0], unit)


def ruler_ticks(length_mm: float, unit: Unit, label_stride: int = 1) -> list[Tick]:
    """Return ticks from 0 to the paper length; only every Nth major tick is labelled."""

    if length_mm <= 0:
        raise ValueError("Ruler length must be positive")
    if label_stride < 1:
        raise ValueError("Label stride must be at least 1")
    major, minor = RULER_STEPS[unit]
    minors_per_major = round(major / minor)
    count = floor(from_millimetres(length_mm, unit) / minor + _EPSILON)
    ticks = []
    for index in range(count + 1):
        value = index * minor
        is_major = index % minors_per_major == 0
        labelled = is_major and (index // minors_per_major) % label_stride == 0
        ticks.append(
            Tick(
                to_millimetres(value, unit),
                is_major,
                format_physical_value(value, unit) if labelled else None,
            )
        )
    return ticks


def label_stride_for(major_spacing_px: float, min_label_spacing_px: float) -> int:
    """Return the smallest stride that keeps labelled ticks far enough apart."""

    for stride in LABEL_STRIDES:
        if major_spacing_px * stride >= min_label_spacing_px:
            return stride
    return LABEL_STRIDES[-1]


def photo_bands(layout: PhysicalLayout, unit: Unit) -> tuple[RulerBand, RulerBand]:
    """Return (horizontal, vertical) bands for the photo-size box, not the fitted image."""

    target = layout.target
    return (
        RulerBand(target.x, target.x + target.width, format_length(target.width, unit)),
        RulerBand(target.y, target.y + target.height, format_length(target.height, unit)),
    )


def layout_axis_labels(
    ticks: Sequence[tuple[float, str]],
    paper_end: float,
    paper_label: str,
    band: tuple[float, str] | None,
    extent: Callable[[str], float],
    gap: float,
) -> list[AxisLabel]:
    """Place labels along one axis without overlaps.

    Priority: paper length (end-aligned at the paper end), then the photo band
    label (end-aligned at the band end, nudged clear of the paper label), then tick
    labels (centred on their tick), which are dropped where they would collide.
    """

    placed: list[AxisLabel] = []

    def collides(start: float, end: float) -> bool:
        return any(start < label.end + gap and end + gap > label.start for label in placed)

    paper_size = extent(paper_label)
    paper = AxisLabel(paper_label, paper_end - paper_size, paper_end, "paper")
    if band is not None:
        band_end, band_text = band
        band_size = extent(band_text)
        if abs(band_end - paper_end) <= _SAME_POSITION_PX and band_text == paper_label:
            # The photo spans the full paper length: one band label states both.
            placed.append(AxisLabel(band_text, paper_end - band_size, paper_end, "band"))
        else:
            placed.append(paper)
            end = min(band_end, paper.start - gap)
            placed.append(AxisLabel(band_text, end - band_size, end, "band"))
    else:
        placed.append(paper)

    for position, text in ticks:
        size = extent(text)
        start, end = position - size / 2.0, position + size / 2.0
        if not collides(start, end):
            placed.append(AxisLabel(text, start, end, "tick"))
    return placed
