"""Layout calculations expressed in physical millimetres.

No widget dimensions belong here. Both a preview renderer and a future printer
renderer can scale the resulting rectangles into their own coordinate systems.
"""

from __future__ import annotations

from dataclasses import dataclass

from .crop import CropState, SourceRect, crop_source_rect
from .models import LayoutSettings, Position, RectMM, ResizeMode

@dataclass(frozen=True)
class PhysicalLayout:
    paper: RectMM
    target: RectMM
    image: RectMM | None
    source: SourceRect | None


def photo_fits_on_paper(settings: LayoutSettings) -> bool:
    paper = settings.paper_size_mm
    photo = settings.photo_size_mm
    return photo.width <= paper.width and photo.height <= paper.height


def calculate_layout(
    settings: LayoutSettings,
    source_width: int | None = None,
    source_height: int | None = None,
    crop_state: CropState | None = None,
) -> PhysicalLayout:
    """Calculate paper, target, image, and crop geometry in physical units."""

    paper_size = settings.paper_size_mm
    target_size = settings.photo_size_mm
    if not photo_fits_on_paper(settings):
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
        source = crop_source_rect(
            crop_state or CropState(),
            source_width,
            source_height,
            target.width,
            target.height,
        )
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
