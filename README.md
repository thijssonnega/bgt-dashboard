# BGT-meldingen dashboard (prototype)

Eerste werkende prototype voor Team 7, Gemeente IJsselstein. Het doet drie dingen:

1. **Controleren**: `maak_meldingen.py` voert de kwaliteitscontroles uit op de bewaarde werkset (824 begroeide terreindelen) en schrijft elke bevinding als melding weg.
2. **Karteren**: `dashboard/index.html` toont op een kaart met de PDOK-luchtfoto eronder alle 824 BGT-vlakken van het testgebied, gekleurd per soort groen, met de meldingen erbovenop.
3. **Beoordelen**: een medewerker (of jullie zelf) markeert elke melding als terecht, onterecht of onzeker. Dat levert de testset van beoordeelde locaties op die jullie Data Mining Goals vragen.

Een melding is een **signaal**, geen vastgestelde fout. De drempels (klein vlak < 5 m2, overlap > 0,01 m2) zijn verkennende onderzoeksdrempels, geen BGT-normen.

## Mappen

```
maak_meldingen.py          controles -> meldingen.geojson en bgt_vlakken.geojson
requirements.txt           shapely en pyproj (dezelfde versies als in het rapport)
data/                      bewaarde werkset BGT_testgebied_actueel.geojson (824 objecten)
dashboard/
  index.html               de kaartpagina (geen build-stap)
  meldingen.geojson        de meldingen (uitvoer van het script, al meegeleverd)
  bgt_vlakken.geojson      alle 824 BGT-vlakken met soort groen (idem)
  lib/leaflet/             Leaflet 1.9.4, lokaal meegeleverd (BSD-2, zie LICENSE)
```

## Draaien

Python 3.10 of hoger.

```
pip install -r requirements.txt
```

Meldingen en vlakken opnieuw maken (een bestaand uitvoerbestand wordt niet overschreven, verwijder `meldingen.geojson` en `bgt_vlakken.geojson` eerst):

```
python maak_meldingen.py data/BGT_testgebied_actueel.geojson --uitvoer dashboard/meldingen.geojson
```

Dashboard openen. Dubbelklikken op `index.html` werkt niet, want de pagina haalt een bestand op. Start een lokale server:

```
cd dashboard
python -m http.server 8000
```

en open daarna http://localhost:8000 in je browser.

## Wat staat erin (op de bewaarde werkset)

| Soort melding | Aantal | Ernst |
| --- | --- | --- |
| Plus-kenmerk onbekend (groenvoorziening) | 42 | laag |
| Klein vlak (< 5 m2) | 67 | laag |
| Randobject | 86 | info |
| Ingesloten open ruimte | 34 | info |
| Ongeldige geometrie, overlap, dubbele geometrie, dubbel lokaal_id, leeg basisveld, waarde buiten domein | 0 | hoog |

Dit komt overeen met de cijfers in het Data Quality Rapport. De controles met nul meldingen zijn bewust zichtbaar in het dashboard: ze zijn uitgevoerd en niets gevonden. Op een bewust kapotte kopie van de data (ongeldige vorm, overlap, dubbel record, leeg veld, ongeldige waarde) slaan ze alle aan.

Een object kan meerdere meldingen hebben (bijvoorbeeld randobject en plus onbekend). Die liggen dan op de kaart op elkaar; in de lijst staan ze apart.

## De BGT-vlakken op de kaart

Onder **Kaartlagen** (tabblad Filters) staan alle 824 BGT-vlakken van het testgebied, gekleurd per soort groen. De soort is het aanvullende kenmerk `plus_fysiek_voorkomen`:

| Soort groen | Aantal |
| --- | --- |
| Heesters | 391 |
| Gras- en kruidachtigen | 284 |
| Bosplantsoen | 72 |
| Planten | 18 |
| Bodembedekkers | 1 |
| Plus onbekend (groenvoorziening zonder aanvullend kenmerk) | 42 |
| Grasland agrarisch | 15 |
| Grasland overig | 1 |

Dat zijn 808 groenvoorzieningen en 16 graslandvlakken, samen 824. Elke soort kun je los aan- of uitzetten, de laag als geheel ook, en de meldingen kun je apart verbergen. Klik op een vlak (waar geen melding bovenop ligt) voor lokaal_id, bronhouder, registratiejaar en oppervlakte. De vlakken liggen onder de meldingen. Ontbreekt `bgt_vlakken.geojson`, dan toont het dashboard alleen de meldingen en zegt dat erbij.

## Het dashboard gebruiken

- **Filters**: soort, ernst, beoordeling en zoeken op ID of lokaal_id. Het aantal per soort staat erbij.
- **Lijst**: alle zichtbare meldingen. Klik om naar het vlak te zoomen.
- **Melding**: details, drie beoordelingsknoppen, notitie en "Volgende onbeoordeelde". Kies ook of een locatie een *voorbeeld* is (om drempels te kiezen) of een *toets* (voor de eindbeoordeling). Houd die twee gescheiden.
- **Achtergrond** wisselen kan rechtsboven (luchtfoto 2026, luchtfoto 2025, infrarood 2026, infrarood actueel, BGT-kaart, OpenStreetMap). Op de infraroodfoto kleurt levend groen rood, zo zie je snel of een groenvlak echt begroeid is.
- Beoordelingen worden alleen **in jouw browser** bewaard. Exporteer ze (JSON of CSV, onderaan) om ze te delen. Een JSON-export kan een teamgenoot importeren; het bestand moet bij dezelfde werkset horen (controle op de hash van het bronbestand).

## Formaat van meldingen.geojson

Elke feature heeft deze properties: `id`, `type`, `ernst`, `toelichting`, `lokaal_id`, `bronhouder`, `fysiek_voorkomen`, `plus_fysiek_voorkomen`, `registratiejaar`, `oppervlakte_m2`. Bovenaan staat `metadata` met onder andere het bronbestand, de SHA-256 ervan, de drempels en per soort een label, ernst en uitleg.

## Volgende stap: groensignaal toevoegen

Het dashboard leest de soorten uit `metadata.typen` en kleurt ze automatisch. Een nieuwe soort, bijvoorbeeld `mogelijk_verhard` uit een groenheidsberekening op de luchtfoto, toevoegen gaat dus zonder iets aan `index.html` te veranderen: schrijf features met dezelfde properties en voeg het type toe aan `metadata.typen`.

## Groensignaal uit de luchtfoto (groensignaal.py)

`groensignaal.py` berekent per BGT-vlak hoe groen het op de luchtfoto van 2026 is en markeert vlakken waar BGT en foto elkaar tegenspreken. Het schrijft naar een **apart bestand** en verandert niets aan `meldingen.geojson`.

```
pip install -r requirements.txt numpy rasterio
python groensignaal.py data/BGT_testgebied_actueel.geojson --uitvoer dashboard/meldingen_groen.geojson
```

Bestaat `dashboard/meldingen_groen.geojson` of `data/groensignaal_per_vlak.csv` al, dan stopt het script. Al gedownloade luchtfoto's worden hergebruikt.

### Gebruikte luchtfoto's

Alles hieronder komt uit de WMS GetCapabilities van PDOK en de metadata in het Nationaal Georegister (opgehaald op 9 november 2026).

| | RGB | Infrarood (CIR) |
| --- | --- | --- |
| Service | `https://service.pdok.nl/hwh/luchtfotorgb/wms/v1_0` | `https://service.pdok.nl/hwh/luchtfotocir/wms/v1_0` |
| Laag | `2026_orthoHR` (Luchtfoto 2026 Ortho 5 en 8cm RGB) | `2026_orthoHRIR` (Luchtfoto 2026 Ortho 5 en 8cm Infrarood) |
| Bestand | `data/luchtfoto_2026_orthoHR_rgb.tif` | `data/luchtfoto_2026_orthoHRIR_cir.tif` |
| Opnameperiode (metadata) | 2026-01-01 t/m 2026-06-01 | 2026-01-01 t/m 2026-06-01 |
| Gedownload | 2026-11-09 | 2026-11-09 |

- **Raster:** GeoTIFF in EPSG:28992 (RD New), **0,25 m** per pixel, 4005 × 2470 px, 3 banden van 8 bit. De bbox is de bbox van het testgebied (EPSG:3857, zie `maak_meldingen.py`), omgerekend naar RD en naar buiten afgerond: 131031,75 448975,5 132033,0 449593,0.
- **Alleen WMS:** er is geen WCS (de WCS-URL geeft "not found"). WMS levert alleen `image/jpeg` en maximaal 2500 px per verzoek. Het script haalt daarom 6 blokken van maximaal 2000 px op en voegt die samen. Elke GetMap-URL staat in het `.json`-bestand naast elke `.tif`.
- **Gevolg:** het zijn JPEG-gecomprimeerde, kleurgecorrigeerde 8-bit beelden, geen gekalibreerde reflectie. De NDVI is daarom een *pseudo-NDVI*. Die is alleen bruikbaar om vlakken binnen deze foto met elkaar te vergelijken.
- **Bandvolgorde CIR:** die staat niet in de metadata. Het script neemt de gangbare indeling aan (band 1 = NIR, band 2 = rood, band 3 = groen) en controleert dat. Binnen de groenvlakken is band 1 gemiddeld 192 en band 2 gemiddeld 81, wat bij vegetatie past.
- **Ligging gecontroleerd:** het contrast tussen binnen en buiten de BGT-vlakken is het grootst zonder verschuiving van het raster.

### Wat er per vlak berekend wordt

- **ExG = 2g − r − b** op chromatische coördinaten (r = R/(R+G+B), enzovoort). Zo telt de kleurverhouding en niet de helderheid.
- **NDVI = (NIR − R) / (NIR + R)** uit de infraroodfoto.
- Per vlak, op de pixels waarvan het middelpunt in het vlak valt: **gemiddelde, mediaan en aandeel pixels boven de drempel**. Ook het aantal pixels en de dekking, dat is welk deel van het vlak op de foto staat. Alles staat in `data/groensignaal_per_vlak.csv` (scheidingsteken `;`).

### Drempels (verkennend, bovenaan in het script)

| Constante | Waarde | Hoe gekozen |
| --- | --- | --- |
| `EXG_DREMPEL` | 0,07 | Otsu-drempel over alle pixels van het gebied (0,071), afgerond. Mediaan ExG is 0,14 binnen de BGT-vlakken en 0,01 erbuiten. |
| `NDVI_DREMPEL` | 0,25 | Otsu-drempel (0,261), afgerond. Mediaan NDVI is 0,44 binnen de vlakken en 0,15 erbuiten. |
| `LAAG_AANDEEL` | 0,20 | Gevoeligheidstest: 0,1 / 0,2 / 0,3 gaf 26 / 38 / 51 keer "verhard" (vóór de dekkingseis). Typische groenvlakken halen 0,65 tot 0,9. |
| `HOOG_AANDEEL` | 0,50 | Duidelijk groen volgens één index. |
| `MIN_PIXELS` | 16 | Minder dan 1 m² aan pixels: geen oordeel. |
| `MIN_DEKKING` | 0,80 | Randobjecten lopen buiten het fotogebied door. Onder 80% dekking komt er geen melding. Dat zijn 60 vlakken. |

### Meldingstypen

| Type | Ernst | Wanneer |
| --- | --- | --- |
| `mogelijk_verhard` (Mogelijk verhard of kaal) | midden | Zowel ExG als NDVI: minder dan 20% groene pixels. |
| `groensignaal_tegenstrijdig` (Groensignaal tegenstrijdig) | info | RGB (ExG) en infrarood (NDVI) zijn het oneens: de ene index ziet duidelijk groen (≥ 50%), de andere nauwelijks (< 20%). Vaak door schaduw. |

Het formaat is hetzelfde als `meldingen.geojson`: dezelfde properties, de typen in `metadata.typen` en dezelfde SHA-256 van het bronbestand. De ID's beginnen met `G-` in plaats van `M-`, zodat ze na samenvoegen niet botsen. Het dashboard toont het bestand zonder aanpassingen; dat is getest door het tijdelijk als `meldingen.geojson` te laden.

### Resultaat op de werkset (86 meldingen)

| Soort groen | Vlakken | Mogelijk verhard | Tegenstrijdig |
| --- | --- | --- | --- |
| Heesters | 391 | 16 | 32 |
| Gras- en kruidachtigen | 284 | 5 | 10 |
| Bosplantsoen | 72 | 2 | 0 |
| Plus onbekend | 42 | 12 | 8 |
| Planten | 18 | 1 | 0 |
| Grasland agrarisch | 15 | 0 | 0 |
| Grasland overig | 1 | 0 | 0 |
| Bodembedekkers | 1 | 0 | 0 |

De tegenstrijdige meldingen liggen vooral in diepe slagschaduw aan de noordkant van gebouwen. NDVI ziet daar nog vegetatie, RGB niet. Ze zijn dus eerder een teken van "foto onduidelijk" dan van een BGT-fout.

### Let op: foto en BGT beschrijven niet altijd hetzelfde

Een melding is een **signaal**, geen vastgestelde fout. Mogelijke oorzaken van een verschil:

- **Seizoen:** de foto's zijn genomen tussen januari en juni 2026. Bladverliezende heesters en bosplantsoen kunnen dan kaal zijn, en gras kan nog geel of bruin zijn.
- **Schaduw:** in schaduw van gebouwen en bomen zakt vooral ExG weg.
- **Bomen over verharding** (of andersom): de foto ziet het kronendak, de BGT beschrijft de grond.
- **Tijdverschil:** de BGT kan ouder of nieuwer zijn dan de foto. Een vlak kan inmiddels zijn heringericht.
- **Geometrie:** smalle stroken langs gevels of daken krijgen randpixels van het dak of de stoep. Een kleine verschuiving van de BGT-grens geeft dan al een laag groensignaal.
- **Kunstgras** ziet er groen uit, maar heeft een lage NDVI.

### Vergelijking luchtfoto 2025 en 2026 (`--vergelijk 2025`)

```
python groensignaal.py data/BGT_testgebied_actueel.geojson --vergelijk 2025
```

Hiervoor worden dezelfde bbox, resolutie (0,25 m), CRS en werkwijze gebruikt als bij 2026. Beide jaren liggen op exact hetzelfde pixelraster; het script controleert dat.

| | RGB | Infrarood |
| --- | --- | --- |
| Laag 2025 (uit GetCapabilities) | `2025_orthoHR` (Luchtfoto 2025 Ortho 5 en 8cm RGB) | `2025_orthoHRIR` (Luchtfoto 2025 Ortho 5 en 8cm Infrarood) |
| Bestand | `data/luchtfoto_2025_orthoHR_rgb.tif` | `data/luchtfoto_2025_orthoHRIR_cir.tif` |
| Opgevraagde URL's | `data/luchtfoto_2025_orthoHR_rgb.json` | `data/luchtfoto_2025_orthoHRIR_cir.json` |
| Gedownload | 2026-11-09 | 2026-11-09 |

#### Opnamedatum: zelfde periode volgens de metadata, maar niet hetzelfde seizoen

| Jaar | Opnameperiode in de metadata (Nationaal Georegister) |
| --- | --- |
| 2025 | 2025-01-01 t/m 2025-06-01 (RGB en infrarood) |
| 2026 | 2026-01-01 t/m 2026-06-01 (RGB en infrarood) |

Volgens de metadata zijn beide jaren in dezelfde maanden genomen (januari t/m mei). **Dat is een venster van vijf maanden, en een exacte vliegdatum per plek is niet beschikbaar**: de metadata noemt alleen de periode, en de WMS-lagen zijn niet `queryable`, dus GetFeatureInfo geeft geen datum.

**Waarschuwing:** op de foto's is te zien dat ze niet in hetzelfde seizoen zijn genomen. In 2025 zijn bomen en heesters kaal en zijn de schaduwen lang. In 2026 staat alles vol in blad. Over het hele gebied is de mediane NDVI 0,06 in 2025 en 0,29 in 2026. Een ruw verschil meet daardoor vooral het seizoen: met een vaste drempel zouden meer dan 500 vlakken "toegenomen" zijn.

#### Wat er per vlak berekend wordt

`data/groensignaal_2025_2026.csv` (824 rijen, scheidingsteken `;`) bevat per vlak:
- ExG en NDVI voor 2025 en voor 2026: gemiddelde, mediaan en aandeel groene pixels (zelfde pixeldrempels als hierboven)
- het ruwe verschil (`d_…`)
- de mediane verandering van de eigen soort groen (`…_stijging_klasse`)
- het verwachte aandeel groen in 2026 en de afwijking daarvan (`…_afwijking`)
- `bruikbaar`: genoeg pixels én minstens 80% van het vlak op de foto

#### Hoe de meldingen bepaald worden

Om het seizoen eruit te halen, wordt elk vlak vergeleken met zijn eigen soort groen:

> verwacht aandeel 2026 = aandeel 2025 + mediane verandering van die soort, afgekapt op 0–100%
> afwijking = werkelijk aandeel 2026 − verwacht

Het afkappen zorgt ervoor dat een vlak dat in beide jaren al groen was (bijvoorbeeld wintergroen) niet als "gedaald" telt. Soorten met minder dan 10 bruikbare vlakken (`MIN_KLASSE`) krijgen de mediane verandering van alle vlakken.

| Soort groen | Mediane verandering aandeel groen, ExG / NDVI |
| --- | --- |
| Heesters | +0,62 / +0,56 |
| Gras- en kruidachtigen | +0,40 / +0,37 |
| Bosplantsoen | +0,69 / +0,61 |
| Planten | +0,99 / +0,86 |
| Plus onbekend | +0,00 / +0,53 |
| Overige soorten (minder dan 10 vlakken) | +0,55 / +0,50 (alle vlakken) |

| Type | Ernst | Wanneer |
| --- | --- | --- |
| `groen_afgenomen` (Groen afgenomen (experimenteel, seizoensgevoelig)) | laag | Afwijking ≤ −0,40 bij ExG én NDVI. In de uitleg staat dat de jaren verschillend in blad zijn opgenomen. |
| `groen_toegenomen` (Groen toegenomen) | info | Afwijking ≥ +0,40 bij ExG én NDVI |

**Drempel `VERANDERING_DREMPEL` = 0,40.** De robuuste spreiding (1,4826 × MAD) van de afwijking is 0,33 voor ExG en 0,28 voor NDVI. 0,40 ligt boven één spreiding van beide, en beide indexen moeten dezelfde kant op wijzen. Gevoeligheid op deze werkset:

| Drempel | Afgenomen | Toegenomen |
| --- | --- | --- |
| 0,30 | 52 | 70 |
| 0,40 | 28 | 25 |
| 0,50 | 16 | 11 |
| 0,60 | 8 | 0 |

De uitvoer staat in `dashboard/meldingen_groen_verschil.geojson`, in hetzelfde formaat als de andere meldingen. De ID's beginnen met `V-`: V-0001 t/m V-0028 zijn groen_afgenomen, V-0029 t/m V-0053 groen_toegenomen.

De V-meldingen zitten niet meer in het dashboard. In versie 2 (nu in `oud/`) stond alleen groen_afgenomen erin. Versie 3 gebruikt de verschilmeldingen van 2024–2026 in plaats daarvan (zie "Samenvoegen" hieronder).

#### Resultaat en wat het nakijken liet zien (53 meldingen)

| Soort groen | Vlakken | Groen afgenomen | Groen toegenomen |
| --- | --- | --- | --- |
| Heesters | 391 | 19 | 0 |
| Gras- en kruidachtigen | 284 | 5 | 22 |
| Bosplantsoen | 72 | 3 | 0 |
| Plus onbekend | 42 | 0 | 3 |
| Planten | 18 | 1 | 0 |
| Grasland agrarisch, grasland overig, bodembedekkers | 17 | 0 | 0 |

Bij 8 voorbeelden die met de hand zijn bekeken:
- **Groen afgenomen** is gemengd. V-0004 lijkt een echte verandering: een groene berm in 2025 en een kale strook in 2026. V-0017 is een bloeiende boom (witte kruin) in 2026. V-0001 en V-0009 liggen in 2026 in de schaduw van bomen die dan in blad staan.
- **Groen toegenomen** komt vooral door het seizoen: bladerdak dat in 2026 boven gras hangt (V-0029, V-0038) en lange winterschaduw in 2025 (V-0039, V-0045). Dit type is weinig betrouwbaar zolang de jaren in een ander seizoen zijn opgenomen.

### Samenvoegen met de bestaande meldingen

```
python voeg_samen.py
```

Dit maakt `dashboard/meldingen_alle.geojson` uit `meldingen.geojson` en `meldingen_groen.geojson`: 229 + 86 = 315 meldingen. Het dashboard laadt dit bestand (`DATA_URL` in `index.html`).

- De metadata van `meldingen.geojson` blijft staan, ook `sha256_bronbestand`, zodat geëxporteerde beoordelingen nog te importeren zijn.
- `typen` en `aantal_per_type` zijn van beide bestanden samengevoegd.
- `samengevoegd_uit` noemt per bronbestand de naam, de SHA-256, het aantal features en de drempels.
- Het script stopt bij dubbele ID's, bij een andere werkset of bij een aantal dat niet klopt. Een bestaand uitvoerbestand overschrijft het niet.
- Beoordelingen in de browser blijven bewaard, want ze hangen aan het meldings-ID (`M-…`, `G-…`) en die veranderen niet.

#### Versie 3: met de verschilmeldingen 2024–2026 (dit laadt het dashboard nu)

```
python voeg_samen.py dashboard/meldingen_alle.geojson \
    dashboard/meldingen_groen_verschil_2024_2026.geojson \
    --vervang-typen typen_verschil_algemeen.json --uitvoer dashboard/meldingen_alle_v3.geojson
```

Dit levert 315 + 38 = **353 meldingen** in 14 typen op:
- de 315 uit `meldingen_alle.geojson` (M- en G-meldingen), ongewijzigd
- de 38 X-meldingen van 2024–2026: 13 groen_afgenomen en 25 groen_toegenomen, ongewijzigd

De V-meldingen (2025–2026) en W-meldingen (2022–2023) zitten er niet in.

**Algemene uitleg met `--vervang-typen`.** De uitleg van `groen_afgenomen` en `groen_toegenomen` verschilt per jaarpaar. Normaal stopt `voeg_samen.py` dan. Met `--vervang-typen typen_verschil_algemeen.json` worden label en uitleg van die twee typen bewust vervangen door één algemene tekst, die voor elk jaarpaar geldt:
- **Labels:** "Groen afgenomen" en "Groen toegenomen", zonder "experimenteel, seizoensgevoelig".
- **Uitleg:** "Groen is minder/meer geworden tussen de twee beeldjaren die in de toelichting staan … Let op: kan ook snoeien, schaduw of droogte zijn."
- **Het jaarpaar** staat in de toelichting van elke melding ("Vergelijking 2024-2026. …").

Het script:
- doet dit alleen voor de genoemde typen; voor alle andere typen blijft de controle op tegenstrijdige uitleg staan
- weigert als de ernst in het JSON-bestand afwijkt van die in de bronnen of de meldingen
- meldt per type en per bron welke tekst er stond en wat ervoor in de plaats komt
- bewaart de oorspronkelijke teksten per bron in `metadata.vervangen_typen`

Als een bron zelf al samengevoegd is (zoals `meldingen_alle.geojson`), staat de herkomst daarvan in `samengevoegd_uit[…].bestond_uit`.

**Dashboard:** `DATA_URL` wijst naar `meldingen_alle_v3.geojson`. In `PALET` is een 14e kleur toegevoegd: `#EE6677`, helderrood uit het "bright"-schema van Paul Tol, voor groen_toegenomen. Bij gewoon zicht ligt die kleur minstens 29,9 ΔE van de andere 13 af, en bij protanopie, deuteranopie en tritanopie minstens 10,1. Zwart, donkerrood en donkergroen scoorden hoger, maar vallen op de luchtfoto weg tegen schaduw of tussen het groen.

**Beoordelingen van V-meldingen** (uit v2) blijven in de browser bewaard, maar zijn in v3 niet zichtbaar. Bij exporteren gaan ze mee, zonder type en lokaal_id. Bij importeren in v3 worden ze overgeslagen.

#### Versie 2: met groen_afgenomen 2025–2026 (vorige versie, nu `oud/meldingen_alle_v2.geojson`)

```
python voeg_samen.py dashboard/meldingen.geojson dashboard/meldingen_groen.geojson \
    dashboard/meldingen_groen_verschil.geojson --zonder-type groen_toegenomen \
    --uitvoer dashboard/meldingen_alle_v2.geojson
```

Dit levert 229 + 86 + 28 = **343 meldingen** in 13 typen op. De 315 meldingen uit `meldingen_alle.geojson` zitten er ongewijzigd in. `--zonder-type` laat een type weg, zowel de features als `metadata.typen`. In `samengevoegd_uit` staat per bestand wat er is weggelaten.

In versie 2 wees `DATA_URL` naar dit bestand. In `PALET` is een 13e kleur toegevoegd: `#FFAABB`, lichtroze uit het "light"-schema van Paul Tol, voor groen_afgenomen. Bij een simulatie van protanopie, deuteranopie en tritanopie ligt die kleur minstens 10,9 ΔE van de andere 12 af. Zwart scoorde hoger, maar valt op de luchtfoto weg tegen schaduw en boomkruinen.

### Welke luchtfotojaren zijn bladloos of in blad? (2022–2026)

PDOK heeft voor alle jaren 2022–2026 zowel RGB als infrarood in de WMS. Gebruikte lagen (uit GetCapabilities): RGB `20xx_orthoHR`, infrarood `2025/2026_orthoHRIR` en `2022/2023/2024_ortho25IR`. Voor 2022–2024 bestaat er geen HR-infrarood. Alle rasters staan in `data/` (0,25 m, zelfde grid), met de URL's ernaast.

**Let op: in 2022–2024 zijn RGB en infrarood aparte vluchten.** Volgens de metadata is RGB genomen in januari t/m mei en infrarood in de zomer (15 mei t/m 15 augustus). Alleen in 2025 en 2026 komen ze uit dezelfde periode.

| Jaar | RGB-periode (metadata) | Infrarood-periode (metadata) | Mediaan NDVI gebied / BGT-vlakken | Mediaan ExG gebied / BGT-vlakken | RGB op de foto | Infrarood op de foto |
| --- | --- | --- | --- | --- | --- | --- |
| 2022 | jan t/m mei | 15 mei t/m 15 aug | 0,212 / 0,378 | 0,024 / 0,076 | bladloos | in blad |
| 2023 | jan t/m mei | 15 mei t/m 15 aug | 0,044 / 0,223 | 0,062 / 0,160 | in blad (licht, jong blad) | in blad |
| 2024 | jan t/m mei | 15 mei t/m 15 aug | 0,178 / 0,318 | 0,044 / 0,093 | donkere opname, blad per plek verschillend | in blad |
| 2025 | jan t/m mei | jan t/m mei | 0,061 / 0,291 | 0,014 / 0,065 | bladloos | bladloos |
| 2026 | jan t/m mei | jan t/m mei | 0,292 / 0,443 | 0,060 / 0,140 | in blad | in blad |

**Hoe "RGB op de foto" is bepaald (gecorrigeerd op 2026-11-10).** Eerst was dit met het oog vastgesteld op één bomenrij langs de vaart. Daarbij heette 2023 ten onrechte bladloos en 2024 "in blad". Nu is het gemeten op alle bosplantsoen- en heestervlakken die minstens 95% op de foto staan (63 van 72 bosplantsoen, 377 van 391 heesters). Een montage van zes bosplantsoenvlakken per jaar is met het oog nagekeken.

| Jaar | Bosplantsoen: med. ExG / aandeel groene pixels / vlakken > 50% groen | Heesters: idem | Helderheid (mediaan RGB) |
| --- | --- | --- | --- |
| 2022 | 0,027 / 12% / 11% | 0,024 / 10% / 2% | 101 |
| 2023 | 0,091 / 65% / 79% | 0,088 / 63% / 50% | 85 |
| 2024 | 0,070 / 50% / 35% | 0,063 / 45% / 43% | 57 |
| 2025 | 0,023 / 13% / 6% | 0,021 / 11% / 3% | 105 |
| 2026 | 0,104 / 74% / 81% | 0,097 / 68% / 68% | 87 |

2024 is de donkerste opname. De waarden liggen tussen de bladloze jaren (2022, 2025) en de jaren in blad (2023, 2026) in.

Infrarood "op de foto" is nog steeds bepaald op de bomenrij en het overzichtsbeeld.

**De medianen van het hele gebied zijn hiervoor niet betrouwbaar.** De kleurbalans verschilt per vlucht. 2023 heeft bijvoorbeeld een lagere NDVI dan 2025, terwijl het infrarood van 2023 in blad staat. Een andere maat vergelijkt houtig groen met gras uit dezelfde foto. Bosplantsoen en heesters min gras-vlakken:

| Jaar | NDVI houtig − gras | ExG houtig − gras |
| --- | --- | --- |
| 2022 | +0,006 | −0,032 |
| 2023 | +0,069 | −0,029 |
| 2024 | +0,021 | −0,015 |
| 2025 | −0,062 | −0,024 |
| 2026 | +0,006 | +0,002 |

Bij NDVI is houtig groen alleen in 2025 duidelijk minder groen dan gras: het enige bladloze infraroodjaar. Bij ExG werkt deze maat niet goed voor 2023, omdat daar ook het gras erg groen is. Het verschil (−0,029) lijkt dan op dat van een bladloos jaar, terwijl de bomen in blad staan. Daarom is de RGB-conditie nu bepaald met de tabel per soort hierboven.

**Opeenvolgende jaren met dezelfde conditie (gecorrigeerd):**
- **2023–2024** komt het dichtst bij: infrarood in beide jaren in blad (zomer, zelfde product `ortho25IR`). RGB is in 2023 in blad (licht, jong blad) en in 2024 donkere opname, blad per plek verschillend. Gelijk in RGB is het dus niet.
- **2022–2023** verschilt in RGB: bladloos in 2022, in blad in 2023. Dat verklaart de grote ExG-stijging (+0,42 per vlak) bij dat paar. Eerder stond hier dat dit het enige gelijke paar was; dat klopte niet.
- **2024–2025** en **2025–2026** verschillen in beide.
- **2024 en 2026** liggen twee jaar uit elkaar. 2024 heeft infrarood van 25 cm uit een zomervlucht, 2026 HR-infrarood uit het voorjaar.

De bestaande W-meldingen (2022–2023) zijn gemaakt met de oude conditie. In hun uitleg en `let_op` staat daarom nog "RGB 2022 bladloos, 2023 bladloos". Bij opnieuw draaien komt de gecorrigeerde tekst erin.

### Vergelijking van andere jaarparen (2022–2023 en 2024–2026)

```
python groensignaal.py data/BGT_testgebied_actueel.geojson --vergelijk 2022 2023
python groensignaal.py data/BGT_testgebied_actueel.geojson --vergelijk 2024 2026
```

`--vergelijk` accepteert nu twee jaren. Met één jaar wordt, zoals eerder, met 2026 vergeleken. De werkwijze is gelijk aan 2025–2026:
- verwachting op basis van de mediane verandering per soort groen
- ExG en NDVI moeten dezelfde kant op afwijken
- dezelfde `VERANDERING_DREMPEL` = 0,40, zodat de aantallen vergelijkbaar zijn

| Jaarpaar | ID-prefix | Meldingen | CSV |
| --- | --- | --- | --- |
| 2025–2026 | `V-` | `dashboard/meldingen_groen_verschil.geojson` (oorspronkelijke naam) | `data/groensignaal_2025_2026.csv` |
| 2022–2023 | `W-` | `dashboard/meldingen_groen_verschil_2022_2023.geojson` | `data/groensignaal_2022_2023.csv` |
| 2024–2026 | `X-` | `dashboard/meldingen_groen_verschil_2024_2026.geojson` | `data/groensignaal_2024_2026.csv` |
| 2023–2024 | `Y-` | `dashboard/meldingen_groen_verschil_2023_2024.geojson` | `data/groensignaal_2023_2024.csv` |

- **Typen:** voor alle paren `groen_afgenomen` en `groen_toegenomen`. Het jaarpaar staat in de toelichting ("Vergelijking 2022-2023. …"), en de conditie per jaar staat in de uitleg en in `let_op`.
- **Labels:** alleen bij 2025–2026 heet `groen_afgenomen` "Groen afgenomen (experimenteel, seizoensgevoelig)"; bij 2022–2023 en 2024–2026 is het "Groen afgenomen". `groen_toegenomen` heet bij alle paren "Groen toegenomen". De bestaande W- en X-bestanden zijn gemaakt vóór deze wijziging en hebben nog het oude label; opnieuw draaien geeft het nieuwe.
- **Extra metadata:** de mediane NDVI en ExG van het hele gebied per jaar, en de mediane verandering.
- **2025–2026 ongewijzigd:** voor dat paar blijven label, uitleg en toelichting zoals ze in het dashboard staan. Opnieuw draaien geeft byte voor byte dezelfde meldingen en CSV (getest).
- **Registratiejaar:** vlakken met een registratiejaar (uit `tijdstip_registratie`) later dan het eerste vergeleken jaar krijgen in de toelichting "LET OP: registratiejaar … is later dan …; het object bestond toen mogelijk nog niet (of had een andere vorm)". Dat zijn er 1 (W) en 8 (X). `tijdstip_registratie` is de datum van de huidige *versie*, niet van het ontstaan. Van de 92 vlakken met een registratiejaar na 2024 hebben er maar 15 ook een `creation_date` na 2024. De markering vangt dus ook gewijzigde objecten, niet alleen nieuwe.

#### 25 cm-infrarood (2024) tegenover HR-infrarood (2026)

Voor 2024 bestaat alleen `2024_ortho25IR` (25 cm), voor 2026 `2026_orthoHRIR` (5–8 cm). Beide zijn bij de WMS opgevraagd op **hetzelfde raster van 0,25 m** (zelfde bbox, zelfde pixelhoeken, EPSG:28992). 2024 komt dus vrijwel op de eigen resolutie binnen. 2026 is door de PDOK-server verkleind; welke methode die gebruikt, staat niet in de capabilities.

Wat dat betekent voor de NDVI-vergelijking:
- **Pixelgrootte en ligging zijn gelijk.** Dezelfde pixels binnen een vlak worden geteld.
- **2026 is scherper.** Het fijne detail in NDVI (mediaan van |NDVI − 3×3-gemiddelde| binnen de vlakken) is 0,0075 in 2026 tegenover 0,0035 in 2024. Dat komt deels door het product en deels doordat 2026 vol in blad staat. Een scherper beeld heeft meer pixels aan beide kanten van de NDVI-drempel, vooral langs randen en in smalle vlakken.
- **Gevoeligheidstest:** met 2026-infrarood gladgemaakt met een 3×3-gemiddelde (vergelijkbaar met 2024) blijven 37 van de 38 meldingen gelijk, komt er 0 bij en verdwijnt er 1. Het resolutieverschil verklaart de meldingen dus niet.
- **Het productverschil is niet los te meten.** Het enige jaar met beide producten (2025) heeft het 25 cm-infrarood uit een aparte zomervlucht (15 mei t/m 15 aug), dus dan verschilt ook het seizoen.
- **Andere vlucht en kleurbalans.** Het 25 cm-infrarood van 2024 is een zomervlucht, dat van 2026 een voorjaarsvlucht. Wat hiervan per soort overblijft, vangt de correctie met de mediane verandering per soort op. Lokale verschillen, zoals droogte in de zomer, niet.

#### Is de seizoensruis weg?

Mediane verandering over het hele gebied (alle pixels) en per vlak (aandeel groene pixels, bruikbare vlakken).

Dit zijn twee verschillende grootheden:
- **ΔExG/ΔNDVI gebied** is de verandering van de *indexwaarde*: de mediaan over alle pixels van het testgebied in het tweede jaar min die in het eerste jaar (functie `gebied_medianen`, in de metadata als `mediane_verandering_gebied`).
- **Δaandeel vlakken** is de mediane verandering van het *aandeel groene pixels* per vlak (pixels boven de ExG- of NDVI-drempel, als fractie van 0 tot 1), over de 764 bruikbare vlakken (kolommen `d_exg_aandeel` en `d_ndvi_aandeel` in de CSV, `bruikbaar` = True). −0,16 betekent dus 16 procentpunt minder groene pixels, niet een ExG die 0,16 lager is.

Alle paren zijn op dezelfde manier berekend. Voor 2025–2026 staat de gebiedsmediaan niet in de metadata, omdat dat bestand ongewijzigd is gebleven; nagerekend met dezelfde functie levert hij dezelfde waarden op.

| Jaarpaar | Conditie op de foto (RGB / infrarood) | ΔExG gebied | ΔNDVI gebied | Δaandeel ExG vlakken | Δaandeel NDVI vlakken | Robuuste spreiding afwijking ExG / NDVI |
| --- | --- | --- | --- | --- | --- | --- |
| 2025–2026 | bladloos→in blad / bladloos→in blad | +0,046 | +0,231 | +0,55 | +0,50 | 0,33 / 0,28 |
| 2022–2023 | bladloos→in blad / in blad→in blad | +0,038 | −0,168 | +0,42 | −0,10 | 0,32 / 0,21 |
| 2024–2026 | donkere opname, blad per plek verschillend→in blad / in blad→in blad | +0,016 | +0,114 | +0,16 | +0,08 | 0,26 / 0,25 |
| 2023–2024 | in blad (licht, jong blad)→donkere opname, blad per plek verschillend / in blad→in blad | −0,018 | +0,134 | −0,16 | +0,03 | 0,34 / 0,13 |

- **2022–2023 is niet gelijk in conditie** (gecorrigeerd). In RGB gaat het van bladloos naar in blad, en daardoor stijgt de ExG bijna net zoveel als bij 2025–2026. De NDVI daalt flink: het infrarood van 2023 is blauwer en grijzer van kleur. De correctie per soort vangt de algemene verschuiving op, en er blijven **5 meldingen "toegenomen"** over (tegen 25 bij 2025–2026).
- **2024–2026 komt het dichtst bij gelijk:** de kleinste verschuiving en de kleinste spreiding. Toch blijven er **25 meldingen "toegenomen"** over, evenveel als bij 2025–2026. Bij nakijken zijn dat hier vooral echte veranderingen (nieuwe aanplant) en zomerdroogte in 2024, geen bladgroei.

#### Resultaat per soort groen

| Soort groen | Vlakken | 2022–2023 afgenomen | 2022–2023 toegenomen | 2024–2026 afgenomen | 2024–2026 toegenomen |
| --- | --- | --- | --- | --- | --- |
| Heesters | 391 | 5 | 3 | 7 | 16 |
| Gras- en kruidachtigen | 284 | 0 | 0 | 3 | 1 |
| Bosplantsoen | 72 | 1 | 0 | 1 | 1 |
| Plus onbekend | 42 | 0 | 0 | 2 | 5 |
| Planten | 18 | 0 | 1 | 0 | 0 |
| Grasland agrarisch | 15 | 0 | 1 | 0 | 0 |
| Grasland overig | 1 | 0 | 0 | 0 | 1 |
| Bodembedekkers | 1 | 0 | 0 | 0 | 1 |
| **Totaal** | 824 | **6** | **5** | **13** | **25** |

#### Gevoeligheid (afgenomen / toegenomen)

| Drempel | 2025–2026 | 2022–2023 | 2024–2026 |
| --- | --- | --- | --- |
| 0,30 | 52 / 70 | 18 / 10 | 23 / 42 |
| 0,40 | 28 / 25 | 6 / 5 | 13 / 25 |
| 0,50 | 16 / 11 | 0 / 2 | 8 / 18 |
| 0,60 | 8 / 0 | 0 / 1 | 5 / 6 |

#### Nagekeken voorbeelden (op de foto, telkens RGB en infrarood van beide jaren)

2022–2023:

| ID | Type | Soort | Wat te zien is |
| --- | --- | --- | --- |
| W-0005 | afgenomen | heesters | In 2023 minder rood in het infrarood dan in 2022. Mogelijk gesnoeid, maar het infrarood van 2023 is in het hele gebied donkerder. Twijfelgeval. |
| W-0001 | afgenomen | heesters | In 2023 bleker in het infrarood, mogelijk teruggesnoeid. Twijfelgeval. |
| W-0002 | afgenomen | heesters | Registratiejaar 2023: het object is in 2023 opnieuw vastgelegd. Ligt onder bomen, het infrarood wordt minder rood. |
| W-0006 | afgenomen | bosplantsoen | In 2022 deels rood in het infrarood, in 2023 grijs. Waarschijnlijk echt verwijderd of verhard. |
| W-0011 | toegenomen | grasland agrarisch | Akker: in 2022 kaal of net bewerkt, in 2023 vol gewas. Echte verandering, maar een landbouwcyclus en geen BGT-fout. |
| W-0009 | toegenomen | heesters | In 2022 grijs in het infrarood, in 2023 een rode kruin. Waarschijnlijk aangeplant of uitgegroeid. |
| W-0008 | toegenomen | planten | In 2022 bleek in het infrarood, in 2023 rood. Oorzaak onduidelijk (bloei of schaduw?). |
| W-0010 | toegenomen | heesters | Klein vlak (6,9 m²), in 2023 roder. Randeffect mogelijk. |

2024–2026:

| ID | Type | Soort | Wat te zien is |
| --- | --- | --- | --- |
| X-0001 | afgenomen | plus onbekend | Doolhofhaag: in 2024 dicht, in 2026 flink teruggesnoeid, de paden zijn zichtbaar. Echte verandering. |
| X-0008 | afgenomen | heesters | Registratiejaar 2025. Het terrein is heringericht (verharding, parkeren). Echte verandering, de BGT is al bijgewerkt. |
| X-0002 | afgenomen | heesters | In 2026 open plekken in het groen. Mogelijk gekapt of gesnoeid. |
| X-0012 | afgenomen | gras- en kruidachtigen | In 2024 groen, in 2026 een speelplek met toestellen. **Gecorrigeerd na de vergelijking 2023–2024:** de speelplek was er in 2023 al (Y-0024). In 2024 lag hij onder dicht bladerdak. Dit is dus bladerdak, geen nieuwe speelplek. |
| X-0038 | toegenomen | grasland overig | In 2024 grijs in het infrarood (zomervlucht, waarschijnlijk droogte), in 2026 groen. Seizoen of weer, geen verandering in het terrein. |
| X-0014 | toegenomen | heesters | Registratiejaar 2025. In 2024 kaal, in 2026 een groene strook langs het sportveld. Nieuw aangeplant. |
| X-0020 | toegenomen | heesters | In 2024 in de schaduw en grijs, in 2026 groen. Deels schaduw, mogelijk ook groei. |
| X-0016 | toegenomen | heesters | In 2024 kale grond, in 2026 groene heesters. Nieuw aangeplant of hersteld. |

### Vergelijking 2023–2024 (prefix `Y-`)

```
python groensignaal.py data/BGT_testgebied_actueel.geojson --vergelijk 2023 2024
```

De uitvoer staat in `dashboard/meldingen_groen_verschil_2023_2024.geojson` (28 meldingen) en `data/groensignaal_2023_2024.csv`. Het bestand zit **niet** in het dashboard. De aanpak en drempel (0,40) zijn dezelfde als bij de andere paren.

Conditie op de foto:
- **RGB:** 2023 in blad (licht, jong blad), 2024 donkere opname, blad per plek verschillend.
- **Infrarood:** in beide jaren in blad. Het is in beide jaren een zomervlucht met hetzelfde product (`ortho25IR`).

| Maat | 2023 → 2024 |
| --- | --- |
| Mediaan ExG / NDVI hele gebied | 0,062 → 0,044 (−0,018) / 0,044 → 0,178 (+0,134) |
| Mediane Δaandeel groen per vlak, ExG / NDVI | −0,164 / +0,027 |
| Robuuste spreiding afwijking, ExG / NDVI | 0,343 / 0,127 |
| Meldingen met registratiejaar na 2023 | 6 |

| Soort groen | Vlakken | Afgenomen | Toegenomen |
| --- | --- | --- | --- |
| Heesters | 391 | 2 | 17 |
| Gras- en kruidachtigen | 284 | 0 | 3 |
| Bosplantsoen | 72 | 1 | 1 |
| Plus onbekend | 42 | 1 | 2 |
| Grasland overig | 1 | 1 | 0 |
| Overige soorten | 34 | 0 | 0 |
| **Totaal** | 824 | **5** | **23** |

Gevoeligheid (afgenomen / toegenomen): 0,30 → 10 / 32, **0,40 → 5 / 23**, 0,50 → 2 / 16, 0,60 → 1 / 13.

#### Vertekent de donkere 2024-opname de ExG?

De houtige vlakken zijn in 2024 veel donkerder dan in 2023: een mediane helderheid van 60 tegen 85. Over het hele gebied is het verschil klein (76 tegen 81). De mediane ExG is in 2024 lager: bosplantsoen 0,091 → 0,070, heesters 0,088 → 0,063.

- ExG wordt berekend op kleurverhoudingen. **Lineair ophelderen verandert niets** (gecontroleerd: 0,070 → 0,071).
- **Binnen 2024 hangt ExG wel af van de helderheid.** De donkerste houtige pixels (helderheid 19–44) hebben een mediane ExG van 0,009, de lichtere (66–252) 0,087–0,088. In 2023 is dat niet zo. Donkere pixels drukken de ExG van 2024 dus omlaag.

Hoeveel meldingen blijven over als de 2024-RGB wordt gecorrigeerd (infrarood ongewijzigd; de gecorrigeerde rasters staan alleen in de scratchpad):

| Correctie van 2024 | Δaandeel ExG per vlak | Afgenomen (blijft van 5) | Toegenomen (blijft van 23) | Nieuw |
| --- | --- | --- | --- | --- |
| Geen | −0,164 | 5 | 23 | – |
| Lineair ophelderen (controle) | −0,163 | 5 (5) | 23 (23) | 0 |
| Gamma, helderheid hele foto gelijk aan 2023 (γ = 0,95) | −0,184 | 5 (5) | 23 (23) | 0 |
| Gamma, helderheid houtige vlakken gelijk aan 2023 (γ = 0,76) | −0,339 | 4 (4) | 17 (17) | 0 |
| Donkere pixels (helderheid < 45 in een van beide jaren) uitsluiten | −0,103 | 4 (4) | 23 (22) | 1 |
| Histogram-matching per kanaal naar 2023 (helderheid én kleurbalans) | +0,132 | 3 (2) | 19 (17) | 3 |

**Conclusie:** de donkere opname verlaagt de ExG van 2024, maar verklaart de meldingen nauwelijks. Bij elke helderheidscorrectie blijven 17 tot 23 van de 23 "toegenomen" en 4 tot 5 van de 5 "afgenomen" staan. Ophelderen met gamma verlaagt de ExG zelfs verder. De correctie per soort vangt de algemene verschuiving al op; wat overblijft zijn verschillen per vlak.

#### Nagekeken voorbeelden 2023–2024

| ID | Type | Soort | Wat te zien is |
| --- | --- | --- | --- |
| Y-0005 | afgenomen | grasland overig | In 2023 groen gras. In 2024 is de strook in RGB (voorjaar) en infrarood (zomer) bruin en kaal. Waarschijnlijk tijdelijk kaal of werkzaamheden. In 2026 is het weer groen; dat is X-0038, eerder als "droogte" uitgelegd. |
| Y-0002 | afgenomen | heesters | In 2023 heesters in blad, in 2024 kale grond in RGB en infrarood. Waarschijnlijk verwijderd. |
| Y-0001 | afgenomen | bosplantsoen | Klein vlak (19 m²). In 2023 een lichtgroene kruin, in 2024 donker en in de schaduw. In infrarood 2024 deels nog rood. Waarschijnlijk de donkere opname, geen verandering. |
| Y-0004 | afgenomen | heesters | Klein vlak (11 m²), registratiejaar 2025. In 2024 staat er een bouwwerk of schuur in. Mogelijk een echte verandering, die de BGT al heeft bijgewerkt. |
| Y-0021 | toegenomen | gras- en kruidachtigen | Gras onder bomen. In 2023 zijn de kruinen nog bruin (laat uitlopend), in 2024 dicht en groen. Bladerdak, geen verandering in het vlak. |
| Y-0008 | toegenomen | bosplantsoen | Registratiejaar 2025. In 2023 deels kale grond, in 2024 donkergroen. Groei of aanplant, deels het moment van uitlopen. |
| Y-0024 | toegenomen | gras- en kruidachtigen | In 2023 is de speelplek met toestellen zichtbaar, in 2024 ligt hij onder dicht bladerdak. Bladerdak. Hetzelfde vlak als X-0012. |
| Y-0018 | toegenomen | heesters | In 2023 nog bruin of kaal, in 2024 donkergroen. Het moment van uitlopen. Hetzelfde vlak als W-0005. |

**Heen en weer tussen jaarparen.** Tien vlakken met een Y-melding hebben in een ander paar een melding in de tegenovergestelde richting:
- W "afgenomen" en daarna Y "toegenomen": W-0001/Y-0006, W-0002/Y-0007, W-0004/Y-0013, W-0005/Y-0018.
- Y "afgenomen" en daarna X "toegenomen": Y-0001/X-0018, Y-0003/X-0027, Y-0005/X-0038.
- Y "toegenomen" en daarna X "afgenomen": Y-0013/X-0005, Y-0014/X-0006, Y-0024/X-0012.

Zo'n dip of piek in één jaar wijst eerder op een eigenschap van die opname (bladstand, schaduw, kleur) of op iets tijdelijks dan op een blijvende verandering. Kijk bij het beoordelen daarom ook naar de buurjaren.

Bij X-0016 en X-0001 (zie de montage 2022–2026 in de scratchpad van deze sessie):
- **X-0016:** in 2023 heesters, in 2024 kale grond, in 2026 weer dicht groen. Waarschijnlijk verwijderd en opnieuw aangeplant.
- **X-0001** (doolhof): in 2022, 2023, 2025 en 2026 gesnoeid met zichtbare paden. Alleen in 2024 is hij dichtgegroeid. De melding "afgenomen" 2024–2026 komt dus door snoei na een uitschieter in 2024.

Dit paar staat niet in de Y-meldingen.

#### Nog niet gedaan of bekend probleem

- De X-meldingen (2024–2026) staan sinds versie 3 in het dashboard; W (2022–2023) en V (2025–2026) niet.
- Verschilmeldingen van verschillende jaarparen samenvoegen kan met `voeg_samen.py --vervang-typen typen_verschil_algemeen.json` (zie "Versie 3"). Zonder die optie stopt het script, omdat de uitleg per jaarpaar verschilt.
- De conditie per jaar (`CONDITIE` in het script) is met het oog vastgesteld en wordt alleen in teksten gebruikt, niet in de berekening.

## Beperkingen

- De achtergrondtegels van PDOK zijn niet getest vanuit de omgeving waarin dit is gebouwd (PDOK was daar niet bereikbaar). Blijft de kaart grijs, vergelijk dan de tegel-URL's bovenin het script van `index.html` (`PDOK_LUCHT`, `PDOK_INFRAROOD`, `PDOK_BGT`) met de WMTS-URL die in QGIS werkt. Het dashboard meldt het zelf als de achtergrond niet laadt.
- Het is een prototype voor Data Preparation en Modeling. Zet er geen modelresultaten van in Data Understanding-documenten.
- Geen gebruikersbeheer of gedeelde opslag: iedereen beoordeelt in een eigen browser en deelt via export.
- Open ruimten zijn geen bewezen BGT-gaten, want andere vlaktypen (wegen, water, gebouwen) ontbreken in de werkset.
