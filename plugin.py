from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QToolBar

try:
    from qgis.PyQt.QtGui import QAction
except ImportError:
    from qgis.PyQt.QtWidgets import QAction

from . import PLUGIN_NAME, PLUGIN_VERSION
from .gui.dialog import PolskieDaneDialog

if TYPE_CHECKING:
    from qgis.gui import QgisInterface


class PolskieDanePlugin:
    def __init__(self, iface: QgisInterface) -> None:
        self.iface = iface
        self.dlg: PolskieDaneDialog | None = None
        self.action: QAction | None = None
        self.menu = self.tr(PLUGIN_NAME)
        self.toolbar: QToolBar | None = None
        self._owns_toolbar = False

    @staticmethod
    def tr(message: str) -> str:
        return QCoreApplication.translate("PolskieDanePlugin", message)

    def initGui(self) -> None:
        if self.action is not None:
            return
        if self.dlg is None:
            self.dlg = PolskieDaneDialog(self.iface.mainWindow())
            self.dlg.setup_dialog(PLUGIN_NAME, PLUGIN_VERSION)
        self.toolbar = self.iface.mainWindow().findChild(QToolBar, PLUGIN_NAME)
        self._owns_toolbar = self.toolbar is None
        if self.toolbar is None:
            self.toolbar = self.iface.addToolBar(PLUGIN_NAME)
            self.toolbar.setObjectName(PLUGIN_NAME)
        icon_path = (
            Path(__file__).resolve().parent
            / "resources"
            / "icons"
            / "icon.svg"
        )
        self.action = QAction(
            QIcon(str(icon_path)),
            self.tr(PLUGIN_NAME),
            self.iface.mainWindow(),
        )
        self.action.triggered.connect(self.run)
        self.dlg.setWindowIcon(self.action.icon())
        self.toolbar.addAction(self.action)
        self.iface.addPluginToMenu(self.menu, self.action)

    def unload(self) -> None:
        if self.dlg is not None:
            self.dlg.close()
        if self.action is not None:
            self.iface.removePluginMenu(self.menu, self.action)
            self.toolbar.removeAction(self.action)
            self.action.deleteLater()
            self.action = None
        if self._owns_toolbar:
            self.toolbar.hide()
            self.iface.mainWindow().removeToolBar(self.toolbar)
            self.toolbar.setParent(None)
            self.toolbar.deleteLater()
            self._owns_toolbar = False
            self.toolbar = None

    def run(self) -> None:
        if self.dlg is not None:
            self.dlg.exec()
