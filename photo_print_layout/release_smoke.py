"""Functional smoke test executed from inside a packaged release binary."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from PIL import Image

from .crop_dialog import CropEditorDialog
from .exporter import export_jpeg
from .image_loader import load_photo
from .main_window import MainWindow
from .models import ResizeMode
from .ui_scale import UiMetrics


def run_release_smoke_test() -> int:
    """Exercise bundled loading, crop preview, assets, and 300-DPI export."""

    try:
        asset = Path(__file__).with_name("assets") / "chevron-down.svg"
        if not asset.is_file():
            raise RuntimeError("Bundled combo-box asset is missing")

        with tempfile.TemporaryDirectory(prefix="photo-layout-release-") as directory:
            temp_dir = Path(directory)
            source = temp_dir / "source.png"
            Image.new("RGB", (80, 120), "#2b67d1").save(source)
            source_hash = hashlib.sha256(source.read_bytes()).digest()
            photo = load_photo(source)

            window = MainWindow(UiMetrics(1.0))
            window.set_photo(photo)
            crop_index = window.resize_combo.findData(ResizeMode.CROP)
            window.resize_combo.setCurrentIndex(crop_index)
            preview, plan = window.preview._rendered_page(240, 340)
            if preview.isNull() or plan.source is None:
                raise RuntimeError("Crop preview did not render")

            dialog = CropEditorDialog(
                photo,
                window._settings.photo_size_mm,
                window._effective_crop_state(),
                window,
            )
            dialog.reset_crop()
            if dialog.crop_state.width <= 0 or dialog.crop_state.height <= 0:
                raise RuntimeError("Crop editor state is invalid")
            dialog.close()

            output = export_jpeg(
                temp_dir / "release-smoke.jpg",
                photo,
                window._settings,
                window._effective_crop_state(),
            )
            with Image.open(output) as rendered:
                if rendered.format != "JPEG" or rendered.size != (3508, 4961):
                    raise RuntimeError("Packaged JPEG dimensions are incorrect")
                dpi = rendered.info.get("dpi", (0, 0))
                if abs(dpi[0] - 300) > 1 or abs(dpi[1] - 300) > 1:
                    raise RuntimeError("Packaged JPEG DPI metadata is incorrect")

            window.close()
            if hashlib.sha256(source.read_bytes()).digest() != source_hash:
                raise RuntimeError("Release smoke test modified its source image")
        return 0
    except Exception:
        return 1
