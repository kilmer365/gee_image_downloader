# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
"""Main dialog of GEE Image Downloader.

Layout: connection panel (onboarding) -> 1. area -> 2. what to download -> 3. download.
All user-facing text goes through tr() (English source, Portuguese translation in i18n.py).
"""

import configparser
import datetime
import math
import os
import sys

from qgis.core import (
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeedback, QgsProject,
    QgsRasterLayer, QgsRectangle, QgsSettings, QgsVectorLayer,
)
from qgis.gui import QgsCollapsibleGroupBox, QgsFileWidget, QgsMapLayerComboBox, QgsProjectionSelectionWidget
from qgis.PyQt.QtCore import Qt, QDate, QThread, QTimer, QUrl, pyqtSignal
from qgis.PyQt.QtGui import QDesktopServices, QIcon, QPixmap
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox, QDateEdit, QDialog,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit,
    QProgressBar, QPushButton, QScrollArea, QSpinBox, QStackedWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

try:
    from qgis.core import QgsMapLayerProxyModel
    _POLYGON_FILTER = QgsMapLayerProxyModel.PolygonLayer
except Exception:  # newer QGIS
    from qgis.core import Qgis
    _POLYGON_FILTER = Qgis.LayerFilter.PolygonLayer

from . import gee_core as core
from .i18n import month_names, tr

SETTINGS = "gee_image_downloader/"
CURRENT_YEAR = datetime.date.today().year
ACCESS_GUIDE_URL = "https://developers.google.com/earth-engine/guides/access"
MAX_AREA_KM2 = 60000   # above this the download would take hours and gigabytes
LARGE_BATCH = 15  # ask for confirmation above this many images

STYLE = """
QPushButton#mode { min-height: 62px; padding: 6px 10px; text-align: center; }
QPushButton#mode:checked { background: palette(highlight); color: palette(highlighted-text); font-weight: bold; }
QPushButton#download { min-height: 40px; font-weight: bold; font-size: 11pt; }
QLabel#hint { color: palette(mid); }
"""


def plugin_version():
    """Read the version from metadata.txt so the About box never goes out of date."""
    try:
        cp = configparser.ConfigParser(interpolation=None)
        cp.read(os.path.join(os.path.dirname(__file__), "metadata.txt"), encoding="utf-8")
        return cp.get("general", "version")
    except Exception:
        return ""


def error_text(code, detail=""):
    """Friendly, translated message for an error code (see gee_core.classify_error)."""
    msgs = {
        "no_lib": tr("The Earth Engine Python library is not installed."),
        "no_project": tr("Enter your Earth Engine project ID."),
        "not_registered": tr("This project is not registered for Earth Engine. Register it (free for "
                             "non-commercial use) and try again."),
        "api_disabled": tr("The Earth Engine API is not enabled for this Google Cloud project. Enable it "
                           "in the Google Cloud console and try again."),
        "permission": tr("Your Google account has no permission on this project. Check the project ID "
                         "and the account you signed in with."),
        "quota": tr("Earth Engine quota or rate limit reached. Wait a few minutes and try again."),
        "too_large": tr("The area is too large for one download. Use a smaller area or margin."),
        "network": tr("Network problem while talking to Google. Check your connection and the QGIS "
                      "proxy settings."),
        "auth": tr("Sign-in with Google failed or was cancelled."),
        "mapbiomas": tr("Could not read the MapBiomas data for this year. Check the asset path in "
                        "the advanced options."),
        "no_scenes": tr("No image found for this date or period."),
        "busy": tr("Earth Engine is busy right now. The plugin already retried. Wait a minute and try "
                   "again, or use a smaller area or a shorter range of months."),
    }
    if code in msgs:
        return msgs[code]
    return tr("Unexpected error: %s") % (detail[:300] or code)


class AreaError(Exception):
    pass


class ConnectWorker(QThread):
    """Connects to Earth Engine without freezing QGIS (the login can wait for the browser)."""
    connected = pyqtSignal()
    failed = pyqtSignal(str, str)  # code, detail

    def __init__(self, project, authenticate, parent=None):
        super().__init__(parent)
        self.project = project
        self.authenticate = authenticate
        self.ee = None

    def run(self):
        try:
            self.ee = core.connect(self.project, self.authenticate)
            self.connected.emit()
        except core.EeError as exc:
            self.failed.emit(exc.code, str(exc))
        except Exception as exc:  # keep the thread from dying silently
            self.failed.emit(core.classify_error(exc), str(exc))


class DatesWorker(QThread):
    """Looks for scenes/dates without freezing QGIS."""
    done = pyqtSignal(int, list)   # scenes on the chosen day (-1 = not asked), rows
    failed = pyqtSignal(str, str)  # code, detail

    def __init__(self, ee, plan, parent=None):
        super().__init__(parent)
        self.ee, self.plan = ee, plan

    def run(self):
        p = self.plan
        try:
            n = -1
            if p.get("count_day"):
                n = core.count_scenes(self.ee, p["sensor"], p["area"], p["count_day"])
                if n > 0:
                    self.done.emit(n, [])
                    return
            rows = core.list_dates(self.ee, p["sensor"], p["area"], p["region"], p["start"], p["end"], p["fill"],
                                   p.get("cache_key"))
            self.done.emit(n, rows)
        except core.EeError as exc:
            self.failed.emit(exc.code, str(exc))
        except Exception as exc:
            self.failed.emit(core.classify_error(exc), str(exc))


class DownloadWorker(QThread):
    """Downloads the images in the background so QGIS stays usable."""
    log = pyqtSignal(str)
    progress = pyqtSignal(int, int, str)   # done, total, current label
    layer_ready = pyqtSignal(str, str, str, str)  # path, layer name, group name, kind (COLOR/NDVI/CLASS)
    finished_all = pyqtSignal(int, int)    # downloaded or reused, failed

    def __init__(self, ee, params, parent=None):
        super().__init__(parent)
        self.ee, self.p = ee, params
        self._cancel = False
        self.feedback = QgsFeedback()

    def cancel(self):
        self._cancel = True
        self.feedback.cancel()

    def _cancelled(self):
        return self._cancel

    def run(self):
        ok = failed = 0
        total = len(self.p["items"])
        for i, item in enumerate(self.p["items"]):
            if self._cancel:
                break
            self.progress.emit(i, total, item["label"])
            try:
                for path, name, kind in self._one(item):
                    self.layer_ready.emit(path, name, self.p["group"], kind)
                ok += 1
            except core.Cancelled:
                break
            except core.EeError as exc:
                failed += 1
                self.log.emit("  %s: %s (%s)" % (item["label"], error_text(exc.code, str(exc)), exc))
            except Exception as exc:
                failed += 1
                self.log.emit("  %s: %s" % (item["label"], error_text("other", str(exc))))
        self.finished_all.emit(ok, failed)

    def _one(self, item):
        """Download one item; returns a list of (file, layer name, kind)."""
        ee, p = self.ee, self.p
        os.makedirs(p["folder"], exist_ok=True)
        self.log.emit("[%s]" % item["label"])
        if p["source"] == "MAPBIOMAS":
            name, scale = "MAPBIOMAS_%d" % item["year"], 30
            layer_name = "MapBiomas · %d" % item["year"]
            out = os.path.join(p["folder"], name + ".tif")
            if p["skip_existing"] and os.path.exists(out):
                self.log.emit("  " + tr("already in the folder, reusing"))
                return [(out, layer_name, "CLASS")]
            img = core.mapbiomas_image(ee, p["asset"], item["year"])
            core.download_image(ee, img, p["bounds_crs"], p["crs"], scale, out,
                                log=self.log.emit, cancelled=self._cancelled, feedback=self.feedback,
                                classes=True)
            self.log.emit("  " + tr("saved: %s") % out)
            return [(out, layer_name, "CLASS")]
        sensor = item["sensor"]
        day = item.get("day")
        if not day:
            self.log.emit("  " + tr("looking for the best date of %d...") % item["year"])
            if p["source"] == "AUTO" and p.get("prefer_s2") and item["year"] >= core.S2_FIRST_YEAR:
                def s2_note(clear):
                    self.log.emit("  " + (tr("Sentinel-2 is not clean and complete enough (best: %.0f%% clear); "
                                          "using the clearest Landsat.") % (100 * clear) if clear is not None
                                          else tr("No Sentinel-2 image found; using the clearest Landsat.")))
                sensor, best = core.best_auto(ee, p["area"], p["region"], item["year"], p["month_from"],
                                              p["month_to"], p.get("fill"), p.get("cache_key"),
                                              p.get("s2_min_clear", core.PREFER_S2_MIN_CLEAR), True, s2_note)
                if sensor == "S2":
                    self.log.emit("  " + tr("Sentinel-2 is clean and complete: using it (10 m)."))
            else:
                best = core.best_date(ee, sensor, p["area"], p["region"], item["year"], p["month_from"],
                                      p["month_to"], core.FILL_DAYS[sensor] if p.get("fill") else 0,
                                      p.get("cache_key"))
            if best is None:
                raise core.EeError("no scenes", "no_scenes")
            cfg = core.SENSORS[sensor]
            fill = core.FILL_DAYS[sensor] if p.get("fill") else 0
            day = best["date"]
            self.log.emit("  " + tr("best date: %s (%s, %.0f%% clear)") % (
                day, best["sats"], 100 * (best["clear"] or 0)))
            cov = best.get("coverage")
            if cov is not None and cov < 0.99:
                self.log.emit("  " + tr("Warning: only %.0f%% of the area has data on the available dates.")
                              % (100 * cov))
        else:
            cfg = core.SENSORS[sensor]
            fill = core.FILL_DAYS[sensor] if p.get("fill") else 0
            if core.count_scenes(ee, sensor, p["area"], day) == 0:
                raise core.EeError("no scenes", "no_scenes")
        results = []
        for kind in p.get("products") or ["COLOR"]:
            if kind in core.INDICES:
                if not core.index_supported(sensor, kind):
                    self.log.emit("  " + tr("%s needs a red-edge band, which only Sentinel-2 has; skipped for this image.") % kind)
                    continue
                name, label = "%s_%s_%s" % (cfg["prefix"], day, kind), "%s %s" % (kind, cfg["short"])
            elif kind == "NATURAL":
                name, label = "%s_%s" % (cfg["natural"]["prefix"], day), cfg["short"] + " " + tr("natural colour")
            else:
                name, label = "%s_%s" % (cfg["prefix"], day), cfg["short"]
            layer_name = "%s · %s" % (label, day)
            out = os.path.join(p["folder"], name + ".tif")
            if p["skip_existing"] and os.path.exists(out):
                self.log.emit("  " + tr("already in the folder, reusing"))
                results.append((out, layer_name, kind))
                continue
            if fill:
                self.log.emit("  " + tr("Completing empty parts with dates up to %d days away.") % fill)
            if kind in core.INDICES:
                img = core.index_image(ee, sensor, p["area"], day, fill, kind)
            else:
                img = core.composite_image(ee, sensor, p["area"], day, fill, kind == "NATURAL")
            core.download_image(ee, img, p["bounds_crs"], p["crs"], cfg["scale"], out,
                                log=self.log.emit, cancelled=self._cancelled, feedback=self.feedback,
                                nodata=core.NDVI_NODATA if kind in core.INDICES else None)
            self.log.emit("  " + tr("saved: %s") % out)
            results.append((out, layer_name, kind))
        if not results:
            raise core.EeError("nothing to download for this image", "other")
        return results


class GeeDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle(tr("GEE Image Downloader"))
        self.setWindowIcon(QIcon(os.path.join(os.path.dirname(__file__), "icon.png")))
        self.setStyleSheet(STYLE)
        self.resize(720, 840)
        self.ee = None
        self.state = "disconnected"
        self.has_lib = True
        self.connect_worker = None
        self.worker = None
        self.dates_worker = None
        self._layers_this_run = 0
        self._load_queue = []
        self._load_timer = QTimer(self)
        self._load_timer.setSingleShot(True)
        self._load_timer.timeout.connect(self._load_next)
        self._canvas_frozen = False
        self._area_km2 = 0.0
        self._area_timer = QTimer(self)
        self._area_timer.setSingleShot(True)
        self._area_timer.setInterval(350)
        self._area_timer.timeout.connect(self._area_info)
        self._bg_widget = None
        self._bg_bar = None
        self._bg_label = None
        self._layer_listened = None
        self._area_ok = False
        self._area_msg = ""
        self._first_show = True
        self._last_folder = ""
        self._ready = False        # signals fired while building must not touch missing widgets
        self._reason_shown = False
        self._silent_connect = False
        self._build()
        self._load_settings()
        self._check_library()
        self._ready = True
        self._on_layer_changed(self.cb_layer.currentLayer())
        self._refresh()

    # ================================================================ UI
    def _build(self):
        root = QVBoxLayout(self)
        title = QLabel("<span style='font-size:15pt;font-weight:bold'>%s</span><br>%s" % (
            tr("Download satellite imagery"),
            tr("Pick an area, say what you want and click download. The image opens straight in QGIS.")))
        title.setWordWrap(True)
        root.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        col = QVBoxLayout(body)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        col.addWidget(self._build_connection())
        col.addWidget(self._build_area())
        col.addWidget(self._build_what())
        col.addWidget(self._build_advanced())
        col.addWidget(self._build_log())
        col.addStretch()
        root.addWidget(self._build_download())

        for w in (self.sp_year, self.sp_from, self.sp_to):
            w.valueChanged.connect(self._refresh)
        self.dt.dateChanged.connect(self._refresh)
        self.cb_m_from.currentIndexChanged.connect(self._refresh)
        self.cb_m_to.currentIndexChanged.connect(self._refresh)
        self.sp_buffer.valueChanged.connect(self._area_info_later)
        for b in self.findChildren(QPushButton):
            b.setAutoDefault(False)

    # ---------- connection panel ----------
    def _build_connection(self):
        g = QGroupBox(tr("Google Earth Engine"))
        v = QVBoxLayout(g)
        self.lb_con = QLabel("")
        self.lb_con.setWordWrap(True)
        self.lb_con.setTextFormat(Qt.TextFormat.RichText)
        v.addWidget(self.lb_con)

        # library missing
        self.w_lib = QWidget()
        vl = QVBoxLayout(self.w_lib)
        vl.setContentsMargins(0, 0, 0, 0)
        self.lb_lib = QLabel("")
        self.lb_lib.setWordWrap(True)
        self.lb_lib.setTextFormat(Qt.TextFormat.RichText)
        self.ed_cmd = QLineEdit(self._install_command())
        self.ed_cmd.setReadOnly(True)
        hl = QHBoxLayout()
        self.b_copy = QPushButton(tr("Copy command"))
        self.b_copy.clicked.connect(lambda: QApplication.clipboard().setText(self.ed_cmd.text()))
        self.b_recheck = QPushButton(tr("I installed it, check again"))
        self.b_recheck.clicked.connect(self._recheck_library)
        hl.addWidget(self.b_copy)
        hl.addWidget(self.b_recheck)
        hl.addStretch()
        vl.addWidget(self.lb_lib)
        vl.addWidget(self.ed_cmd)
        vl.addLayout(hl)
        v.addWidget(self.w_lib)

        # connect form
        self.w_form = QWidget()
        vf = QVBoxLayout(self.w_form)
        vf.setContentsMargins(0, 0, 0, 0)
        hf = QHBoxLayout()
        hf.addWidget(QLabel(tr("Project ID:")))
        self.ed_project = QLineEdit()
        self.ed_project.setPlaceholderText(tr("your Google Cloud project with Earth Engine, e.g. my-project-123"))
        self.ed_project.setToolTip(tr("The ID of the Google Cloud project registered for Earth Engine."))
        self.ed_project.returnPressed.connect(self._connect)
        self.b_connect = QPushButton(tr("Connect"))
        self.b_connect.clicked.connect(self._connect)
        hf.addWidget(self.ed_project, 1)
        hf.addWidget(self.b_connect)
        vf.addLayout(hf)
        lb_help = QLabel("<a href='%s'>%s</a>" % (ACCESS_GUIDE_URL, tr("How do I get a project ID?")))
        lb_help.setOpenExternalLinks(True)
        vf.addWidget(lb_help)
        v.addWidget(self.w_form)

        self.b_change = QPushButton(tr("Change project or account"))
        self.b_change.clicked.connect(lambda: self._set_state("disconnected"))
        v.addWidget(self.b_change, 0, Qt.AlignmentFlag.AlignLeft)
        return g

    @staticmethod
    def _install_command():
        if sys.platform.startswith("win"):
            return "python -m pip install earthengine-api"
        return "python3 -m pip install earthengine-api"

    # ---------- step 1 ----------
    def _build_area(self):
        g = QGroupBox(tr("1. Which area?"))
        v = QVBoxLayout(g)
        self.cb_layer = QgsMapLayerComboBox()
        self.cb_layer.setFilters(_POLYGON_FILTER)
        self.cb_layer.setToolTip(tr("Polygon layer of the property or area of interest."))
        self.cb_layer.layerChanged.connect(self._on_layer_changed)
        active = self.iface.activeLayer() if self.iface is not None else None
        if active is not None:
            self.cb_layer.setLayer(active)
        self.ck_sel = QCheckBox(tr("Use only the features selected on the map"))
        self.ck_sel.toggled.connect(self._area_info_later)
        self.lb_area = QLabel("")
        self.lb_area.setWordWrap(True)
        self.lb_area.setTextFormat(Qt.TextFormat.RichText)
        v.addWidget(self.cb_layer)
        v.addWidget(self.ck_sel)
        v.addWidget(self.lb_area)
        return g

    # ---------- step 2 ----------
    def _build_what(self):
        g = QGroupBox(tr("2. What do you want to download?"))
        v = QVBoxLayout(g)

        row = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        self.b_day = self._mode_button(tr("One date\nI pick the day"), 0)
        self.b_year = self._mode_button(tr("Best image of a year\nThe plugin finds the clearest"), 1)
        self.b_series = self._mode_button(tr("Series of years\nTime series, e.g. 1995 to today"), 2)
        for b in (self.b_day, self.b_year, self.b_series):
            row.addWidget(b)
            b.toggled.connect(self._refresh)
        v.addLayout(row)
        self.b_year.setChecked(True)

        form = QFormLayout()
        self.cb_source = QComboBox()
        self.cb_source.addItem(tr("Automatic by year (recommended)"), "AUTO")
        self.cb_source.addItem(tr("Landsat 8/9 - 2013 to today - 30 m"), "L89")
        self.cb_source.addItem(tr("Landsat 4/5 - up to 2012 - 30 m"), "L45")
        self.cb_source.addItem(tr("Sentinel-2 - 2017 to today - 10 m"), "S2")
        self.cb_source.addItem(tr("MapBiomas Brazil - land cover (beta)"), "MAPBIOMAS")
        self.cb_source.currentIndexChanged.connect(self._refresh)
        self.lb_source = QLabel("")
        self.lb_source.setObjectName("hint")
        self.lb_source.setWordWrap(True)
        form.addRow(tr("Imagery source:"), self.cb_source)
        self.w_products = QWidget()
        hp_ = QHBoxLayout(self.w_products)
        hp_.setContentsMargins(0, 0, 0, 0)
        self.ck_false = QCheckBox(tr("Vegetation colours"))
        self.ck_false.setChecked(True)
        self.ck_false.setToolTip(tr("False-colour composite: vegetation in green, bare soil in pink. "
                                    "The best one to tell forest, pasture and crops apart."))
        self.ck_natural = QCheckBox(tr("Natural colours"))
        self.ck_natural.setToolTip(tr("How the area looks to the human eye (red, green and blue bands)."))
        for c in (self.ck_false, self.ck_natural):
            c.toggled.connect(self._refresh)
            hp_.addWidget(c)
        hp_.addStretch()
        self.lb_product = QLabel(tr("Image types:"))
        form.addRow(self.lb_product, self.w_products)
        # Vegetation indices (saved as real values, one file each)
        self.w_indices = QWidget()
        hi_ = QHBoxLayout(self.w_indices)
        hi_.setContentsMargins(0, 0, 0, 0)
        tips = {
            "NDVI": tr("Vegetation vigour and canopy cover (-1 to 1). Near 1: dense, vigorous vegetation; near 0: "
                       "sparse vegetation or bare soil; negative: water, snow or clouds. Clouds are not removed."),
            "GNDVI": tr("Like NDVI but with the green band. Saturates later, so it is better for mid-to-late crop "
                        "stages; related to chlorophyll, water and nitrogen uptake in dense canopies."),
            "NDRE": tr("Uses the red-edge band (Sentinel-2 only). Follows chlorophyll and leaf nitrogen; useful "
                       "in advanced crop stages where NDVI saturates, and to spot vigour loss early."),
            "MSAVI2": tr("NDVI corrected for the soil background. Best for early stages, emergence, crops that do "
                         "not close the canopy and woody crops, where NDVI can mislead."),
            "NDWI": tr("(NIR - SWIR) / (NIR + SWIR): water content of the vegetation. High: plenty of water and "
                       "cover; low: little water or sparse cover. Not a map of water bodies."),
        }
        self.ck_idx = {}
        for k in core.INDEX_ORDER:
            ck = QCheckBox(k)
            ck.setToolTip(tips[k])
            ck.toggled.connect(self._refresh)
            self.ck_idx[k] = ck
            hi_.addWidget(ck)
        hi_.addStretch()
        self.lb_indices = QLabel(tr("Vegetation indices:"))
        form.addRow(self.lb_indices, self.w_indices)
        form.addRow("", self.lb_source)
        v.addLayout(form)

        self.pages = QStackedWidget()
        # page 0: one date
        p0 = QWidget()
        f0 = QFormLayout(p0)
        self.dt = QDateEdit(QDate.currentDate().addYears(-1))
        self.dt.setCalendarPopup(True)
        self.dt.setDisplayFormat("yyyy-MM-dd")
        self.b_check = QPushButton(tr("Check if there is an image on this day"))
        self.b_check.clicked.connect(self._check_dates)
        f0.addRow(tr("Day:"), self.dt)
        f0.addRow("", self.b_check)
        # page 1: best of a year
        p1 = QWidget()
        f1 = QFormLayout(p1)
        self.sp_year = QSpinBox()
        self.sp_year.setRange(core.FIRST_YEAR, 2100)
        self.sp_year.setValue(CURRENT_YEAR - 1)
        self.b_list = QPushButton(tr("Show available dates"))
        self.b_list.clicked.connect(self._check_dates)
        self.lb_year_hint = QLabel(tr("If you do not pick a row in the table, the clearest date is downloaded."))
        self.lb_year_hint.setObjectName("hint")
        self.lb_year_hint.setWordWrap(True)
        f1.addRow(tr("Year:"), self.sp_year)
        f1.addRow("", self.b_list)
        f1.addRow("", self.lb_year_hint)
        # page 2: series
        p2 = QWidget()
        v2 = QVBoxLayout(p2)
        h2 = QHBoxLayout()
        self.sp_from = QSpinBox()
        self.sp_from.setRange(core.FIRST_YEAR, 2100)
        self.sp_from.setValue(1995)
        self.sp_to = QSpinBox()
        self.sp_to.setRange(core.FIRST_YEAR, 2100)
        self.sp_to.setValue(CURRENT_YEAR)
        h2.addWidget(QLabel(tr("From")))
        h2.addWidget(self.sp_from)
        h2.addWidget(QLabel(tr("to")))
        h2.addWidget(self.sp_to)
        h2.addStretch()
        v2.addLayout(h2)
        h3 = QHBoxLayout()
        h3.addWidget(QLabel(tr("Shortcuts:")))
        for first in (1985, 1995, 2005):
            b = QPushButton(tr("%d to today") % first)
            b.clicked.connect(lambda _=False, a=first: (self.sp_from.setValue(a), self.sp_to.setValue(CURRENT_YEAR)))
            h3.addWidget(b)
        b10 = QPushButton(tr("Last 10 years"))
        b10.clicked.connect(lambda: (self.sp_from.setValue(CURRENT_YEAR - 9), self.sp_to.setValue(CURRENT_YEAR)))
        h3.addWidget(b10)
        h3.addStretch()
        v2.addLayout(h3)
        for p in (p0, p1, p2):
            self.pages.addWidget(p)
        v.addWidget(self.pages)

        self.w_months = QWidget()
        hm = QHBoxLayout(self.w_months)
        hm.setContentsMargins(0, 0, 0, 0)
        self.cb_m_from = QComboBox()
        self.cb_m_to = QComboBox()
        for c in (self.cb_m_from, self.cb_m_to):
            for i, m in enumerate(month_names(), 1):
                c.addItem(m, i)
        self.cb_m_from.setCurrentIndex(0)
        self.cb_m_to.setCurrentIndex(11)
        self.cb_m_from.setToolTip(tr("Tip: limit the months to the dry season of your region to avoid clouds."))
        hm.addWidget(QLabel(tr("Look for the image between")))
        hm.addWidget(self.cb_m_from)
        hm.addWidget(QLabel(tr("and")))
        hm.addWidget(self.cb_m_to)
        hm.addStretch()
        v.addWidget(self.w_months)
        self.lb_months_hint = QLabel(tr("Tip: choose the dry season of your region to get fewer clouds."))
        self.lb_months_hint.setObjectName("hint")
        v.addWidget(self.lb_months_hint)

        self.ck_fill = QCheckBox(tr("Complete the area with nearby dates (recommended on scene borders)"))
        self.ck_fill.setChecked(True)
        self.ck_fill.setToolTip(tr(
            "Neighbouring satellite tracks are imaged on different days. When the chosen date does not "
            "cover the whole area, the empty part is filled with the closest date (up to a few days "
            "away). The chosen date always has priority. Untick to use only the exact date."))
        v.addWidget(self.ck_fill)

        self.ck_s2 = QCheckBox(tr("Prefer Sentinel-2 when it has a clean, complete image (2017 onwards)"))
        self.ck_s2.setChecked(True)
        self.ck_s2.setToolTip(tr(
            "Sentinel-2 has 10 m pixels, sharper than Landsat's 30 m. For each year the plugin first looks "
            "for a Sentinel-2 image that covers the whole area with almost no clouds; if there is none, it "
            "uses the clearest Landsat of the year. Before 2017 only Landsat exists."))
        self.ck_s2.toggled.connect(self._refresh)
        v.addWidget(self.ck_s2)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            [tr("Date"), tr("Satellite"), tr("Scenes"), tr("% cloud"), tr("% clear in area"),
             tr("% area covered")])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setMinimumHeight(150)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._row_selected)
        self.table.hide()
        v.addWidget(self.table)
        self.lb_check = QLabel("")
        self.lb_check.setWordWrap(True)
        self.lb_check.setTextFormat(Qt.TextFormat.RichText)
        self.lb_check.hide()
        v.addWidget(self.lb_check)
        return g

    def _mode_button(self, text, idx):
        b = QPushButton(text)
        b.setObjectName("mode")
        b.setCheckable(True)
        self.mode_group.addButton(b, idx)
        return b

    # ---------- advanced / log ----------
    def _build_advanced(self):
        box = QgsCollapsibleGroupBox(tr("Advanced options (you usually do not need these)"))
        box.setCollapsed(True)
        self.advanced = box
        f = QFormLayout(box)
        self.sp_buffer = QSpinBox()
        self.sp_buffer.setRange(0, 20000)
        self.sp_buffer.setValue(500)
        self.sp_buffer.setSuffix(" m")
        self.sp_buffer.setToolTip(tr("Margin around the area, so the image is not cut at the property limit."))
        self.cb_crs = QComboBox()
        self.cb_crs.addItem(tr("Automatic (best UTM zone for the area)"), "auto")
        self.cb_crs.addItem(tr("Same as the layer (if projected)"), "layer")
        self.cb_crs.addItem(tr("Custom..."), "custom")
        self.cb_crs.currentIndexChanged.connect(self._crs_mode_changed)
        self.crs_widget = QgsProjectionSelectionWidget()
        self.crs_widget.setCrs(QgsProject.instance().crs())
        self.crs_widget.hide()
        self.sp_s2clear = QSpinBox()
        self.sp_s2clear.setRange(50, 100)
        self.sp_s2clear.setValue(int(core.PREFER_S2_MIN_CLEAR * 100))
        self.sp_s2clear.setSuffix(" %")
        self.sp_s2clear.setToolTip(tr("Sentinel-2 is chosen only if at least this much of the area is free of "
                                      "clouds and shadows (and fully covered). Lower it to accept more Sentinel-2 images."))
        self.ed_asset = QLineEdit(core.MAPBIOMAS_DEFAULT_ASSET)
        f.addRow(tr("Margin around the area:"), self.sp_buffer)
        f.addRow(tr("Sentinel-2 minimum clear area:"), self.sp_s2clear)
        f.addRow(tr("Output coordinate system:"), self.cb_crs)
        f.addRow("", self.crs_widget)
        f.addRow(tr("MapBiomas asset path:"), self.ed_asset)
        return box

    def _build_log(self):
        box = QgsCollapsibleGroupBox(tr("Details of what is happening"))
        box.setCollapsed(True)
        self.log_box = box
        v = QVBoxLayout(box)
        self.log = QPlainTextEdit()
        self.log.setMaximumBlockCount(3000)   # a long series must not make the log slower and slower
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(130)
        v.addWidget(self.log)
        return box

    # ---------- step 3 ----------
    def _build_download(self):
        g = QGroupBox(tr("3. Download"))
        v = QVBoxLayout(g)
        self.lb_summary = QLabel("")
        self.lb_summary.setWordWrap(True)
        self.lb_summary.setTextFormat(Qt.TextFormat.RichText)
        self.fw_folder = QgsFileWidget()
        self.fw_folder.setStorageMode(QgsFileWidget.StorageMode.GetDirectory)
        self.fw_folder.fileChanged.connect(self._refresh)
        hp = QHBoxLayout()
        hp.addWidget(QLabel(tr("Save in:")))
        hp.addWidget(self.fw_folder, 1)
        self.ck_skip = QCheckBox(tr("Skip images already in the folder (lets you resume a long series)"))
        self.ck_skip.setChecked(True)
        self.bar = QProgressBar()
        self.bar.setFormat("%v / %m")
        self.bar.hide()
        self.lb_status = QLabel("")
        self.lb_status.setWordWrap(True)
        self.lb_status.setTextFormat(Qt.TextFormat.RichText)
        hb = QHBoxLayout()
        self.b_download = QPushButton(tr("Download to QGIS"))
        self.b_download.setObjectName("download")
        self.b_download.clicked.connect(self._download)
        self.b_cancel = QPushButton(tr("Cancel"))
        self.b_cancel.setEnabled(False)
        self.b_cancel.clicked.connect(self._cancel)
        self.b_bg = QPushButton(tr("Keep working in QGIS"))
        self.b_bg.setToolTip(tr("Hides this window. The download continues in the background and a progress "
                                "bar appears at the top of QGIS."))
        self.b_bg.setEnabled(False)
        self.b_bg.clicked.connect(self._go_background)
        self.b_open = QPushButton(tr("Open folder"))
        self.b_open.clicked.connect(self._open_folder)
        self.b_open.hide()
        self.b_about = QPushButton(tr("About"))
        self.b_about.clicked.connect(self._about)
        hb.addWidget(self.b_download, 1)
        hb.addWidget(self.b_cancel)
        hb.addWidget(self.b_bg)
        hb.addWidget(self.b_open)
        hb.addWidget(self.b_about)
        v.addWidget(self.lb_summary)
        v.addLayout(hp)
        v.addWidget(self.ck_skip)
        v.addWidget(self.bar)
        v.addWidget(self.lb_status)
        v.addLayout(hb)
        return g

    def mode(self):
        return self.mode_group.checkedId()

    def source(self):
        return self.cb_source.currentData()

    def products(self):
        out = []
        if self.ck_false.isChecked():
            out.append("COLOR")
        if self.ck_natural.isChecked():
            out.append("NATURAL")
        for k in core.INDEX_ORDER:
            if self.ck_idx[k].isChecked():
                out.append(k)
        return out

    def fill_days(self, sensor):
        return core.FILL_DAYS[sensor] if self.ck_fill.isChecked() else 0

    def _sensor_for(self, year):
        s = self.source()
        return core.sensor_for_year(year) if s == "AUTO" else s

    def _busy(self):
        return (self.worker is not None and self.worker.isRunning()) or \
               (self.connect_worker is not None and self.connect_worker.isRunning()) or \
               (self.dates_worker is not None and self.dates_worker.isRunning())

    def _set_state(self, state, detail=""):
        self.state = state
        self.w_lib.setVisible(state == "nolib")
        self.w_form.setVisible(state in ("disconnected", "connecting"))
        self.b_change.setVisible(state == "connected")
        self.w_form.setEnabled(state == "disconnected")
        if state == "nolib":
            self.lb_con.setText("<b>%s</b>" % tr("One-time setup needed"))
            self.lb_lib.setText(tr(
                "This plugin needs the Earth Engine Python library. Open the \"OSGeo4W Shell\" (Windows) or a "
                "terminal that uses the same Python as QGIS, run the command below, then restart QGIS or "
                "click the button.") if sys.platform.startswith("win") else tr(
                "This plugin needs the Earth Engine Python library. Open a terminal that uses the same Python "
                "as QGIS, run the command below, then restart QGIS or click the button."))
        elif state == "disconnected":
            self.lb_con.setText(detail or tr(
                "Sign in to Google Earth Engine to start. You need a Google Cloud project with Earth "
                "Engine enabled."))
        elif state == "connecting":
            self.lb_con.setText(tr("Connecting... if your browser opens, sign in with Google and come back here."))
        elif state == "connected":
            self.lb_con.setText("✔ " + tr("Connected · project <b>%s</b>") % self.ed_project.text().strip())
        self._refresh()

    def _check_library(self):
        try:
            core.import_ee()
            self.has_lib = True
        except core.EeError:
            self.has_lib = False
        self._set_state("disconnected" if self.has_lib else "nolib")

    def _recheck_library(self):
        # A library installed while QGIS was running may live in a folder Python has not scanned yet.
        import importlib
        import site
        importlib.invalidate_caches()
        try:
            user_site = site.getusersitepackages()
            if user_site not in sys.path and os.path.isdir(user_site):
                sys.path.append(user_site)
        except Exception:
            pass
        self._check_library()
        if not self.has_lib:
            self._status(tr("Still not found. Restart QGIS after installing and open this window again."),
                         error=True)

    def showEvent(self, event):
        super().showEvent(event)
        if self._first_show:
            self._first_show = False
            # Silent reconnect with saved credentials; no browser, no error pop-ups.
            if self.has_lib and self.ed_project.text().strip():
                self._start_connect(authenticate=False, silent=True)

    # ---------- connection ----------
    def _connect(self):
        self._start_connect(authenticate=True, silent=False)

    def _start_connect(self, authenticate, silent):
        if self._busy():
            return
        project = self.ed_project.text().strip()
        if not project:
            self._set_state("disconnected", "<span style='color:#c62828'>%s</span>" % error_text("no_project"))
            return
        self._silent_connect = silent
        self.connect_worker = ConnectWorker(project, authenticate, self)
        self.connect_worker.connected.connect(self._on_connected)
        self.connect_worker.failed.connect(self._on_connect_failed)
        # `finished` fires when the thread has really ended, so controls re-enable correctly.
        self.connect_worker.finished.connect(self._refresh)
        self._set_state("connecting")
        self.connect_worker.start()

    def _on_connected(self):
        self.ee = self.connect_worker.ee
        self._save_settings()
        self._set_state("connected")
        self._log("Connected to Earth Engine.")

    def _on_connect_failed(self, code, detail):
        self.ee = None
        self._log("Connection failed (%s): %s" % (code, detail))
        if getattr(self, "_silent_connect", False):
            self._set_state("disconnected")  # first run or expired login: just show the form
        else:
            self._set_state("disconnected", "<span style='color:#c62828'>⚠ %s</span>" % error_text(code, detail))

    # ---------- area ----------
    def _on_layer_changed(self, layer):
        try:
            if self._layer_listened is not None:
                self._layer_listened.selectionChanged.disconnect(self._area_info_later)
        except Exception:
            pass
        self._layer_listened = layer
        if layer is not None:
            try:
                layer.selectionChanged.connect(self._area_info_later)
            except Exception:
                pass
        self._area_info()

    def _bbox_wgs84(self):
        layer = self.cb_layer.currentLayer()
        if layer is None:
            raise AreaError(tr("Choose a polygon layer in step 1."))

        def combine(features):
            rect, n = None, 0
            for f in features:
                geom = f.geometry()
                if geom is None or geom.isNull() or geom.isEmpty():
                    continue
                n += 1
                bb = geom.boundingBox()
                if rect is None:
                    rect = QgsRectangle(bb)
                else:
                    rect.combineExtentWith(bb)
            return rect, n

        rect, n = None, 0
        if self.ck_sel.isChecked() and layer.selectedFeatureCount() > 0:
            try:  # fast, computed by QGIS itself (does not loop over thousands of features in Python)
                rect, n = layer.boundingBoxOfSelected(), layer.selectedFeatureCount()
            except AttributeError:
                rect, n = None, 0
            if rect is None or rect.isNull() or rect.isEmpty():
                rect, n = combine(layer.selectedFeatures())
        else:
            layer.updateExtents()
            rect = layer.extent()
            if rect is None or rect.isNull() or rect.isEmpty():
                rect, n = combine(layer.getFeatures())  # extent not reliable (e.g. temporary layers)
        if rect is None or rect.isNull() or rect.isEmpty():
            raise AreaError(tr("No polygons found in layer '%s' (%d features, %d with geometry). "
                               "Check that it is the right layer.") % (layer.name(), layer.featureCount(), n))
        tr_ = QgsCoordinateTransform(layer.crs(), QgsCoordinateReferenceSystem("EPSG:4326"),
                                     QgsProject.instance().transformContext())
        r = tr_.transformBoundingBox(rect)
        return (r.xMinimum(), r.yMinimum(), r.xMaximum(), r.yMaximum())

    def _area_info_later(self, *_):
        """Wait for the user to stop clicking/typing before measuring the area (keeps QGIS responsive)."""
        if self._ready:
            self._area_timer.start()

    def _area_info(self, *_):
        if not self._ready:
            return
        try:
            bb = self._bbox_wgs84()
            lat = (bb[1] + bb[3]) / 2.0
            margin_km = 2 * self.sp_buffer.value() / 1000.0
            w = (bb[2] - bb[0]) * 111.32 * math.cos(math.radians(lat)) + margin_km
            h = (bb[3] - bb[1]) * 110.57 + margin_km
            self._area_km2 = w * h
            n = int(math.ceil(w * 1000 / 90000.0)) * int(math.ceil(h * 1000 / 90000.0))
            extra = "" if n <= 1 else tr(" · downloaded in %d blocks (automatic)") % n
            self.lb_area.setText("<span style='color:#2e7d32'>✔ %s</span>" % (
                tr("Area ready: about %.1f x %.1f km") % (w, h) + extra))
            self._area_ok, self._area_msg = True, ""
        except AreaError as exc:
            self.lb_area.setText("<span style='color:#c62828'>⚠ %s</span>" % exc)
            self._area_ok, self._area_msg = False, str(exc)
        except Exception as exc:
            self.lb_area.setText("<span style='color:#c62828'>⚠ %s</span>" % exc)
            self._area_ok, self._area_msg = False, str(exc)
        self._refresh()

    def _crs_mode_changed(self, *_):
        self.crs_widget.setVisible(self.cb_crs.currentData() == "custom")

    def _context(self):
        """Geometries for the filters (WGS 84) and for the download (output CRS, metres)."""
        bb = self._bbox_wgs84()
        area = self.ee.Geometry.Rectangle(list(bb))
        margin = self.sp_buffer.value()
        region = area.buffer(margin).bounds()
        crs_obj = self._output_crs(bb)
        tr_ = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"), crs_obj,
                                     QgsProject.instance().transformContext())
        r = tr_.transformBoundingBox(QgsRectangle(*bb))
        bounds = (r.xMinimum() - margin, r.yMinimum() - margin, r.xMaximum() + margin, r.yMaximum() + margin)
        return area, region, crs_obj.authid(), bounds

    def _output_crs(self, bb):
        auto = QgsCoordinateReferenceSystem(
            "EPSG:%d" % core.utm_epsg((bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0))
        mode = self.cb_crs.currentData()
        if mode == "layer":
            c = self.cb_layer.currentLayer().crs()
            if c.isValid() and not c.isGeographic() and c.authid().startswith("EPSG:"):
                return c
            self._log("Layer CRS is not a projected EPSG system; using the automatic UTM zone instead.")
        elif mode == "custom":
            c = self.crs_widget.crs()
            if c.isGeographic() or not c.authid().startswith("EPSG:"):
                raise AreaError(tr("Pick a projected coordinate system in metres that has an EPSG code."))
            return c
        return auto

    # ================================================================ summary / enabling
    def _items(self):
        s = self.source()
        mode = self.mode()
        if mode == 2:
            a0, a1 = self.sp_from.value(), self.sp_to.value()
            if s == "MAPBIOMAS":
                return [{"year": a, "label": "MapBiomas %d" % a} for a in range(a0, a1 + 1)]
            auto_s2 = s == "AUTO" and self.ck_s2.isChecked()
            return [{"year": a, "sensor": self._sensor_for(a),
                     "label": str(a) if auto_s2 and a >= core.S2_FIRST_YEAR else "%d (%s)" % (a, self._sensor_for(a))}
                    for a in range(a0, a1 + 1)]
        if s == "MAPBIOMAS":
            a = self.sp_year.value()
            return [{"year": a, "label": "MapBiomas %d" % a}]
        if mode == 1:
            a = self.sp_year.value()
            sel = self.table.selectedItems()
            day = self.table.item(sel[0].row(), 0).text() if sel else ""
            if day.startswith(str(a)):  # ignore a stale selection from another year
                return [{"year": a, "sensor": self._sensor_for(a), "day": day, "label": day}]
            return [{"year": a, "sensor": self._sensor_for(a), "label": str(a)}]
        day = self.dt.date().toString("yyyy-MM-dd")
        a = self.dt.date().year()
        return [{"year": a, "sensor": self._sensor_for(a), "day": day, "label": day}]

    def _can_download(self):
        if self._busy():
            return False, ""
        if self.state != "connected":
            return False, tr("Connect to Earth Engine first (top of this window).")
        if not self._area_ok:
            return False, self._area_msg
        if self.source() != "MAPBIOMAS" and not self.products():
            return False, tr("Tick at least one image type (vegetation colours, natural colours or an index).")
        if self._area_km2 > MAX_AREA_KM2:
            return False, tr("The area is very large (about %d km²). Select fewer polygons or a smaller area; "
                             "this limit avoids freezing QGIS and filling the disk.") % self._area_km2
        if self.mode() == 2 and self.sp_from.value() > self.sp_to.value():
            return False, tr("The first year is after the last year.")
        if not self.fw_folder.filePath().strip():
            return False, tr("Choose a folder to save the images.")
        return True, ""

    def _refresh(self, *_):
        if not self._ready:
            return
        s = self.source()
        mb = s == "MAPBIOMAS"
        fixed = mb                  # sources where you pick a year, not a date
        mode = self.mode()
        if mode < 0:
            return
        self.b_day.setEnabled(not fixed)
        if fixed and mode == 0:
            self.b_year.setChecked(True)
            return  # the toggle fires _refresh again
        self.b_year.setText(tr("One year\nMap of the chosen year") if mb else
                            tr("Best image of a year\nThe plugin finds the clearest"))
        self.pages.setCurrentIndex(mode)
        self.b_list.setVisible(not fixed)
        self.lb_year_hint.setVisible(not fixed)
        self.w_months.setVisible(not fixed and mode in (1, 2))
        self.lb_months_hint.setVisible(not fixed and mode in (1, 2))
        self.ck_fill.setVisible(not fixed)
        self.ck_s2.setVisible(s == "AUTO" and mode in (1, 2))
        self.sp_s2clear.setEnabled(s == "AUTO" and self.ck_s2.isChecked())
        self.w_products.setVisible(not fixed)
        self.w_indices.setVisible(not fixed)
        self.lb_indices.setVisible(not fixed)
        self.lb_product.setVisible(not fixed)
        self.ed_asset.setEnabled(mb)
        if mode == 2 or fixed:
            self.table.hide()
            self.lb_check.hide()
        self.lb_source.setText({
            "AUTO": tr("Landsat 4/5 up to 2012 and Landsat 8/9 from 2013, chosen for each year. Landsat 7 is not "
                       "used because its images have black stripes (sensor fault). Landsat 5 ends in May 2012, "
                       "so 2012 has only a few months."),
            "L89": tr("Landsat 8 starts in 2013 and Landsat 9 in late 2021. Each passes every 16 days."),
            "L45": tr("Landsat 4 covers 1982-1993 and Landsat 5 1984 to May 2012. Landsat 7 is not used (stripes)."),
            "S2": tr("Sentinel-2 passes every 5 days (full coverage from 2017)."),
            "MAPBIOMAS": tr("Downloads the class raster (forest, pasture, etc.) of the year. "
                            "One file per year. Beta: the data path may need adjusting in the advanced options."),
        }[s])
        self._summary()
        ok, reason = self._can_download()
        self.b_download.setEnabled(ok)
        self.b_check.setEnabled(not self._busy() and self.state == "connected")
        self.b_list.setEnabled(not self._busy() and self.state == "connected")
        self.b_connect.setEnabled(not self._busy())
        if not self._busy():
            # Show why the button is off; never wipe a success/progress message with an empty reason.
            if reason:
                self.lb_status.setText("<span style='color:#c62828'>%s</span>" % reason)
                self._reason_shown = True
            elif self._reason_shown:
                self.lb_status.setText("")
                self._reason_shown = False

    def _summary(self):
        try:
            mode, s = self.mode(), self.source()
            names = month_names()
            window = tr("between %s and %s") % (names[self.cb_m_from.currentData() - 1],
                                                 names[self.cb_m_to.currentData() - 1])
            src = self.cb_source.currentText().split(" - ")[0].split(" (")[0]
            if s == "MAPBIOMAS":
                if mode == 2:
                    n = max(0, self.sp_to.value() - self.sp_from.value() + 1)
                    t = tr("<b>%d MapBiomas maps</b>, from %d to %d") % (n, self.sp_from.value(), self.sp_to.value())
                else:
                    t = tr("<b>1 MapBiomas map</b> of %d") % self.sp_year.value()
            elif mode == 0:
                t = tr("<b>1 image</b> from %s (%s)") % (self.dt.date().toString("yyyy-MM-dd"), src)
            elif mode == 1:
                t = tr("<b>1 image</b>: the clearest of %d, %s (%s)") % (self.sp_year.value(), window, src)
            else:
                a0, a1 = self.sp_from.value(), self.sp_to.value()
                t = tr("<b>%d images</b>, one per year from %d to %d: the clearest of each year, %s (%s)") % (
                    max(0, a1 - a0 + 1), a0, a1, window, src)
            if s != "MAPBIOMAS" and len(self.products()) > 1:
                t += " " + tr("(%d files each)") % len(self.products())
            self.lb_summary.setText(tr("Will download %s.<br>Each one is saved in the folder below and "
                                       "opens in QGIS.") % t)
        except Exception:
            self.lb_summary.setText("")

    # ================================================================ settings
    def _default_folder(self):
        home = QgsProject.instance().homePath()
        if home:
            return os.path.join(home, "gee_downloads")
        return os.path.join(os.path.expanduser("~"), "GEE_Downloads")

    def _load_settings(self):
        st = QgsSettings()
        self.ed_project.setText(str(st.value(SETTINGS + "project", "")))
        self.fw_folder.setFilePath(str(st.value(SETTINGS + "folder", self._default_folder())))
        self.ck_skip.setChecked(str(st.value(SETTINGS + "skip", "true")).lower() == "true")
        self.sp_buffer.setValue(int(st.value(SETTINGS + "buffer", 500)))
        self.ck_fill.setChecked(str(st.value(SETTINGS + "fill", "true")).lower() == "true")
        self.ck_s2.setChecked(str(st.value(SETTINGS + "prefer_s2", "true")).lower() == "true")
        self.sp_s2clear.setValue(int(st.value(SETTINGS + "s2_clear", 95)))
        prods = str(st.value(SETTINGS + "products", "COLOR")).split(",")
        self.ck_false.setChecked("COLOR" in prods)
        self.ck_natural.setChecked("NATURAL" in prods)
        for k in core.INDEX_ORDER:
            self.ck_idx[k].setChecked(k in prods)
        self.cb_m_from.setCurrentIndex(int(st.value(SETTINGS + "month_from", 1)) - 1)
        self.cb_m_to.setCurrentIndex(int(st.value(SETTINGS + "month_to", 12)) - 1)
        saved_source = str(st.value(SETTINGS + "source", "AUTO"))
        idx = self.cb_source.findData("L45" if saved_source == "L57" else saved_source)
        self.cb_source.setCurrentIndex(max(0, idx))
        btn = self.mode_group.button(int(st.value(SETTINGS + "mode", 1)))
        if btn is not None:
            btn.setChecked(True)

    def _save_settings(self):
        st = QgsSettings()
        st.setValue(SETTINGS + "project", self.ed_project.text().strip())
        st.setValue(SETTINGS + "folder", self.fw_folder.filePath())
        st.setValue(SETTINGS + "skip", self.ck_skip.isChecked())
        st.setValue(SETTINGS + "buffer", self.sp_buffer.value())
        st.setValue(SETTINGS + "fill", self.ck_fill.isChecked())
        st.setValue(SETTINGS + "prefer_s2", self.ck_s2.isChecked())
        st.setValue(SETTINGS + "s2_clear", self.sp_s2clear.value())
        st.setValue(SETTINGS + "products", ",".join(self.products()))
        st.setValue(SETTINGS + "month_from", self.cb_m_from.currentData())
        st.setValue(SETTINGS + "month_to", self.cb_m_to.currentData())
        st.setValue(SETTINGS + "source", self.source())
        st.setValue(SETTINGS + "mode", self.mode())

    # ================================================================ helpers
    def _log(self, text):
        self.log.appendPlainText(text)

    def _status(self, html, error=False):
        color = "#c62828" if error else "palette(text)"
        self._reason_shown = False
        self.lb_status.setText("<span style='color:%s'>%s</span>" % (color, html))
        self._log(html.replace("<b>", "").replace("</b>", ""))

    def _row_selected(self):
        sel = self.table.selectedItems()
        if sel:
            d = QDate.fromString(self.table.item(sel[0].row(), 0).text(), "yyyy-MM-dd")
            self.dt.blockSignals(True)
            self.dt.setDate(d)
            self.dt.blockSignals(False)
            self._summary()

    # ================================================================ actions
    def _check_dates(self):
        """Count scenes for one day, or list the dates of a year, with their cloud/clear score.
        The search runs in a background thread; the window and QGIS stay responsive."""
        if self.ee is None or self._busy():
            return
        try:
            area, region, _crs, _bounds = self._context()
            plan = {"area": area, "region": region, "count_day": ""}
            if self.mode() == 0:
                sensor = self._sensor_for(self.dt.date().year())
                plan["count_day"] = self.dt.date().toString("yyyy-MM-dd")
                plan["start"] = self.dt.date().addDays(-30).toString("yyyy-MM-dd")
                plan["end"] = self.dt.date().addDays(31).toString("yyyy-MM-dd")
            else:
                year = self.sp_year.value()
                sensor = self._sensor_for(year)
                m0, m1 = self.cb_m_from.currentData(), self.cb_m_to.currentData()
                plan["start"] = "%d-%02d-01" % (year, m0)
                plan["end"] = "%d-01-01" % (year + 1) if m1 >= 12 else "%d-%02d-01" % (year, m1 + 1)
                self.lb_check.setText(tr("Dates sorted from clearest to cloudiest. Click a row to choose; "
                                         "with no choice, the first one is downloaded."))
                self.lb_check.show()
            plan["sensor"] = sensor
            plan["fill"] = self.fill_days(sensor)
            plan["cache_key"] = "%s|%s" % (_crs, ",".join("%.1f" % b for b in _bounds))
        except AreaError as exc:
            self._status(str(exc), error=True)
            return
        except Exception as exc:
            self._status(error_text("other", str(exc)), error=True)
            return
        self._status(tr("Looking for dates... (can take a few seconds)"))
        QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
        self.dates_worker = DatesWorker(self.ee, plan, self)
        self.dates_worker.done.connect(self._dates_done)
        self.dates_worker.failed.connect(self._dates_failed)
        self.dates_worker.finished.connect(self._dates_finished)
        self.dates_worker.start()
        self._refresh()

    def _dates_finished(self):
        QApplication.restoreOverrideCursor()
        self._refresh()

    def _dates_failed(self, code, detail):
        self._status(error_text(code, detail), error=True)

    def _dates_done(self, n, rows):
        if n > 0:
            self.table.hide()
            self.lb_check.setText("<span style='color:#2e7d32'>✔ %s</span>" % (
                tr("%d scene(s) on this day. You can download.") % n))
            self.lb_check.show()
            self._status(tr("%d scene(s) on this day. You can download.") % n)
            return
        if n == 0:
            self.lb_check.setText("<span style='color:#c62828'>%s</span> %s" % (
                tr("No image on this day."), tr("Nearby dates (within 30 days) are listed below; click one.")))
            self.lb_check.show()
        self.table.setRowCount(0)
        for r in rows:
            i = self.table.rowCount()
            self.table.insertRow(i)
            vals = [r["date"], r["sats"], str(r["scenes"]),
                    "" if r["cloud"] is None else "%.1f" % r["cloud"],
                    "" if r["clear"] is None else "%.0f" % (100 * r["clear"]),
                    "" if r.get("coverage") is None else "%.0f" % (100 * r["coverage"])]
            for j, val in enumerate(vals):
                self.table.setItem(i, j, QTableWidgetItem(val))
        self.table.setVisible(bool(rows))
        if not rows:
            self.lb_check.setText("<span style='color:#c62828'>%s</span> %s" % (
                tr("No images found in this period."), tr("Try another year, other months or another source.")))
            self.lb_check.show()
        self._status(tr("%d date(s) found.") % len(rows))

    def _download(self):
        ok, reason = self._can_download()
        if not ok:
            self._status(reason, error=True)
            return
        try:
            items = self._items()
            if len(items) > LARGE_BATCH:
                answer = QMessageBox.question(
                    self, tr("GEE Image Downloader"),
                    tr("This will download %d images. It can take a long time and use a lot of disk "
                       "space. Continue?") % len(items))
                if answer != QMessageBox.StandardButton.Yes:
                    return
            area, region, crs, bounds = self._context()
            self._save_settings()
            if self.mode() == 2:
                group = tr("GEE time series %d-%d") % (self.sp_from.value(), self.sp_to.value())
            else:
                group = tr("GEE images")
            params = {
                "items": items, "group": group, "folder": self.fw_folder.filePath().strip(),
                "source": self.source(), "area": area, "region": region, "crs": crs, "bounds_crs": bounds,
                "month_from": self.cb_m_from.currentData(), "month_to": self.cb_m_to.currentData(),
                "asset": self.ed_asset.text().strip(), "skip_existing": self.ck_skip.isChecked(),
                "fill": self.ck_fill.isChecked(), "products": self.products(),
                "prefer_s2": self.ck_s2.isChecked() and self.source() == "AUTO",
                "s2_min_clear": self.sp_s2clear.value() / 100.0,
                "cache_key": None if bounds is None else "%s|%s" % (crs, ",".join("%.1f" % b for b in bounds)),
            }
            self._last_folder = params["folder"]
        except AreaError as exc:
            self._status(str(exc), error=True)
            return
        except Exception as exc:
            self._status(error_text("other", str(exc)), error=True)
            return
        self.b_open.hide()
        self._layers_this_run = 0
        self.bar.setMaximum(len(items))
        self.bar.setValue(0)
        self.bar.show()
        self.worker = DownloadWorker(self.ee, params, self)
        self.worker.log.connect(self._log)
        self.worker.progress.connect(self._on_progress)
        self.worker.layer_ready.connect(self._queue_layer)
        self.worker.finished_all.connect(self._on_finished)
        self.worker.finished.connect(self._refresh)
        self.b_cancel.setEnabled(True)
        self.b_bg.setEnabled(True)
        self.b_download.setEnabled(False)
        self.worker.start()
        try:   # keep the download from competing with QGIS's own drawing for the processor
            self.worker.setPriority(QThread.Priority.LowPriority)
        except Exception:
            pass
        self._on_progress(0, len(items), items[0]["label"])

    def _cancel(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self._status(tr("Cancelling after the current download..."))

    def _downloading(self):
        return self.worker is not None and self.worker.isRunning()

    def _go_background(self):
        """Hide the window; the download keeps running and a progress bar shows in the QGIS message bar."""
        if self._downloading() and self._bg_widget is None:
            try:
                from qgis.core import Qgis
                level = getattr(Qgis, "MessageLevel", Qgis).Info
                bar = self.iface.messageBar()
                w = bar.createMessage(tr("GEE Image Downloader"), "")
                lay = w.layout()
                self._bg_label = QLabel(tr("Downloading in the background..."))
                self._bg_bar = QProgressBar()
                self._bg_bar.setMaximum(max(1, self.bar.maximum()))
                self._bg_bar.setValue(self.bar.value())
                self._bg_bar.setMaximumWidth(220)
                b_show = QPushButton(tr("Show window"))
                b_show.clicked.connect(self._show_again)
                b_stop = QPushButton(tr("Cancel"))
                b_stop.clicked.connect(self._cancel)
                for widget in (self._bg_label, self._bg_bar, b_show, b_stop):
                    lay.addWidget(widget)
                self._bg_widget = w
                bar.pushWidget(w, level, 0)
            except Exception:
                self._remove_bg_message()
        self.hide()

    def _show_again(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _remove_bg_message(self):
        if self._bg_widget is not None:
            try:
                self.iface.messageBar().popWidget(self._bg_widget)
            except Exception:
                pass
        self._bg_widget = self._bg_bar = self._bg_label = None

    def reject(self):  # Esc / close button: never stop a running download
        if self._downloading():
            self._go_background()
            return
        super().reject()

    def closeEvent(self, event):
        if self._downloading():
            event.ignore()
            self._go_background()
            return
        super().closeEvent(event)

    def shutdown(self):
        """Called when the plugin is unloaded: stop background work cleanly."""
        self._remove_bg_message()
        for w in (self.worker, self.connect_worker, self.dates_worker):
            if w is not None and w.isRunning():
                if hasattr(w, "cancel"):
                    w.cancel()
                w.wait(3000)

    def _on_progress(self, done, total, label):
        self.bar.setValue(done)
        self._status(tr("Downloading %d of %d: <b>%s</b>") % (done + 1, total, label))
        if self._bg_bar is not None:
            self._bg_bar.setMaximum(total)
            self._bg_bar.setValue(done)
            self._bg_label.setText(tr("Downloading %d of %d: %s") % (done + 1, total, label))

    def _on_finished(self, ok, failed):
        self.bar.setValue(self.bar.maximum())
        self.b_cancel.setEnabled(False)
        self.b_bg.setEnabled(False)
        self._remove_bg_message()
        if ok:
            self.b_open.show()
        if ok and not failed:
            msg = tr("%d image(s) are now in QGIS, in the layer tree group.") % ok
            self._status("<span style='color:#2e7d32'>✔ %s</span>" % msg)
            self.iface.messageBar().pushSuccess(tr("GEE Image Downloader"), msg)
        elif ok:
            msg = tr("Finished: %d image(s) in QGIS and %d failure(s). Open 'Details' to see which.") % (ok, failed)
            self._status(msg, error=True)
            self.log_box.setCollapsed(False)
            self.iface.messageBar().pushWarning(tr("GEE Image Downloader"), msg)
        else:
            msg = tr("Nothing was downloaded. Open 'Details' to see why.")
            self._status(msg, error=True)
            self.log_box.setCollapsed(False)
        self._refresh()

    def _queue_layer(self, path, name, group, kind=""):
        """Layers are added one at a time with a short pause between them, so QGIS stays responsive."""
        self._load_queue.append((path, name, group, kind))
        if len(self._load_queue) > 1 and not self._canvas_frozen:
            self._freeze_canvas(True)
        if not self._load_timer.isActive():
            self._load_timer.start(60)

    def _freeze_canvas(self, on):
        try:
            self.iface.mapCanvas().freeze(on)
            self._canvas_frozen = on
        except Exception:
            self._canvas_frozen = False

    def _load_next(self):
        if not self._load_queue:
            return
        item = self._load_queue.pop(0)
        try:
            self._load_layer(*item)
        except Exception as exc:
            self._log("  WARNING: could not add %s to QGIS (%s)" % (item[1], exc))
        if self._load_queue:
            self._load_timer.start(120)
        elif self._canvas_frozen:
            self._freeze_canvas(False)
            try:
                self.iface.mapCanvas().refresh()
            except Exception:
                pass

    def _load_layer(self, path, name, group, kind=""):
        layer = QgsRasterLayer(path, name)
        if not layer.isValid():
            self._log("  WARNING: QGIS could not open %s" % path)
            return
        project = QgsProject.instance()
        if kind in core.INDICES:
            self._style_index(layer, kind, path)
        elif kind == "CLASS":
            self._style_mapbiomas(layer, path)
        project.addMapLayer(layer, False)
        root = project.layerTreeRoot()
        node = root.findGroup(group) or root.insertGroup(0, group)
        first = self._layers_this_run == 0     # first layer of this download: shown and zoomed to
        self._layers_this_run += 1
        tree_layer = node.insertLayer(0, layer)  # newest on top
        if not first:
            # Only the first layer is drawn: a series of 30+ big rasters all visible would make QGIS crawl.
            try:
                tree_layer.setItemVisibilityChecked(False)
            except Exception:
                pass
        if first:
            canvas = self.iface.mapCanvas()
            xform = QgsCoordinateTransform(layer.crs(), canvas.mapSettings().destinationCrs(),
                                           project.transformContext())
            canvas.setExtent(xform.transformBoundingBox(layer.extent()))
            canvas.refresh()

    @staticmethod
    def _save_style(layer, path):
        """Saves the style next to the GeoTIFF (.qml), so reopening the file in QGIS keeps it."""
        try:
            layer.saveNamedStyle(os.path.splitext(path)[0] + ".qml")
        except Exception:
            pass

    @staticmethod
    def _style_index(layer, index, path=None):
        """Colour ramp for a vegetation index. Falls back to grey on any API difference."""
        try:
            from qgis.core import QgsColorRampShader, QgsRasterShader, QgsSingleBandPseudoColorRenderer
            from qgis.PyQt.QtGui import QColor
            stops = core.INDEX_STYLE[index]
            shader_fn = QgsColorRampShader()
            shader_fn.setColorRampType(getattr(QgsColorRampShader, "Type", QgsColorRampShader).Interpolated)
            shader_fn.setColorRampItemList([QgsColorRampShader.ColorRampItem(v, QColor(c), lab) for v, c, lab in stops])
            shader = QgsRasterShader()
            shader.setRasterShaderFunction(shader_fn)
            renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
            renderer.setClassificationMin(stops[0][0])
            renderer.setClassificationMax(stops[-1][0])
            layer.setRenderer(renderer)
            if path:
                GeeDialog._save_style(layer, path)
        except Exception:
            pass

    @staticmethod
    def _style_mapbiomas(layer, path=None):
        """Official MapBiomas legend (colours and names, Portuguese or English by the QGIS language).
        Only the classes that exist in the raster are listed; all of them if that cannot be read."""
        try:
            from qgis.core import QgsPalettedRasterRenderer
            from qgis.PyQt.QtGui import QColor
            from . import mapbiomas_legend as legend
            from .i18n import language
            pt = language() == "pt"
            known = legend.by_value()
            present = None
            try:
                if layer.width() * layer.height() <= 40_000_000:
                    found = QgsPalettedRasterRenderer.classDataFromRaster(layer.dataProvider(), 1)
                    present = {int(c.value) for c in found}
            except Exception:
                present = None
            classes = []
            for value, hexcolor, en, pt_name in legend.CLASSES:
                if present is None or value in present:
                    classes.append(QgsPalettedRasterRenderer.Class(
                        value, QColor(hexcolor), "%d - %s" % (value, pt_name if pt else en)))
            for value in sorted((present or set()) - set(known)):   # a class this plugin version does not know
                classes.append(QgsPalettedRasterRenderer.Class(value, QColor("#999999"), str(value)))
            layer.setRenderer(QgsPalettedRasterRenderer(layer.dataProvider(), 1, classes))
            if path:
                GeeDialog._save_style(layer, path)
        except Exception:
            pass

    def _open_folder(self):
        if self._last_folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._last_folder))

    def _about(self):
        box = QMessageBox(self)
        box.setWindowTitle(tr("About GEE Image Downloader"))
        box.setIconPixmap(QPixmap(os.path.join(os.path.dirname(__file__), "logo.png")).scaledToWidth(
            120, Qt.TransformationMode.SmoothTransformation))
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(
            "<b>GEE Image Downloader %s</b><br><br>%s<br><br>%s<br><br>%s" % (
                plugin_version(),
                tr("Downloads Landsat, Sentinel-2 and MapBiomas images from Google Earth Engine straight into "
                   "QGIS, including multi-year time series."),
                tr("Data: Landsat (USGS/NASA); Sentinel-2 (contains modified Copernicus Sentinel data); "
                   "MapBiomas (MapBiomas Project, see mapbiomas.org for its terms)."),
                tr("Earth Engine is free for non-commercial use; commercial use needs a commercial project. "
                   "You are responsible for following Google's terms of service.")))
        box.exec()
