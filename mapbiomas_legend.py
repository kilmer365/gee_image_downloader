# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
"""Official MapBiomas Brazil legend (Collection 10): class value, colour, English and Portuguese names.

Source: MapBiomas "Legenda Colecao 10 - Legend Code" (brasil.mapbiomas.org). Pure data, no QGIS imports.
"""

# (value, hex colour, English name, Portuguese name)
CLASSES = [
    (1, "#1f8d49", "Forest", "Floresta"),
    (3, "#1f8d49", "Forest Formation", "Formação Florestal"),
    (4, "#7dc975", "Savanna Formation", "Formação Savânica"),
    (5, "#04381d", "Mangrove", "Mangue"),
    (6, "#007785", "Floodable Forest", "Floresta Alagável"),
    (49, "#02d659", "Wooded Sandbank Vegetation", "Restinga Arbórea"),
    (10, "#d6bc74", "Herbaceous and Shrubby Vegetation", "Vegetação Herbácea e Arbustiva"),
    (11, "#519799", "Wetland", "Campo Alagado e Área Pantanosa"),
    (12, "#d6bc74", "Grassland", "Formação Campestre"),
    (32, "#fc8114", "Hypersaline Tidal Flat", "Apicum"),
    (29, "#ffaa5f", "Rocky Outcrop", "Afloramento Rochoso"),
    (50, "#ad5100", "Herbaceous Sandbank Vegetation", "Restinga Herbácea"),
    (14, "#ffefc3", "Farming", "Agropecuária"),
    (15, "#edde8e", "Pasture", "Pastagem"),
    (18, "#e974ed", "Agriculture", "Agricultura"),
    (19, "#c27ba0", "Temporary Crop", "Lavoura Temporária"),
    (39, "#f5b3c8", "Soybean", "Soja"),
    (20, "#db7093", "Sugar cane", "Cana"),
    (40, "#c71585", "Rice", "Arroz"),
    (62, "#ff69b4", "Cotton (beta)", "Algodão (beta)"),
    (41, "#f54ca9", "Other Temporary Crops", "Outras Lavouras Temporárias"),
    (36, "#d082de", "Perennial Crop", "Lavoura Perene"),
    (46, "#d68fe2", "Coffee", "Café"),
    (47, "#9932cc", "Citrus", "Citrus"),
    (35, "#9065d0", "Palm Oil", "Dendê"),
    (48, "#e6ccff", "Other Perennial Crops", "Outras Lavouras Perenes"),
    (9, "#7a5900", "Forest Plantation", "Silvicultura"),
    (21, "#ffefc3", "Mosaic of Uses", "Mosaico de Usos"),
    (22, "#d4271e", "Non vegetated area", "Área não Vegetada"),
    (23, "#ffa07a", "Beach, Dune and Sand Spot", "Praia, Duna e Areal"),
    (24, "#d4271e", "Urban Area", "Área Urbanizada"),
    (30, "#9c0027", "Mining", "Mineração"),
    (75, "#c12100", "Photovoltaic Power Plant (beta)", "Usina Fotovoltaica (beta)"),
    (25, "#db4d4f", "Other non Vegetated Areas", "Outras Áreas não Vegetadas"),
    (26, "#2532e4", "Water", "Corpo D'água"),
    (33, "#2532e4", "River, Lake and Ocean", "Rio, Lago e Oceano"),
    (31, "#091077", "Aquaculture", "Aquicultura"),
    (27, "#ffffff", "Not Observed", "Não observado"),
]


def by_value():
    return {c[0]: c for c in CLASSES}
