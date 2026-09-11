"""Device-independent normalized crop-frame state and geometry."""

from __future__ import annotations

from dataclasses import dataclass


MIN_CROP_FRACTION = 0.05


@dataclass(frozen=True)
class SourceRect:
    """A rectangle in working-image pixels."""

    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class CropState:
    """A crop rectangle normalized to the working image's width and height."""

    x: float = 0.0
    y: float = 0.0
    width: float = 1.0
    height: float = 1.0


def _maximum_crop_size(
    source_width: float,
    source_height: float,
    target_width: float,
    target_height: float,
) -> tuple[float, float]:
    target_aspect = target_width / target_height
    source_aspect = source_width / source_height
    if source_aspect > target_aspect:
        return target_aspect / source_aspect, 1.0
    return 1.0, source_aspect / target_aspect


def default_crop_state(
    source_width: float,
    source_height: float,
    target_width: float,
    target_height: float,
) -> CropState:
    """Return the largest centered crop with the requested physical ratio."""

    if min(source_width, source_height, target_width, target_height) <= 0:
        raise ValueError("Source and target dimensions must be positive")
    width, height = _maximum_crop_size(
        source_width, source_height, target_width, target_height
    )
    return CropState((1.0 - width) / 2.0, (1.0 - height) / 2.0, width, height)


def constrained_crop_state(
    state: CropState,
    source_width: float,
    source_height: float,
    target_width: float,
    target_height: float,
) -> CropState:
    """Clamp a crop to positive, fixed-ratio bounds within the source image."""

    if min(source_width, source_height, target_width, target_height) <= 0:
        raise ValueError("Source and target dimensions must be positive")
    max_width, max_height = _maximum_crop_size(
        source_width, source_height, target_width, target_height
    )
    width = min(max_width, max(MIN_CROP_FRACTION * max_width, state.width))
    normalized_ratio = (target_width / target_height) / (source_width / source_height)
    height = width / normalized_ratio
    if height > max_height:
        height = max_height
        width = height * normalized_ratio

    center_x = state.x + state.width / 2.0
    center_y = state.y + state.height / 2.0
    center_x = min(1.0 - width / 2.0, max(width / 2.0, center_x))
    center_y = min(1.0 - height / 2.0, max(height / 2.0, center_y))
    return CropState(center_x - width / 2.0, center_y - height / 2.0, width, height)


def crop_source_rect(
    state: CropState,
    source_width: float,
    source_height: float,
    target_width: float,
    target_height: float,
) -> SourceRect:
    """Resolve logical crop state into an exact source-pixel rectangle."""

    crop = constrained_crop_state(
        state, source_width, source_height, target_width, target_height
    )
    return SourceRect(
        crop.x * source_width,
        crop.y * source_height,
        crop.width * source_width,
        crop.height * source_height,
    )


def move_crop_state(
    state: CropState,
    delta_x: float,
    delta_y: float,
    source_width: float,
    source_height: float,
    target_width: float,
    target_height: float,
) -> CropState:
    """Move a crop by normalized source fractions, clamped to image bounds."""

    moved = CropState(state.x + delta_x, state.y + delta_y, state.width, state.height)
    return constrained_crop_state(
        moved, source_width, source_height, target_width, target_height
    )


def resize_crop_state(
    state: CropState,
    width: float,
    anchor_x: float,
    anchor_y: float,
    horizontal_direction: int,
    vertical_direction: int,
    source_width: float,
    source_height: float,
    target_width: float,
    target_height: float,
) -> CropState:
    """Resize from a corner while preserving ratio and its opposite anchor."""

    del state
    normalized_ratio = (target_width / target_height) / (source_width / source_height)
    height = width / normalized_ratio
    x = anchor_x if horizontal_direction > 0 else anchor_x - width
    y = anchor_y if vertical_direction > 0 else anchor_y - height
    return constrained_crop_state(
        CropState(x, y, width, height),
        source_width,
        source_height,
        target_width,
        target_height,
    )
