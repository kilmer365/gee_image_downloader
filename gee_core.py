# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
"""Earth Engine logic for GEE Image Downloader (no GUI dependency).

Rules kept from the original workflow:
- Do NOT mask clouds and do NOT clip to the polygon: it creates black holes
  and black backgrounds when the image is opened in QGIS.
- Region = bounds of the area buffered by a margin (500 m by default).
- 8-bit output through .visualize(vis); 30 m (Landsat) or 10 m (Sentinel-2).

Images are downloaded straight to a local GeoTIFF with getDownloadURL (in
blocks when the area is large) and merged into a single file, so nothing
goes through Google Drive.
"""

import math
import os
import shutil
import zipfile

SENSORS = {
    "L89": {
        "name": "Landsat 8/9 (6-5-2)",
        "short": "Landsat 8/9",
        "collections": ["LANDSAT/LC08/C02/T1_L2", "LANDSAT/LC09/C02/T1_L2"],
        "bands": ["SR_B6", "SR_B5", "SR_B2"],
        "scale": 30,
        "factor": (0.0000275, -0.2),
        "vis": {"min": [0.02, 0.02, 0.0], "max": [0.40, 0.45, 0.10], "gamma": 1.2},
        "prop_sat": "SPACECRAFT_ID",
        "prop_cloud": "CLOUD_COVER",
        "prefix": "L89_652",
        "ndvi": ("SR_B5", "SR_B4"),  # (near infrared, red)
        "roles": {"nir": "SR_B5", "red": "SR_B4", "green": "SR_B3", "swir1": "SR_B6"},
        "natural": {"bands": ["SR_B4", "SR_B3", "SR_B2"], "prefix": "L89_432",
                    "vis": {"min": 0.0, "max": 0.30, "gamma": 1.4}},
    },
    "L45": {
        "name": "Landsat 4/5 (5-4-1)",
        "short": "Landsat 4/5",
        # Landsat 7 is left out on purpose: its scan-line corrector failed in 2003 and the images have gaps.
        "collections": ["LANDSAT/LT04/C02/T1_L2", "LANDSAT/LT05/C02/T1_L2"],
        "bands": ["SR_B5", "SR_B4", "SR_B1"],
        "scale": 30,
        "factor": (0.0000275, -0.2),
        "vis": {"min": [0.02, 0.02, 0.0], "max": [0.40, 0.45, 0.10], "gamma": 1.2},
        "prop_sat": "SPACECRAFT_ID",
        "prop_cloud": "CLOUD_COVER",
        "prefix": "L45_541",
        "ndvi": ("SR_B4", "SR_B3"),
        "roles": {"nir": "SR_B4", "red": "SR_B3", "green": "SR_B2", "swir1": "SR_B5"},
        "natural": {"bands": ["SR_B3", "SR_B2", "SR_B1"], "prefix": "L45_321",
                    "vis": {"min": 0.0, "max": 0.30, "gamma": 1.4}},
    },
    "S2": {
        "name": "Sentinel-2 (11-8-2)",
        "short": "Sentinel-2",
        "collections": ["COPERNICUS/S2_SR_HARMONIZED"],
        "bands": ["B11", "B8", "B2"],
        "scale": 10,
        "factor": (0.0001, 0.0),
        # Starting stretch for Sentinel-2; adjust the style in QGIS if needed.
        "vis": {"min": [0.0, 0.02, 0.0], "max": [0.40, 0.45, 0.15], "gamma": 1.2},
        "prop_sat": "SPACECRAFT_NAME",
        "prop_cloud": "CLOUDY_PIXEL_PERCENTAGE",
        "prefix": "S2_1182",
        "ndvi": ("B8", "B4"),
        "roles": {"nir": "B8", "red": "B4", "green": "B3", "swir1": "B11", "rededge": "B5"},
        "natural": {"bands": ["B4", "B3", "B2"], "prefix": "S2_432",
                    "vis": {"min": 0.0, "max": 0.30, "gamma": 1.3}},
    },
}

# Public MapBiomas Brazil asset. Layout can change between collections, so the
# path is editable in the advanced options.
NDVI_NODATA = -9999.0

MAPBIOMAS_DEFAULT_ASSET = "projects/mapbiomas-public/assets/brazil/lulc/v1"

# 3000 x 3000 px x 3 bands x 8 bit is about 27 MB (Earth Engine limit is about 48 MB per request).
MAX_BLOCK_PX = 3000

FIRST_YEAR = 1984  # first full Landsat 5 year (Landsat 4 starts in 1982)


class EeError(Exception):
    """Error with a machine-readable code so the GUI can translate the message."""

    def __init__(self, message, code="other"):
        super().__init__(message)
        self.code = code


class Cancelled(Exception):
    pass


# ---------------------------------------------------------------- connection
def import_ee():
    try:
        import ee  # noqa: F401
        return ee
    except ImportError:
        raise EeError("earthengine-api is not installed", "no_lib")


def classify_error(exc):
    """Map an exception to a short code the GUI turns into a friendly message."""
    text = str(exc).lower()
    if "concurrent" in text or "too many aggregations" in text or "computation timed out" in text \
            or "capacity" in text:
        return "busy"
    if "not registered" in text or "not signed up" in text or "must be registered" in text:
        return "not_registered"
    if "has not been used" in text or "service_disabled" in text or "has not been enabled" in text \
            or "api is not enabled" in text:
        return "api_disabled"
    if "permission" in text or "403" in text or "does not have" in text:
        return "permission"
    if "quota" in text or "too many requests" in text or "429" in text or "rate limit" in text:
        return "quota"
    if "total request size" in text or "too large" in text or "user memory limit" in text \
            or "must be less than or equal to" in text:
        return "too_large"
    if "max retries" in text or "name or service" in text or "failed to establish" in text \
            or "timed out" in text or "connection" in text or "network" in text:
        return "network"
    if "credentials" in text or "authenticate" in text or "authorize" in text or "oauth" in text:
        return "auth"
    return "other"


def _wrap(exc):
    if isinstance(exc, (EeError, Cancelled)):
        return exc
    return EeError(str(exc), classify_error(exc))


def connect(project, authenticate):
    """Initialize Earth Engine. Opens the browser for login only if authenticate=True.

    A tiny server call is made at the end to validate the project early
    (Initialize alone does not check permissions or registration).
    """
    ee = import_ee()
    if not project:
        raise EeError("project id is empty", "no_project")
    try:
        ee.Initialize(project=project)
        ee.Number(1).getInfo()
        return ee
    except Exception as first:
        if not authenticate:
            raise _wrap(first)
    try:
        # 'localhost' opens the browser and receives the answer on a local port.
        # The default modes may wait for a code typed in a terminal, which QGIS does not have.
        ee.Authenticate(auth_mode="localhost")
        ee.Initialize(project=project)
        ee.Number(1).getInfo()
        return ee
    except Exception as second:
        raise _wrap(second)


# ---------------------------------------------------------------- geometry
def utm_epsg(lon, lat):
    """Best UTM zone for a point.

    SIRGAS 2000 inside Brazil (south 31978-31985 for zones 18S-25S,
    north 31972-31976 for zones 18N-22N); WGS 84 UTM everywhere else.
    """
    zone = int(math.floor((lon + 180) / 6) + 1)
    in_brazil = -75.0 <= lon <= -28.0 and -34.0 <= lat <= 6.0
    if in_brazil:
        if lat < 0 and 18 <= zone <= 25:
            return 31960 + zone
        if lat >= 0 and 18 <= zone <= 22:
            return 31954 + zone
    return (32700 if lat < 0 else 32600) + zone


def split_blocks(xmin, ymin, xmax, ymax, scale, max_px=MAX_BLOCK_PX):
    """Split a region (metres in the output CRS) into blocks aligned to the pixel grid."""
    x0 = math.floor(xmin / scale) * scale
    y0 = math.floor(ymin / scale) * scale
    x1 = math.ceil(xmax / scale) * scale
    y1 = math.ceil(ymax / scale) * scale
    step = max_px * scale
    xs = [x0 + i * step for i in range(int(math.ceil((x1 - x0) / step)))]
    ys = [y0 + j * step for j in range(int(math.ceil((y1 - y0) / step)))]
    return [(x, y, min(x + step, x1), min(y + step, y1)) for y in ys for x in xs]


def sensor_for_year(year):
    """Automatic sensor: Landsat 4/5 up to 2012, Landsat 8/9 from 2013."""
    return "L45" if year <= 2012 else "L89"


S2_FIRST_YEAR = 2017        # Sentinel-2 SR covers the world from 2017
PREFER_S2_MIN_CLEAR = 0.95  # Sentinel-2 is preferred only when at least this much of the area is clear...
PREFER_S2_MIN_COVER = 0.99  # ...and at least this much of it has data (complete)


def best_auto(ee, area, region, year, month_from, month_to, fill_on, cache_key=None,
              min_clear=PREFER_S2_MIN_CLEAR, prefer_s2=True, log=None):
    """Automatic source for a year: Sentinel-2 (10 m) when it has an image that is clean AND complete
    over the area, otherwise the clearest Landsat of the year. Returns (sensor, best_row or None)."""
    base = sensor_for_year(year)
    if prefer_s2 and year >= S2_FIRST_YEAR:
        s2 = best_date(ee, "S2", area, region, year, month_from, month_to,
                       FILL_DAYS["S2"] if fill_on else 0, cache_key)
        if s2 and (s2["clear"] or 0) >= min_clear and (s2.get("coverage") or 0) >= PREFER_S2_MIN_COVER:
            return "S2", s2
        if log:
            log(s2 and s2["clear"])
    return base, best_date(ee, base, area, region, year, month_from, month_to,
                           FILL_DAYS[base] if fill_on else 0, cache_key)


# ---------------------------------------------------------------- collections
def _apply_factor(img, sensor):
    mult, add = SENSORS[sensor]["factor"]
    return img.multiply(mult).add(add)


def collection(ee, sensor):
    cols = SENSORS[sensor]["collections"]
    col = ee.ImageCollection(cols[0])
    for c in cols[1:]:
        col = col.merge(ee.ImageCollection(c))
    return col


def clear_mask(ee, img, sensor):
    """1 = clear, 0 = cloud/shadow/cirrus. Used only to SCORE dates, never on the downloaded image."""
    if sensor == "S2":
        scl = img.select("SCL")
        bad = scl.eq(0).Or(scl.eq(3)).Or(scl.eq(8)).Or(scl.eq(9)).Or(scl.eq(10)).Or(scl.eq(11))
        return bad.Not().rename("c")
    qa = img.select("QA_PIXEL")
    return qa.bitwiseAnd(0b11111).eq(0).rename("c")  # bit 0 = fill (no data)


def valid_mask(ee, img, sensor):
    """1 where the scene really has data (inside its footprint)."""
    if sensor == "S2":
        return img.select("SCL").neq(0).rename("v")
    return img.select("QA_PIXEL").bitwiseAnd(1).eq(0).rename("v")


# Days on each side of the chosen date used to fill the part of the area that the chosen
# date does not cover. Neighbouring Landsat paths are imaged on different days (a few days to
# a week apart); neighbouring Sentinel-2 orbits are 2-5 days apart.
FILL_DAYS = {"L89": 8, "L45": 8, "S2": 5}


def window_collection(ee, sensor, area, day, fill_days):
    """Scenes within +-fill_days of `day`, ordered so that the NEAREST scene ends up on top
    of a mosaic (mosaic() puts the last image on top)."""
    target = ee.Date(day)
    col = (collection(ee, sensor).filterBounds(area)
           .filterDate(target.advance(-fill_days, "day"), target.advance(fill_days + 1, "day")))

    def add_dist(im):
        return im.set("dist", ee.Number(im.date().difference(target, "day")).abs())

    return col.map(add_dist).sort("dist", False)


SCORE_BATCH = 12  # dates scored per Earth Engine request (keeps each request light)


def with_retry(func, attempts=3, wait=3.0, sleep=None):
    """Run func(); retry with growing waits when Earth Engine says it is busy or rate limited."""
    import time
    sleep = sleep or time.sleep
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except Exception as exc:
            if attempt == attempts or classify_error(exc) not in ("busy", "quota"):
                raise _wrap(exc)
            sleep(wait * attempt)


def group_scenes(features):
    """Group per-scene metadata (from one server call) by acquisition date, client side.

    Doing this in Python avoids many nested server-side aggregations, which Earth Engine
    rejects with 'Too many concurrent aggregations'.
    """
    days = {}
    for f in features:
        p = f.get("properties", {})
        d = p.get("date")
        if not d:
            continue
        item = days.setdefault(d, {"sats": set(), "clouds": [], "scenes": 0})
        item["scenes"] += 1
        if p.get("sat"):
            item["sats"].add(p["sat"])
        if p.get("cloud") is not None:
            item["clouds"].append(p["cloud"])
    return days


_DATES_CACHE = {}  # (cache_key, sensor, start, end, fill) -> rows; avoids repeating slow Earth Engine scoring


def list_dates(ee, sensor, area, region, start, end, fill_days=0, cache_key=None):
    """Dates with satellite, cloud % and clear fraction inside the region.

    The score of a date is computed on the image that would be downloaded: the scenes of that
    day, completed with the nearest scenes within +-fill_days when fill_days > 0 (so an area
    that lies between two satellite paths is judged as a whole). "coverage" is the fraction of
    the region that has any data in that image.
    Returns dicts sorted by clear fraction, best first.
    """
    ckey = (cache_key, sensor, start, end, fill_days) if cache_key else None
    if ckey and ckey in _DATES_CACHE:
        return [dict(r) for r in _DATES_CACHE[ckey]]
    cfg = SENSORS[sensor]
    col = collection(ee, sensor).filterBounds(area).filterDate(start, end)

    def meta(im):  # only reads properties: no aggregation involved
        return ee.Feature(None, {
            "date": ee.Date(im.get("system:time_start")).format("YYYY-MM-dd"),
            "sat": im.get(cfg["prop_sat"]),
            "cloud": im.get(cfg["prop_cloud"]),
        })

    features = with_retry(lambda: ee.FeatureCollection(col.map(meta)).getInfo()["features"])
    days = group_scenes(features)
    score_scale = 60 if sensor == "S2" else 90

    def per_date(d):
        d = ee.String(d)
        if fill_days:
            day = window_collection(ee, sensor, area, d, fill_days)
        else:
            day = col.filterDate(ee.Date(d), ee.Date(d).advance(1, "day"))

        def score(im):
            v = valid_mask(ee, im, sensor)
            return clear_mask(ee, im, sensor).updateMask(v).addBands(v.updateMask(v))

        both = day.map(score).mosaic().unmask(0)
        stats = both.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=region, scale=score_scale,
            bestEffort=True, maxPixels=1e8, tileScale=4,
        )
        return ee.Feature(None, {"date": d, "clear": stats.get("c"), "coverage": stats.get("v")})

    names = sorted(days)
    clear, coverage = {}, {}
    batch = max(2, SCORE_BATCH // 2) if fill_days else SCORE_BATCH
    for i in range(0, len(names), batch):
        chunk = names[i:i + batch]
        info = with_retry(lambda c=chunk: ee.FeatureCollection(ee.List(c).map(per_date)).getInfo())
        for f in info.get("features", []):
            clear[f["properties"]["date"]] = f["properties"].get("clear")
            coverage[f["properties"]["date"]] = f["properties"].get("coverage")

    rows = []
    for d in names:
        item = days[d]
        clouds = item["clouds"]
        rows.append({
            "date": d, "sats": ", ".join(sorted(item["sats"])),
            "cloud": (sum(clouds) / len(clouds)) if clouds else None,
            "clear": clear.get(d), "coverage": coverage.get(d), "scenes": item["scenes"],
        })
    rows.sort(key=lambda r: (r["clear"] is None, -(r["clear"] or 0)))
    if ckey:
        if len(_DATES_CACHE) > 200:
            _DATES_CACHE.clear()
        _DATES_CACHE[ckey] = [dict(r) for r in rows]
    return rows


def best_date(ee, sensor, area, region, year, month_from, month_to, fill_days=0, cache_key=None):
    """Best date of a year inside a month window, or None when there are no scenes."""
    start = "%d-%02d-01" % (year, month_from)
    end = "%d-01-01" % (year + 1) if month_to >= 12 else "%d-%02d-01" % (year, month_to + 1)
    rows = [r for r in list_dates(ee, sensor, area, region, start, end, fill_days, cache_key) if r["clear"] is not None]
    if not rows:
        return None
    rows.sort(key=lambda r: (-r["clear"], r["cloud"] if r["cloud"] is not None else 100))
    return rows[0]


def count_scenes(ee, sensor, area, day):
    col = collection(ee, sensor).filterBounds(area).filterDate(day, ee.Date(day).advance(1, "day"))
    try:
        return int(col.size().getInfo())
    except Exception as exc:
        raise _wrap(exc)


def _scene_mosaic(ee, sensor, area, day, fill_days):
    if fill_days:
        return window_collection(ee, sensor, area, day, fill_days).mosaic()
    return collection(ee, sensor).filterBounds(area).filterDate(day, ee.Date(day).advance(1, "day")).mosaic()


def composite_image(ee, sensor, area, day, fill_days=0, natural=False):
    """Image of `day`. With fill_days > 0, pixels the chosen day does not cover (the neighbouring
    satellite path) are taken from the nearest other date within +-fill_days. No cloud masking.
    natural=True gives the natural-colour (red-green-blue) composite instead of the vegetation one."""
    cfg = SENSORS[sensor]
    bands, vis = (cfg["natural"]["bands"], cfg["natural"]["vis"]) if natural else (cfg["bands"], cfg["vis"])
    mosaic = _apply_factor(_scene_mosaic(ee, sensor, area, day, fill_days).select(bands), sensor)
    return mosaic.visualize(**vis)


# Vegetation indices (names and interpretation: Auravant, "Indices de vegetacao e sua interpretacao").
# "bands" are the roles each index needs; Landsat has no red-edge band, so NDRE exists only for Sentinel-2.
INDICES = {
    "NDVI": {"bands": ("nir", "red"), "name": "NDVI",
             "full": "Normalized Difference Vegetation Index (NIR - red) / (NIR + red)"},
    "GNDVI": {"bands": ("nir", "green"), "name": "GNDVI",
              "full": "Green NDVI (NIR - green) / (NIR + green)"},
    "NDRE": {"bands": ("nir", "rededge"), "name": "NDRE",
             "full": "Normalized Difference Red Edge (NIR - red edge) / (NIR + red edge)"},
    "MSAVI2": {"bands": ("nir", "red"), "name": "MSAVI2",
               "full": "Modified Soil Adjusted Vegetation Index 2"},
    "NDWI": {"bands": ("nir", "swir1"), "name": "NDWI",
             "full": "Normalized Difference Water Index (NIR - SWIR) / (NIR + SWIR)"},
}
INDEX_ORDER = ["NDVI", "GNDVI", "NDRE", "MSAVI2", "NDWI"]

_GREENS = [(0.0, "#d73027", "0"), (0.2, "#fdae61", "0.2"), (0.4, "#d9ef8b", "0.4"),
           (0.6, "#66bd63", "0.6"), (0.8, "#1a9850", "0.8"), (1.0, "#006837", "1")]
# Colour ramp (value, colour, label) used to show each index in QGIS.
INDEX_STYLE = {
    "NDVI": [(-0.2, "#a50026", "<0")] + _GREENS,
    "GNDVI": [(-0.2, "#a50026", "<0")] + _GREENS,
    "NDRE": [(-0.1, "#a50026", "<0")] + [(v * 0.8, col, lab) for v, col, lab in [
        (0.0, "#d73027", "0"), (0.25, "#fdae61", "0.2"), (0.5, "#d9ef8b", "0.4"),
        (0.75, "#66bd63", "0.6"), (1.0, "#006837", "0.8")]],
    "MSAVI2": [(-0.2, "#a50026", "<0")] + _GREENS,
    "NDWI": [(-0.6, "#8c510a", "-0.6"), (-0.4, "#bf812d", "-0.4"), (-0.2, "#dfc27d", "-0.2"),
             (0.0, "#f6e8c3", "0"), (0.2, "#c7eae5", "0.2"), (0.4, "#5ab4ac", "0.4"),
             (0.6, "#01665e", "0.6")],
}


def index_supported(sensor, index):
    roles = SENSORS[sensor].get("roles", {})
    return all(r in roles for r in INDICES[index]["bands"])


def index_image(ee, sensor, area, day, fill_days=0, index="NDVI"):
    """A vegetation index of the same mosaic as the colour image, as real values (Float32).
    No cloud masking, like the colour image. Pixels without data become NDVI_NODATA (-9999)."""
    roles = SENSORS[sensor]["roles"]
    if not index_supported(sensor, index):
        raise EeError("%s needs a band this satellite does not have" % index, "other")
    need = sorted({roles[r] for r in ("nir", "red", "green", "swir1", "rededge") if r in roles})
    refl = _apply_factor(_scene_mosaic(ee, sensor, area, day, fill_days).select(need), sensor)
    nir = roles["nir"]
    if index == "MSAVI2":
        red = roles["red"]
        out = refl.expression("(2 * N + 1 - sqrt((2 * N + 1) * (2 * N + 1) - 8 * (N - R))) / 2",
                              {"N": refl.select(nir), "R": refl.select(red)})
    else:
        other = roles[INDICES[index]["bands"][1]]
        out = refl.normalizedDifference([nir, other])
    return out.rename(index).toFloat().unmask(NDVI_NODATA)


def ndvi_image(ee, sensor, area, day, fill_days=0):
    """NDVI = (NIR - red) / (NIR + red). Kept for compatibility; see index_image."""
    return index_image(ee, sensor, area, day, fill_days, "NDVI")


def mapbiomas_image(ee, asset, year):
    """Class raster of one year. Accepts an Image asset (bands classification_YEAR)
    or an ImageCollection with a 'classification' band and a 'year' property."""
    band = "classification_%d" % year
    try:
        img = ee.Image(asset)
        if band in img.bandNames().getInfo():
            return img.select(band).toByte()
    except Exception:
        pass
    col = ee.ImageCollection(asset)
    try:
        col = col.filter(ee.Filter.eq("collection_id", 10.0))
    except Exception:
        pass
    try:
        img = col.filter(ee.Filter.eq("year", year)).mosaic()
        if "classification" not in img.bandNames().getInfo():
            raise EeError("MapBiomas band for %d not found" % year, "mapbiomas")
        return img.select("classification").toByte()
    except EeError:
        raise
    except Exception as exc:
        raise _wrap(exc)


# ---------------------------------------------------------------- download
OVERVIEW_MIN_PX = 1500  # build pyramids for rasters larger than this, so QGIS draws them quickly


def build_overviews(path, resampling="AVERAGE", log=None):
    """Add internal pyramids (overviews). Makes big rasters draw fast and stops QGIS from stalling when
    it zooms out. Runs in the worker thread. Never fails the download: errors are only logged."""
    try:
        from osgeo import gdal
        gdal.UseExceptions()
        ds = gdal.Open(path, gdal.GA_Update)
        if ds is None:
            return
        size = max(ds.RasterXSize, ds.RasterYSize)
        if size <= OVERVIEW_MIN_PX or ds.GetRasterBand(1).GetOverviewCount() > 0:
            return
        levels, f = [], 2
        while size / f >= 256:
            levels.append(f)
            f *= 2
        if levels:
            gdal.SetThreadLocalConfigOption("COMPRESS_OVERVIEW", "LZW")
            ds.BuildOverviews(resampling, levels)
        ds = None
    except Exception as exc:  # noqa: BLE001
        if log:
            log("  (could not build pyramids: %s)" % exc)
    finally:
        try:
            from osgeo import gdal
            gdal.SetThreadLocalConfigOption("COMPRESS_OVERVIEW", None)
        except Exception:
            pass


def _fetch(url, dest, feedback, cancelled):
    """Download url into dest using the QGIS network stack (respects the QGIS proxy settings)."""
    from qgis.core import QgsBlockingNetworkRequest
    from qgis.PyQt.QtCore import QUrl
    from qgis.PyQt.QtNetwork import QNetworkRequest

    codes = getattr(QgsBlockingNetworkRequest, "ErrorCode", QgsBlockingNetworkRequest)
    last = ""
    for _attempt in range(3):
        if cancelled and cancelled():
            raise Cancelled()
        req = QgsBlockingNetworkRequest()
        err = req.get(QNetworkRequest(QUrl(url)), True, feedback)
        if cancelled and cancelled():
            raise Cancelled()
        if err == codes.NoError:
            data = bytes(req.reply().content())
            if data[:1] == b"{":  # JSON error body instead of a file
                raise EeError(data[:300].decode("utf-8", "ignore"), classify_error(data.decode("utf-8", "ignore")))
            with open(dest, "wb") as fh:
                fh.write(data)
            return
        last = req.errorMessage()
    raise EeError(last or "download failed", "network")


def _unzip_if_needed(path):
    """Earth Engine may answer with a zip; returns a .tif (or a VRT when bands come split)."""
    with open(path, "rb") as fh:
        magic = fh.read(2)
    if magic != b"PK":
        return path
    folder = path + "_x"
    with zipfile.ZipFile(path) as z:
        z.extractall(folder)
    tifs = sorted(os.path.join(folder, n) for n in os.listdir(folder) if n.lower().endswith(".tif"))
    if not tifs:
        raise EeError("the download had no GeoTIFF", "other")
    if len(tifs) == 1:
        return tifs[0]
    from osgeo import gdal
    vrt = path + ".vrt"
    gdal.BuildVRT(vrt, tifs, separate=True)
    return vrt


def download_image(ee, image, bounds_crs, crs, scale, out_tif, log=None, cancelled=None, feedback=None,
                   nodata=None, classes=False):
    """Download `image` (already visualized / Byte) to out_tif, in blocks when needed.

    bounds_crs = (xmin, ymin, xmax, ymax) in metres in the output CRS.
    """
    from osgeo import gdal
    gdal.UseExceptions()
    blocks = split_blocks(*bounds_crs, scale=scale)
    tmp = out_tif + "_blocks"
    os.makedirs(tmp, exist_ok=True)
    parts = []
    try:
        for i, (x0, y0, x1, y1) in enumerate(blocks, 1):
            if cancelled and cancelled():
                raise Cancelled()
            if log:
                log("  block %d/%d..." % (i, len(blocks)))
            rect = ee.Geometry.Rectangle([x0, y0, x1, y1], crs, False)
            try:
                url = image.getDownloadURL({"region": rect, "scale": scale, "crs": crs, "format": "GEO_TIFF"})
            except Exception as exc:
                raise _wrap(exc)
            raw = os.path.join(tmp, "b%03d.tif" % i)
            _fetch(url, raw, feedback, cancelled)
            parts.append(_unzip_if_needed(raw))
        if len(parts) == 1 and parts[0].lower().endswith(".tif"):
            shutil.move(parts[0], out_tif)
        else:
            vrt_path = os.path.join(tmp, "mosaic.vrt")
            vrt = gdal.BuildVRT(vrt_path, parts)
            gdal.Translate(out_tif, vrt, creationOptions=["COMPRESS=LZW", "TILED=YES", "BIGTIFF=IF_SAFER"])
            vrt = None
    except BaseException:
        if os.path.exists(out_tif):  # never leave a half-written file that "skip existing" would reuse
            try:
                os.remove(out_tif)
            except OSError:
                pass
        raise
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if nodata is not None:
        ds = gdal.Open(out_tif, gdal.GA_Update)
        ds.GetRasterBand(1).SetNoDataValue(nodata)
        ds = None
    build_overviews(out_tif, "NEAREST" if classes else "AVERAGE", log)
    return out_tif
