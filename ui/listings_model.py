"""Pandas-backed QAbstractTableModel for editing the listings grid."""

from typing import Optional

import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt


class ListingsPandasModel(QAbstractTableModel):
    """A QAbstractTableModel that wraps a pandas DataFrame for in-place editing.

    The DataFrame is held by reference so changes flow directly into whatever
    the surrounding app is holding. Use set_dataframe() to swap it wholesale
    (emits the proper reset signals)."""

    def __init__(self, df: Optional[pd.DataFrame] = None, parent=None):
        super().__init__(parent)
        self._df: pd.DataFrame = df.copy() if df is not None else pd.DataFrame()

    # ---- public accessors -------------------------------------------------

    def dataframe(self) -> pd.DataFrame:
        return self._df

    def set_dataframe(self, df: pd.DataFrame) -> None:
        self.beginResetModel()
        self._df = df.copy() if df is not None else pd.DataFrame()
        self.endResetModel()

    # ---- Qt model API ------------------------------------------------------

    def rowCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._df.index)

    def columnCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._df.columns)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            if 0 <= section < len(self._df.columns):
                return str(self._df.columns[section])
        else:
            return str(section + 1)
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        if role not in (Qt.DisplayRole, Qt.EditRole):
            return None
        value = self._df.iat[index.row(), index.column()]
        if pd.isna(value):
            return ""
        return str(value)

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

    def setData(self, index: QModelIndex, value, role: int = Qt.EditRole) -> bool:
        if role != Qt.EditRole or not index.isValid():
            return False
        col = self._df.columns[index.column()]
        current = self._df.iat[index.row(), index.column()]
        # Coerce to existing column dtype when possible so numeric columns stay numeric
        try:
            if pd.api.types.is_integer_dtype(self._df[col]):
                new_value = int(value) if value not in ("", None) else 0
            elif pd.api.types.is_float_dtype(self._df[col]):
                new_value = float(value) if value not in ("", None) else float('nan')
            else:
                new_value = value
        except (ValueError, TypeError):
            new_value = value
        self._df.iat[index.row(), index.column()] = new_value
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
        return True

    # ---- row manipulation --------------------------------------------------

    def insertRows(self, row: int, count: int, parent=QModelIndex()) -> bool:
        if count <= 0:
            return False
        self.beginInsertRows(QModelIndex(), row, row + count - 1)
        empty = pd.DataFrame({col: [None] * count for col in self._df.columns})
        top = self._df.iloc[:row]
        bottom = self._df.iloc[row:]
        self._df = pd.concat([top, empty, bottom], ignore_index=True)
        self.endInsertRows()
        return True

    def removeRows(self, row: int, count: int, parent=QModelIndex()) -> bool:
        if count <= 0 or row < 0 or row >= len(self._df.index):
            return False
        end = min(row + count, len(self._df.index))
        self.beginRemoveRows(QModelIndex(), row, end - 1)
        self._df = self._df.drop(self._df.index[row:end]).reset_index(drop=True)
        self.endRemoveRows()
        return True
