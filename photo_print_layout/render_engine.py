"""Authoritative physical-to-raster rendering for preview and final output."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image
from PySide6.QtGui import QImage

from .crop import CropState, SourceRect
from .image_loader import LoadedPhoto
from .layout import PhysicalLayout, calculate_layout
from .models import MM_PER_INCH, LayoutSettings, RectMM


@dataclass(frozen=True)
class PixelRect:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class RenderPlan:
    """A physical layout resolved to one raster canvas."""

    layout: PhysicalLayout
    canvas_width: int
    canvas_height: int
    target: PixelRect
    image: PixelRect | None
    source: SourceRect | None
    dpi: int | None


def pixels_for_mm(length_mm: float, dpi: int) -> int:
    """Convert a physical length to pixels using the application's one formula."""

    if length_mm <= 0 or dpi <= 0:
        raise ValueError("Physical length and DPI must be positive")
    return round(length_mm / MM_PER_INCH * dpi)


def paper_pixel_size(settings: LayoutSettings) -> tuple[int, int]:
    paper = settings.paper_size_mm
    return pixels_for_mm(paper.width, settings.dpi), pixels_for_mm(
        paper.height, settings.dpi
    )


def _scaled_rect(rect: RectMM, layout: PhysicalLayout, width: int, height: int) -> PixelRect:
    return PixelRect(
        round(rect.x / layout.paper.width * width),
        round(rect.y / layout.paper.height * height),
        max(1, round(rect.width / layout.paper.width * width)),
        max(1, round(rect.height / layout.paper.height * height)),
    )


def _final_rect(rect: RectMM, dpi: int) -> PixelRect:
    # Convert each physical measurement directly so custom target dimensions are exact.
    return PixelRect(
        round(rect.x / MM_PER_INCH * dpi),
        round(rect.y / MM_PER_INCH * dpi),
        pixels_for_mm(rect.width, dpi),
        pixels_for_mm(rect.height, dpi),
    )


def build_render_plan(
    settings: LayoutSettings,
    source_width: int,
    source_height: int,
    crop_state: CropState,
    *,
    canvas_size: tuple[int, int] | None = None,
) -> RenderPlan:
    """Resolve app state to final or display raster geometry.

    Omitting ``canvas_size`` creates the true-DPI final plan. Passing a canvas
    size creates a proportional preview plan from the same physical layout.
    """

    if source_width < 1 or source_height < 1:
        raise ValueError("Source dimensions must be positive")
    layout = calculate_layout(settings, source_width, source_height, crop_state)
    if canvas_size is None:
        width, height = paper_pixel_size(settings)
        convert = lambda rect: _final_rect(rect, settings.dpi)
        dpi: int | None = settings.dpi
    else:
        width, height = canvas_size
        if width < 1 or height < 1:
            raise ValueError("Canvas dimensions must be positive")
        convert = lambda rect: _scaled_rect(rect, layout, width, height)
        dpi = None

    return RenderPlan(
        layout=layout,
        canvas_width=width,
        canvas_height=height,
        target=convert(layout.target),
        image=convert(layout.image) if layout.image else None,
        source=layout.source,
        dpi=dpi,
    )


def qimage_to_pillow(image: QImage) -> Image.Image:
    """Copy a QImage into Pillow only for the duration of a render."""

    converted = image.convertToFormat(QImage.Format.Format_RGBA8888)
    data = bytes(converted.constBits())
    return Image.frombytes(
        "RGBA",
        (converted.width(), converted.height()),
        data,
        "raw",
        "RGBA",
        converted.bytesPerLine(),
        1,
    )


def pillow_to_qimage(image: Image.Image, dpi: int | None = None) -> QImage:
    """Create a detached QImage for Qt display and compatibility callers."""

    rgb = image.convert("RGB")
    raw = rgb.tobytes("raw", "RGB")
    result = QImage(
        raw,
        rgb.width,
        rgb.height,
        rgb.width * 3,
        QImage.Format.Format_RGB888,
    ).copy()
    if dpi:
        dots_per_meter = round(dpi / 0.0254)
        result.setDotsPerMeterX(dots_per_meter)
        result.setDotsPerMeterY(dots_per_meter)
    return result


def render_plan(photo: LoadedPhoto, plan: RenderPlan) -> Image.Image:
    """Composite a plan on white paper with one high-quality source resample."""

    if plan.image is None or plan.source is None:
        raise ValueError("A render plan requires image and source geometry")

    canvas = Image.new("RGB", (plan.canvas_width, plan.canvas_height), "white")
    destination = plan.image
    source = plan.source
    source_image = qimage_to_pillow(photo.image)
    if (
        source.x == 0.0
        and source.y == 0.0
        and source.width == photo.width
        and source.height == photo.height
    ):
        # Fit Inside uses the full source, so avoid allocating a redundant crop buffer.
        source_region = source_image
    else:
        source_region = source_image.crop(
            (source.x, source.y, source.x + source.width, source.y + source.height)
        )
    resized = source_region.resize(
        (destination.width, destination.height), Image.Resampling.LANCZOS
    )
    if resized.mode == "RGBA":
        canvas.paste(resized, (destination.x, destination.y), resized)
    else:
        canvas.paste(resized, (destination.x, destination.y))
    return canvas


def render_final_image(
    photo: LoadedPhoto, settings: LayoutSettings, crop_state: CropState
) -> tuple[Image.Image, RenderPlan]:
    plan = build_render_plan(settings, photo.width, photo.height, crop_state)
    return render_plan(photo, plan), plan


def render_preview_image(
    photo: LoadedPhoto,
    settings: LayoutSettings,
    crop_state: CropState,
    canvas_size: tuple[int, int],
) -> tuple[Image.Image, RenderPlan]:
    plan = build_render_plan(
        settings,
        photo.width,
        photo.height,
        crop_state,
        canvas_size=canvas_size,
    )
    return render_plan(photo, plan), plan
