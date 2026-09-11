"""Device-independent crop composition state and geometry."""

from __future__ import annotations

from dataclasses import dataclass


MIN_ZOOM = 1.0
MAX_ZOOM = 4.0


@dataclass(frozen=True)
class SourceRect:
    """A rectangle in normalized working-image pixels."""

    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class CropState:
    """A reusable crop composition independent of display pixel dimensions.

    ``zoom`` is relative to the minimum scale that covers the target. The
    normalized center is expressed within the working image, from 0 to 1.
    """

    zoom: float = MIN_ZOOM
    center_x: float = 0.5
    center_y: float = 0.5


def crop_source_rect(
    state: CropState,
    source_width: float,
    source_height: float,
    target_width: float,
    target_height: float,
) -> SourceRect:
    """Resolve a logical crop state into a constrained source-pixel rectangle."""

    if min(source_width, source_height, target_width, target_height) <= 0:
        raise ValueError("Source and target dimensions must be positive")

    target_aspect = target_width / target_height
    source_aspect = source_width / source_height
    if source_aspect > target_aspect:
        cover_width = source_height * target_aspect
        cover_height = source_height
    else:
        cover_width = source_width
        cover_height = source_width / target_aspect

    zoom = min(MAX_ZOOM, max(MIN_ZOOM, state.zoom))
    width = cover_width / zoom
    height = cover_height / zoom
    half_x = width / (2.0 * source_width)
    half_y = height / (2.0 * source_height)
    center_x = min(1.0 - half_x, max(half_x, state.center_x))
    center_y = min(1.0 - half_y, max(half_y, state.center_y))
    return SourceRect(
        center_x * source_width - width / 2.0,
        center_y * source_height - height / 2.0,
        width,
        height,
    )


def constrained_crop_state(
    state: CropState,
    source_width: float,
    source_height: float,
    target_width: float,
    target_height: float,
) -> CropState:
    """Clamp zoom and center so the crop is always fully covered."""

    rect = crop_source_rect(state, source_width, source_height, target_width, target_height)
    return CropState(
        zoom=min(MAX_ZOOM, max(MIN_ZOOM, state.zoom)),
        center_x=(rect.x + rect.width / 2.0) / source_width,
        center_y=(rect.y + rect.height / 2.0) / source_height,
    )


def pan_crop_state(
    state: CropState,
    drag_fraction_x: float,
    drag_fraction_y: float,
    source_width: float,
    source_height: float,
    target_width: float,
    target_height: float,
) -> CropState:
    """Move the image by crop-frame fractions and return a constrained state."""

    rect = crop_source_rect(state, source_width, source_height, target_width, target_height)
    moved = CropState(
        zoom=state.zoom,
        center_x=state.center_x - drag_fraction_x * rect.width / source_width,
        center_y=state.center_y - drag_fraction_y * rect.height / source_height,
    )
    return constrained_crop_state(
        moved, source_width, source_height, target_width, target_height
    )
