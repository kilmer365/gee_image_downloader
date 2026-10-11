# Changelog

## 0.17.0

- New vegetation indices next to NDVI: **GNDVI**, **NDRE**, **MSAVI2** and **NDWI** (the set described by Auravant). Each is saved as a Float32 GeoTIFF (nodata -9999) with its own colour ramp, tooltips explain how to read each one. NDRE needs the red-edge band, so it is only produced from Sentinel-2 (skipped, with a note in the log, for Landsat images).
- MapBiomas layers now open with the **official MapBiomas legend** (Collection 10 colours and class names, in Portuguese or English following the QGIS language), listing only the classes present in your area. The style is also saved as a `.qml` next to the GeoTIFF, so it is kept when you reopen the file.

## 0.16.0

- New toolbar "GEE Image Downloader" with a simplified icon that stays legible at small sizes (the Raster toolbar is often hidden).
- The plugin now appears in the Processing Toolbox and its search box (search for "GEE", "Landsat", "Sentinel" or "download"): the algorithm opens the plugin window.

## 0.15.1

- New logo: plugin icon, window icon and About box.

## 0.15.0

- Landsat 7 removed: its images have black stripes since 2003. The old-satellite source is now "Landsat 4/5" (Landsat 4 added, 1982-1993; Landsat 5 1984 to May 2012). Files are named `L45_...` instead of `L57_...`; a saved choice of the old source is migrated automatically. Landsat 5 ends in May 2012, so 2012 has only a few months.

## 0.14.0

- "Automatic by year" now prefers Sentinel-2 (10 m, from 2017) when the year has an image that is clean and complete over the area (at least 95% clear and 99% covered; the clear limit is adjustable in the advanced options). Otherwise it uses the clearest Landsat of the year, as before. The log says which one was chosen and why. Can be turned off with a checkbox.

## 0.13.0

- Removed the Esri World Imagery (Wayback) source; it did not work reliably. The 0.12.1-0.12.3 Esri fixes are gone with it.
- Less freezing: downloaded layers are added to QGIS one at a time with a short pause and the map canvas frozen meanwhile (one redraw at the end), the log keeps only the last 3,000 lines, and the download thread runs at low priority.

## 0.12.0

- New image types: tick any of vegetation colours, natural colours (RGB) and NDVI; one file each.
- New source: Esri World Imagery Wayback, by year (newest version of the year or a version you pick). Needs no Earth Engine.
- Less freezing: internal pyramids on big rasters, only the first downloaded layer is visible, the area is measured after you stop clicking, selected-feature extent is computed natively, repeated date searches are cached, areas above 60,000 km² are refused with an explanation.
- A cancelled or failed download no longer leaves a half-written file that "skip existing images" would reuse.

## 0.11.0

- Everything now runs in the background: searching for dates no longer freezes QGIS.
- New "Keep working in QGIS" button: hides the window while the download continues; a progress bar (with Show window / Cancel) appears in the QGIS message bar. Closing the window or pressing Esc during a download no longer interrupts it.

## 0.10.0

- New "What to download" option: colour image, NDVI, or both. NDVI is saved as a Float32 GeoTIFF (values -1 to 1, no-data -9999) and opens in QGIS with a red-to-green palette. Works with one date, best image of a year and time series; uses the same nearby-date completion for scene borders.

## 0.9.2

- Fix incomplete images when the area is on the border between satellite scenes (Landsat paths / Sentinel-2 orbits are imaged on different days). The part missing on the chosen date is filled with the nearest date within a few days; the chosen date always has priority.
- New option "Complete the area with nearby dates" (on by default) and a "% area covered" column in the dates table; the best date is now chosen on the image that will actually be downloaded.
- Warning in the log when the available dates do not cover the whole area.

## 0.9.1

- Fix "Too many concurrent aggregations" when listing dates of long periods or large areas.
- Retry automatically (with waits) when Earth Engine is busy; friendlier message when it still fails.

## 0.9.0

- First public release.
- Download straight to QGIS (no Google Drive); large areas are downloaded in blocks and merged.
- One date, best image of a year, or multi-year time series.
- Guided first-run setup (library check, Earth Engine sign-in, project ID).
- Resume long series by skipping images already in the folder.
- English and Portuguese interface.
