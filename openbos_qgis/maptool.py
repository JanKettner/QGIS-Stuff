from qgis.gui import QgsMapToolEmitPoint


class OpenBOSPlaceTool(QgsMapToolEmitPoint):
    def __init__(self, canvas, callback):
        super().__init__(canvas)
        self._callback = callback
        self.canvasClicked.connect(self._clicked)

    def _clicked(self, point, button):
        self._callback(point)
