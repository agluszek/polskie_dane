from __future__ import annotations

from qgis.core import (
    Qgis,
    QgsMessageLog,
)
from qgis.PyQt.QtWidgets import QMessageBox, QWidget

from .. import PLUGIN_NAME
from .qt_compat import QtCompat


class MessageUtils:
    @staticmethod
    def _show_message_box(
        parent: QWidget | None,
        title: str,
        message: str,
        icon: str,
    ) -> None:
        msg_box = QMessageBox(parent)
        msg_box.setIcon(QtCompat.get_message_box_icon(icon))
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setStandardButtons(
            QtCompat.get_enum(QMessageBox, "StandardButton", "Ok")
        )
        if parent is not None:
            msg_box.setWindowIcon(parent.windowIcon())
        msg_box.exec()

    @staticmethod
    def push_message_box_warning(
        parent: QWidget | None, title: str, message: str
    ) -> None:
        MessageUtils._show_message_box(parent, title, message, "Warning")

    @staticmethod
    def log_warning(message: str) -> None:
        warning = QtCompat.get_enum(Qgis, "MessageLevel", "Warning")
        QgsMessageLog.logMessage(message, tag=PLUGIN_NAME, level=warning)

    @staticmethod
    def log_critical(message: str) -> None:
        critical = QtCompat.get_enum(Qgis, "MessageLevel", "Critical")
        QgsMessageLog.logMessage(message, tag=PLUGIN_NAME, level=critical)
