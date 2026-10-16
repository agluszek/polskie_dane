from __future__ import annotations

from functools import lru_cache
from typing import Any

from qgis.PyQt.QtCore import QModelIndex, QRect, QSortFilterProxyModel, Qt
from qgis.PyQt.QtGui import QFont, QFontMetrics
from qgis.PyQt.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

from ..core.qt_compat import QtCompat


class NumberedRowsProxyModel(QSortFilterProxyModel):
    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int | None = None,
    ) -> Any:
        vertical = QtCompat.get_enum(Qt, "Orientation", "Vertical")
        display = QtCompat.get_enum(Qt, "ItemDataRole", "DisplayRole")
        if role is None:
            role = display
        if orientation == vertical and role == display:
            return section + 1
        return super().headerData(section, orientation, role)


class WrappedNameDelegate(QStyledItemDelegate):
    def initStyleOption(
        self, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        super().initStyleOption(option, index)
        option.features |= QtCompat.get_enum(
            QStyleOptionViewItem, "ViewItemFeature", "WrapText"
        )


@lru_cache(maxsize=1024)
def wrapped_name_height(text: str, width: int, font_description: str) -> int:
    font = QFont()
    font.fromString(font_description)
    metrics = QFontMetrics(font)
    return (
        metrics.boundingRect(
            QRect(0, 0, width, 0),
            QtCompat.get_enum(Qt, "TextFlag", "TextWordWrap"),
            text,
        ).height()
        + 12
    )
