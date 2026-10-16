from __future__ import annotations

from configparser import ConfigParser
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qgis.gui import QgisInterface

    from .plugin import PolskieDanePlugin


def _read_metadata() -> tuple[str, str]:
    metadata = ConfigParser(interpolation=None)
    with (
        Path(__file__).with_name("metadata.txt").open(encoding="utf-8") as file
    ):
        metadata.read_file(file)
    return metadata.get("general", "name"), metadata.get("general", "version")


PLUGIN_NAME, PLUGIN_VERSION = _read_metadata()


def classFactory(iface: QgisInterface) -> PolskieDanePlugin:
    from .plugin import PolskieDanePlugin

    return PolskieDanePlugin(iface)
