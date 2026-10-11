# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
"""Makes the plugin findable in the Processing Toolbox (and its search box).

The single algorithm has no parameters: running it opens the plugin window, where everything is chosen
with the mouse. It is a thin shortcut, so nothing here can affect the downloads themselves.
"""

import os

from qgis.core import QgsProcessingAlgorithm, QgsProcessingProvider
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtGui import QIcon

from .i18n import tr

_ICON = os.path.join(os.path.dirname(__file__), "icon_toolbar.png")


def _flag(name):
    """QgsProcessingAlgorithm flags moved between QGIS 3 and 4; look it up either way."""
    try:
        return getattr(QgsProcessingAlgorithm, name)
    except AttributeError:
        return getattr(QgsProcessingAlgorithm.Flag, name[4:] if name.startswith("Flag") else name)


class OpenDownloaderAlgorithm(QgsProcessingAlgorithm):
    """Opens the GEE Image Downloader window."""

    opener = None  # set by the plugin: a callable that shows the window

    def name(self):
        return "download_satellite_images"

    def displayName(self):
        return tr("Download satellite images (Landsat, Sentinel-2, MapBiomas)")

    def group(self):
        return tr("Download")

    def groupId(self):
        return "download"

    def tags(self):
        return ["gee", "earth engine", "landsat", "sentinel", "sentinel-2", "mapbiomas", "ndvi",
                "satellite", "imagery", "download", "time series", "multitemporal"]

    def shortHelpString(self):
        return tr("Opens the GEE Image Downloader window: pick a polygon, the imagery and the years, and the "
                  "images are saved as GeoTIFF and opened in QGIS. Needs a Google Earth Engine account.")

    def icon(self):
        return QIcon(_ICON)

    def flags(self):
        # The window must be created in the main thread.
        return super().flags() | _flag("FlagNoThreading")

    def createInstance(self):
        return OpenDownloaderAlgorithm()

    def initAlgorithm(self, config=None):
        pass

    def processAlgorithm(self, parameters, context, feedback):
        if OpenDownloaderAlgorithm.opener is not None:
            QTimer.singleShot(0, OpenDownloaderAlgorithm.opener)
        feedback.pushInfo(tr("The GEE Image Downloader window is open."))
        return {}


class GeeProvider(QgsProcessingProvider):
    def id(self):
        return "gee_image_downloader"

    def name(self):
        return "GEE Image Downloader"

    def longName(self):
        return self.name()

    def icon(self):
        return QIcon(_ICON)

    def loadAlgorithms(self):
        self.addAlgorithm(OpenDownloaderAlgorithm())
