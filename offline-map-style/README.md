# Offline Map Style für QGIS

Dieses Unterverzeichnis enthält das QGIS-Plugin **Offline Map Style** sowie eine universelle UTM-Drucklayoutvorlage.

## Funktionen

- Import beliebiger Geofabrik-Dateien im Format `.osm.pbf`
- vollständig offline nutzbares GeoPackage und QGIS-Projekt
- heller Straßenkartenstil mit kontrastreichen Straßenkonturen
- Gebäude, Straßen, Wege, Bahnlinien, Gewässer, Küstenlinien und Verwaltungsgrenzen
- Orts- und Straßennamen mit maßstabsabhängiger Darstellung
- kompatibel mit GDAL 3.13.1 und älteren GDAL-Versionen
- universelle A3-Querformat-UTM-Ausgabe mit 1-km-Gitter und Nordpfeil

## Verzeichnisstruktur

```text
offline-map-style/
├── plugin/offline_map_style/      QGIS-Plugin-Quellcode
├── dist/                          Installierbare ZIP-Datei
├── layouts/                       QGIS-Layoutvorlage (.qpt)
└── docs/                          Anleitungen
```

## Plugin installieren

1. Die aktuelle ZIP-Datei aus `dist/` herunterladen.
2. In QGIS **Erweiterungen → Erweiterungen verwalten und installieren** öffnen.
3. **Aus ZIP installieren** auswählen.
4. Das Werkzeug **Geofabrik als Offline-Karte öffnen** starten.

## Layoutvorlage verwenden

Das QGIS-Projekt zuerst auf eine passende UTM-Zone mit Metern als Einheit einstellen. Anschließend die `.qpt`-Datei aus `layouts/` über die Layoutverwaltung als spezifische Vorlage laden.

Für Sciacca/Sizilien eignet sich beispielsweise `EPSG:32633`.

## Datenquellen

Die Kartendaten stammen aus OpenStreetMap-Extrakten von [Geofabrik](https://download.geofabrik.de/). Das Plugin verwendet keine Google-Kartendaten und keine Online-Kacheln.
