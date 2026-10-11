# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-2.0-or-later
"""Tiny translation layer: English is the source language, Portuguese (pt) is provided.

Other languages fall back to English. To add a language, add a dictionary like _PT
and register it in _CATALOGS.
"""

from qgis.core import QgsSettings
from qgis.PyQt.QtCore import QLocale

_MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August",
              "September", "October", "November", "December"]
_MONTHS_PT = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
              "setembro", "outubro", "novembro", "dezembro"]

_PT = {
    "%s needs a red-edge band, which only Sentinel-2 has; skipped for this image.": "%s precisa da banda red edge, que só o Sentinel-2 tem; ignorado nesta imagem.",
    "Vegetation indices:": "Índices de vegetação:",
    "Tick at least one image type (vegetation colours, natural colours or an index).": "Marque pelo menos um tipo de imagem (cores de vegetação, cores naturais ou um índice).",
    "Vegetation vigour and canopy cover (-1 to 1). Near 1: dense, vigorous vegetation; near 0: sparse vegetation or bare soil; negative: water, snow or clouds. Clouds are not removed.": "Vigor da vegetação e cobertura do dossel (-1 a 1). Perto de 1: vegetação densa e vigorosa; perto de 0: vegetação esparsa ou solo exposto; negativo: água, neve ou nuvens. As nuvens não são removidas.",
    "Like NDVI but with the green band. Saturates later, so it is better for mid-to-late crop stages; related to chlorophyll, water and nitrogen uptake in dense canopies.": "Como o NDVI, mas com a banda verde. Satura mais tarde, então é melhor para fases intermediárias e finais da cultura; ligado à clorofila, à água e à absorção de nitrogênio em dosséis densos.",
    "Uses the red-edge band (Sentinel-2 only). Follows chlorophyll and leaf nitrogen; useful in advanced crop stages where NDVI saturates, and to spot vigour loss early.": "Usa a banda red edge (só Sentinel-2). Acompanha a clorofila e o nitrogênio foliar; útil em fases avançadas da cultura, quando o NDVI satura, e para notar perda de vigor cedo.",
    "NDVI corrected for the soil background. Best for early stages, emergence, crops that do not close the canopy and woody crops, where NDVI can mislead.": "NDVI corrigido para o efeito do solo. Melhor para fases iniciais, emergência, culturas que não fecham o dossel e culturas lenhosas, em que o NDVI pode enganar.",
    "(NIR - SWIR) / (NIR + SWIR): water content of the vegetation. High: plenty of water and cover; low: little water or sparse cover. Not a map of water bodies.": "(NIR - SWIR) / (NIR + SWIR): conteúdo de água da vegetação. Alto: muita água e cobertura; baixo: pouca água ou cobertura esparsa. Não é um mapa de corpos d'água.",
    "Download satellite images (Landsat, Sentinel-2, MapBiomas)": "Baixar imagens de satélite (Landsat, Sentinel-2, MapBiomas)",
    "Download": "Baixar",
    "Opens the GEE Image Downloader window: pick a polygon, the imagery and the years, and the images are saved as GeoTIFF and opened in QGIS. Needs a Google Earth Engine account.": "Abre a janela do GEE Image Downloader: escolha um polígono, as imagens e os anos, e elas são salvas em GeoTIFF e abertas no QGIS. Precisa de uma conta do Google Earth Engine.",
    "The GEE Image Downloader window is open.": "A janela do GEE Image Downloader está aberta.",
    "No Sentinel-2 image found; using the clearest Landsat.": "Nenhuma imagem Sentinel-2 encontrada; usando a Landsat mais limpa.",
    "Prefer Sentinel-2 when it has a clean, complete image (2017 onwards)": "Preferir Sentinel-2 quando houver imagem limpa e completa (a partir de 2017)",
    "Sentinel-2 has 10 m pixels, sharper than Landsat's 30 m. For each year the plugin first looks for a Sentinel-2 image that covers the whole area with almost no clouds; if there is none, it uses the clearest Landsat of the year. Before 2017 only Landsat exists.": "O Sentinel-2 tem pixels de 10 m, mais nítidos que os 30 m da Landsat. Para cada ano, o complemento procura primeiro uma imagem Sentinel-2 que cubra toda a área com quase nenhuma nuvem; se não houver, usa a Landsat mais limpa do ano. Antes de 2017 só existe Landsat.",
    "Sentinel-2 is chosen only if at least this much of the area is free of clouds and shadows (and fully covered). Lower it to accept more Sentinel-2 images.": "O Sentinel-2 só é escolhido se pelo menos esta parte da área estiver livre de nuvens e sombras (e totalmente coberta). Diminua para aceitar mais imagens Sentinel-2.",
    "Sentinel-2 is clean and complete: using it (10 m).": "Sentinel-2 limpo e completo: usando-o (10 m).",
    "Sentinel-2 is not clean and complete enough (best: %.0f%% clear); using the clearest Landsat.": "Sentinel-2 não está limpo e completo o bastante (melhor: %.0f%% limpo); usando a Landsat mais limpa.",
    "Sentinel-2 minimum clear area:": "Área limpa mínima do Sentinel-2:",
    "The Earth Engine Python library is not installed.":
        "A biblioteca Python do Earth Engine não está instalada.",
    "Enter your Earth Engine project ID.":
        "Informe o ID do seu projeto do Earth Engine.",
    "This project is not registered for Earth Engine. Register it (free for non-commercial use) and try again.":
        "Este projeto não está registrado no Earth Engine. Registre-o (gratuito para uso não comercial) e tente de novo.",
    "The Earth Engine API is not enabled for this Google Cloud project. Enable it in the Google Cloud console and try again.":
        "A API do Earth Engine não está ativada neste projeto do Google Cloud. Ative-a no console do Google Cloud e tente de novo.",
    "Your Google account has no permission on this project. Check the project ID and the account you signed in with.":
        "Sua conta Google não tem permissão neste projeto. Confira o ID do projeto e a conta usada no login.",
    "Earth Engine quota or rate limit reached. Wait a few minutes and try again.":
        "Limite de uso do Earth Engine atingido. Espere alguns minutos e tente de novo.",
    "The area is too large for one download. Use a smaller area or margin.":
        "A área é grande demais para um download. Use uma área ou margem menor.",
    "Network problem while talking to Google. Check your connection and the QGIS proxy settings.":
        "Problema de rede ao falar com o Google. Confira sua conexão e as configurações de proxy do QGIS.",
    "Sign-in with Google failed or was cancelled.":
        "O login no Google falhou ou foi cancelado.",
    "Could not read the MapBiomas data for this year. Check the asset path in the advanced options.":
        "Não consegui ler os dados do MapBiomas deste ano. Confira o caminho do asset nas opções avançadas.",
    "No image found for this date or period.":
        "Nenhuma imagem encontrada para esta data ou período.",
    "Earth Engine is busy right now. The plugin already retried. Wait a minute and try again, or use a smaller area or a shorter range of months.":
        "O Earth Engine está ocupado agora. O plugin já tentou de novo. Espere um minuto e tente outra vez, ou use uma área menor ou menos meses.",
    "Unexpected error: %s": "Erro inesperado: %s",
    "GEE Image Downloader": "GEE Image Downloader",
    "Google Earth Engine": "Google Earth Engine",
    "Copy command": "Copiar comando",
    "I installed it, check again": "Já instalei, verificar de novo",
    "your Google Cloud project with Earth Engine, e.g. my-project-123":
        "seu projeto do Google Cloud com Earth Engine, ex.: meu-projeto-123",
    "The ID of the Google Cloud project registered for Earth Engine.":
        "O ID do projeto do Google Cloud registrado no Earth Engine.",
    "Connect": "Conectar",
    "Change project or account": "Trocar projeto ou conta",
    "1. Which area?": "1. Qual é a área?",
    "Polygon layer of the property or area of interest.":
        "Camada de polígono do imóvel ou da área de interesse.",
    "Use only the features selected on the map": "Usar só as feições selecionadas no mapa",
    "2. What do you want to download?": "2. O que você quer baixar?",
    "One date\nI pick the day": "Uma data\nEu escolho o dia",
    "Best image of a year\nThe plugin finds the clearest":
        "Melhor imagem do ano\nO plugin acha a mais limpa",
    "Series of years\nTime series, e.g. 1995 to today":
        "Série de anos\nMultitemporal, ex.: 1995 até hoje",
    "Automatic by year (recommended)": "Automático pelo ano (recomendado)",
    "Landsat 8/9 - 2013 to today - 30 m": "Landsat 8/9 - de 2013 até hoje - 30 m",
    "Landsat 4/5 - up to 2012 - 30 m": "Landsat 4/5 - até 2012 - 30 m",
    "Sentinel-2 - 2017 to today - 10 m": "Sentinel-2 - de 2017 até hoje - 10 m",
    "MapBiomas Brazil - land cover (beta)": "MapBiomas Brasil - uso e cobertura da terra (beta)",
    "Imagery source:": "Fonte da imagem:",
    "Check if there is an image on this day": "Verificar se existe imagem nesse dia",
    "Day:": "Dia:",
    "Show available dates": "Ver as datas disponíveis",
    "If you do not pick a row in the table, the clearest date is downloaded.":
        "Se você não escolher uma linha da tabela, a data mais limpa é baixada.",
    "Year:": "Ano:",
    "Last 10 years": "Últimos 10 anos",
    "Tip: limit the months to the dry season of your region to avoid clouds.":
        "Dica: limite os meses à época seca da sua região para evitar nuvens.",
    "Tip: choose the dry season of your region to get fewer clouds.":
        "Dica: escolha a época seca da sua região para ter menos nuvens.",
    "Advanced options (you usually do not need these)":
        "Opções avançadas (normalmente não precisa mexer)",
    "Margin around the area, so the image is not cut at the property limit.":
        "Margem ao redor da área, para a imagem não ser cortada no limite do imóvel.",
    "Automatic (best UTM zone for the area)": "Automático (melhor fuso UTM para a área)",
    "Same as the layer (if projected)": "Igual ao da camada (se for projetado)",
    "Custom...": "Personalizado...",
    "Margin around the area:": "Margem ao redor da área:",
    "Output coordinate system:": "Sistema de coordenadas de saída:",
    "MapBiomas asset path:": "Caminho do asset do MapBiomas:",
    "Details of what is happening": "Detalhes do que está acontecendo",
    "3. Download": "3. Baixar",
    "Skip images already in the folder (lets you resume a long series)":
        "Pular imagens que já estão na pasta (permite retomar uma série longa)",
    "Download to QGIS": "Baixar para o QGIS",
    "Cancel": "Cancelar",
    "Open folder": "Abrir pasta",
    "About": "Sobre",
    "About GEE Image Downloader": "Sobre o GEE Image Downloader",
    "Project ID:": "ID do projeto:",
    "From": "De",
    "to": "até",
    "Shortcuts:": "Atalhos:",
    "Look for the image between": "Procurar a imagem entre",
    "and": "e",
    "Date": "Data",
    "(%d files each)": "(%d arquivos cada)",
    "False-colour composite: vegetation in green, bare soil in pink. The best one to tell forest, pasture and crops apart.": "Composição falsa-cor: vegetação em verde, solo exposto em rosa. A melhor para separar floresta, pastagem e lavoura.",
    "How the area looks to the human eye (red, green and blue bands).": "Como a área aparece ao olho humano (bandas vermelho, verde e azul).",
    "Image types:": "Tipos de imagem:",
    "Natural colours": "Cores naturais",
    "The area is very large (about %d km²). Select fewer polygons or a smaller area; this limit avoids freezing QGIS and filling the disk.": "A área é muito grande (cerca de %d km²). Selecione menos polígonos ou uma área menor; esse limite evita travar o QGIS e encher o disco.",
    "Vegetation colours": "Cores da vegetação",
    "natural colour": "cores naturais",
    "Keep working in QGIS": "Continuar trabalhando no QGIS",
    "Hides this window. The download continues in the background and a progress bar appears at the top of QGIS.": "Oculta esta janela. O download continua em segundo plano e uma barra de progresso aparece no topo do QGIS.",
    "Downloading in the background...": "Baixando em segundo plano...",
    "Downloading %d of %d: %s": "Baixando %d de %d: %s",
    "Show window": "Mostrar janela",
    "Download satellite imagery from Google Earth Engine into QGIS": "Baixar imagens de satélite do Google Earth Engine para o QGIS",
    "Complete the area with nearby dates (recommended on scene borders)": "Completar a área com datas próximas (recomendado em divisa de cenas)",
    "Neighbouring satellite tracks are imaged on different days. When the chosen date does not cover the whole area, the empty part is filled with the closest date (up to a few days away). The chosen date always has priority. Untick to use only the exact date.": "Faixas vizinhas do satélite são imageadas em dias diferentes. Quando a data escolhida não cobre toda a área, a parte vazia é preenchida com a data mais próxima (até alguns dias de diferença). A data escolhida sempre tem prioridade. Desmarque para usar somente a data exata.",
    "% area covered": "% da área coberta",
    "Warning: only %.0f%% of the area has data on the available dates.": "Aviso: somente %.0f%% da área tem dados nas datas disponíveis.",
    "Completing empty parts with dates up to %d days away.": "Completando as partes vazias com datas até %d dias de diferença.",
    "Satellite": "Satélite",
    "Scenes": "Cenas",
    "% cloud": "% nuvem",
    "% clear in area": "% limpo na área",
    "Save in:": "Salvar em:",
    "Still not found. Restart QGIS after installing and open this window again.":
        "Ainda não encontrei. Reinicie o QGIS depois de instalar e abra esta janela de novo.",
    "Choose a polygon layer in step 1.": "Escolha uma camada de polígonos no passo 1.",
    "Connect to Earth Engine first (top of this window).":
        "Conecte-se ao Earth Engine primeiro (no topo desta janela).",
    "The first year is after the last year.": "O ano inicial é maior que o final.",
    "Choose a folder to save the images.": "Escolha uma pasta para salvar as imagens.",
    "One year\nMap of the chosen year": "Um ano\nMapa do ano escolhido",
    "between %s and %s": "entre %s e %s",
    "Looking for dates... (can take a few seconds)": "Procurando datas... (pode levar alguns segundos)",
    "GEE images": "Imagens GEE",
    "Cancelling after the current download...": "Cancelando depois do download atual...",
    "Downloading %d of %d: <b>%s</b>": "Baixando %d de %d: <b>%s</b>",
    "%d image(s) are now in QGIS, in the layer tree group.":
        "%d imagem(ns) já estão no QGIS, no grupo da árvore de camadas.",
    "Nothing was downloaded. Open 'Details' to see why.":
        "Nada foi baixado. Abra 'Detalhes' para ver o motivo.",
    "saved: %s": "salvo: %s",
    "Download satellite imagery": "Baixar imagem de satélite",
    "Pick an area, say what you want and click download. The image opens straight in QGIS.":
        "Escolha a área, diga o que quer e clique em baixar. A imagem abre direto no QGIS.",
    "How do I get a project ID?": "Como obtenho um ID de projeto?",
    "%d to today": "%d até hoje",
    "One-time setup needed": "Configuração necessária (só uma vez)",
    "This plugin needs the Earth Engine Python library. Open the \"OSGeo4W Shell\" (Windows) or a terminal that uses the same Python as QGIS, run the command below, then restart QGIS or click the button.":
        "Este plugin precisa da biblioteca Python do Earth Engine. Abra o \"OSGeo4W Shell\" (Windows) ou um terminal que use o mesmo Python do QGIS, rode o comando abaixo e depois reinicie o QGIS ou clique no botão.",
    "This plugin needs the Earth Engine Python library. Open a terminal that uses the same Python as QGIS, run the command below, then restart QGIS or click the button.":
        "Este plugin precisa da biblioteca Python do Earth Engine. Abra um terminal que use o mesmo Python do QGIS, rode o comando abaixo e depois reinicie o QGIS ou clique no botão.",
    "No polygons found in layer '%s' (%d features, %d with geometry). Check that it is the right layer.":
        "Não achei polígonos na camada '%s' (%d feições, %d com geometria). Confira se é a camada certa.",
    " · downloaded in %d blocks (automatic)": " · download em %d blocos (automático)",
    "Landsat 4/5 up to 2012 and Landsat 8/9 from 2013, chosen for each year. Landsat 7 is not used because its images have black stripes (sensor fault). Landsat 5 ends in May 2012, so 2012 has only a few months.":
        "Landsat 4/5 até 2012 e Landsat 8/9 de 2013 em diante, escolhidos para cada ano. O Landsat 7 não é usado porque suas imagens têm faixas pretas (falha do sensor). O Landsat 5 termina em maio de 2012, então 2012 tem poucos meses.",
    "Landsat 8 starts in 2013 and Landsat 9 in late 2021. Each passes every 16 days.":
        "O Landsat 8 começa em 2013 e o Landsat 9 no fim de 2021. Cada um passa a cada 16 dias.",
    "Landsat 4 covers 1982-1993 and Landsat 5 1984 to May 2012. Landsat 7 is not used (stripes).":
        "O Landsat 4 cobre 1982-1993 e o Landsat 5, de 1984 a maio de 2012. O Landsat 7 não é usado (faixas).",
    "Sentinel-2 passes every 5 days (full coverage from 2017).":
        "O Sentinel-2 passa a cada 5 dias (cobertura completa a partir de 2017).",
    "Downloads the class raster (forest, pasture, etc.) of the year. One file per year. Beta: the data path may need adjusting in the advanced options.":
        "Baixa o raster de classes (floresta, pastagem etc.) do ano. Um arquivo por ano. Beta: o caminho dos dados pode precisar de ajuste nas opções avançadas.",
    "Will download %s.<br>Each one is saved in the folder below and opens in QGIS.":
        "Vai baixar %s.<br>Cada uma é salva na pasta abaixo e já aparece no QGIS.",
    "Dates sorted from clearest to cloudiest. Click a row to choose; with no choice, the first one is downloaded.":
        "Datas ordenadas da mais limpa para a mais nublada. Clique numa linha para escolher; sem escolha, baixo a primeira.",
    "%d date(s) found.": "%d data(s) encontrada(s).",
    "GEE time series %d-%d": "Série GEE %d-%d",
    "Finished: %d image(s) in QGIS and %d failure(s). Open 'Details' to see which.":
        "Terminou: %d imagem(ns) no QGIS e %d falha(s). Abra 'Detalhes' para ver quais.",
    "Downloads Landsat, Sentinel-2 and MapBiomas images from Google Earth Engine straight into QGIS, including multi-year time series.":
        "Baixa imagens Landsat, Sentinel-2 e MapBiomas do Google Earth Engine direto para o QGIS, inclusive séries multitemporais.",
    "Data: Landsat (USGS/NASA); Sentinel-2 (contains modified Copernicus Sentinel data); MapBiomas (MapBiomas Project, see mapbiomas.org for its terms).":
        "Dados: Landsat (USGS/NASA); Sentinel-2 (contém dados Copernicus Sentinel modificados); MapBiomas (Projeto MapBiomas, veja os termos em mapbiomas.org).",
    "Earth Engine is free for non-commercial use; commercial use needs a commercial project. You are responsible for following Google's terms of service.":
        "O Earth Engine é gratuito para uso não comercial; uso comercial exige um projeto comercial. Você é responsável por seguir os termos de serviço do Google.",
    "already in the folder, reusing": "já está na pasta, reaproveitando",
    "Sign in to Google Earth Engine to start. You need a Google Cloud project with Earth Engine enabled.":
        "Entre no Google Earth Engine para começar. Você precisa de um projeto do Google Cloud com o Earth Engine ativado.",
    "Connecting... if your browser opens, sign in with Google and come back here.":
        "Conectando... se o navegador abrir, entre com sua conta Google e volte aqui.",
    "Pick a projected coordinate system in metres that has an EPSG code.":
        "Escolha um sistema de coordenadas projetado, em metros, que tenha código EPSG.",
    "<b>%d MapBiomas maps</b>, from %d to %d": "<b>%d mapas do MapBiomas</b>, de %d a %d",
    "<b>1 MapBiomas map</b> of %d": "<b>1 mapa do MapBiomas</b> de %d",
    "<b>1 image</b> from %s (%s)": "<b>1 imagem</b> de %s (%s)",
    "This will download %d images. It can take a long time and use a lot of disk space. Continue?":
        "Serão baixadas %d imagens. Isso pode demorar bastante e ocupar muito espaço em disco. Continuar?",
    "looking for the best date of %d...": "procurando a melhor data de %d...",
    "best date: %s (%s, %.0f%% clear)": "melhor data: %s (%s, %.0f%% limpo)",
    "Area ready: about %.1f x %.1f km": "Área pronta: cerca de %.1f x %.1f km",
    "<b>1 image</b>: the clearest of %d, %s (%s)": "<b>1 imagem</b>: a mais limpa de %d, %s (%s)",
    "<b>%d images</b>, one per year from %d to %d: the clearest of each year, %s (%s)":
        "<b>%d imagens</b>, uma por ano de %d a %d: a mais limpa de cada ano, %s (%s)",
    "No image on this day.": "Não há imagem nesse dia.",
    "Nearby dates (within 30 days) are listed below; click one.":
        "As datas próximas (até 30 dias) estão listadas abaixo; clique na que quiser.",
    "No images found in this period.": "Nenhuma imagem encontrada nesse período.",
    "Try another year, other months or another source.":
        "Tente outro ano, outros meses ou outra fonte.",
    "%d scene(s) on this day. You can download.": "%d cena(s) nesse dia. Pode baixar.",
    "Connected · project <b>%s</b>": "Conectado · projeto <b>%s</b>",
}

_CATALOGS = {"pt": (_PT, _MONTHS_PT)}


def _language():
    """Two-letter language code following the QGIS interface language."""
    st = QgsSettings()
    override = str(st.value("locale/overrideFlag", "false")).lower() == "true"
    locale = str(st.value("locale/userLocale", "")) if override else ""
    if not locale:
        locale = QLocale().name()
    return locale[:2].lower()


language = _language   # public name


def tr(text):
    """Translate an English UI string; unknown strings and languages stay in English."""
    catalog = _CATALOGS.get(_language())
    if catalog is None:
        return text
    return catalog[0].get(text, text)


def month_names():
    catalog = _CATALOGS.get(_language())
    return list(catalog[1]) if catalog else list(_MONTHS_EN)
