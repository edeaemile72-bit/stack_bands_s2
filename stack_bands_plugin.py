import os
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon

from .stack_bands_dialog import StackBandsDialog


class StackBandsPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dialog = None

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        if os.path.exists(icon_path):
            icon = QIcon(icon_path)
        else:
            icon = QIcon()  # icône vide par défaut si icon.png absent

        self.action = QAction(icon, "Stack Bands S2", self.iface.mainWindow())
        self.action.triggered.connect(self.run)

        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&Stack Bands S2", self.action)

    def unload(self):
        self.iface.removePluginMenu("&Stack Bands S2", self.action)
        self.iface.removeToolBarIcon(self.action)

    def run(self):
        self.dialog = StackBandsDialog(self.iface, self.iface.mainWindow())
        self.dialog.show()
        self.dialog.exec_()
