"""Left-side dock widget listing past sessions grouped by year with search + filter."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)


class HistoryPanel(QDockWidget):
    """Dock widget that shows saved sessions grouped by year.

    Emits `session_activated(session_id)` when the user double-clicks an entry.
    """

    session_activated = Signal(str)

    ROLE_SESSION_ID = Qt.UserRole + 1
    ROLE_IS_YEAR = Qt.UserRole + 2

    def __init__(self, session_manager, parent=None):
        super().__init__("History", parent)
        self.session_manager = session_manager

        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Search box
        self.search_edit = QLineEdit(container)
        self.search_edit.setPlaceholderText("Search set, box, sport…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._refresh)
        layout.addWidget(self.search_edit)

        # Year filter row
        year_row = QHBoxLayout()
        year_row.setSpacing(6)
        year_row.addWidget(QLabel("Year:", container))
        self.year_combo = QComboBox(container)
        self.year_combo.currentTextChanged.connect(self._refresh)
        year_row.addWidget(self.year_combo, 1)
        self.refresh_button = QPushButton("⟳", container)
        self.refresh_button.setFixedWidth(28)
        self.refresh_button.setToolTip("Rebuild index from disk")
        self.refresh_button.clicked.connect(self._rebuild_and_refresh)
        year_row.addWidget(self.refresh_button)
        layout.addLayout(year_row)

        # Tree of sessions grouped by year
        self.tree = QTreeView(container)
        self.tree.setHeaderHidden(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setEditTriggers(QTreeView.NoEditTriggers)
        self.tree.setSelectionMode(QTreeView.SingleSelection)
        self.tree.doubleClicked.connect(self._on_double_click)
        layout.addWidget(self.tree, 1)

        self.model = QStandardItemModel(self)
        self.tree.setModel(self.model)

        self.setWidget(container)
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setFeatures(
            QDockWidget.DockWidgetMovable
            | QDockWidget.DockWidgetFloatable
        )

        self._populate_years()
        self._refresh()

    # ----------------------------------------------------------------- API

    def refresh(self) -> None:
        """Public hook the main window calls after a save/delete."""
        self._populate_years()
        self._refresh()

    # ------------------------------------------------------------ internal

    def _populate_years(self) -> None:
        current = self.year_combo.currentText()
        self.year_combo.blockSignals(True)
        self.year_combo.clear()
        self.year_combo.addItem("All")
        for year in self.session_manager.available_years():
            self.year_combo.addItem(year)
        # Restore prior selection if still available
        idx = self.year_combo.findText(current) if current else 0
        self.year_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.year_combo.blockSignals(False)

    def _rebuild_and_refresh(self) -> None:
        self.session_manager.rebuild_index()
        self.refresh()

    def _refresh(self) -> None:
        query = self.search_edit.text()
        year_choice = self.year_combo.currentText()
        year = None if year_choice in ("", "All") else year_choice
        entries = self.session_manager.search_sessions(query=query, year=year)

        self.model.clear()
        root = self.model.invisibleRootItem()

        # Group by year (entries already newest-first)
        by_year: dict = {}
        for entry in entries:
            by_year.setdefault(entry.get('year', '????'), []).append(entry)

        for year_key in sorted(by_year.keys(), reverse=True):
            year_item = QStandardItem(year_key)
            year_item.setData(True, self.ROLE_IS_YEAR)
            year_item.setEditable(False)
            f = year_item.font()
            f.setBold(True)
            year_item.setFont(f)
            for entry in by_year[year_key]:
                label = self._format_entry(entry)
                child = QStandardItem(label)
                child.setData(entry.get('id'), self.ROLE_SESSION_ID)
                child.setData(False, self.ROLE_IS_YEAR)
                child.setEditable(False)
                child.setToolTip(entry.get('path', ''))
                year_item.appendRow(child)
            root.appendRow(year_item)

        self.tree.expandAll()

    @staticmethod
    def _format_entry(entry: dict) -> str:
        stamp = (entry.get('updated_at') or entry.get('created_at') or '')[:10]
        short = entry.get('card_set_short') or entry.get('card_set') or entry.get('id', '')
        box = entry.get('box') or ''
        if box:
            return f"{stamp}  {short}  · {box}"
        return f"{stamp}  {short}"

    def _on_double_click(self, index) -> None:
        item = self.model.itemFromIndex(index)
        if item is None:
            return
        if item.data(self.ROLE_IS_YEAR):
            return
        session_id = item.data(self.ROLE_SESSION_ID)
        if session_id:
            self.session_activated.emit(session_id)
