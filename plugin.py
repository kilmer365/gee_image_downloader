# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
"""QGIS plugin entry point: registers the menu/toolbar action and opens the dialog."""

import os

from qgis.core import QgsApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .i18n import tr

MENU = "&GEE Image Downloader"


class GeeImageDownloader:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dialog = None
        self.toolbar = None
        self.provider = None

    def initGui(self):
        here = os.path.dirname(__file__)
        icon = QIcon(os.path.join(here, "icon_toolbar.png"))
        self.action = QAction(icon, tr("GEE Image Downloader"), self.iface.mainWindow())
        self.action.setToolTip(tr("Download satellite imagery from Google Earth Engine into QGIS"))
        self.action.triggered.connect(self.run)
        # Its own toolbar, always visible (the Raster toolbar is often hidden), plus the Raster menu.
        self.toolbar = self.iface.addToolBar("GEE Image Downloader")
        self.toolbar.setObjectName("GEEImageDownloaderToolbar")
        self.toolbar.addAction(self.action)
        self.iface.addPluginToRasterMenu(MENU, self.action)
        self._init_processing()

    def _init_processing(self):
        """Adds the shortcut to the Processing Toolbox; never allowed to break the plugin."""
        try:
            from .processing_provider import GeeProvider, OpenDownloaderAlgorithm
            OpenDownloaderAlgorithm.opener = self.run
            self.provider = GeeProvider()
            QgsApplication.processingRegistry().addProvider(self.provider)
        except Exception:
            self.provider = None

    def unload(self):
        if self.provider is not None:
            try:
                QgsApplication.processingRegistry().removeProvider(self.provider)
            except Exception:
                pass
            self.provider = None
        if self.action is not None:
            self.iface.removePluginRasterMenu(MENU, self.action)
            if self.toolbar is not None:
                self.toolbar.removeAction(self.action)
                self.iface.mainWindow().removeToolBar(self.toolbar)
                self.toolbar.deleteLater()
                self.toolbar = None
            self.action = None
        if self.dialog is not None:
            self.dialog.shutdown()
            self.dialog.deleteLater()
            self.dialog = None

    def run(self):
        from .dialog import GeeDialog  # imported lazily so QGIS starts fast
        if self.dialog is None:
            self.dialog = GeeDialog(self.iface, self.iface.mainWindow())
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
