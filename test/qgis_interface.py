from qgis.PyQt.QtWidgets import QMainWindow


class QgisInterface:
    def __init__(self, canvas):
        self.canvas = canvas
        self.window = QMainWindow()
        self.actions = []

    def mainWindow(self):
        return self.window

    def addToolBar(self, name):
        return self.window.addToolBar(name)

    def addPluginToMenu(self, menu, action):
        self.actions.append(action)

    def removePluginMenu(self, menu, action):
        self.actions.remove(action)
