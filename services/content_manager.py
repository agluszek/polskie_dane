from __future__ import annotations

from qgis.PyQt.QtCore import QObject

from .add_service import AddOGCService
from .registry_metadata import RegistryMetadataFetcher


class ContentManager(QObject):
    def __init__(self, dialog_parent: QObject) -> None:
        super().__init__(dialog_parent)
        self.ogc_service = AddOGCService()
        self.registry = RegistryMetadataFetcher()
        self._services_by_area: dict[
            tuple[str, str], list[dict[str, str]]
        ] = {}

    def has_cached_services(
        self, service_type: str, teryt: str = "PL"
    ) -> bool:
        return (teryt, service_type.upper()) in self._services_by_area

    def get_cached_services(
        self, service_type: str, teryt: str = "PL"
    ) -> list[dict[str, str]]:
        return self._services_by_area.get((teryt, service_type.upper()), [])

    def cache_services(
        self, service_type: str, rows: list[dict[str, str]], teryt: str = "PL"
    ) -> None:
        self._services_by_area[teryt, service_type.upper()] = rows

    def invalidate_services(self, teryt: str = "PL") -> None:
        self.registry.invalidate(teryt)
        for key in tuple(self._services_by_area):
            if key[0] == teryt:
                del self._services_by_area[key]

    def fetch_services(
        self, service_type: str, teryt: str = "PL"
    ) -> list[dict[str, str]]:
        return self.registry.fetch_services(teryt, service_type)
