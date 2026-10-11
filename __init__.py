# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later


def classFactory(iface):  # noqa: N802 (name required by QGIS)
    from .plugin import GeeImageDownloader
    return GeeImageDownloader(iface)
