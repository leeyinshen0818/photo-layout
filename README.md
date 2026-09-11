# Photo Print Layout Manager

A focused Windows desktop utility for laying out a single photo on Standard A3 or A3+ paper. Phase 3 adds editable physical photo dimensions with inch, centimetre, and millimetre input while keeping one millimetre-based geometry model.

## Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

Use **Open Photo…** (or `Ctrl+O`) to choose a JPG, JPEG, PNG, or TIFF file. Loading is read-only; the original file is never written or changed.

The window starts maximized (with the normal Windows title bar). Before loading, the target defaults to 11×14 inches. A newly loaded portrait image starts at 11×14 and a landscape image at 14×11. Afterward, the entered width and height determine target and paper orientation; square targets consistently use portrait paper.

Enter custom width and height directly and select `in`, `cm`, or `mm`. Changing units preserves the exact physical size. The app validates the requested size against the selected paper, reports oversized targets in the preview, and prevents invalid crop or output operations.

**Fit Inside** is the safe default. Select **Crop to Size** after opening a photo to enable and highlight **Crop / Adjust…**. In the crop editor, drag inside the frame to move it, drag a blue corner to resize it, and drag in the dimmed image area (or right-drag) to reposition the image. The frame always follows the current custom width-to-height ratio.

**Clear** removes only the loaded photo and its crop. **Output JPEG…** writes the complete white paper canvas at 300 DPI through a Save As dialog. Output uses the original in-memory image and shared physical layout geometry rather than the preview resolution.

## Test

```powershell
python -m unittest discover -s tests -v
```

## Structure

- `photo_print_layout/models.py` — millimetre-based paper/photo settings and unit conversion
- `photo_print_layout/layout.py` — device-independent millimetre geometry and crop calculations
- `photo_print_layout/crop.py` — normalized crop rectangle, fixed-ratio resize, movement, and constraints
- `photo_print_layout/crop_dialog.py` — modal crop editor and fixed-ratio editing canvas
- `photo_print_layout/exporter.py` — full-paper 300 DPI rendering and JPEG encoding
- `photo_print_layout/image_loader.py` — Pillow loading and EXIF correction while retaining natural image orientation
- `photo_print_layout/preview.py` — rendering of the physical model into a widget
- `photo_print_layout/main_window.py` — controls and application workflow
- `photo_print_layout/app.py` / `main.py` — startup

Printer integration, calibration, custom sizes, PNG/PDF output, and batch workflows remain intentionally out of scope.
