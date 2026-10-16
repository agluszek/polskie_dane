from __future__ import annotations

from typing import Any

from qgis.PyQt.QtWidgets import QMessageBox


class QtCompat:
    @staticmethod
    def get_enum(parent: type, enum_class: str, value: str) -> Any:
        scoped = getattr(parent, enum_class, None)
        return getattr(scoped if scoped is not None else parent, value)

    @staticmethod
    def get_message_box_icon(icon: str = "Information") -> Any:
        return QtCompat.get_enum(QMessageBox, "Icon", icon)
