from pathlib import Path
import os
import traceback

from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QAction, QDesktopServices, QIcon
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import Qgis, QgsSettings

from .catalog import SymbolCatalog
from .dock import SymbolDock
from .layers import LayerManager
from .maptool import OpenBOSPlaceTool

# Qt 5 (QGIS 3) and Qt 6 (QGIS 4) compatible enum value.
RIGHT_DOCK_AREA = getattr(Qt, "RightDockWidgetArea", Qt.DockWidgetArea.RightDockWidgetArea)


class OpenBOSPlugin:
    MENU_NAME = "&OpenBOS"
    SETTINGS_KEY = "svg/searchPathsForSVG"

    def __init__(self, iface):
        self.iface = iface
        self.actions = []
        self.catalog = None
        self.layers = LayerManager(iface)
        self.bos_dock = None
        self.electro_dock = None
        self.active_dock = None
        self.place_tool = None

    @property
    def plugin_dir(self):
        return Path(__file__).resolve().parent

    @property
    def svg_dir(self):
        return self.plugin_dir / "svg"

    def initGui(self):
        try:
            self.catalog = SymbolCatalog(self.svg_dir).load()
            self._register_svg_path()
            self._create_actions()
            self._create_docks()
        except Exception as exc:
            details = traceback.format_exc()
            QMessageBox.critical(self.iface.mainWindow(), "OpenBOS", f"Plugin konnte nicht geladen werden:\n\n{exc}\n\n{details}")
            raise

    def _create_actions(self):
        specs = [
            ("BOS-Symbolbrowser", self.show_bos_browser, True),
            ("Elektro-Symbolbrowser", self.show_electro_browser, True),
            ("Symbolordner öffnen", self.open_folder, False),
        ]
        for text, callback, toolbar in specs:
            icon = QIcon(str(self.plugin_dir / "icon.svg")) if text.startswith("BOS") else QIcon()
            action = QAction(icon, text, self.iface.mainWindow())
            action.triggered.connect(callback)
            self.iface.addPluginToMenu(self.MENU_NAME, action)
            if toolbar:
                self.iface.addToolBarIcon(action)
            self.actions.append((action, toolbar))

    def _create_docks(self):
        self.bos_dock = SymbolDock(self.catalog, False, self.iface.mainWindow())
        self.electro_dock = SymbolDock(self.catalog, True, self.iface.mainWindow())
        for dock in (self.bos_dock, self.electro_dock):
            dock.placeRequested.connect(self.activate_place_tool)
            dock.layerRequested.connect(self.layers.ensure)
            self.iface.addDockWidget(RIGHT_DOCK_AREA, dock)
            dock.hide()

    def unload(self):
        try:
            if self.place_tool and self.iface.mapCanvas().mapTool() == self.place_tool:
                self.iface.mapCanvas().unsetMapTool(self.place_tool)
        finally:
            for dock in (self.bos_dock, self.electro_dock):
                if dock is not None:
                    self.iface.removeDockWidget(dock)
                    dock.deleteLater()
            self.bos_dock = self.electro_dock = None
            for action, toolbar in self.actions:
                self.iface.removePluginMenu(self.MENU_NAME, action)
                if toolbar:
                    self.iface.removeToolBarIcon(action)
                action.deleteLater()
            self.actions.clear()

    def show_bos_browser(self):
        if self.bos_dock:
            self.bos_dock.show(); self.bos_dock.raise_()

    def show_electro_browser(self):
        if self.electro_dock:
            self.electro_dock.show(); self.electro_dock.raise_()

    def activate_place_tool(self, dock):
        entry = dock.selected_entry()
        if not entry:
            QMessageBox.information(self.iface.mainWindow(), "OpenBOS", "Bitte zuerst ein Symbol auswählen.")
            return
        self.active_dock = dock
        self.layers.ensure(dock.electro)
        if self.place_tool is None:
            self.place_tool = OpenBOSPlaceTool(self.iface.mapCanvas(), self.add_feature)
        self.iface.mapCanvas().setMapTool(self.place_tool)
        self.iface.messageBar().pushMessage(
            "OpenBOS", f"{entry['name']}: Position auf der Karte anklicken.", level=Qgis.Info, duration=6
        )

    def add_feature(self, point):
        if self.active_dock is None:
            return
        entry = self.active_dock.selected_entry()
        if not entry:
            return
        try:
            self.layers.add(point, entry, self.active_dock.values(), self.active_dock.electro)
        except Exception as exc:
            QMessageBox.warning(self.iface.mainWindow(), "OpenBOS", str(exc))

    def _register_svg_path(self):
        settings = QgsSettings()
        value = settings.value(self.SETTINGS_KEY, [])
        paths = [value] if isinstance(value, str) and value else list(value or [])
        source = str(self.svg_dir)
        normalized = {os.path.normcase(os.path.normpath(str(path))) for path in paths}
        if os.path.normcase(os.path.normpath(source)) not in normalized:
            paths.append(source)
            settings.setValue(self.SETTINGS_KEY, paths)

    def open_folder(self):
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.svg_dir))):
            QMessageBox.warning(self.iface.mainWindow(), "OpenBOS", f"Ordner konnte nicht geöffnet werden:\n{self.svg_dir}")
