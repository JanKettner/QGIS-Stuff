from pathlib import Path
import os, sys, subprocess

from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices, QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.core import QgsApplication

from .catalog import SymbolCatalog
from .dock import SymbolBrowserDock
from .layers import LayerManager
from .maptool import PlacementTool


class OpenBOSPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.root = Path(__file__).resolve().parent
        self.svg_root = self.root / "svg"
        self.catalog = SymbolCatalog(self.svg_root)
        self.layers = LayerManager(iface, self.svg_root)
        self.actions = []
        self.docks = {}
        self.map_tool = None
        self._previous_map_tool = None

    def initGui(self):
        try:
            self._register_svg_path()
            self.catalog.reload()
            self._add_action("BOS-Symbolbrowser", self.open_bos_browser)
            self._add_action("Elektro-Symbolbrowser", self.open_electro_browser)
            self._add_action("Symbolordner öffnen", self.open_folder)
        except Exception as exc:
            QMessageBox.critical(self.iface.mainWindow(), "OpenBOS", f"OpenBOS konnte nicht initialisiert werden:\n{exc}")
            raise

    def unload(self):
        if self.map_tool is not None:
            try:
                self.iface.mapCanvas().unsetMapTool(self.map_tool)
            except Exception:
                pass
            self.map_tool = None
        for dock in list(self.docks.values()):
            try:
                self.iface.removeDockWidget(dock)
                dock.deleteLater()
            except Exception:
                pass
        self.docks.clear()
        for action in self.actions:
            try:
                self.iface.removePluginMenu("&OpenBOS", action)
                self.iface.removeToolBarIcon(action)
            except Exception:
                pass
        self.actions.clear()

    def _add_action(self, text, callback):
        action = QAction(QIcon(str(self.root / "icon.svg")), text, self.iface.mainWindow())
        action.triggered.connect(callback)
        self.iface.addPluginToMenu("&OpenBOS", action)
        if text in ("BOS-Symbolbrowser", "Elektro-Symbolbrowser"):
            self.iface.addToolBarIcon(action)
        self.actions.append(action)
        return action

    def _register_svg_path(self):
        if not self.svg_root.is_dir():
            raise RuntimeError(f"SVG-Bibliothek fehlt: {self.svg_root}")
        path = str(self.svg_root)
        paths = list(QgsApplication.svgPaths())
        if path not in paths:
            QgsApplication.setSvgPaths(paths + [path])

    def _open_browser(self, mode):
        dock = self.docks.get(mode)
        if dock is None:
            dock = SymbolBrowserDock(self, mode, self.iface.mainWindow())
            self.docks[mode] = dock
            # QGIS 3/Qt5 and QGIS 4/Qt6 compatible dock-area enum.
            try:
                area = Qt.DockWidgetArea.RightDockWidgetArea
            except AttributeError:
                area = Qt.RightDockWidgetArea
            self.iface.addDockWidget(area, dock)
        dock.refresh()
        dock.show()
        dock.raise_()

    def open_bos_browser(self):
        self._open_browser("bos")

    def open_electro_browser(self):
        self._open_browser("electro")

    def activate_place_tool(self, browser):
        entry = browser.selected_entry()
        if entry is None:
            QMessageBox.information(browser, "OpenBOS", "Bitte zuerst ein Symbol auswählen.")
            return
        attrs = browser.form_values()
        canvas = self.iface.mapCanvas()
        if self.map_tool is not None:
            try:
                canvas.unsetMapTool(self.map_tool)
            except Exception:
                pass
        self._previous_map_tool = canvas.mapTool()
        self.map_tool = PlacementTool(canvas, lambda point: self._place_point(point, entry, attrs))
        canvas.setMapTool(self.map_tool)
        self.iface.messageBar().pushMessage("OpenBOS", "Position des Symbols in der Karte anklicken.", level=0, duration=5)

    def _place_point(self, point, entry, attrs):
        try:
            layer = self.layers.layer_for(entry)
            self.layers.add_feature(layer, point, entry, attrs)
            layer.triggerRepaint()
            self.iface.mapCanvas().refresh()
            self.iface.messageBar().pushMessage("OpenBOS", f"{entry.label} platziert.", level=0, duration=3)
        except Exception as exc:
            QMessageBox.critical(self.iface.mainWindow(), "OpenBOS", f"Symbol konnte nicht platziert werden:\n{exc}")
        finally:
            canvas = self.iface.mapCanvas()
            if self.map_tool is not None:
                try:
                    canvas.unsetMapTool(self.map_tool)
                except Exception:
                    pass
            self.map_tool = None
            if self._previous_map_tool is not None:
                try:
                    canvas.setMapTool(self._previous_map_tool)
                except Exception:
                    pass
            self._previous_map_tool = None

    def open_folder(self):
        path = str(self.svg_root)
        if not os.path.isdir(path):
            QMessageBox.warning(self.iface.mainWindow(), "OpenBOS", f"Symbolordner wurde nicht gefunden:\n{path}")
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
