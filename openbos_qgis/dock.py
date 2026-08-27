from qgis.PyQt.QtCore import Qt, QSize, pyqtSignal

# Qt 5 (QGIS 3) and Qt 6 (QGIS 4) compatible enum values.
USER_ROLE = getattr(Qt, "UserRole", Qt.ItemDataRole.UserRole)
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QComboBox, QDockWidget, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton, QSpinBox, QTextEdit,
    QVBoxLayout, QWidget,
)


class SymbolDock(QDockWidget):
    placeRequested = pyqtSignal(object)
    layerRequested = pyqtSignal(bool)

    def __init__(self, catalog, electro=False, parent=None):
        title = "OpenBOS – Elektroversorgung" if electro else "OpenBOS – Taktische Zeichen"
        super().__init__(title, parent)
        self.catalog = catalog
        self.electro = electro
        self.setObjectName("OpenBOSElectroDock" if electro else "OpenBOSDock")
        self.resize(450, 720)

        root = QWidget(self)
        layout = QVBoxLayout(root)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Elektrosymbol suchen …" if electro else "BOS-Symbol suchen …")
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        self.category = QComboBox()
        layout.addWidget(self.category)
        self.list = QListWidget()
        self.list.setIconSize(QSize(72, 72))
        self.list.setUniformItemSizes(True)
        self.list.setSpacing(3)
        layout.addWidget(self.list, 1)

        form = QFormLayout()
        self.label = QLineEdit()
        self.size = QSpinBox(); self.size.setRange(3, 60); self.size.setValue(12); self.size.setSuffix(" mm")
        self.operator = QLineEdit(); self.operator.setPlaceholderText("z. B. THW Darmstadt")
        self.notes = QTextEdit(); self.notes.setMaximumHeight(65)
        form.addRow("Bezeichnung", self.label)
        self.status = self.power = self.voltage = self.current = self.length = None
        if electro:
            self.status = QComboBox(); self.status.addItems(["Unbekannt", "Geplant", "Bereit", "In Betrieb", "Gestört", "Außer Betrieb"])
            self.power = QDoubleSpinBox(); self.power.setRange(0, 10000); self.power.setDecimals(1); self.power.setSuffix(" kVA")
            self.voltage = QDoubleSpinBox(); self.voltage.setRange(0, 50000); self.voltage.setValue(400); self.voltage.setSuffix(" V")
            self.current = QDoubleSpinBox(); self.current.setRange(0, 10000); self.current.setDecimals(1); self.current.setSuffix(" A")
            self.length = QDoubleSpinBox(); self.length.setRange(0, 100000); self.length.setDecimals(1); self.length.setSuffix(" m")
            form.addRow("Status", self.status); form.addRow("Leistung", self.power)
            form.addRow("Spannung", self.voltage); form.addRow("Nennstrom", self.current); form.addRow("Kabellänge", self.length)
        form.addRow("Betreiber", self.operator); form.addRow("Symbolgröße", self.size); form.addRow("Bemerkung", self.notes)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        self.place = QPushButton("Auf Karte platzieren")
        self.create_layer = QPushButton("Layer anlegen")
        buttons.addWidget(self.place); buttons.addWidget(self.create_layer)
        layout.addLayout(buttons)
        self.info = QLabel("Symbol auswählen und anschließend auf die Karte klicken.")
        self.info.setWordWrap(True); layout.addWidget(self.info)
        self.setWidget(root)

        self.search.textChanged.connect(self.refresh)
        self.category.currentTextChanged.connect(self.refresh)
        self.list.currentItemChanged.connect(self._selection_changed)
        self.list.itemDoubleClicked.connect(lambda _: self.placeRequested.emit(self))
        self.place.clicked.connect(lambda: self.placeRequested.emit(self))
        self.create_layer.clicked.connect(lambda: self.layerRequested.emit(self.electro))
        self.populate_categories()

    def populate_categories(self):
        current = self.category.currentText()
        self.category.blockSignals(True)
        self.category.clear(); self.category.addItem("Alle Kategorien")
        self.category.addItems(self.catalog.category_names(self.electro))
        index = self.category.findText(current)
        self.category.setCurrentIndex(index if index >= 0 else 0)
        self.category.blockSignals(False)
        self.refresh()

    def refresh(self):
        category = self.category.currentText()
        category = None if category == "Alle Kategorien" else category
        self.list.clear()
        for entry in self.catalog.iter_entries(self.electro, category, self.search.text()):
            item = QListWidgetItem(QIcon(entry["path"]), entry["name"])
            item.setData(USER_ROLE, entry)
            item.setToolTip(f"{entry['category']}\n{entry['name']}\n{entry['path']}")
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        else:
            self.info.setText("Keine passenden Zeichen gefunden.")

    def _selection_changed(self, current, previous):
        if current is None:
            return
        entry = current.data(USER_ROLE)
        self.label.setText(entry["name"])
        self.info.setText(f"Ausgewählt: {entry['category']} / {entry['name']}")

    def selected_entry(self):
        item = self.list.currentItem()
        return item.data(USER_ROLE) if item else None

    def values(self):
        result = {
            "bezeichnung": self.label.text().strip(), "groesse_mm": self.size.value(),
            "betreiber": self.operator.text().strip(), "bemerkung": self.notes.toPlainText().strip(),
            "status": self.status.currentText() if self.status else "",
        }
        if self.electro:
            result.update({"leistung_kva": self.power.value(), "spannung_v": self.voltage.value(),
                           "nennstrom_a": self.current.value(), "kabellaenge_m": self.length.value()})
        return result
