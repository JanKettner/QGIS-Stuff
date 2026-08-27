from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    Qgis, QgsFeature, QgsField, QgsGeometry, QgsMarkerSymbol, QgsProject,
    QgsProperty, QgsSvgMarkerSymbolLayer, QgsSymbolLayer, QgsVectorLayer,
)


class LayerManager:
    BOS_NAME = "OpenBOS – Taktische Zeichen"
    ELECTRO_NAME = "OpenBOS – Elektroversorgung"

    def __init__(self, iface):
        self.iface = iface

    def layer_name(self, electro=False):
        return self.ELECTRO_NAME if electro else self.BOS_NAME

    def find(self, electro=False):
        name = self.layer_name(electro)
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer) and layer.name() == name:
                return layer
        return None

    def ensure(self, electro=False):
        layer = self.find(electro)
        if layer is not None:
            self.iface.setActiveLayer(layer)
            return layer

        crs = self.iface.mapCanvas().mapSettings().destinationCrs()
        authid = crs.authid() or "EPSG:4326"
        name = self.layer_name(electro)
        layer = QgsVectorLayer(f"Point?crs={authid}", name, "memory")
        if not layer.isValid():
            raise RuntimeError(f"Der Punktlayer '{name}' konnte nicht angelegt werden.")

        fields = [
            QgsField("bezeichnung", QVariant.String),
            QgsField("kategorie", QVariant.String),
            QgsField("symbol", QVariant.String),
            QgsField("groesse_mm", QVariant.Double),
            QgsField("status", QVariant.String),
            QgsField("betreiber", QVariant.String),
            QgsField("bemerkung", QVariant.String),
        ]
        if electro:
            fields.extend([
                QgsField("leistung_kva", QVariant.Double),
                QgsField("spannung_v", QVariant.Double),
                QgsField("nennstrom_a", QVariant.Double),
                QgsField("kabellaenge_m", QVariant.Double),
            ])
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()

        svg_layer = QgsSvgMarkerSymbolLayer("", 12.0)
        svg_layer.setDataDefinedProperty(QgsSymbolLayer.PropertyName, QgsProperty.fromField("symbol"))
        svg_layer.setDataDefinedProperty(QgsSymbolLayer.PropertySize, QgsProperty.fromField("groesse_mm"))
        marker = QgsMarkerSymbol()
        marker.changeSymbolLayer(0, svg_layer)
        layer.renderer().setSymbol(marker)

        QgsProject.instance().addMapLayer(layer)
        self.iface.setActiveLayer(layer)
        self.iface.messageBar().pushMessage(
            "OpenBOS", f"Layer '{name}' wurde angelegt.", level=Qgis.Info, duration=4
        )
        return layer

    def add(self, point, entry, values, electro=False):
        layer = self.ensure(electro)
        feature = QgsFeature(layer.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(point))
        feature["bezeichnung"] = values.get("bezeichnung") or entry["name"]
        feature["kategorie"] = entry["category"]
        feature["symbol"] = entry["path"]
        feature["groesse_mm"] = float(values.get("groesse_mm", 12.0))
        feature["status"] = values.get("status", "")
        feature["betreiber"] = values.get("betreiber", "")
        feature["bemerkung"] = values.get("bemerkung", "")
        if electro:
            feature["leistung_kva"] = float(values.get("leistung_kva", 0.0))
            feature["spannung_v"] = float(values.get("spannung_v", 400.0))
            feature["nennstrom_a"] = float(values.get("nennstrom_a", 0.0))
            feature["kabellaenge_m"] = float(values.get("kabellaenge_m", 0.0))
        if not layer.isEditable() and not layer.startEditing():
            raise RuntimeError(f"Der Layer '{layer.name()}' konnte nicht bearbeitet werden.")
        if not layer.addFeature(feature):
            raise RuntimeError("Das Zeichen konnte nicht eingefügt werden.")
        layer.updateExtents()
        layer.triggerRepaint()
        return feature
