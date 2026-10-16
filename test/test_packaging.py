import subprocess  # nosec B404
import sys
import tempfile
import textwrap
import unittest
from configparser import ConfigParser
from pathlib import Path
from zipfile import ZipFile

from ..scripts.package_plugin import REPOSITORY_ROOT, build_package


class PackagingTest(unittest.TestCase):
    def test_archive_has_runtime_resources_and_no_development_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            output = build_package(
                REPOSITORY_ROOT, Path(directory) / "polskie_dane.zip"
            )
            with ZipFile(output) as archive:
                self.assertIsNone(archive.testzip())
                names = set(archive.namelist())
                required = {
                    "__init__.py",
                    "plugin.py",
                    "LICENSE",
                    "metadata.txt",
                    "core/__init__.py",
                    "gui/dialog.py",
                    "services/registry_metadata.py",
                    "resources/forms/polskie_dane.ui",
                    "resources/styles/light.qss",
                    "resources/styles/dark.qss",
                    "resources/icons/icon.svg",
                    "resources/icons/combo_arrow_light.svg",
                    "resources/icons/combo_arrow_dark.svg",
                }
                self.assertTrue(
                    {f"polskie_dane/{name}" for name in required} <= names
                )
                for name in names:
                    with self.subTest(path=name):
                        path = Path(name)
                        self.assertEqual(path.parts[0], "polskie_dane")
                        self.assertTrue(
                            set(path.parts).isdisjoint(
                                {
                                    "test",
                                    "scripts",
                                    "dist",
                                    ".git",
                                    ".venv",
                                    "__pycache__",
                                }
                            )
                        )
                        self.assertNotEqual(path.suffix, ".pyc")
                metadata = ConfigParser(interpolation=None)
                metadata.read_string(
                    archive.read("polskie_dane/metadata.txt").decode("utf-8")
                )
                self.assertEqual(
                    metadata.get("general", "name"), "Polskie dane"
                )
                self.assertIn(
                    "polskie_dane/" + metadata.get("general", "icon"), names
                )

    def test_extracted_package_initializes_in_qgis(self):
        with tempfile.TemporaryDirectory() as directory:
            output = build_package(
                REPOSITORY_ROOT, Path(directory) / "polskie_dane.zip"
            )
            with ZipFile(output) as archive:
                archive.extractall(directory)
            smoke_test = textwrap.dedent("""\
                from pathlib import Path
                from qgis.core import QgsApplication, QgsProviderRegistry
                from qgis.PyQt.QtWidgets import QMainWindow
                import polskie_dane

                assert Path(polskie_dane.__file__).resolve() == (
                    Path.cwd() / "polskie_dane" / "__init__.py"
                )
                app = QgsApplication([], False)
                app.initQgis()
                providers = QgsProviderRegistry.instance().providerList()
                assert {"wms", "WFS", "wcs"} <= set(providers)

                class Interface:
                    def __init__(self):
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

                iface = Interface()
                plugin = polskie_dane.classFactory(iface)
                plugin.initGui()
                assert polskie_dane.PLUGIN_NAME == "Polskie dane"
                assert polskie_dane.PLUGIN_NAME in plugin.dlg.windowTitle()
                assert not iface.actions[0].icon().isNull()
                assert "__COMBO_ARROW__" not in plugin.dlg.styleSheet()
                assert "QComboBox" in plugin.dlg.styleSheet()
                plugin.unload()
                assert not iface.actions
                print("Packaged plugin initialized and unloaded")
            """)
            result = subprocess.run(  # nosec B603
                [sys.executable, "-c", smoke_test],
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(
                result.returncode, 0, result.stdout + result.stderr
            )
            self.assertIn("Packaged plugin initialized", result.stdout)
