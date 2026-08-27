import os
import shutil
import subprocess
import tempfile

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QAction, QApplication, QCheckBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QVBoxLayout
)
from qgis.core import (
    QgsApplication, QgsFillSymbol, QgsLineSymbol, QgsMarkerSymbol,
    Qgis, QgsProject, QgsRuleBasedRenderer, QgsSimpleLineSymbolLayer,
    QgsSingleSymbolRenderer, QgsTask,
    QgsVectorLayer
)


class ImportTask(QgsTask):
    def __init__(self, pbf, gpkg, osmconf, ogr2ogr):
        super().__init__("OSM-PBF in Offline-Karte umwandeln", QgsTask.CanCancel)
        self.pbf, self.gpkg, self.osmconf, self.ogr2ogr = pbf, gpkg, osmconf, ogr2ogr
        self.error_text = ""

    def run(self):
        cmd = [
            self.ogr2ogr, "-f", "GPKG", self.gpkg, self.pbf,
            "-oo", "CONFIG_FILE=" + self.osmconf,
            "-dsco", "SPATIAL_INDEX=YES", "-nlt", "PROMOTE_TO_MULTI",
            "--config", "OGR_INTERLEAVED_READING", "YES"
        ]
        try:
            creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    creationflags=creation_flags)
            if result.returncode:
                self.error_text = (result.stderr or result.stdout or "Unbekannter GDAL-Fehler")[-4000:]
                return False
            return os.path.exists(self.gpkg)
        except Exception as exc:
            self.error_text = str(exc)
            return False
        finally:
            try:
                os.remove(self.osmconf)
            except OSError:
                pass


class ImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Offline Map Style – Geofabrik importieren")
        self.setMinimumWidth(620)
        root = QVBoxLayout(self)
        intro = QLabel("Geofabrik-OSM-Datei lokal in eine gestaltete Offline-Karte umwandeln.")
        intro.setWordWrap(True)
        root.addWidget(intro)
        form = QFormLayout()
        self.pbf = QLineEdit()
        self.out = QLineEdit()
        self.name = QLineEdit("Offline_Karte")
        self.buildings = QCheckBox("Gebäude bei großen Maßstäben anzeigen")
        self.buildings.setChecked(True)
        form.addRow("OSM-PBF:", self._picker(self.pbf, self.pick_pbf))
        form.addRow("Ausgabeordner:", self._picker(self.out, self.pick_out))
        form.addRow("Kartenname:", self.name)
        form.addRow("Kartendetails:", self.buildings)
        root.addLayout(form)
        note = QLabel("Gebäude werden erst beim Hineinzoomen eingeblendet. Große Länderdateien benötigen ausreichend freien Speicher.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#666")
        root.addWidget(note)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Abbrechen")
        cancel.clicked.connect(self.reject)
        start = QPushButton("Offline-Karte erstellen")
        start.setDefault(True)
        start.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(start)
        root.addLayout(buttons)

    def _picker(self, edit, callback):
        box = QHBoxLayout()
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(edit)
        button = QPushButton("…")
        button.setFixedWidth(40)
        button.clicked.connect(callback)
        box.addWidget(button)
        from qgis.PyQt.QtWidgets import QWidget
        widget = QWidget()
        widget.setLayout(box)
        return widget

    def pick_pbf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Geofabrik-Datei wählen", "", "OSM PBF (*.osm.pbf *.pbf)")
        if path:
            self.pbf.setText(path)
            if not self.out.text():
                self.out.setText(os.path.dirname(path))

    def pick_out(self):
        path = QFileDialog.getExistingDirectory(self, "Ausgabeordner wählen")
        if path:
            self.out.setText(path)


class OfflineMapStylePlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.task = None
        self.target_gpkg = None
        self.include_buildings = True

    def initGui(self):
        icon = os.path.join(os.path.dirname(__file__), "icon.svg")
        from qgis.PyQt.QtGui import QIcon
        self.action = QAction(QIcon(icon), "Geofabrik als Offline-Karte öffnen", self.iface.mainWindow())
        self.action.triggered.connect(self.open_dialog)
        self.iface.addPluginToMenu("&Offline Map Style", self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        self.iface.removePluginMenu("&Offline Map Style", self.action)
        self.iface.removeToolBarIcon(self.action)

    def _find_ogr2ogr(self):
        candidates = [
            os.path.join(QgsApplication.prefixPath(), "bin", "ogr2ogr.exe"),
            os.path.join(QgsApplication.prefixPath(), "ogr2ogr.exe"),
            shutil.which("ogr2ogr.exe"), shutil.which("ogr2ogr")
        ]
        return next((p for p in candidates if p and os.path.exists(p)), None)

    def _runtime_osmconf(self):
        from osgeo import gdal
        template_path = os.path.join(os.path.dirname(__file__), "osmconf.ini")
        with open(template_path, "r", encoding="utf-8") as source:
            config = source.read()
        version_number = int(gdal.VersionInfo("VERSION_NUM"))
        general_section = "[general]" if version_number >= 3100000 else ""
        config = config.replace("__GENERAL_SECTION__", general_section)
        handle = tempfile.NamedTemporaryFile(mode="w", suffix=".ini", prefix="offline_map_style_", delete=False, encoding="utf-8")
        try:
            handle.write(config)
            return handle.name
        finally:
            handle.close()

    def open_dialog(self):
        dialog = ImportDialog(self.iface.mainWindow())
        if dialog.exec_() != QDialog.Accepted:
            return
        pbf = dialog.pbf.text().strip()
        out = dialog.out.text().strip()
        name = "".join(c if c.isalnum() or c in "-_" else "_" for c in dialog.name.text().strip())
        if not os.path.isfile(pbf) or not out or not name:
            QMessageBox.warning(dialog, "Eingaben prüfen", "Bitte PBF-Datei, Ausgabeordner und Kartenname vollständig angeben.")
            return
        ogr2ogr = self._find_ogr2ogr()
        if not ogr2ogr:
            QMessageBox.critical(dialog, "GDAL fehlt", "ogr2ogr wurde in der QGIS-/OSGeo4W-Installation nicht gefunden.")
            return
        os.makedirs(out, exist_ok=True)
        self.target_gpkg = os.path.join(out, name + ".gpkg")
        self.include_buildings = dialog.buildings.isChecked()
        if os.path.exists(self.target_gpkg):
            if QMessageBox.question(dialog, "Datei ersetzen?", "Das GeoPackage existiert bereits. Soll es ersetzt werden?") != QMessageBox.Yes:
                return
            os.remove(self.target_gpkg)
        osmconf = self._runtime_osmconf()
        self.task = ImportTask(pbf, self.target_gpkg, osmconf, ogr2ogr)
        self.task.taskCompleted.connect(self._import_done)
        self.task.taskTerminated.connect(self._import_failed)
        QgsApplication.taskManager().addTask(self.task)
        self.iface.messageBar().pushInfo("Offline Map Style", "Import läuft im Hintergrund …")

    def _import_failed(self):
        detail = self.task.error_text if self.task else "Import abgebrochen."
        QMessageBox.critical(self.iface.mainWindow(), "Import fehlgeschlagen", detail)

    def _layer(self, table, title, subset=""):
        layer = QgsVectorLayer(self.target_gpkg + "|layername=" + table, title, "ogr")
        if layer.isValid() and subset:
            layer.setSubsetString(subset)
        return layer

    @staticmethod
    def _single_fill(layer, color, outline="transparent"):
        symbol = QgsFillSymbol.createSimple({"color": color, "outline_color": outline})
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))

    @staticmethod
    def _single_line(layer, color, width, style="solid"):
        symbol = QgsLineSymbol.createSimple({"line_color": color, "line_width": str(width), "line_style": style})
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))

    def _road_renderer(self, layer):
        root = QgsRuleBasedRenderer.Rule(None)
        rules = [
            ("Autobahn", "\"highway\" IN ('motorway','motorway_link')", "#ef9a82", "#c87562", 1.25, 5000000, "solid", True),
            ("Hauptstraße", "\"highway\" IN ('trunk','trunk_link','primary','primary_link')", "#f4c56d", "#c99f4d", 1.05, 3000000, "solid", True),
            ("Regionalstraße", "\"highway\" IN ('secondary','secondary_link')", "#f8dfa0", "#c9b476", .85, 1500000, "solid", True),
            ("Kreis-/Sammelstraße", "\"highway\" IN ('tertiary','tertiary_link')", "#fff2bd", "#b8aa7c", .7, 750000, "solid", True),
            ("Ortsstraße", "\"highway\" IN ('residential','unclassified','living_street','road')", "#f7f9fb", "#aeb8c2", .55, 300000, "solid", True),
            ("Zufahrt und Fußgängerbereich", "\"highway\" IN ('service','pedestrian','busway','escape','raceway')", "#e8edf1", "#aab4bd", .4, 150000, "solid", True),
            ("Feld- und Waldweg", "\"highway\" IN ('track','path','bridleway')", "#aa8754", "#aa8754", .32, 100000, "dash", False),
            ("Fuß- und Radweg", "\"highway\" IN ('footway','cycleway','steps','corridor')", "#8e9d83", "#8e9d83", .28, 75000, "dot", False),
            ("Baustelle/geplante Straße", "\"highway\" IN ('construction','proposed')", "#a7adb2", "#a7adb2", .32, 100000, "dash", False),
        ]
        expressions = []
        for label, expression, color, casing, width, min_scale, line_style, cased in rules:
            expressions.append("(" + expression + ")")
            if cased:
                symbol = QgsLineSymbol.createSimple({"line_color": casing, "line_width": str(width + .34), "line_style": "solid", "capstyle": "round", "joinstyle": "round"})
                inner = QgsSimpleLineSymbolLayer.create({"line_color": color, "line_width": str(width), "line_style": line_style, "capstyle": "round", "joinstyle": "round"})
                symbol.appendSymbolLayer(inner)
            else:
                symbol = QgsLineSymbol.createSimple({"line_color": color, "line_width": str(width), "line_style": line_style, "capstyle": "round", "joinstyle": "round"})
            rule = QgsRuleBasedRenderer.Rule(symbol)
            rule.setFilterExpression(expression)
            rule.setLabel(label)
            rule.setMinimumScale(min_scale)
            rule.setMaximumScale(0)
            root.appendChild(rule)
        fallback_symbol = QgsLineSymbol.createSimple({"line_color": "#9ea8b0", "line_width": ".38", "line_style": "solid", "capstyle": "round"})
        fallback = QgsRuleBasedRenderer.Rule(fallback_symbol)
        fallback.setFilterExpression("NOT (" + " OR ".join(expressions) + ")")
        fallback.setLabel("Sonstige Straße oder Weg")
        fallback.setMinimumScale(100000)
        fallback.setMaximumScale(0)
        root.appendChild(fallback)
        layer.setRenderer(QgsRuleBasedRenderer(root))

    def _label_places(self, layer, font_size=9, max_scale=0, marker_size=.8):
        from qgis.core import QgsPalLayerSettings, QgsTextBufferSettings, QgsTextFormat, QgsVectorLayerSimpleLabeling
        settings = QgsPalLayerSettings()
        settings.fieldName = "name"
        settings.enabled = True
        settings.placement = Qgis.LabelPlacement.OverPoint
        settings.displayAll = True
        settings.priority = 9
        fmt = QgsTextFormat()
        fmt.setFont(QApplication.font())
        fmt.setSize(font_size)
        fmt.setColor(QColor("#3c4043"))
        buffer = QgsTextBufferSettings()
        buffer.setEnabled(True)
        buffer.setSize(1.0)
        buffer.setColor(QColor("#ffffff"))
        fmt.setBuffer(buffer)
        settings.setFormat(fmt)
        layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
        layer.setLabelsEnabled(True)
        if max_scale:
            layer.setScaleBasedVisibility(True)
            layer.setMinimumScale(max_scale)
            layer.setMaximumScale(0)
        layer.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple({"name": "circle", "size": str(marker_size), "color": "#5f6368", "outline_color": "#ffffff", "outline_width": ".2"})))

    def _label_major_roads(self, layer):
        from qgis.core import QgsPalLayerSettings, QgsTextBufferSettings, QgsTextFormat, QgsVectorLayerSimpleLabeling
        settings = QgsPalLayerSettings()
        settings.fieldName = "CASE WHEN \"highway\" IN ('motorway','motorway_link','trunk','trunk_link','primary','primary_link','secondary','secondary_link','tertiary','tertiary_link') THEN CASE WHEN \"name\" IS NOT NULL AND \"ref\" IS NOT NULL THEN \"name\" || '  ' || \"ref\" WHEN \"name\" IS NOT NULL THEN \"name\" ELSE \"ref\" END ELSE NULL END"
        settings.isExpression = True
        settings.enabled = True
        settings.placement = Qgis.LabelPlacement.Curved
        settings.priority = 8
        settings.displayAll = False
        fmt = QgsTextFormat()
        fmt.setFont(QApplication.font())
        fmt.setSize(7.5)
        fmt.setColor(QColor("#53616d"))
        buffer = QgsTextBufferSettings()
        buffer.setEnabled(True)
        buffer.setSize(1.0)
        buffer.setColor(QColor("#ffffff"))
        fmt.setBuffer(buffer)
        settings.setFormat(fmt)
        layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
        layer.setLabelsEnabled(True)

    def _import_done(self):
        project = QgsProject.instance()
        group = project.layerTreeRoot().insertGroup(0, os.path.splitext(os.path.basename(self.target_gpkg))[0])
        specs = []
        land = self._layer("multipolygons", "Landnutzung", "\"landuse\" IS NOT NULL OR \"leisure\" IS NOT NULL")
        self._single_fill(land, "#e7efdf")
        specs.append(land)
        water = self._layer("multipolygons", "Gewässerflächen", "\"natural\"='water' OR \"water\" IS NOT NULL OR \"waterway\" IS NOT NULL")
        self._single_fill(water, "#b9dff5")
        specs.append(water)
        if self.include_buildings:
            buildings = self._layer("multipolygons", "Gebäude", "\"building\" IS NOT NULL")
            self._single_fill(buildings, "#e2e1df", "#d0cfcc")
            buildings.setScaleBasedVisibility(True)
            buildings.setMinimumScale(75000)
            buildings.setMaximumScale(0)
            specs.append(buildings)
        coastline = self._layer("lines", "Küstenlinie", "\"natural\"='coastline'")
        self._single_line(coastline, "#6f9fb8", .65)
        specs.append(coastline)
        boundaries = self._layer("multilinestrings", "Verwaltungsgrenzen", "\"boundary\"='administrative' AND \"admin_level\" IN ('2','4','6')")
        self._single_line(boundaries, "#a68ab8", .35, "dash")
        specs.append(boundaries)
        hiking = self._layer("multilinestrings", "Wander- und Fahrradrouten", "\"route\" IN ('hiking','foot','bicycle','mtb')")
        self._single_line(hiking, "#6b9b68", .35, "dash")
        hiking.setScaleBasedVisibility(True)
        hiking.setMinimumScale(250000)
        hiking.setMaximumScale(0)
        specs.append(hiking)
        waterways = self._layer("lines", "Flüsse und Bäche", "\"waterway\" IS NOT NULL")
        self._single_line(waterways, "#8bc8ea", .45)
        specs.append(waterways)
        rail = self._layer("lines", "Bahnlinien", "\"railway\" IS NOT NULL")
        self._single_line(rail, "#777777", .35, "dash")
        specs.append(rail)
        roads = self._layer("lines", "Straßen und Wege", "\"highway\" IS NOT NULL")
        self._road_renderer(roads)
        self._label_major_roads(roads)
        specs.append(roads)
        cities = self._layer("points", "Städte und größere Orte", "\"place\" IN ('city','town') AND \"name\" IS NOT NULL")
        self._label_places(cities, 10, 3000000, 1.1)
        specs.append(cities)
        villages = self._layer("points", "Dörfer und Ortsteile", "\"place\" IN ('village','hamlet','suburb','neighbourhood','locality') AND \"name\" IS NOT NULL")
        self._label_places(villages, 8, 350000, .65)
        specs.append(villages)
        valid = [x for x in specs if x.isValid()]
        for layer in valid:
            project.addMapLayer(layer, False)
            group.insertLayer(0, layer)
        if valid:
            extent_layer = roads if roads.isValid() else valid[0]
            self.iface.mapCanvas().setExtent(extent_layer.extent())
            self.iface.mapCanvas().refresh()
        qgz = os.path.splitext(self.target_gpkg)[0] + ".qgz"
        project.write(qgz)
        QMessageBox.information(self.iface.mainWindow(), "Offline-Karte fertig", "GeoPackage und QGIS-Projekt wurden erstellt:\n" + qgz)
