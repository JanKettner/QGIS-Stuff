# Offline Map Style für QGIS 3.34+

Das Plugin importiert beliebige Geofabrik-Dateien (`.osm.pbf`) und erzeugt daraus eine vollständig offline nutzbare QGIS-Karte im hellen Straßenkartenstil. Es verwendet keine Google-Daten und keine Online-Kacheln.

## Installation

1. In QGIS **Erweiterungen → Erweiterungen verwalten und installieren** öffnen.
2. **Aus ZIP installieren** auswählen.
3. `Offline_Map_Style_QGIS.zip` auswählen und die Sicherheitsabfrage bestätigen.
4. Das Werkzeug **Geofabrik als Offline-Karte öffnen** in der Symbolleiste starten.

## Verwendung

1. Eine regionale `.osm.pbf` von Geofabrik herunterladen.
2. PBF-Datei und Ausgabeordner auswählen.
3. Kartenname festlegen und **Offline-Karte erstellen** drücken.
4. Nach dem Hintergrundimport werden das GeoPackage und ein QGIS-Projekt im Ausgabeordner gespeichert.

Standardebenen: Landnutzung, Gewässer, Gebäude, Küstenlinien, Verwaltungsgrenzen, Wasserläufe, Bahnlinien, Straßen/Wege und beschriftete Orte. Gebäude können im Dialog abgewählt werden und erscheinen standardmäßig erst beim Hineinzoomen.

Version 1.0.1 ergänzt die zuvor fehlende Küstenlinie und ordnet die Ebenen korrekt übereinander an.

Version 1.0.2 stellt Städte bereits in der Übersicht dar und blendet Dörfer sowie Ortsteile beim Hineinzoomen ein. Ortsnamen erhalten einen weißen Lesbarkeitspuffer.

Version 1.0.3 korrigiert die Beschriftungsposition für aktuelle QGIS-3.x-Versionen.

Version 1.0.4 korrigiert die QGIS-Maßstabslogik. Gebäude und Ortsnamen werden nun beim Hineinzoomen statt beim Herauszoomen eingeblendet.

Version 1.0.5 erweitert die Straßen- und Wegeklassen und enthält eine Auffangregel für sämtliche übrigen OSM-Highway-Typen.

Version 1.0.6 korrigiert die GDAL-Konfiguration für geschlossene OSM-Wege. Gewöhnliche Gebäude werden dadurch korrekt als Polygone in die Ebene `multipolygons` importiert. Zusätzlich werden Zugangs-, Fuß- und Fahrradeigenschaften sowie Wander-, Fuß-, Fahrrad- und MTB-Routen übernommen.

Version 1.0.7 beschriftet Autobahnen, Haupt-, Land- und Regionalstraßen entlang ihres Verlaufs mit OSM-Straßennamen und Straßenreferenz.

Version 1.0.8 erkennt die GDAL-Version automatisch. Für GDAL 3.10 und neuer wird die erforderliche `[general]`-Sektion erzeugt; ältere Versionen erhalten weiterhin das Legacy-Format. Dies behebt den Gebäudeimport insbesondere mit GDAL 3.13.1.

Version 1.0.9 verwendet für befahrbare Straßen zweilagige Symbole mit kontrastreicher Außenkante und heller Fahrbahn. Wege erhalten kräftigere Farben und unterscheidbare Strichmuster.

## Hinweise

- Die Umwandlung großer Dateien kann mehrere Minuten dauern und benötigt freien Festplattenspeicher.
- Das Plugin sucht `ogr2ogr` automatisch in der QGIS-/OSGeo4W-Installation.
- Die Darstellung ist eigenständig und lediglich an moderne helle Straßenkarten angelehnt.
