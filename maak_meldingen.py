"""Maak meldingen.geojson uit een lokale BGT-werkset (begroeidterreindeel).

Elke melding is een signaal, geen vastgestelde fout. De controles en drempels
zijn dezelfde als in controleer_bgt.py en controleer_ruimtelijk.py uit het
Data Quality Rapport. Vereist: Python 3.10+, shapely 2 en pyproj 3.

Gebruik:
    python maak_meldingen.py data/BGT_testgebied_actueel.geojson \
        --uitvoer dashboard/meldingen.geojson
"""
import argparse
import collections
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import Polygon, box, mapping, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree
from shapely.validation import explain_validity, make_valid

# Gebied van de API-aanvraag (EPSG:3857), zoals in het rapport.
BBOX_3857 = (560822.7, 6805306.6, 562441.9, 6806302.7)

# Verkennende onderzoeksdrempels, geen BGT-normen.
KLEIN_M2 = 5.0      # vlakken kleiner dan dit krijgen een melding "klein_vlak"
OVERLAP_M2 = 0.01   # overlap groter dan dit krijgt een melding "overlap"

# Waardelijsten uit BGT-catalogus 1.2 (par. 9.8 en 9.1), zoals in controleer_bgt.py.
FYSIEK = {'loofbos', 'gemengd bos', 'naaldbos', 'heide', 'struiken',
          'houtwal', 'duin', 'grasland overig', 'moeras', 'rietland',
          'kwelder', 'fruitteelt', 'boomteelt', 'bouwland',
          'grasland agrarisch', 'groenvoorziening'}
STATUS = {'bestaand'}
BASIS = ['lokaal_id', 'fysiek_voorkomen', 'bronhouder', 'status']

# type -> (label, ernst, uitleg). De volgorde bepaalt ook de volgorde in het dashboard.
TYPEN = {
    'ongeldige_geometrie': ('Ongeldige geometrie', 'hoog',
                            'Het vlak is ongeldig volgens GEOS.'),
    'overlap': ('Overlap tussen vlakken', 'hoog',
                f'Twee vlakken overlappen elkaar met meer dan {OVERLAP_M2} m2.'),
    'dubbele_geometrie': ('Dubbele geometrie', 'hoog',
                          'Twee objecten hebben exact dezelfde vorm.'),
    'dubbel_lokaal_id': ('Dubbel lokaal_id', 'hoog',
                         'Dit lokaal_id komt in meer dan een record voor.'),
    'leeg_basisveld': ('Leeg basisveld', 'hoog',
                       'Een van de vier basisvelden is leeg.'),
    'waarde_buiten_domein': ('Waarde buiten domein', 'hoog',
                             'fysiek_voorkomen of status staat niet in de catalogus.'),
    'plus_onbekend': ('Plus-kenmerk onbekend', 'laag',
                      'Groenvoorziening zonder aanvullend vegetatiekenmerk. '
                      'Het veld is optioneel; dit is geen normoverschrijding.'),
    'klein_vlak': ('Klein vlak', 'laag',
                   f'Kleiner dan {KLEIN_M2:g} m2: gevoeliger voor schaduw, randpixels '
                   'en kleine positieverschillen op beeldmateriaal. Geen BGT-afkeurgrens.'),
    'randobject': ('Randobject', 'info',
                   'Het vlak raakt of kruist de rand van het gekozen gebied. '
                   'Het vlak is niet afgeknipt.'),
    'open_ruimte': ('Ingesloten open ruimte', 'info',
                    'Open ruimte binnen de unie van begroeide terreindelen. '
                    'Geen bewezen BGT-gat: andere vlaktypen ontbreken in de werkset.'),
}


def leeg(waarde):
    return waarde is None or (isinstance(waarde, str) and not waarde.strip())


def afronden(geom, decimalen=7):
    return shapely.transform(geom, lambda c: np.round(c, decimalen))


def maak_meldingen(pad):
    pad = Path(pad)
    raw = pad.read_bytes()
    features = json.loads(raw)['features']
    props = [f['properties'] for f in features]
    geoms_4326 = [shape(f['geometry']) for f in features]

    naar_rd = Transformer.from_crs(4326, 28992, always_xy=True)
    naar_3857 = Transformer.from_crs(4326, 3857, always_xy=True)
    naar_4326 = Transformer.from_crs(28992, 4326, always_xy=True)

    def projecteer(geom, tr):
        return shapely.transform(geom, lambda c: np.column_stack(tr.transform(c[:, 0], c[:, 1])))

    geoms_rd = [projecteer(g, naar_rd) for g in geoms_4326]
    geoms_3857 = [projecteer(g, naar_3857) for g in geoms_4326]
    bbox_grens = box(*BBOX_3857).boundary

    meldingen = []

    def voeg_toe(typ, geom_4326, p, toelichting, lokaal_id=None, oppervlakte=None):
        meldingen.append({
            'type': typ,
            'geometry': geom_4326,
            'lokaal_id': lokaal_id if lokaal_id is not None else (p or {}).get('lokaal_id'),
            'toelichting': toelichting,
            'p': p or {},
            'oppervlakte': oppervlakte,
        })

    # Per object
    id_telling = collections.Counter(p['lokaal_id'] for p in props if not leeg(p.get('lokaal_id')))
    for i, p in enumerate(props):
        g4326, grd = geoms_4326[i], geoms_rd[i]
        opp = grd.area
        if not g4326.is_valid:
            voeg_toe('ongeldige_geometrie', g4326, p, explain_validity(g4326), oppervlakte=opp)
        lege = [k for k in BASIS if leeg(p.get(k))]
        if lege:
            voeg_toe('leeg_basisveld', g4326, p, 'Leeg: ' + ', '.join(lege), oppervlakte=opp)
        if (not leeg(p.get('fysiek_voorkomen')) and p['fysiek_voorkomen'] not in FYSIEK) or \
           (not leeg(p.get('status')) and p['status'] not in STATUS):
            voeg_toe('waarde_buiten_domein', g4326, p,
                     f"fysiek_voorkomen={p.get('fysiek_voorkomen')!r}, status={p.get('status')!r}",
                     oppervlakte=opp)
        if not leeg(p.get('lokaal_id')) and id_telling[p['lokaal_id']] > 1:
            voeg_toe('dubbel_lokaal_id', g4326, p,
                     f"Komt {id_telling[p['lokaal_id']]} keer voor.", oppervlakte=opp)
        if p.get('fysiek_voorkomen') == 'groenvoorziening' and leeg(p.get('plus_fysiek_voorkomen')):
            reden = p.get('plus_fysiek_voorkomen_leeg') or 'onbekend'
            voeg_toe('plus_onbekend', g4326, p,
                     f'plus_fysiek_voorkomen is leeg (reden in bron: {reden}).', oppervlakte=opp)
        if opp < KLEIN_M2:
            voeg_toe('klein_vlak', g4326, p, f'Oppervlakte {opp:.2f} m2.', oppervlakte=opp)
        if geoms_3857[i].intersects(bbox_grens):
            voeg_toe('randobject', g4326, p,
                     'Raakt of kruist de rand van het gekozen gebied.', oppervlakte=opp)

    # Per paar: gelijke vormen en overlap. Ongeldige vlakken worden alleen voor deze
    # berekening hersteld (make_valid); de oorspronkelijke data blijft ongewijzigd en
    # het ongeldige vlak is hierboven al gemeld.
    reken = [g if g.is_valid else make_valid(g) for g in geoms_rd]
    boom = STRtree(reken)
    for i, g in enumerate(reken):
        for j0 in boom.query(g):
            j = int(j0)
            if j <= i:
                continue
            if g.equals(reken[j]):
                voeg_toe('dubbele_geometrie', geoms_4326[i], props[i],
                         f"Zelfde vorm als {props[j].get('lokaal_id')}.", oppervlakte=g.area)
            doorsnede = g.intersection(reken[j])
            if doorsnede.area > OVERLAP_M2:
                voeg_toe('overlap', afronden(projecteer(doorsnede, naar_4326)), props[i],
                         f"Overlapt {props[j].get('lokaal_id')} over {doorsnede.area:.2f} m2.",
                         oppervlakte=doorsnede.area)

    # Ingesloten open ruimten in de unie van alle vlakken
    unie = unary_union(reken)
    if unie.geom_type == 'Polygon':
        delen = [unie]
    else:
        delen = [d for d in getattr(unie, 'geoms', []) if d.geom_type == 'Polygon']
    for deel in delen:
        for ring in deel.interiors:
            gat = Polygon(ring)
            voeg_toe('open_ruimte', afronden(projecteer(gat, naar_4326)), None,
                     f'Ingesloten open ruimte van {gat.area:.2f} m2.',
                     lokaal_id=None, oppervlakte=gat.area)

    # Vaste volgorde: type, daarna lokaal_id, zodat ID's reproduceerbaar zijn
    volgorde = {t: n for n, t in enumerate(TYPEN)}
    meldingen.sort(key=lambda m: (volgorde[m['type']], str(m['lokaal_id']), m['toelichting']))

    uit = []
    for n, m in enumerate(meldingen, 1):
        p = m['p']
        jaar = None
        if not leeg(p.get('tijdstip_registratie')):
            try:
                jaar = datetime.fromisoformat(p['tijdstip_registratie'].replace('Z', '+00:00')).year
            except ValueError:
                pass
        uit.append({
            'type': 'Feature',
            'geometry': mapping(afronden(m['geometry'])),
            'properties': {
                'id': f'M-{n:04d}',
                'type': m['type'],
                'ernst': TYPEN[m['type']][1],
                'toelichting': m['toelichting'],
                'lokaal_id': m['lokaal_id'],
                'bronhouder': p.get('bronhouder'),
                'fysiek_voorkomen': p.get('fysiek_voorkomen'),
                'plus_fysiek_voorkomen': p.get('plus_fysiek_voorkomen'),
                'registratiejaar': jaar,
                'oppervlakte_m2': None if m['oppervlakte'] is None else round(m['oppervlakte'], 2),
            },
        })

    telling = collections.Counter(f['properties']['type'] for f in uit)
    return {
        'type': 'FeatureCollection',
        'metadata': {
            'bronbestand': pad.name,
            'sha256_bronbestand': hashlib.sha256(raw).hexdigest(),
            'aantal_objecten': len(features),
            'gegenereerd_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'drempels': {'klein_vlak_m2': KLEIN_M2, 'overlap_m2': OVERLAP_M2},
            'bbox_epsg3857': list(BBOX_3857),
            'software': {'shapely': shapely.__version__, 'GEOS': shapely.geos_version_string},
            'let_op': 'Een melding is een signaal en geen vastgestelde fout. '
                      'Drempels zijn verkennende onderzoeksdrempels, geen BGT-normen.',
            'typen': {t: {'label': v[0], 'ernst': v[1], 'uitleg': v[2]} for t, v in TYPEN.items()},
            'aantal_per_type': {t: telling.get(t, 0) for t in TYPEN},
        },
        'features': uit,
    }


def klasse_van(p):
    """Soort groen voor de kaart: het plus-kenmerk, of (zonder) 'plus onbekend' bij
    groenvoorziening, of bij de graslandklassen het fysiek_voorkomen zelf."""
    if not leeg(p.get('plus_fysiek_voorkomen')):
        return p['plus_fysiek_voorkomen']
    if p.get('fysiek_voorkomen') == 'groenvoorziening':
        return 'plus onbekend'
    return p.get('fysiek_voorkomen') or 'onbekend'


# Vaste volgorde in de legenda; soorten die hier niet in staan komen daarna.
KLASSE_VOLGORDE = ['bosplantsoen', 'heesters', 'gras- en kruidachtigen', 'planten',
                   'bodembedekkers', 'struikrozen', 'plus onbekend',
                   'grasland agrarisch', 'grasland overig']


def maak_vlakken(pad):
    """Alle BGT-vlakken van de werkset, met een klasse per vlak, voor de kaartlaag."""
    pad = Path(pad)
    raw = pad.read_bytes()
    features = json.loads(raw)['features']
    naar_rd = Transformer.from_crs(4326, 28992, always_xy=True)

    uit = []
    for f in features:
        p = f['properties']
        g = shape(f['geometry'])
        opp = shapely.transform(g, lambda c: np.column_stack(naar_rd.transform(c[:, 0], c[:, 1]))).area
        jaar = None
        if not leeg(p.get('tijdstip_registratie')):
            try:
                jaar = datetime.fromisoformat(p['tijdstip_registratie'].replace('Z', '+00:00')).year
            except ValueError:
                pass
        uit.append({
            'type': 'Feature',
            'geometry': mapping(afronden(g)),
            'properties': {
                'lokaal_id': p.get('lokaal_id'),
                'klasse': klasse_van(p),
                'fysiek_voorkomen': p.get('fysiek_voorkomen'),
                'plus_fysiek_voorkomen': p.get('plus_fysiek_voorkomen'),
                'bronhouder': p.get('bronhouder'),
                'registratiejaar': jaar,
                'oppervlakte_m2': round(opp, 2),
            },
        })

    telling = collections.Counter(f['properties']['klasse'] for f in uit)
    volgorde = [k for k in KLASSE_VOLGORDE if k in telling] + \
               sorted(k for k in telling if k not in KLASSE_VOLGORDE)
    return {
        'type': 'FeatureCollection',
        'metadata': {
            'bronbestand': pad.name,
            'sha256_bronbestand': hashlib.sha256(raw).hexdigest(),
            'aantal_objecten': len(uit),
            'gegenereerd_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'klassen': volgorde,
            'aantal_per_klasse': {k: telling[k] for k in volgorde},
            'let_op': 'Klasse = plus_fysiek_voorkomen. "plus onbekend" betekent: groenvoorziening '
                      'zonder aanvullend kenmerk. De graslandklassen hebben in de catalogus geen plus-kenmerk.',
        },
        'features': uit,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('bestand', help='lokale werkset (GeoJSON, EPSG:4326)')
    parser.add_argument('--uitvoer', default='dashboard/meldingen.geojson')
    parser.add_argument('--vlakken', default=None,
                        help='uitvoer met alle BGT-vlakken (standaard: bgt_vlakken.geojson naast --uitvoer)')
    args = parser.parse_args()
    uit = Path(args.uitvoer)
    uit_vlakken = Path(args.vlakken) if args.vlakken else uit.parent / 'bgt_vlakken.geojson'
    for pad in (uit, uit_vlakken):
        if pad.exists():
            parser.error(f'{pad} bestaat al; verwijder het of kies een andere naam')
    resultaat = maak_meldingen(args.bestand)
    vlakken = maak_vlakken(args.bestand)
    uit.parent.mkdir(parents=True, exist_ok=True)
    uit_vlakken.parent.mkdir(parents=True, exist_ok=True)
    uit.write_text(json.dumps(resultaat, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    uit_vlakken.write_text(json.dumps(vlakken, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    m = resultaat['metadata']
    print(f"{len(resultaat['features'])} meldingen uit {m['aantal_objecten']} objecten -> {uit}")
    for t, n in m['aantal_per_type'].items():
        print(f'  {n:4d}  {t}')
    print(f"{len(vlakken['features'])} BGT-vlakken -> {uit_vlakken}")
    for k, n in vlakken['metadata']['aantal_per_klasse'].items():
        print(f'  {n:4d}  {k}')


if __name__ == '__main__':
    main()
