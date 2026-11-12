"""Voeg meldingen.geojson en meldingen_groen.geojson samen tot meldingen_alle.geojson.

- features: achter elkaar (eerst meldingen.geojson, dan meldingen_groen.geojson)
- metadata: die van meldingen.geojson blijft staan (ook sha256_bronbestand), met
  metadata.typen en metadata.aantal_per_type van beide bestanden samengevoegd en een
  extra veld 'samengevoegd_uit' met de bronbestanden
- controles: zelfde werkset (sha256_bronbestand), geen dubbele id's, aantal klopt,
  geen type dat in beide bestanden een andere betekenis heeft
- een bestaand uitvoerbestand wordt niet overschreven
- --zonder-type TYPE laat een type weg
- --vervang-typen BESTAND.json vervangt bewust label/uitleg van de genoemde typen door
  één definitie. Alleen voor die typen vervalt de controle op tegenstrijdige uitleg; de
  oorspronkelijke teksten per bron komen in metadata.vervangen_typen. De ernst mag niet
  veranderen, omdat die ook in elke melding staat.

Gebruik:
    python voeg_samen.py
    python voeg_samen.py dashboard/meldingen.geojson dashboard/meldingen_groen.geojson \
        --uitvoer dashboard/meldingen_alle.geojson
    python voeg_samen.py dashboard/meldingen_alle.geojson \
        dashboard/meldingen_groen_verschil_2024_2026.geojson \
        --vervang-typen typen_verschil_algemeen.json --uitvoer dashboard/meldingen_alle_v3.geojson
"""
import argparse
import collections
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def lees(pad):
    raw = Path(pad).read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def lees_vervanging(pad):
    """Lees {type: {label, ernst, uitleg}} en controleer de vorm."""
    if not pad:
        return {}
    data = json.loads(Path(pad).read_text(encoding='utf-8'))
    for t, info in data.items():
        if t.startswith('_'):
            continue  # commentaarvelden
        if set(info) != {'label', 'ernst', 'uitleg'} or not all(isinstance(v, str) and v for v in info.values()):
            sys.exit(f'FOUT: {pad}: type {t!r} moet precies label, ernst en uitleg hebben (niet leeg)')
    return {t: info for t, info in data.items() if not t.startswith('_')}


def voeg_samen(paden, zonder_typen=(), vervang=None):
    zonder_typen = set(zonder_typen)
    vervang = vervang or {}
    delen = [(Path(p), *lees(p)) for p in paden]
    alle_typen = {t for _, d, _ in delen for t in d.get('metadata', {}).get('typen', {})}
    onbekend = sorted(zonder_typen - alle_typen)
    if onbekend:
        sys.exit(f'FOUT: --zonder-type {onbekend} komt in geen enkel bestand voor')
    onbekend = sorted(set(vervang) - alle_typen)
    if onbekend:
        sys.exit(f'FOUT: --vervang-typen {onbekend} komt in geen enkel bestand voor')
    dubbel_opgegeven = sorted(set(vervang) & zonder_typen)
    if dubbel_opgegeven:
        sys.exit(f'FOUT: {dubbel_opgegeven} staat zowel bij --zonder-type als bij --vervang-typen')
    basis = delen[0][1]
    meta = dict(basis['metadata'])
    werkset = meta.get('sha256_bronbestand')

    features, typen, per_type, bronnen = [], {}, collections.Counter(), []
    oorspronkelijk = collections.defaultdict(dict)   # type -> {bestand: info}
    for pad, d, sha in delen:
        m = d.get('metadata', {})
        if m.get('sha256_bronbestand') != werkset:
            sys.exit(f'FOUT: {pad} hoort bij een andere werkset '
                     f'(sha256_bronbestand {m.get("sha256_bronbestand")} != {werkset})')
        for t, info in m.get('typen', {}).items():
            if t in zonder_typen:
                continue
            if t in vervang:
                # Bewust vervangen: geen controle op gelijke uitleg, wel op gelijke ernst
                if info.get('ernst') != vervang[t]['ernst']:
                    sys.exit(f'FOUT: --vervang-typen {t!r}: ernst {vervang[t]["ernst"]!r} wijkt af van '
                             f'{info.get("ernst")!r} in {pad}; de ernst staat ook in elke melding')
                oorspronkelijk[t][pad.name] = info
                typen.setdefault(t, dict(vervang[t]))
                continue
            if t in typen and typen[t] != info:
                sys.exit(f'FOUT: type {t!r} heeft in {pad} een andere label/ernst/uitleg')
            typen.setdefault(t, info)
        opgenomen = [f for f in d['features'] if f['properties']['type'] not in zonder_typen]
        for f in opgenomen:
            per_type[f['properties']['type']] += 1
        features.extend(opgenomen)
        bron = {
            'bestand': pad.name,
            'sha256': sha,
            'aantal_features': len(opgenomen),
            'gegenereerd_utc': m.get('gegenereerd_utc'),
            'drempels': m.get('drempels'),
        }
        if len(opgenomen) != len(d['features']):
            bron['weggelaten'] = dict(collections.Counter(
                f['properties']['type'] for f in d['features'] if f['properties']['type'] in zonder_typen))
        if m.get('samengevoegd_uit'):
            # Bron is zelf al een samengevoegd bestand: herkomst bewaren
            bron['bestond_uit'] = m['samengevoegd_uit']
        bronnen.append(bron)
    for f in features:
        t = f['properties']['type']
        if t in vervang and f['properties'].get('ernst') != vervang[t]['ernst']:
            sys.exit(f"FOUT: melding {f['properties']['id']} heeft ernst {f['properties'].get('ernst')!r}, "
                     f"--vervang-typen zegt {vervang[t]['ernst']!r}")

    # Controles
    dubbel = [i for i, n in collections.Counter(f['properties']['id'] for f in features).items() if n > 1]
    if dubbel:
        sys.exit(f'FOUT: {len(dubbel)} dubbele id\'s, bijvoorbeeld {dubbel[:5]}')
    verwacht = sum(b['aantal_features'] for b in bronnen)
    if len(features) != verwacht:
        sys.exit(f'FOUT: {len(features)} features, verwacht {verwacht}')
    zonder_type = sorted({f['properties']['type'] for f in features} - set(typen))
    if zonder_type:
        sys.exit(f'FOUT: typen zonder beschrijving in metadata.typen: {zonder_type}')

    meta['typen'] = typen
    meta['aantal_per_type'] = {t: per_type.get(t, 0) for t in typen}
    meta['samengevoegd_uit'] = bronnen
    if vervang:
        meta['vervangen_typen'] = {t: {'nieuw': vervang[t], 'oorspronkelijk_per_bron': oorspronkelijk[t]}
                                   for t in vervang}
    else:
        meta.pop('vervangen_typen', None)
    meta['samengevoegd_utc'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    return {'type': 'FeatureCollection', 'metadata': meta, 'features': features}


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('bestanden', nargs='*',
                        default=['dashboard/meldingen.geojson', 'dashboard/meldingen_groen.geojson'],
                        help='in te voegen bestanden; het eerste levert de metadata')
    parser.add_argument('--uitvoer', default='dashboard/meldingen_alle.geojson')
    parser.add_argument('--zonder-type', action='append', default=[], metavar='TYPE',
                        help='laat dit meldingstype weg (features en metadata.typen); herhaalbaar')
    parser.add_argument('--vervang-typen', metavar='JSON',
                        help='JSON {type: {label, ernst, uitleg}}: vervang bewust label en uitleg van deze typen')
    args = parser.parse_args()
    uit = Path(args.uitvoer)
    if uit.exists():
        parser.error(f'{uit} bestaat al; verwijder het of kies een andere naam')
    if len(args.bestanden) < 2:
        parser.error('geef minstens twee bestanden')

    vervang = lees_vervanging(args.vervang_typen)
    resultaat = voeg_samen(args.bestanden, args.zonder_type, vervang)
    uit.write_text(json.dumps(resultaat, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    m = resultaat['metadata']
    som = ' + '.join(str(b['aantal_features']) for b in m['samengevoegd_uit'])
    print(f"{som} = {len(resultaat['features'])} meldingen, geen dubbele id's -> {uit}")
    for b in m['samengevoegd_uit']:
        if b.get('weggelaten'):
            print(f"  weggelaten uit {b['bestand']}: {b['weggelaten']}")
    for t, v in m.get('vervangen_typen', {}).items():
        print(f"  VERVANGEN (--vervang-typen {args.vervang_typen}): type {t!r}")
        for bestand, info in v['oorspronkelijk_per_bron'].items():
            print(f"    was in {bestand}: label {info.get('label')!r}, uitleg {info.get('uitleg', '')[:70]!r}...")
        print(f"    nu: label {v['nieuw']['label']!r}, ernst {v['nieuw']['ernst']!r}")
        print(f"    controle op gelijke uitleg tussen bronnen is voor dit type uitgezet; "
              f"oorspronkelijke teksten staan in metadata.vervangen_typen")
    for t, n in m['aantal_per_type'].items():
        print(f'  {n:4d}  {t}')


if __name__ == '__main__':
    main()
