"""Groensignaal per BGT-vlak uit de PDOK-luchtfoto 2026 (RGB en infrarood).

Stap 1  Download de luchtfoto's van het testgebied als GeoTIFF (EPSG:28992) via de
        PDOK WMS (er is geen WCS voor de luchtfoto's). Bestaande rasters worden
        hergebruikt en niet opnieuw opgehaald of overschreven.
Stap 2  Per BGT-vlak: ExG (RGB) en NDVI (infrarood): gemiddelde, mediaan en aandeel
        pixels boven de drempel. Uitvoer per vlak naar data/groensignaal_per_vlak.csv.
Stap 3  Meldingen "mogelijk_verhard" en "groensignaal_tegenstrijdig" in hetzelfde formaat
        als dashboard/meldingen.geojson, naar een NIEUW bestand (meldingen_groen.geojson).

Elke melding is een signaal, geen vastgestelde fout. Luchtfoto en BGT kunnen een ander
moment beschrijven (schaduw, bomen over verharding, seizoen; de foto's van 2026 zijn
opgenomen tussen januari en juni). De drempels hieronder zijn verkennend.

Vereist: Python 3.10+, shapely 2, pyproj 3, numpy, rasterio.

Met --vergelijk JAAR1 JAAR2: zelfde werkwijze voor twee jaren, per vlak het verschil
(data/groensignaal_JAAR1_JAAR2.csv) en meldingen "groen_afgenomen" en "groen_toegenomen"
(dashboard/meldingen_groen_verschil_JAAR1_JAAR2.geojson; voor 2025-2026 de oorspronkelijke
naam meldingen_groen_verschil.geojson). Met één jaar wordt met 2026 vergeleken.
Zie de constanten VERANDERING_DREMPEL, PREFIX_VERSCHIL en CONDITIE.

Gebruik:
    python groensignaal.py data/BGT_testgebied_actueel.geojson \
        --uitvoer dashboard/meldingen_groen.geojson
    python groensignaal.py data/BGT_testgebied_actueel.geojson --vergelijk 2025 2026
    python groensignaal.py data/BGT_testgebied_actueel.geojson --vergelijk 2022 2023
"""
import argparse
import collections
import csv
import hashlib
import json
import math
import time
import urllib.parse
import urllib.request
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
import shapely
from pyproj import Transformer
from rasterio.features import geometry_mask
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from rasterio.windows import Window, from_bounds
from shapely.geometry import box, mapping, shape

from maak_meldingen import BBOX_3857, afronden, klasse_van, leeg

# De losse JPEG-blokken van de WMS hebben geen georeferentie; die zetten we zelf.
warnings.filterwarnings('ignore', category=rasterio.errors.NotGeoreferencedWarning)

# ---------------------------------------------------------------------------
# Bron: PDOK WMS, waarden letterlijk uit GetCapabilities (opgehaald 2026-11-09).
#   https://service.pdok.nl/hwh/luchtfotorgb/wms/v1_0?request=GetCapabilities&service=WMS
#   https://service.pdok.nl/hwh/luchtfotocir/wms/v1_0?request=GetCapabilities&service=WMS
# WMS 1.3.0, enige GetMap-formaat image/jpeg, MaxWidth/MaxHeight 2500.
# De WCS-endpoints (.../wcs/v1_0) geven "not found": er is geen WCS.
# De lagen zijn niet "queryable": GetFeatureInfo geeft geen opnamedatum per plek.
# ---------------------------------------------------------------------------
SERVICE = {
    'rgb': 'https://service.pdok.nl/hwh/luchtfotorgb/wms/v1_0',
    'cir': 'https://service.pdok.nl/hwh/luchtfotocir/wms/v1_0',
}
# Laagnaam per jaar, telkens een definitief product, niet "Actueel". RGB: orthoHR (5-8 cm).
# Infrarood: orthoHRIR waar die bestaat (2025, 2026); voor 2022-2024 heeft de WMS alleen
# ortho25IR (25 cm). Alle rasters worden op 0,25 m opgevraagd.
LAGEN = {
    2026: {'rgb': '2026_orthoHR', 'cir': '2026_orthoHRIR'},
    2025: {'rgb': '2025_orthoHR', 'cir': '2025_orthoHRIR'},
    2024: {'rgb': '2024_orthoHR', 'cir': '2024_ortho25IR'},
    2023: {'rgb': '2023_orthoHR', 'cir': '2023_ortho25IR'},
    2022: {'rgb': '2022_orthoHR', 'cir': '2022_ortho25IR'},
}
# Opnameperiode per laag uit de metadata (Nationaal Georegister, gml:beginPosition/
# endPosition), met de uuid van de MetadataURL uit GetCapabilities.
# Let op: voor 2022-2024 is infrarood een aparte zomervlucht (15 mei - 15 aug), RGB niet.
OPNAME = {
    2026: {'rgb': (('2026-01-01', '2026-06-01'), '4d8e14a9-302c-48e7-a0ee-1b23ed2a2122'),
           'cir': (('2026-01-01', '2026-06-01'), '3e94cc75-c4e8-404d-9dd1-6bf710093af1')},
    2025: {'rgb': (('2025-01-01', '2025-06-01'), 'bc9b2d88-9d6b-46c9-ad0e-23f0b7da657c'),
           'cir': (('2025-01-01', '2025-06-01'), 'f08b421f-1ebb-4f74-85e6-fc401577d4e7')},
    2024: {'rgb': (('2024-01-01', '2024-06-01'), '8b4d70cd-4233-4299-8ce6-01943d1bbd1f'),
           'cir': (('2024-05-15', '2024-08-15'), '22279b6e-1a05-49a0-92e3-fee16cc34ce5')},
    2023: {'rgb': (('2023-01-01', '2023-06-01'), '84ae8387-a93b-4a70-ac5c-6bb47792c1b4'),
           'cir': (('2023-05-15', '2023-08-15'), 'a9beeba1-721b-415a-8e6e-f31af55eee1c')},
    2022: {'rgb': (('2022-01-01', '2022-06-01'), 'cd9b7810-054e-4c8a-94dc-c9cf35a30f1d'),
           'cir': (('2022-05-15', '2022-08-15'), 'ac33d7d4-10a1-4151-b742-7aa064734a3e')},
}
JAAR = 2026                 # het jaar voor de gewone groensignaal-meldingen


def bron(soort, jaar=JAAR):
    laag = LAGEN[jaar][soort]
    return {'url': SERVICE[soort], 'laag': laag, 'bestand': f'luchtfoto_{laag}_{soort}.tif'}
CRS = 'EPSG:28992'          # RD New: in meters, dus pixelgrootte = grondresolutie
RESOLUTIE_M = 0.25          # pixelgrootte van het opgevraagde raster (bron is 5-8 cm)
MAX_PX = 2000               # per WMS-verzoek (service-maximum is 2500)

# CIR-banden. De metadata noemt de volgorde niet; dit is de gangbare CIR-samenstelling
# (NIR als rood, rood als groen, groen als blauw). Het script controleert dit: binnen de
# BGT-vlakken moet band 1 gemiddeld hoger zijn dan band 2 (vegetatie reflecteert NIR).
CIR_NIR, CIR_ROOD = 0, 1

# ---------------------------------------------------------------------------
# Verkennende drempels (geen normen). Zie README, "Groensignaal", voor de keuze.
# ---------------------------------------------------------------------------
# ExG = 2g - r - b op chromatische coordinaten (r = R/(R+G+B), enz.). Daardoor telt
# alleen de kleurverhouding en niet de helderheid; schaduw en zon wegen minder zwaar.
# NDVI = (NIR - R) / (NIR + R) op de 8-bit JPEG-waarden van de WMS. Dat is een
# "pseudo-NDVI": niet radiometrisch gekalibreerd, alleen onderling vergelijkbaar.
#
# Pixeldrempels: Otsu-drempel (scheiding in twee groepen) over alle pixels van het
# testgebied, afgerond. Op deze werkset: ExG 0,071 -> 0,07 en NDVI 0,261 -> 0,25.
# Ter controle de medianen: ExG 0,14 binnen de BGT-vlakken en 0,01 erbuiten; NDVI
# 0,44 binnen en 0,15 erbuiten. De drempels liggen dus tussen groen en niet-groen.
EXG_DREMPEL = 0.07          # pixel telt als "groen" in RGB boven deze ExG
NDVI_DREMPEL = 0.25         # pixel telt als "groen" in infrarood boven deze NDVI
# Vlakdrempels: gekozen na een gevoeligheidstest (laag 0,1/0,2/0,3 gaf 26/38/51 keer
# mogelijk_verhard). 0,2 ligt in het midden. Typische groenvlakken zitten rond 0,65-0,9.
LAAG_AANDEEL = 0.20         # minder dan dit aandeel groene pixels = laag groensignaal
HOOG_AANDEEL = 0.50         # meer dan dit aandeel = duidelijk groen
MIN_PIXELS = 16             # minder pixels (1 m2 bij 0,25 m) = te weinig om iets te zeggen
# Randobjecten lopen buiten het testgebied door; de foto dekt dan maar een deel van het
# vlak. Onder deze dekking (pixeloppervlak / vlakoppervlak) geen melding.
MIN_DEKKING = 0.80

# ---------------------------------------------------------------------------
# Vergelijking tussen jaren (--vergelijk 2025). Verkennende drempels.
# ---------------------------------------------------------------------------
# Probleem: 2025 en 2026 vallen volgens de metadata allebei in jan-jun, maar op de foto is
# 2025 bladloos en 2026 vol in blad. Gemiddeld stijgt het aandeel groene pixels per vlak
# daardoor met 0,5 (heesters +0,6, gras +0,4). Een vaste drempel op het ruwe verschil meet
# dan vooral het seizoen (500+ vlakken "toegenomen").
# Daarom: verwacht aandeel 2026 = aandeel 2025 + mediane stijging van dezelfde soort groen,
# afgekapt op 0..1 (zodat vlakken die al groen waren, zoals wintergroen, niet als "gedaald"
# tellen). Afwijking = werkelijk 2026 - verwacht. Een melding alleen als ExG en NDVI
# allebei dezelfde kant op afwijken.
# Drempel 0,40: de robuuste spreiding (1,4826 x MAD) van de afwijking is 0,33 (ExG) en
# 0,28 (NDVI). 0,40 ligt boven één spreiding van beide. Gevoeligheid op deze werkset
# (afgenomen / toegenomen): 0,30 -> 52 / 70, 0,40 -> 28 / 25, 0,50 -> 16 / 11, 0,60 -> 8 / 0.
#
# Dezelfde drempel geldt voor elk jaarpaar, zodat de aantallen vergelijkbaar zijn. De
# spreiding en gevoeligheid per paar staan in de README.
VERANDERING_DREMPEL = 0.40
MIN_KLASSE = 10             # soorten met minder vlakken krijgen de mediane stijging van alles

# ID-prefix per jaarpaar, zodat meldingen van verschillende paren niet botsen.
PREFIX_VERSCHIL = {(2025, 2026): 'V', (2022, 2023): 'W', (2024, 2026): 'X', (2023, 2024): 'Y'}
# Conditie per jaar en soort (zie README, "Welke luchtfotojaren zijn bladloos of in blad?").
# RGB: vastgesteld op alle bosplantsoen- en heestervlakken (mediane ExG, aandeel groene
# pixels) plus een montage per jaar; eerder alleen op één bomenrij, waardoor 2023 ten
# onrechte bladloos heette. Infrarood: bomenrij en overzichtsbeeld. Alleen voor teksten.
CONDITIE = {
    2022: {'rgb': 'bladloos', 'cir': 'in blad'},
    2023: {'rgb': 'in blad (licht, jong blad)', 'cir': 'in blad'},
    2024: {'rgb': 'donkere opname, blad per plek verschillend', 'cir': 'in blad'},
    2025: {'rgb': 'bladloos', 'cir': 'bladloos'},
    2026: {'rgb': 'in blad', 'cir': 'in blad'},
}
# Voor 2025-2026 blijven label, uitleg en toelichting zoals in de V-meldingen die al in
# het dashboard staan (meldingen_alle_v2.geojson), zodat opnieuw draaien hetzelfde geeft.
OORSPRONKELIJK_PAAR = (2025, 2026)

TYPEN = {
    'mogelijk_verhard': (
        'Mogelijk verhard of kaal', 'midden',
        'BGT zegt begroeid, maar op de luchtfoto 2026 is weinig groen te zien: '
        'zowel in RGB (ExG) als in infrarood (NDVI) is het aandeel groene pixels laag. '
        'Kan ook komen door schaduw, kale struiken (opname jan-jun) of een verschoven grens.'),
    'groensignaal_tegenstrijdig': (
        'Groensignaal tegenstrijdig', 'info',
        'RGB (ExG) en infrarood (NDVI) zijn het oneens: de ene index ziet duidelijk groen, '
        'de andere nauwelijks. Vaak komt dat door schaduw: in de slagschaduw van gebouwen '
        'zakt ExG weg terwijl NDVI nog vegetatie ziet. Ook kale takken of een bijzondere '
        'kleur kunnen het veroorzaken. Met de hand bekijken.'),
}

TYPEN_VERSCHIL = {
    'groen_afgenomen': (
        'Groen afgenomen (experimenteel, seizoensgevoelig)', 'laag',
        'Het vlak is in 2026 duidelijk minder groen dan verwacht op basis van 2025 en de '
        'gemiddelde verandering van dezelfde soort groen, in RGB (ExG) en infrarood (NDVI). '
        'Let op: de jaren zijn verschillend in blad opgenomen. In 2025 zijn bomen en heesters '
        'kaal, in 2026 staan ze in blad. Er is per soort groen voor gecorrigeerd, maar de '
        'melding blijft gevoelig voor het seizoen. Mogelijk gerooid, verhard of vervangen. '
        'Andere oorzaken die bij nakijken zijn gezien: bloesem (witte kruinen) in 2026 en '
        'schaduw van bomen die in 2026 in blad staan.'),
    'groen_toegenomen': (
        'Groen toegenomen', 'info',
        'Het vlak is in 2026 duidelijk groener dan verwacht op basis van 2025 en de gemiddelde '
        'verandering van dezelfde soort groen, in RGB (ExG) en infrarood (NDVI). Mogelijk '
        'nieuw aangeplant of ingezaaid. Bij nakijken bleek dit vaak seizoen: bomen die in 2026 '
        'in blad boven het vlak hangen, of lange winterschaduw in 2025. Weinig betrouwbaar.'),
}

STATS_CSV = 'groensignaal_per_vlak.csv'


# ---------------------------------------------------------------------------
# Stap 1: download
# ---------------------------------------------------------------------------
def rd_grid():
    """Bbox van het testgebied (EPSG:3857) als RD-bbox, naar buiten afgerond op het pixelraster."""
    tr = Transformer.from_crs(3857, 28992, always_xy=True)
    x0, y0, x1, y1 = BBOX_3857
    # randen verdichten, zodat de RD-omhullende het hele gebied bevat
    t = np.linspace(0, 1, 101)
    xs = np.concatenate([x0 + (x1 - x0) * t, np.full_like(t, x1), x1 - (x1 - x0) * t, np.full_like(t, x0)])
    ys = np.concatenate([np.full_like(t, y0), y0 + (y1 - y0) * t, np.full_like(t, y1), y1 - (y1 - y0) * t])
    ex, ey = tr.transform(xs, ys)
    r = RESOLUTIE_M
    minx, miny = math.floor(min(ex) / r) * r, math.floor(min(ey) / r) * r
    maxx, maxy = math.ceil(max(ex) / r) * r, math.ceil(max(ey) / r) * r
    return minx, miny, maxx, maxy, round((maxx - minx) / r), round((maxy - miny) / r)


def getmap_url(b, bbox, breedte, hoogte):
    params = {
        'SERVICE': 'WMS', 'VERSION': '1.3.0', 'REQUEST': 'GetMap',
        'LAYERS': b['laag'], 'STYLES': '', 'CRS': CRS,
        # EPSG:28992 heeft as-volgorde x (oost), y (noord), ook in WMS 1.3.0
        'BBOX': ','.join(f'{v:.2f}' for v in bbox),
        'WIDTH': str(breedte), 'HEIGHT': str(hoogte), 'FORMAT': 'image/jpeg',
    }
    return b['url'] + '?' + urllib.parse.urlencode(params, safe=':,')


def haal(url, pogingen=3):
    laatste = None
    for poging in range(pogingen):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'bgt-groensignaal/1.0'})
            with urllib.request.urlopen(req, timeout=120) as r:
                inhoud, ctype = r.read(), r.headers.get('Content-Type', '')
            if not ctype.startswith('image/'):
                # WMS geeft fouten als XML (ServiceException) met status 200
                raise RuntimeError(f'geen afbeelding maar {ctype}: {inhoud[:300]!r}')
            return inhoud
        except Exception as e:  # noqa: BLE001 - alles opnieuw proberen, daarna echt falen
            laatste = e
            time.sleep(2 * (poging + 1))
    raise RuntimeError(f'download mislukt na {pogingen} pogingen: {url}\n  {laatste}')


def download(soort, map_data, jaar=JAAR):
    """Haal een luchtfoto op als GeoTIFF. Geeft (pad, info). Bestaat het bestand al, dan hergebruiken."""
    b = bron(soort, jaar)
    pad = Path(map_data) / b['bestand']
    info_pad = pad.with_suffix('.json')
    if pad.exists():
        info = json.loads(info_pad.read_text(encoding='utf-8')) if info_pad.exists() else {}
        print(f'  {soort} {jaar}: bestaat al, hergebruikt: {pad}')
        return pad, info
    minx, miny, maxx, maxy, w, h = rd_grid()
    r = RESOLUTIE_M
    data = np.zeros((3, h, w), dtype=np.uint8)
    urls = []
    nx, ny = math.ceil(w / MAX_PX), math.ceil(h / MAX_PX)
    print(f'  {soort} {jaar}: {w} x {h} px in {nx * ny} verzoeken ({b["laag"]}) ...')
    for iy in range(ny):
        for ix in range(nx):
            c0, r0 = ix * MAX_PX, iy * MAX_PX
            cw, rh = min(MAX_PX, w - c0), min(MAX_PX, h - r0)
            # rij 0 is de noordrand
            tb = (minx + c0 * r, maxy - (r0 + rh) * r, minx + (c0 + cw) * r, maxy - r0 * r)
            url = getmap_url(b, tb, cw, rh)
            urls.append(url)
            with MemoryFile(haal(url)) as mf, mf.open() as ds:
                blok = ds.read()
            if blok.shape != (3, rh, cw):
                raise RuntimeError(f'onverwachte vorm {blok.shape} voor {url}')
            data[:, r0:r0 + rh, c0:c0 + cw] = blok
    if data.max() == 0:
        raise RuntimeError(f'{soort} {jaar}: alle pixels zijn 0, de download is leeg')
    pad.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(pad, 'w', driver='GTiff', width=w, height=h, count=3, dtype='uint8',
                       crs=CRS, transform=from_origin(minx, maxy, r, r),
                       compress='deflate', tiled=True, photometric='RGB') as ds:
        ds.write(data)
    info = {
        'service': b['url'], 'laag': b['laag'], 'crs': CRS,
        'bbox_rd': [minx, miny, maxx, maxy], 'resolutie_m': r, 'pixels': [w, h],
        'formaat_bron': 'image/jpeg (WMS GetMap), samengevoegd tot GeoTIFF',
        'opnameperiode_metadata': ' t/m '.join(OPNAME[jaar][soort][0]),
        'metadata_uuid': OPNAME[jaar][soort][1],
        'gedownload_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'getmap_urls': urls,
    }
    info_pad.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'  {soort} {jaar}: opgeslagen: {pad} ({pad.stat().st_size / 1e6:.1f} MB)')
    return pad, info


# ---------------------------------------------------------------------------
# Stap 2: indexen per vlak
# ---------------------------------------------------------------------------
def exg(blok):
    rgb = blok.astype(np.float32)
    som = rgb.sum(axis=0)
    som[som == 0] = np.nan
    r, g, b = rgb / som
    return 2 * g - r - b


def ndvi(blok):
    nir, rood = blok[CIR_NIR].astype(np.float32), blok[CIR_ROOD].astype(np.float32)
    noemer = nir + rood
    noemer[noemer == 0] = np.nan
    return (nir - rood) / noemer


def samenvatting(waarden, drempel):
    w = waarden[np.isfinite(waarden)]
    if w.size == 0:
        return None, None, None
    return float(w.mean()), float(np.median(w)), float((w > drempel).mean())


def pixels_in(ds, geom):
    """Pixels (3, n) waarvan het middelpunt binnen het vlak valt."""
    win = from_bounds(*geom.bounds, transform=ds.transform)
    win = win.round_offsets(op='floor').round_lengths(op='ceil')
    win = win.intersection(Window(0, 0, ds.width, ds.height))
    blok = ds.read(window=win)
    binnen = ~geometry_mask([mapping(geom)], out_shape=blok.shape[1:],
                            transform=ds.window_transform(win), all_touched=False)
    return blok[:, binnen]


def bereken(features, rgb_pad, cir_pad):
    naar_rd = Transformer.from_crs(4326, 28992, always_xy=True)
    rgb = rasterio.open(rgb_pad)
    cir = rasterio.open(cir_pad) if cir_pad else None
    rijen = []
    controle = []
    for f in features:
        p = f['properties']
        g = shapely.transform(shape(f['geometry']),
                              lambda c: np.column_stack(naar_rd.transform(c[:, 0], c[:, 1])))
        px = pixels_in(rgb, g)
        rij = {'lokaal_id': p.get('lokaal_id'), 'klasse': klasse_van(p),
               'oppervlakte_m2': round(g.area, 2), 'n_pixels': int(px.shape[1]),
               'dekking': px.shape[1] * RESOLUTIE_M ** 2 / g.area if g.area > 0 else 0.0}
        rij['exg_gem'], rij['exg_med'], rij['exg_aandeel'] = samenvatting(exg(px[:, None, :])[0], EXG_DREMPEL)
        if cir is not None:
            pc = pixels_in(cir, g)
            controle.append(pc[[CIR_NIR, CIR_ROOD]].astype(np.float64).sum(axis=1))
            rij['ndvi_gem'], rij['ndvi_med'], rij['ndvi_aandeel'] = samenvatting(ndvi(pc[:, None, :])[0], NDVI_DREMPEL)
        rijen.append(rij)
    rgb.close()
    if cir is not None:
        cir.close()
        nir_som, rood_som = np.sum(controle, axis=0)
        if nir_som <= rood_som:
            raise RuntimeError('CIR-bandcontrole mislukt: band NIR is binnen de groenvlakken niet hoger '
                               'dan band rood. Controleer CIR_NIR/CIR_ROOD.')
    return rijen


# ---------------------------------------------------------------------------
# Stap 3: meldingen
# ---------------------------------------------------------------------------
def fmt(v, d=2):
    return '-' if v is None else f'{v:.{d}f}'


def beoordeel(rij, met_cir):
    """Geeft een meldingstype of None. Alleen met genoeg pixels en genoeg dekking."""
    if rij['n_pixels'] < MIN_PIXELS or rij['dekking'] < MIN_DEKKING or rij['exg_aandeel'] is None:
        return None
    e = rij['exg_aandeel']
    if not met_cir:
        return 'mogelijk_verhard' if e < LAAG_AANDEEL else None
    n = rij['ndvi_aandeel']
    if n is None:
        return None
    if e < LAAG_AANDEEL and n < LAAG_AANDEEL:
        return 'mogelijk_verhard'
    if (e >= HOOG_AANDEEL and n < LAAG_AANDEEL) or (n >= HOOG_AANDEEL and e < LAAG_AANDEEL):
        return 'groensignaal_tegenstrijdig'
    return None


def toelichting(rij, met_cir):
    t = (f"ExG: {rij['exg_aandeel'] * 100:.0f}% groene pixels (> {EXG_DREMPEL}), "
         f"gemiddeld {fmt(rij['exg_gem'], 3)}, mediaan {fmt(rij['exg_med'], 3)}.")
    if met_cir:
        t += (f" NDVI: {rij['ndvi_aandeel'] * 100:.0f}% groene pixels (> {NDVI_DREMPEL}), "
              f"gemiddeld {fmt(rij['ndvi_gem'])}, mediaan {fmt(rij['ndvi_med'])}.")
    return t + f" {rij['n_pixels']} pixels van {RESOLUTIE_M} m, {min(rij['dekking'], 1) * 100:.0f}% van het vlak op de foto."


def registratiejaar(p):
    if leeg(p.get('tijdstip_registratie')):
        return None
    try:
        return datetime.fromisoformat(p['tijdstip_registratie'].replace('Z', '+00:00')).year
    except ValueError:
        return None


def collectie(bron_pad, meldingen, typen, prefix, drempels, infos, let_op):
    """FeatureCollection in het formaat van meldingen.geojson.

    meldingen: lijst van (type, bron-feature, toelichting, oppervlakte_m2). Volgorde en
    nummering: type (volgorde van `typen`), dan lokaal_id; ID = prefix + volgnummer.
    """
    bron_pad = Path(bron_pad)
    raw = bron_pad.read_bytes()
    n_objecten = len(json.loads(raw)['features'])
    volgorde = {t: n for n, t in enumerate(typen)}
    meldingen = sorted(meldingen, key=lambda m: (volgorde[m[0]], str(m[1]['properties'].get('lokaal_id'))))
    uit = []
    for n, (typ, f, tekst, opp) in enumerate(meldingen, 1):
        p = f['properties']
        uit.append({
            'type': 'Feature',
            'geometry': mapping(afronden(shape(f['geometry']))),
            'properties': {
                'id': f'{prefix}-{n:04d}',
                'type': typ,
                'ernst': typen[typ][1],
                'toelichting': tekst,
                'lokaal_id': p.get('lokaal_id'),
                'bronhouder': p.get('bronhouder'),
                'fysiek_voorkomen': p.get('fysiek_voorkomen'),
                'plus_fysiek_voorkomen': p.get('plus_fysiek_voorkomen'),
                'registratiejaar': registratiejaar(p),
                'oppervlakte_m2': opp,
            },
        })
    telling = collections.Counter(f['properties']['type'] for f in uit)
    return {
        'type': 'FeatureCollection',
        'metadata': {
            'bronbestand': bron_pad.name,
            'sha256_bronbestand': hashlib.sha256(raw).hexdigest(),
            'aantal_objecten': n_objecten,
            'gegenereerd_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            # klein_vlak_m2 en overlap_m2 staan erbij omdat het dashboard ze toont
            'drempels': {'klein_vlak_m2': 5.0, 'overlap_m2': 0.01, **drempels},
            'bbox_epsg3857': list(BBOX_3857),
            'luchtfoto': infos,
            'software': {'shapely': shapely.__version__, 'rasterio': rasterio.__version__,
                         'GDAL': rasterio.__gdal_version__, 'numpy': np.__version__},
            'let_op': let_op,
            'typen': {t: {'label': v[0], 'ernst': v[1], 'uitleg': v[2]} for t, v in typen.items()},
            'aantal_per_type': {t: telling.get(t, 0) for t in typen},
        },
        'features': uit,
    }


def maak_meldingen_groen(bron_pad, rijen, infos, met_cir):
    features = json.loads(Path(bron_pad).read_bytes())['features']
    meldingen = []
    for f, rij in zip(features, rijen):
        typ = beoordeel(rij, met_cir)
        if typ:
            meldingen.append((typ, f, toelichting(rij, met_cir), rij['oppervlakte_m2']))
    typen = TYPEN if met_cir else {k: v for k, v in TYPEN.items() if k == 'mogelijk_verhard'}
    # G- in plaats van M-, zodat ID's niet botsen na samenvoegen met meldingen.geojson
    return collectie(
        bron_pad, meldingen, typen, 'G',
        {'exg': EXG_DREMPEL, 'ndvi': NDVI_DREMPEL if met_cir else None,
         'laag_aandeel': LAAG_AANDEEL, 'hoog_aandeel': HOOG_AANDEEL,
         'min_pixels': MIN_PIXELS, 'min_dekking': MIN_DEKKING, 'resolutie_m': RESOLUTIE_M},
        infos,
        'Een melding is een signaal en geen vastgestelde fout. Luchtfoto (opname '
        'jan-jun 2026) en BGT kunnen een ander moment beschrijven: schaduw, bomen over '
        'verharding, kale struiken in het voorjaar. Drempels zijn verkennend.')


# ---------------------------------------------------------------------------
# Vergelijking tussen twee jaren
# ---------------------------------------------------------------------------
INDEXEN = ('exg', 'ndvi')


def vergelijk(rij_oud, rij_nieuw, jaar_oud, jaar_nieuw):
    """Per vlak: indexen van beide jaren, ruw verschil, verwachting en afwijking."""
    bruikbaar = [i for i, r in enumerate(rij_nieuw)
                 if r['n_pixels'] >= MIN_PIXELS and r['dekking'] >= MIN_DEKKING
                 and all(r[f'{x}_aandeel'] is not None and rij_oud[i][f'{x}_aandeel'] is not None for x in INDEXEN)]
    # Mediane verandering van het aandeel groene pixels per soort groen
    per_klasse = collections.defaultdict(list)
    for i in bruikbaar:
        per_klasse[rij_nieuw[i]['klasse']].append(i)
    alle = {x: float(np.median([rij_nieuw[i][f'{x}_aandeel'] - rij_oud[i][f'{x}_aandeel'] for i in bruikbaar]))
            for x in INDEXEN}
    stijging = {}
    for k, ids in per_klasse.items():
        stijging[k] = ({x: float(np.median([rij_nieuw[i][f'{x}_aandeel'] - rij_oud[i][f'{x}_aandeel'] for i in ids]))
                        for x in INDEXEN} if len(ids) >= MIN_KLASSE else dict(alle))

    rijen = []
    ok = set(bruikbaar)
    for i, (o, n) in enumerate(zip(rij_oud, rij_nieuw)):
        rij = {k: n[k] for k in ('lokaal_id', 'klasse', 'oppervlakte_m2', 'n_pixels', 'dekking')}
        for x in INDEXEN:
            for maat in ('gem', 'med', 'aandeel'):
                rij[f'{x}_{maat}_{jaar_oud}'] = o.get(f'{x}_{maat}')
                rij[f'{x}_{maat}_{jaar_nieuw}'] = n.get(f'{x}_{maat}')
        rij['bruikbaar'] = i in ok
        for x in INDEXEN:
            for maat in ('gem', 'med', 'aandeel'):
                a, b = o.get(f'{x}_{maat}'), n.get(f'{x}_{maat}')
                rij[f'd_{x}_{maat}'] = None if a is None or b is None else b - a
            if i in ok:
                s = stijging[n['klasse']][x]
                verwacht = float(np.clip(o[f'{x}_aandeel'] + s, 0, 1))
                rij[f'{x}_stijging_klasse'] = s
                rij[f'{x}_aandeel_verwacht_{jaar_nieuw}'] = verwacht
                rij[f'{x}_afwijking'] = n[f'{x}_aandeel'] - verwacht
            else:
                rij[f'{x}_stijging_klasse'] = rij[f'{x}_aandeel_verwacht_{jaar_nieuw}'] = rij[f'{x}_afwijking'] = None
        rijen.append(rij)
    return rijen, stijging


def beoordeel_verschil(rij):
    if not rij['bruikbaar']:
        return None
    e, n = rij['exg_afwijking'], rij['ndvi_afwijking']
    if e <= -VERANDERING_DREMPEL and n <= -VERANDERING_DREMPEL:
        return 'groen_afgenomen'
    if e >= VERANDERING_DREMPEL and n >= VERANDERING_DREMPEL:
        return 'groen_toegenomen'
    return None


def conditie_tekst(oud, nieuw):
    return (f"RGB {oud} {CONDITIE[oud]['rgb']}, {nieuw} {CONDITIE[nieuw]['rgb']}; "
            f"infrarood {oud} {CONDITIE[oud]['cir']}, {nieuw} {CONDITIE[nieuw]['cir']}")


def typen_verschil(oud, nieuw):
    """Label, ernst en uitleg per jaarpaar.

    "(experimenteel, seizoensgevoelig)" staat alleen in het label bij 2025-2026 (bladloos
    tegenover in blad). Bij de andere paren is het label kaal; de uitleg per paar blijft.
    """
    if (oud, nieuw) == OORSPRONKELIJK_PAAR:
        return TYPEN_VERSCHIL
    cond = conditie_tekst(oud, nieuw)
    return {
        'groen_afgenomen': (
            'Groen afgenomen', TYPEN_VERSCHIL['groen_afgenomen'][1],
            f'Het vlak is in {nieuw} duidelijk minder groen dan verwacht op basis van {oud} en de '
            'mediane verandering van dezelfde soort groen, in RGB (ExG) en infrarood (NDVI). '
            f'Conditie op de foto: {cond}. Er is per soort groen gecorrigeerd, maar seizoen, '
            'schaduw en kleurbalans per vlucht kunnen meespelen. Mogelijk gerooid, verhard of vervangen.'),
        'groen_toegenomen': (
            'Groen toegenomen', TYPEN_VERSCHIL['groen_toegenomen'][1],
            f'Het vlak is in {nieuw} duidelijk groener dan verwacht op basis van {oud} en de '
            'mediane verandering van dezelfde soort groen, in RGB (ExG) en infrarood (NDVI). '
            f'Conditie op de foto: {cond}. Mogelijk nieuw aangeplant, ingezaaid of uitgegroeid; '
            'seizoen, schaduw en kleurbalans per vlucht kunnen meespelen.'),
    }


def toelichting_verschil(rij, jaar_oud, jaar_nieuw, p=None):
    delen = []
    for x, naam in (('exg', 'ExG'), ('ndvi', 'NDVI')):
        delen.append(
            f"{naam}: groene pixels {rij[f'{x}_aandeel_{jaar_oud}'] * 100:.0f}% ({jaar_oud}) -> "
            f"{rij[f'{x}_aandeel_{jaar_nieuw}'] * 100:.0f}% ({jaar_nieuw}), verwacht "
            f"{rij[f'{x}_aandeel_verwacht_{jaar_nieuw}'] * 100:.0f}%, afwijking {rij[f'{x}_afwijking'] * 100:+.0f} pp.")
    tekst = (' '.join(delen) + f" Verwachting = {jaar_oud} + mediane verandering van '{rij['klasse']}'. "
             f"{rij['n_pixels']} pixels van {RESOLUTIE_M} m.")
    if (jaar_oud, jaar_nieuw) == OORSPRONKELIJK_PAAR:
        return tekst
    tekst = f'Vergelijking {jaar_oud}-{jaar_nieuw}. ' + tekst
    jaar = registratiejaar(p or {})
    if jaar is not None and jaar > jaar_oud:
        tekst += (f' LET OP: registratiejaar {jaar} is later dan {jaar_oud}; het object bestond '
                  f'in {jaar_oud} mogelijk nog niet (of had een andere vorm).')
    return tekst


def maak_meldingen_verschil(bron_pad, rijen, infos, jaar_oud, jaar_nieuw, prefix, extra=None):
    features = json.loads(Path(bron_pad).read_bytes())['features']
    meldingen = []
    for f, rij in zip(features, rijen):
        typ = beoordeel_verschil(rij)
        if typ:
            meldingen.append((typ, f, toelichting_verschil(rij, jaar_oud, jaar_nieuw, f['properties']),
                              rij['oppervlakte_m2']))
    if (jaar_oud, jaar_nieuw) == OORSPRONKELIJK_PAAR:
        let_op = (f'Een melding is een signaal en geen vastgestelde fout. De luchtfoto\'s van {jaar_oud} '
                  f'en {jaar_nieuw} vallen volgens de metadata allebei in jan-jun, maar {jaar_oud} is '
                  f'bladloos en {jaar_nieuw} in blad opgenomen. Er is gecorrigeerd met de mediane '
                  'verandering per soort groen; seizoen, schaduw en kleurbalans kunnen toch meespelen. '
                  'Drempels zijn verkennend.')
    else:
        let_op = (f'Een melding is een signaal en geen vastgestelde fout. Vergelijking {jaar_oud}-{jaar_nieuw}; '
                  f'conditie op de foto: {conditie_tekst(jaar_oud, jaar_nieuw)}. Er is gecorrigeerd met de '
                  'mediane verandering per soort groen; seizoen, schaduw en kleurbalans per vlucht kunnen '
                  'toch meespelen. Drempels zijn verkennend.')
    # Eigen prefix per jaarpaar (V, W, X), zodat ID's niet botsen met M-, G- en elkaar
    resultaat = collectie(
        bron_pad, meldingen, typen_verschil(jaar_oud, jaar_nieuw), prefix,
        {'exg': EXG_DREMPEL, 'ndvi': NDVI_DREMPEL, 'verandering': VERANDERING_DREMPEL,
         'min_klasse': MIN_KLASSE, 'min_pixels': MIN_PIXELS, 'min_dekking': MIN_DEKKING,
         'resolutie_m': RESOLUTIE_M, 'jaren': [jaar_oud, jaar_nieuw]},
        infos, let_op)
    if extra:
        resultaat['metadata'].update(extra)
    return resultaat


def gebied_medianen(paden, jaren):
    """Mediane NDVI en ExG over alle pixels van het testgebied, per jaar."""
    uit = {}
    for j in jaren:
        with rasterio.open(paden[j, 'rgb']) as a, rasterio.open(paden[j, 'cir']) as b:
            uit[j] = {'exg': float(np.nanmedian(exg(a.read()))), 'ndvi': float(np.nanmedian(ndvi(b.read())))}
    return uit


def schrijf_csv(pad, rijen):
    velden = list(rijen[0].keys())
    with open(pad, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=velden, delimiter=';')
        w.writeheader()
        for r in rijen:
            w.writerow({k: (f'{v:.4f}' if isinstance(v, float) else v) for k, v in r.items()})


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('bestand', help='lokale werkset (GeoJSON, EPSG:4326)')
    parser.add_argument('--uitvoer', default=None,
                        help='standaard dashboard/meldingen_groen.geojson, '
                             'met --vergelijk dashboard/meldingen_groen_verschil.geojson')
    parser.add_argument('--data', default='data', help='map voor de luchtfoto-rasters en de CSV')
    parser.add_argument('--zonder-cir', action='store_true', help='alleen RGB gebruiken')
    parser.add_argument('--vergelijk', type=int, nargs='+', metavar='JAAR',
                        help='vergelijk twee jaren (bijv. --vergelijk 2022 2023) en maak '
                             f'groen_afgenomen/groen_toegenomen; met één jaar wordt met {JAAR} vergeleken. '
                             f'Beschikbaar: {", ".join(map(str, sorted(LAGEN)))}')
    parser.add_argument('--prefix', default=None,
                        help='ID-prefix voor de verschilmeldingen (standaard uit PREFIX_VERSCHIL)')
    args = parser.parse_args()
    if args.vergelijk:
        return main_vergelijk(args, parser)

    uit = Path(args.uitvoer or 'dashboard/meldingen_groen.geojson')
    csv_pad = Path(args.data) / STATS_CSV
    for pad in (uit, csv_pad):
        if pad.exists():
            parser.error(f'{pad} bestaat al; verwijder het of kies een andere naam')

    print('Stap 1: luchtfoto 2026 ophalen')
    rgb_pad, rgb_info = download('rgb', args.data)
    cir_pad, cir_info = (None, None)
    if not args.zonder_cir:
        try:
            cir_pad, cir_info = download('cir', args.data)
        except RuntimeError as e:
            print(f'  LET OP: infrarood niet gelukt, verder met alleen RGB.\n  {e}')
    met_cir = cir_pad is not None
    infos = {'rgb': {k: v for k, v in rgb_info.items() if k != 'getmap_urls'}}
    if met_cir:
        infos['cir'] = {k: v for k, v in cir_info.items() if k != 'getmap_urls'}

    print('Stap 2: groenindex per vlak')
    features = json.loads(Path(args.bestand).read_bytes())['features']
    rijen = bereken(features, rgb_pad, cir_pad)
    csv_pad.parent.mkdir(parents=True, exist_ok=True)
    schrijf_csv(csv_pad, rijen)
    print(f'  {len(rijen)} vlakken -> {csv_pad}')

    print('Stap 3: meldingen')
    resultaat = maak_meldingen_groen(args.bestand, rijen, infos, met_cir)
    uit.parent.mkdir(parents=True, exist_ok=True)
    uit.write_text(json.dumps(resultaat, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f"  {len(resultaat['features'])} meldingen -> {uit}")

    # Test-overzicht: per soort groen hoeveel vlakken gemarkeerd
    per_klasse = collections.Counter(r['klasse'] for r in rijen)
    gemarkeerd = collections.defaultdict(collections.Counter)
    klasse_van_id = {r['lokaal_id']: r['klasse'] for r in rijen}
    for f in resultaat['features']:
        gemarkeerd[f['properties']['type']][klasse_van_id[f['properties']['lokaal_id']]] += 1
    typen = list(resultaat['metadata']['typen'])
    print('\n  soort groen               vlakken  ' + '  '.join(f'{t:>24}' for t in typen))
    for k, n in per_klasse.most_common():
        print(f'  {k:<25} {n:7d}  ' + '  '.join(f'{gemarkeerd[t][k]:>24d}' for t in typen))
    te_klein = sum(r['n_pixels'] < MIN_PIXELS for r in rijen)
    weinig_dekking = sum(r['n_pixels'] >= MIN_PIXELS and r['dekking'] < MIN_DEKKING for r in rijen)
    print(f'\n  {te_klein} vlakken overgeslagen: minder dan {MIN_PIXELS} pixels.')
    print(f'  {weinig_dekking} vlakken overgeslagen: minder dan {MIN_DEKKING:.0%} van het vlak op de foto (randobjecten).')


def main_vergelijk(args, parser):
    jaren = args.vergelijk + [JAAR] if len(args.vergelijk) == 1 else args.vergelijk
    if len(jaren) != 2 or jaren[0] == jaren[1]:
        parser.error('--vergelijk verwacht één of twee verschillende jaren')
    onbekend = [j for j in jaren if j not in LAGEN]
    if onbekend:
        parser.error(f'onbekend jaar {onbekend}; beschikbaar: {sorted(LAGEN)}')
    oud, nieuw = sorted(jaren)
    prefix = args.prefix or PREFIX_VERSCHIL.get((oud, nieuw))
    if not prefix:
        parser.error(f'geen ID-prefix voor {oud}-{nieuw}; geef --prefix of vul PREFIX_VERSCHIL aan')
    gebruikt = {p for paar, p in PREFIX_VERSCHIL.items() if paar != (oud, nieuw)} | {'M', 'G'}
    if prefix in gebruikt:
        parser.error(f'prefix {prefix} is al in gebruik ({sorted(gebruikt)})')
    # 2025-2026 houdt zijn oorspronkelijke bestandsnaam
    standaard = ('dashboard/meldingen_groen_verschil.geojson' if (oud, nieuw) == OORSPRONKELIJK_PAAR
                 else f'dashboard/meldingen_groen_verschil_{oud}_{nieuw}.geojson')
    uit = Path(args.uitvoer or standaard)
    csv_pad = Path(args.data) / f'groensignaal_{oud}_{nieuw}.csv'
    for pad in (uit, csv_pad):
        if pad.exists():
            parser.error(f'{pad} bestaat al; verwijder het of kies een andere naam')
    if args.zonder_cir:
        parser.error('--vergelijk gebruikt ExG en NDVI; laat --zonder-cir weg')

    print(f'Stap 1: luchtfoto {oud} en {nieuw} ophalen')
    paden, infos = {}, {}
    for jaar in (oud, nieuw):
        for soort in ('rgb', 'cir'):
            # Geen terugval op alleen RGB: zonder infrarood is de vergelijking niet compleet
            paden[jaar, soort], info = download(soort, args.data, jaar)
            infos[f'{soort}_{jaar}'] = {k: v for k, v in info.items() if k != 'getmap_urls'}
    for soort in ('rgb', 'cir'):
        with rasterio.open(paden[oud, soort]) as a, rasterio.open(paden[nieuw, soort]) as b:
            if (a.transform, a.shape, a.crs) != (b.transform, b.shape, b.crs):
                raise RuntimeError(f'{soort}: rasters {oud} en {nieuw} liggen niet op hetzelfde grid')
    maanden = {}
    for j in (oud, nieuw):
        for soort in ('rgb', 'cir'):
            p = OPNAME[j][soort][0]
            maanden[j, soort] = (p[0][5:], p[1][5:])
            print(f'  opnameperiode {soort} {j} volgens metadata: {p[0]} t/m {p[1]}')
    for soort in ('rgb', 'cir'):
        if maanden[oud, soort] != maanden[nieuw, soort]:
            print(f'  LET OP: {soort} van {oud} en {nieuw} is in verschillende maanden opgenomen.')
    for j in (oud, nieuw):
        if maanden[j, 'rgb'] != maanden[j, 'cir']:
            print(f'  LET OP: in {j} komen RGB en infrarood uit verschillende vluchten (andere periode).')
    for soort in ('rgb', 'cir'):
        a, b = LAGEN[oud][soort], LAGEN[nieuw][soort]
        if a[5:] != b[5:]:
            print(f'  LET OP: ander product voor {soort}: {a} tegenover {b} (beide op {RESOLUTIE_M} m opgevraagd).')
    print(f'  conditie op de foto: {conditie_tekst(oud, nieuw)}')
    med = gebied_medianen(paden, (oud, nieuw))
    verschil_gebied = {x: med[nieuw][x] - med[oud][x] for x in INDEXEN}
    print('  mediaan hele gebied: ' + ', '.join(
        f"{x.upper()} {med[oud][x]:.3f} -> {med[nieuw][x]:.3f} ({verschil_gebied[x]:+.3f})" for x in INDEXEN))

    print('Stap 2: groenindex per vlak, per jaar')
    features = json.loads(Path(args.bestand).read_bytes())['features']
    rij = {j: bereken(features, paden[j, 'rgb'], paden[j, 'cir']) for j in (oud, nieuw)}
    rijen, stijging = vergelijk(rij[oud], rij[nieuw], oud, nieuw)
    csv_pad.parent.mkdir(parents=True, exist_ok=True)
    schrijf_csv(csv_pad, rijen)
    print(f'  {len(rijen)} vlakken -> {csv_pad}')
    print(f'  mediane verandering aandeel groene pixels {oud} -> {nieuw} per soort (ExG / NDVI):')
    for k, s in sorted(stijging.items(), key=lambda kv: kv[0]):
        print(f"    {k:<25} {s['exg']:+.2f} / {s['ndvi']:+.2f}")

    bruikbaar = [r for r in rijen if r['bruikbaar']]
    verschil_vlakken = {x: float(np.median([r[f'd_{x}_aandeel'] for r in bruikbaar])) for x in INDEXEN}
    print('  mediane verandering aandeel groene pixels, alle bruikbare vlakken: ' + ', '.join(
        f'{x.upper()} {verschil_vlakken[x]:+.3f}' for x in INDEXEN))
    for x in INDEXEN:
        a = np.array([r[f'{x}_afwijking'] for r in bruikbaar])
        print(f'  robuuste spreiding afwijking {x.upper()}: {np.median(np.abs(a - np.median(a))) * 1.4826:.3f}')

    print('Stap 3: meldingen')
    extra = None
    if (oud, nieuw) != OORSPRONKELIJK_PAAR:
        extra = {
            'jaarpaar': [oud, nieuw],
            'conditie_op_foto': {str(j): CONDITIE[j] for j in (oud, nieuw)},
            'mediaan_gebied': {str(j): med[j] for j in (oud, nieuw)},
            'mediane_verandering_gebied': verschil_gebied,
            'mediane_verandering_aandeel_vlakken': verschil_vlakken,
        }
    resultaat = maak_meldingen_verschil(args.bestand, rijen, infos, oud, nieuw, prefix, extra)
    uit.parent.mkdir(parents=True, exist_ok=True)
    uit.write_text(json.dumps(resultaat, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f"  {len(resultaat['features'])} meldingen -> {uit}")

    per_klasse = collections.Counter(r['klasse'] for r in rijen)
    gemarkeerd = collections.defaultdict(collections.Counter)
    klasse_van_id = {r['lokaal_id']: r['klasse'] for r in rijen}
    for f in resultaat['features']:
        gemarkeerd[f['properties']['type']][klasse_van_id[f['properties']['lokaal_id']]] += 1
    typen = list(resultaat['metadata']['typen'])
    print('\n  soort groen               vlakken  ' + '  '.join(f'{t:>18}' for t in typen))
    for k, n in per_klasse.most_common():
        print(f'  {k:<25} {n:7d}  ' + '  '.join(f'{gemarkeerd[t][k]:>18d}' for t in typen))
    print(f"\n  {sum(not r['bruikbaar'] for r in rijen)} vlakken zonder oordeel "
          f'(minder dan {MIN_PIXELS} pixels of minder dan {MIN_DEKKING:.0%} op de foto).')
    later = [f for f in resultaat['features'] if 'registratiejaar' in f['properties']['toelichting']
             and 'LET OP: registratiejaar' in f['properties']['toelichting']]
    if (oud, nieuw) != OORSPRONKELIJK_PAAR:
        print(f'  {len(later)} meldingen met registratiejaar na {oud} (gemarkeerd in de toelichting).')
    print('  gevoeligheid (afgenomen / toegenomen): ' + ', '.join(
        f"{t:.2f} -> {sum(r['exg_afwijking'] <= -t and r['ndvi_afwijking'] <= -t for r in bruikbaar)} / "
        f"{sum(r['exg_afwijking'] >= t and r['ndvi_afwijking'] >= t for r in bruikbaar)}"
        for t in (0.30, 0.40, 0.50, 0.60)))


if __name__ == '__main__':
    main()
