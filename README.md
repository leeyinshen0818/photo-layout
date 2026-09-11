# Photo Print Layout Manager

A focused Windows desktop utility for previewing a single 11 × 14 inch photo on Standard A3 or A3+ paper. Phase 1.1 includes image loading, EXIF orientation, automatic source-to-target orientation normalization, crop/fit behaviour, physical layout calculations, and a live preview.

## Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

Use **Open Photo…** (or `Ctrl+O`) to choose a JPG, JPEG, PNG, or TIFF file. Loading is read-only; the original file is never written or changed.

The window starts maximized (with the normal Windows title bar). After EXIF correction, an in-memory source whose portrait/landscape orientation differs from the target is rotated 90° clockwise. Square sources or targets are left unchanged.

## Test

```powershell
python -m unittest discover -s tests -v
```

## Structure

- `photo_print_layout/models.py` — paper/photo definitions and settings
- `photo_print_layout/layout.py` — device-independent millimetre geometry and crop calculations
- `photo_print_layout/image_loader.py` — Pillow loading, EXIF correction, and shared working-image orientation normalization
- `photo_print_layout/preview.py` — rendering of the physical model into a widget
- `photo_print_layout/main_window.py` — controls and application workflow
- `photo_print_layout/app.py` / `main.py` — startup

Interactive crop adjustment, printing, calibration, custom sizes, and batch workflows are intentionally outside Phase 1.
