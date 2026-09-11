"""Layout calculations expressed in physical millimetres.

No widget dimensions belong here. Both a preview renderer and a future printer
renderer can scale the resulting rectangles into their own coordinate systems.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import LayoutSettings, Position, RectMM, ResizeMode


@dataclass(frozen=True)
class SourceRect:
    """A rectangle in source-image pixels."""

    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class PhysicalLayout:
    paper: RectMM
    target: RectMM
    image: RectMM | None
    source: SourceRect | None


def calculate_layout(
    settings: LayoutSettings,
    source_width: int | None = None,
    source_height: int | None = None,
) -> PhysicalLayout:
    """Calculate paper, target, image, and crop geometry in physical units."""

    paper_size = settings.paper.size_mm
    target_size = settings.photo_size.size_mm
    if target_size.width > paper_size.width or target_size.height > paper_size.height:
        raise ValueError("The selected photo size does not fit on the selected paper")

    if settings.position is Position.LEFT_TOP:
        target_x = target_y = 0.0
    else:
        target_x = (paper_size.width - target_size.width) / 2.0
        target_y = (paper_size.height - target_size.height) / 2.0

    paper = RectMM(0.0, 0.0, paper_size.width, paper_size.height)
    target = RectMM(target_x, target_y, target_size.width, target_size.height)

    if not source_width or not source_height or source_width < 1 or source_height < 1:
        return PhysicalLayout(paper, target, None, None)

    source_aspect = source_width / source_height
    target_aspect = target.width / target.height

    if settings.resize_mode is ResizeMode.CROP:
        if source_aspect > target_aspect:
            crop_height = float(source_height)
            crop_width = crop_height * target_aspect
            crop_x = (source_width - crop_width) / 2.0
            crop_y = 0.0
        else:
            crop_width = float(source_width)
            crop_height = crop_width / target_aspect
            crop_x = 0.0
            crop_y = (source_height - crop_height) / 2.0
        source = SourceRect(crop_x, crop_y, crop_width, crop_height)
        image = target
    else:
        source = SourceRect(0.0, 0.0, float(source_width), float(source_height))
        if source_aspect > target_aspect:
            image_width = target.width
            image_height = image_width / source_aspect
        else:
            image_height = target.height
            image_width = image_height * source_aspect
        image = RectMM(
            target.x + (target.width - image_width) / 2.0,
            target.y + (target.height - image_height) / 2.0,
            image_width,
            image_height,
        )

    return PhysicalLayout(paper, target, image, source)

