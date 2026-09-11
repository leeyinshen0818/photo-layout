# Photo Print Layout Manager

A focused Windows desktop utility for laying out a single photo on Standard A3 or A3+ paper. Phase 5 adds a shared responsive UI scale and polished controls while retaining the Phase 4 print-accurate render pipeline.

## Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

Use **Open Photo…** (or `Ctrl+O`) to choose a JPG, JPEG, PNG, or TIFF file. Loading is read-only; the original file is never written or changed.

The window starts maximized (with the normal Windows title bar). Before loading, the target defaults to 11×14 inches. A newly loaded portrait image starts at 11×14 and a landscape image at 14×11. Afterward, the entered width and height determine target and paper orientation; square targets consistently use portrait paper.

Enter custom width and height directly and select `in`, `cm`, or `mm`. Changing units preserves the exact physical size. The current paper maximum is displayed below the fields and follows the target orientation and selected unit. Standard A3 uses its true `297 × 420 mm` dimensions; this application's A3+ workflow uses exactly `13 × 19 in` (`330.2 × 482.6 mm`). Oversized targets are reported in the preview and cannot be cropped or exported.

**Fit Inside** is the safe default. Select **Crop to Size** after opening a photo to enable and highlight **Crop / Adjust…**. In the crop editor, drag inside the frame to move it, drag a blue corner to resize it, and drag in the dimmed image area (or right-drag) to reposition the image. The frame always follows the current custom width-to-height ratio.

**Clear** removes only the loaded photo and its crop. **Output JPEG…** becomes a highlighted primary action only while a photo and valid layout are available. It writes the complete white paper canvas at 300 DPI through a Save As dialog, with 300 DPI metadata and JPEG quality 95.

Preview and output both use the same millimetre-based render plan and Pillow LANCZOS compositor. Crop mode maps the confirmed normalized crop back to the full EXIF-corrected source, then resizes it to the exact target pixels. Fit mode keeps the whole source and centers it inside the physical target rectangle, leaving true white space where aspect ratios differ. The preview uses the same plan at a smaller canvas size and caches unchanged results.

The interface keeps one stable sidebar-and-preview layout across common Windows resolutions. Qt handles native 100%, 125%, and 150% display scaling, while `ui_scale.py` adjusts logical spacing, typography, control heights, sidebar width, crop-editor sizing, and preview margins from the active screen's available logical geometry. The scale is bounded so small screens remain usable and large screens keep the preview dominant. Moving between monitors reapplies these metrics without changing photo-layout state or normal-window geometry.

## Test

```powershell
python -m unittest discover -s tests -v
```

## Structure

- `photo_print_layout/models.py` — millimetre-based paper/photo settings and unit conversion
- `photo_print_layout/layout.py` — device-independent millimetre geometry and crop calculations
- `photo_print_layout/render_engine.py` — authoritative physical-to-pixel plan and Pillow compositor
- `photo_print_layout/ui_scale.py` — shared responsive layout and sizing metrics
- `photo_print_layout/crop.py` — normalized crop rectangle, fixed-ratio resize, movement, and constraints
- `photo_print_layout/crop_dialog.py` — modal crop editor and fixed-ratio editing canvas
- `photo_print_layout/exporter.py` — JPEG path handling and final-canvas encoding
- `photo_print_layout/image_loader.py` — Pillow loading and EXIF correction while retaining natural image orientation
- `photo_print_layout/preview.py` — cached display-sized rendering through the shared engine
- `photo_print_layout/main_window.py` — controls and application workflow
- `photo_print_layout/assets/chevron-down.svg` — scalable combo-box indicator
- `photo_print_layout/app.py` / `main.py` — startup

Printer integration, printable-margin calibration, PNG/PDF output, multiple photos, and batch workflows remain intentionally out of scope.
