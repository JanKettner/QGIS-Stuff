import json
import os
import shutil
from pathlib import Path

from qgis.PyQt.QtCore import Qt, QSettings, QThread
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QAction, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QPushButton, QProgressBar, QRadioButton, QVBoxLayout
)
from qgis.core import (
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject,
    QgsVectorLayer
)

from .workers import BuildWorker, CatalogWorker

CATALOG_URL = "https://download.geofabrik.de/index-v1.json"


def selectable_text_flag():
    try:
        return Qt.TextInteractionFlag.TextSelectableByMouse
    except AttributeError:
        return Qt.TextSelectableByMouse


def user_role():
    try:
        return Qt.ItemDataRole.UserRole
    except AttributeError:
        return Qt.UserRole


class GeneratorDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.settings = QSettings()
        self.bbox = None
        self.catalog = []
        self.catalog_thread = None
        self.build_thread = None
        self.worker = None
        self.setWindowTitle("Offline Map Generator 0.2")
        self.resize(850, 760)
        self._build_ui()
        self.load_catalog()

    def _build_ui(self):
        root = QVBoxLayout(self)
        source_group = QGroupBox("OSM-Quelldaten")
        sl = QVBoxLayout(source_group)
        source_modes = QHBoxLayout()
        self.auto_radio = QRadioButton("Geofabrik-Extrakt automatisch herunterladen")
        self.local_radio = QRadioButton("Lokale OSM-PBF-Datei verwenden")
        self.auto_radio.setChecked(True)
        self.auto_radio.toggled.connect(self.update_source_mode)
        source_modes.addWidget(self.auto_radio); source_modes.addWidget(self.local_radio)
        sl.addLayout(source_modes)
        grid = QGridLayout()
        self.region_combo = QComboBox(); self.region_combo.setEditable(True)
        self.region_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert if hasattr(QComboBox, 'InsertPolicy') else QComboBox.NoInsert)
        self.region_combo.currentIndexChanged.connect(self.region_changed)
        refresh = QPushButton("Katalog neu laden"); refresh.clicked.connect(self.load_catalog)
        grid.addWidget(QLabel("Geofabrik-Region:"), 0, 0); grid.addWidget(self.region_combo, 0, 1); grid.addWidget(refresh, 0, 2)
        self.region_info = QLabel("Katalog wird geladen …"); self.region_info.setWordWrap(True); self.region_info.setTextInteractionFlags(selectable_text_flag())
        grid.addWidget(self.region_info, 1, 1, 1, 2)
        self.pbf_edit = QLineEdit(self.settings.value("offline_map_generator/pbf", ""))
        pbf_btn = QPushButton("Durchsuchen"); pbf_btn.clicked.connect(self.choose_pbf)
        grid.addWidget(QLabel("Lokale PBF-Datei:"), 2, 0); grid.addWidget(self.pbf_edit, 2, 1); grid.addWidget(pbf_btn, 2, 2)
        sl.addLayout(grid); root.addWidget(source_group)

        extent_group = QGroupBox("Kartenausschnitt"); el = QFormLayout(extent_group)
        self.extent_label = QLabel("Noch nicht übernommen"); self.extent_label.setTextInteractionFlags(selectable_text_flag())
        take = QPushButton("Aktuellen QGIS-Kartenausschnitt übernehmen"); take.clicked.connect(self.take_canvas_extent)
        el.addRow(take); el.addRow("WGS84-Bounding-Box:", self.extent_label)
        self.auto_region_btn = QPushButton("Kleinsten passenden Geofabrik-Extrakt vorschlagen"); self.auto_region_btn.clicked.connect(self.suggest_region)
        el.addRow(self.auto_region_btn); root.addWidget(extent_group)

        output_group = QGroupBox("Ausgabe und Werkzeuge"); og = QGridLayout(output_group)
        self.out_edit = QLineEdit(self.settings.value("offline_map_generator/output", "")); self.name_edit = QLineEdit("offline_map")
        self.osmium_edit = QLineEdit(self.settings.value("offline_map_generator/osmium", self._find_tool("osmium")))
        self.ogr_edit = QLineEdit(self.settings.value("offline_map_generator/ogr2ogr", self._find_tool("ogr2ogr")))
        self._path_row(og, 0, "Ausgabeordner:", self.out_edit, self.choose_output)
        og.addWidget(QLabel("Projektname:"), 1, 0); og.addWidget(self.name_edit, 1, 1, 1, 2)
        self._path_row(og, 2, "osmium.exe:", self.osmium_edit, lambda: self.choose_exe(self.osmium_edit))
        self._path_row(og, 3, "ogr2ogr.exe:", self.ogr_edit, lambda: self.choose_exe(self.ogr_edit)); root.addWidget(output_group)

        options = QGroupBox("Optionen"); ol = QVBoxLayout(options)
        self.keep_pbf = QCheckBox("Zugeschnittene PBF-Datei behalten"); self.keep_pbf.setChecked(True)
        self.create_gpkg = QCheckBox("GeoPackage erzeugen"); self.create_gpkg.setChecked(True)
        self.create_project = QCheckBox("QGIS-Projekt erzeugen und öffnen"); self.create_project.setChecked(True)
        self.reuse_download = QCheckBox("Bereits heruntergeladenen Regionalextrakt wiederverwenden"); self.reuse_download.setChecked(True)
        self.delete_download = QCheckBox("Großen Regionalextrakt nach erfolgreicher Verarbeitung löschen")
        for w in (self.keep_pbf, self.create_gpkg, self.create_project, self.reuse_download, self.delete_download): ol.addWidget(w)
        root.addWidget(options)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.progress = QProgressBar(); self.progress.setRange(0, 100)
        root.addWidget(self.log, 1); root.addWidget(self.progress)
        buttons = QHBoxLayout(); test = QPushButton("Werkzeuge prüfen"); test.clicked.connect(self.check_tools)
        self.run_btn = QPushButton("Herunterladen und Offline-Karte erstellen"); self.run_btn.clicked.connect(self.run_generator)
        self.cancel_btn = QPushButton("Abbrechen"); self.cancel_btn.clicked.connect(self.cancel_build); self.cancel_btn.setEnabled(False)
        close = QPushButton("Schließen"); close.clicked.connect(self.close)
        buttons.addWidget(test); buttons.addStretch(1); buttons.addWidget(self.run_btn); buttons.addWidget(self.cancel_btn); buttons.addWidget(close)
        root.addLayout(buttons); self.update_source_mode()

    def _find_tool(self, name):
        found = shutil.which(name)
        if found: return found
        prefix = Path(os.environ.get("OSGEO4W_ROOT", "")); candidates = []
        if prefix: candidates.append(prefix / "bin" / f"{name}.exe")
        qgis_prefix = Path(os.environ.get("QGIS_PREFIX_PATH", ""))
        if qgis_prefix: candidates.extend([qgis_prefix.parent.parent / "bin" / f"{name}.exe", qgis_prefix / "bin" / f"{name}.exe"])
        for c in candidates:
            if c.is_file(): return str(c)
        return ""

    def _path_row(self, layout, row, label, edit, callback):
        layout.addWidget(QLabel(label), row, 0); layout.addWidget(edit, row, 1)
        b = QPushButton("Durchsuchen"); b.clicked.connect(callback); layout.addWidget(b, row, 2)

    def choose_pbf(self):
        path, _ = QFileDialog.getOpenFileName(self, "OSM-PBF auswählen", "", "OSM PBF (*.osm.pbf *.pbf);;Alle Dateien (*)")
        if path: self.pbf_edit.setText(path)

    def choose_output(self):
        path = QFileDialog.getExistingDirectory(self, "Ausgabeordner auswählen")
        if path: self.out_edit.setText(path)

    def choose_exe(self, edit):
        path, _ = QFileDialog.getOpenFileName(self, "Programm auswählen", "", "Programme (*.exe);;Alle Dateien (*)")
        if path: edit.setText(path)

    def update_source_mode(self):
        auto = self.auto_radio.isChecked(); self.region_combo.setEnabled(auto); self.auto_region_btn.setEnabled(auto and bool(self.catalog)); self.pbf_edit.setEnabled(not auto)

    def append(self, text):
        self.log.appendPlainText(text); self.log.ensureCursorVisible()

    def load_catalog(self):
        if self.catalog_thread and self.catalog_thread.isRunning(): return
        self.region_info.setText("Geofabrik-Katalog wird geladen …"); self.catalog_thread = QThread(self); worker = CatalogWorker(CATALOG_URL); worker.moveToThread(self.catalog_thread)
        self.catalog_thread.started.connect(worker.run); worker.finished.connect(self.catalog_loaded); worker.failed.connect(self.catalog_failed); worker.status.connect(self.append)
        worker.finished.connect(self.catalog_thread.quit); worker.failed.connect(self.catalog_thread.quit); self.catalog_thread.finished.connect(worker.deleteLater); self.catalog_thread.start(); self._catalog_worker = worker

    def catalog_loaded(self, data):
        self.catalog = []
        for feature in data.get("features", []):
            props = feature.get("properties", {}); url = props.get("urls", {}).get("pbf")
            if not url: continue
            bbox = self.geometry_bbox(feature.get("geometry"))
            self.catalog.append({"id": props.get("id", ""), "parent": props.get("parent", ""), "name": props.get("name", props.get("id", "")), "url": url, "bbox": bbox})
        self.catalog.sort(key=lambda x: (self.full_region_name(x).casefold(), x["id"])); self.region_combo.clear()
        for entry in self.catalog: self.region_combo.addItem(self.full_region_name(entry), entry)
        self.region_info.setText(f"{len(self.catalog)} Geofabrik-Extrakte geladen."); self.update_source_mode()
        if self.bbox: self.suggest_region()

    def catalog_failed(self, message):
        self.region_info.setText("Katalog konnte nicht geladen werden."); QMessageBox.warning(self, "Geofabrik-Katalog", message)

    def full_region_name(self, entry):
        by_id = {e["id"]: e for e in self.catalog}; parts = [entry["name"]]; parent = entry.get("parent"); seen = set()
        while parent and parent not in seen and parent in by_id:
            seen.add(parent); p = by_id[parent]; parts.append(p["name"]); parent = p.get("parent")
        return " / ".join(reversed(parts))

    def geometry_bbox(self, geometry):
        if not geometry: return None
        values = []
        def walk(obj):
            if isinstance(obj, (list, tuple)):
                if len(obj) >= 2 and isinstance(obj[0], (int, float)) and isinstance(obj[1], (int, float)): values.append((float(obj[0]), float(obj[1])))
                else:
                    for child in obj: walk(child)
        walk(geometry.get("coordinates", []))
        if not values: return None
        xs = [p[0] for p in values]; ys = [p[1] for p in values]; return min(xs), min(ys), max(xs), max(ys)

    def region_changed(self, index):
        entry = self.region_combo.itemData(index)
        if entry: self.region_info.setText(f"{entry['url']}\nRegion-ID: {entry['id']}")

    def take_canvas_extent(self):
        canvas = self.iface.mapCanvas(); rect = canvas.extent(); src = canvas.mapSettings().destinationCrs(); dst = QgsCoordinateReferenceSystem("EPSG:4326")
        try: wgs = QgsCoordinateTransform(src, dst, QgsProject.instance()).transformBoundingBox(rect)
        except Exception as exc:
            QMessageBox.critical(self, "Offline Map Generator", f"Kartenausschnitt konnte nicht transformiert werden:\n{exc}"); return
        self.bbox = (wgs.xMinimum(), wgs.yMinimum(), wgs.xMaximum(), wgs.yMaximum()); self.extent_label.setText(", ".join(f"{v:.7f}" for v in self.bbox))
        if self.catalog and self.auto_radio.isChecked(): self.suggest_region()

    def suggest_region(self):
        if not self.bbox:
            QMessageBox.information(self, "Region vorschlagen", "Bitte zuerst den Kartenausschnitt übernehmen."); return
        candidates = []; x1, y1, x2, y2 = self.bbox
        for i, entry in enumerate(self.catalog):
            b = entry.get("bbox")
            if b and b[0] <= x1 and b[1] <= y1 and b[2] >= x2 and b[3] >= y2:
                area = max(0.000001, (b[2]-b[0]) * (b[3]-b[1])); candidates.append((area, i, entry))
        if not candidates:
            QMessageBox.warning(self, "Region vorschlagen", "Kein vollständig umschließender Geofabrik-Extrakt wurde gefunden. Bitte Region manuell wählen."); return
        _, index, entry = min(candidates, key=lambda t: t[0]); self.region_combo.setCurrentIndex(index); self.append(f"Vorgeschlagener Extrakt: {self.full_region_name(entry)}")

    def check_tools(self):
        missing = []; import subprocess
        for title, exe in (("osmium", self.osmium_edit.text().strip()), ("ogr2ogr", self.ogr_edit.text().strip())):
            try:
                result = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)); self.append(f"{title}: {(result.stdout or result.stderr).strip()}")
                if result.returncode != 0: missing.append(title)
            except Exception as exc: self.append(f"{title}: FEHLER – {exc}"); missing.append(title)
        if missing: QMessageBox.warning(self, "Werkzeugprüfung", "Nicht verfügbar: " + ", ".join(missing))
        else: QMessageBox.information(self, "Werkzeugprüfung", "osmium und ogr2ogr wurden gefunden.")

    def validate(self):
        out_text = self.out_edit.text().strip(); name = self.name_edit.text().strip()
        if not out_text: raise ValueError("Bitte einen Ausgabeordner auswählen.")
        if not name or any(c in name for c in '<>:"/\\|?*'): raise ValueError("Bitte einen gültigen Projektnamen eingeben.")
        if self.bbox is None: raise ValueError("Bitte den aktuellen Kartenausschnitt übernehmen.")
        osmium = self.osmium_edit.text().strip(); ogr = self.ogr_edit.text().strip()
        if not osmium: raise ValueError("Pfad zu osmium.exe fehlt.")
        if self.create_gpkg.isChecked() and not ogr: raise ValueError("Pfad zu ogr2ogr.exe fehlt.")
        config = {"output": out_text, "name": name, "bbox": self.bbox, "osmium": osmium, "ogr2ogr": ogr, "create_gpkg": self.create_gpkg.isChecked(), "keep_clipped": self.keep_pbf.isChecked(), "reuse_download": self.reuse_download.isChecked(), "delete_download": self.delete_download.isChecked(), "download_url": None, "source_pbf": ""}
        config["create_project"] = self.create_project.isChecked()
        if self.auto_radio.isChecked():
            entry = self.region_combo.currentData()
            if not entry: raise ValueError("Bitte einen Geofabrik-Extrakt auswählen.")
            config["download_url"] = entry["url"]; config["download_filename"] = Path(entry["url"]).name
        else:
            pbf = Path(self.pbf_edit.text().strip())
            if not pbf.is_file(): raise ValueError("Bitte eine vorhandene OSM-PBF-Datei auswählen.")
            config["source_pbf"] = str(pbf)
        return config

    def run_generator(self):
        try: config = self.validate()
        except Exception as exc: QMessageBox.critical(self, "Offline Map Generator", str(exc)); return
        self.settings.setValue("offline_map_generator/pbf", self.pbf_edit.text().strip()); self.settings.setValue("offline_map_generator/output", config["output"]); self.settings.setValue("offline_map_generator/osmium", config["osmium"]); self.settings.setValue("offline_map_generator/ogr2ogr", config["ogr2ogr"])
        self.progress.setValue(0); self.run_btn.setEnabled(False); self.cancel_btn.setEnabled(True); self.build_thread = QThread(self); self.worker = BuildWorker(config); self.worker.moveToThread(self.build_thread)
        self.build_thread.started.connect(self.worker.run); self.worker.progress.connect(self.progress.setValue); self.worker.log.connect(self.append); self.worker.finished.connect(lambda path: self.build_finished(path, config)); self.worker.failed.connect(self.build_failed); self.worker.finished.connect(self.build_thread.quit); self.worker.failed.connect(self.build_thread.quit); self.build_thread.finished.connect(self.worker.deleteLater); self.build_thread.start()

    def cancel_build(self):
        if self.worker: self.worker.cancel(); self.append("Abbruch angefordert …")

    def build_failed(self, message):
        self.run_btn.setEnabled(True); self.cancel_btn.setEnabled(False); self.append("\nFEHLER: " + message); QMessageBox.critical(self, "Offline Map Generator", message)

    def build_finished(self, result_path, config):
        try:
            project_path = None
            if config["create_project"] and config["create_gpkg"]: project_path = self.create_qgis_project(Path(result_path), Path(config["output"]) / f"{config['name']}.qgz")
            self.run_btn.setEnabled(True); self.cancel_btn.setEnabled(False); text = f"Offline-Daten wurden erstellt:\n{result_path}"
            if project_path: text += f"\n\nProjekt: {project_path}"
            QMessageBox.information(self, "Offline Map Generator", text)
        except Exception as exc: self.build_failed(str(exc))

    def create_qgis_project(self, gpkg, project_path):
        self.append("QGIS-Projekt wird erzeugt …"); project = QgsProject(); project.setFileName(str(project_path)); project.setCrs(QgsCoordinateReferenceSystem("EPSG:3857")); loaded = 0
        for layer_name in ("multipolygons", "multilinestrings", "lines", "points", "other_relations"):
            layer = QgsVectorLayer(f"{gpkg}|layername={layer_name}", layer_name.replace("_", " ").title(), "ogr")
            if layer.isValid(): project.addMapLayer(layer); loaded += 1
        if loaded == 0: raise RuntimeError("GeoPackage enthält keine erkannten OSM-Standardlayer.")
        if not project.write(str(project_path)): raise RuntimeError("QGIS-Projekt konnte nicht geschrieben werden.")
        QgsProject.instance().read(str(project_path)); self.append(f"Projekt gespeichert und geöffnet: {project_path}"); return project_path


class OfflineMapGeneratorPlugin:
    def __init__(self, iface):
        self.iface = iface; self.action = None; self.dialog = None

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(__file__), "icon.svg"); self.action = QAction(QIcon(icon_path), "Offline Map Generator", self.iface.mainWindow()); self.action.triggered.connect(self.run); self.iface.addPluginToWebMenu("Offline Map Generator", self.action); self.iface.addToolBarIcon(self.action)

    def unload(self):
        if self.action:
            self.iface.removePluginWebMenu("Offline Map Generator", self.action); self.iface.removeToolBarIcon(self.action)

    def run(self):
        if self.dialog is None: self.dialog = GeneratorDialog(self.iface, self.iface.mainWindow())
        self.dialog.show(); self.dialog.raise_(); self.dialog.activateWindow()
