from qgis.core import QgsApplication
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtCore import QEventLoop, QTimer
from qgis.PyQt.QtWidgets import QWidget

from .qgis_interface import QgisInterface

QGIS_APP = None
CANVAS = None
PARENT = None
IFACE = None


def get_qgis_app():
    global QGIS_APP, CANVAS, PARENT, IFACE
    if QGIS_APP is None:
        QGIS_APP = QgsApplication.instance()
        if QGIS_APP is None:
            QGIS_APP = QgsApplication([], False)
        QGIS_APP.initQgis()
    if PARENT is None:
        PARENT = QWidget()
        CANVAS = QgsMapCanvas(PARENT)
        CANVAS.resize(400, 400)
        IFACE = QgisInterface(CANVAS)
    return QGIS_APP, CANVAS, IFACE, PARENT


def wait_until(predicate, timeout_ms=3000):
    loop = QEventLoop()
    poll = QTimer()
    poll.setInterval(5)
    poll.timeout.connect(lambda: loop.quit() if predicate() else None)
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)
    poll.start()
    timeout.start(timeout_ms)
    loop.exec()
    poll.stop()
    timeout.stop()
    if not predicate():
        raise TimeoutError("QGIS operation did not complete")
