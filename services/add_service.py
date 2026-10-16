from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import TypedDict, TypeVar
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from lxml import etree
from owslib.util import ServiceException
from owslib.wcs import WebCoverageService
from owslib.wfs import WebFeatureService
from owslib.wms import WebMapService
from owslib.wmts import WebMapTileService
from qgis.core import (
    QgsApplication,
    QgsDataSourceUri,
    QgsMapLayer,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QObject, QThread

from ..core.constants import SERVICES_REQUEST_TIMEOUT_SECONDS, WCS_NAMESPACES
from ..core.messages import MessageUtils
from ..core.network import NetworkUtils, ServiceAPI

OGCServiceType = TypeVar("OGCServiceType")


class CapabilitiesDownloadError(ValueError):
    pass


class LegacyWebCoverageService:
    def __init__(self, url: str) -> None:
        self.service_api = ServiceAPI()
        self.contents: list[str] = []
        self.update_contents(url=url)

    def update_contents(self, url: str) -> bool:
        self.contents = []
        parser = etree.XMLParser(
            resolve_entities=False,
            no_network=True,
            recover=False,
        )

        try:
            is_ok, capabilities_xml = self.service_api.get_request(url)
            if not is_ok:
                return False
            capabilities_root = etree.fromstring(
                capabilities_xml.encode("utf-8"), parser=parser
            )
        except (etree.XMLSyntaxError, ValueError) as error:
            MessageUtils.log_warning(f"Niepoprawny dokument WCS: {error}")
            return False

        ns = WCS_NAMESPACES
        for node in capabilities_root.findall(".//wcs:CoverageSummary", ns):
            cid = node.find("wcs:CoverageId", ns)
            if cid is None or not cid.text:
                continue
            name = cid.text.strip()
            self.contents.append(name)
        return True


@dataclass(frozen=True)
class LayerDefinition:
    uri: str
    display_name: str
    provider: str
    layer_type: str
    layer_id: str
    title: str


class DownloadedLayer(TypedDict):
    layer: QgsMapLayer
    layer_id: str
    url: str


class AddOGCService(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.downloaded_layers: list[DownloadedLayer] = []
        self._cancel_requested = False
        self._definitions: list[LayerDefinition] | None = None
        self.last_error: str | None = None

    @staticmethod
    def _add_map_layer(layer: QgsMapLayer) -> bool:
        if not layer.isValid():
            return False
        QgsProject.instance().addMapLayer(layer)
        return True

    def cancel_tasks(self) -> None:
        self._cancel_requested = True

    def add_services(
        self,
        selected_layers: Mapping[str, Iterable[str]],
    ) -> dict[tuple[str, str], bool]:
        selected_ids_by_url = {
            url: set(ids) for url, ids in selected_layers.items()
        }
        result = {
            (url, layer_id): False
            for url, layer_ids in selected_ids_by_url.items()
            for layer_id in layer_ids
        }
        for layer in self.downloaded_layers:
            selected_ids = selected_ids_by_url.get(layer["url"], ())

            if layer["layer_id"] not in selected_ids:
                continue

            identity = layer["url"], layer["layer_id"]

            try:
                result[identity] = self._add_map_layer(layer["layer"])
            except (RuntimeError, ValueError) as error:
                MessageUtils.log_warning(
                    f"Nie udało się dodać warstwy: {error}"
                )
                result[identity] = False

        self.clear_cache()
        return result

    def download_services(
        self, name: str, url: str, service_type: str
    ) -> bool:
        self.last_error = None
        handlers = {
            "WMS": self._process_wms_layer,
            "WMTS": self._process_wmts_layer,
            "WFS": self._process_wfs_layer,
            "WCS": self._process_wcs_layer,
        }
        handler = handlers.get(service_type.upper())
        if handler is None or self._cancel_requested:
            return False
        try:
            return handler(name, url)
        except (
            ServiceException,
            requests.exceptions.RequestException,
            ValueError,
            RuntimeError,
            etree.XMLSyntaxError,
        ) as error:
            self.last_error = f"{service_type}: {error}"
            if self._definitions is None:
                MessageUtils.log_warning(self.last_error)
            return False

    @classmethod
    def fetch_definitions(
        cls,
        name: str,
        url: str,
        service_type: str,
    ) -> list[LayerDefinition]:
        collector = cls()
        collector._definitions = []
        succeeded = collector.download_services(name, url, service_type)
        if not succeeded and collector.last_error:
            raise ValueError(collector.last_error)
        return collector._definitions

    def create_layers(
        self,
        name: str,
        url: str,
        service_type: str,
        definitions: list[LayerDefinition],
    ) -> bool:
        return self._process_layer_definitions(
            name, url, service_type, definitions
        )

    def clear_cache(self) -> None:
        self.downloaded_layers = []
        self._cancel_requested = False

    def _create_qgs_layer(
        self,
        service_uri: str,
        service_name: str,
        service_type: str,
        layer_type: str = "raster",
    ) -> tuple[QgsMapLayer | None, bool]:

        if self._cancel_requested:
            return None, True
        app = QgsApplication.instance()
        if app is None or QThread.currentThread() != app.thread():
            raise RuntimeError(
                "Warstwy QGIS można tworzyć wyłącznie w głównym wątku "
                "aplikacji."
            )
        if layer_type == "raster":
            layer = QgsRasterLayer(service_uri, service_name, service_type)
        else:
            layer = QgsVectorLayer(service_uri, service_name, service_type)

        if self._cancel_requested:
            return None, True
        return layer, False

    @staticmethod
    def _provider_uri(**parameters: str) -> str:
        uri = QgsDataSourceUri()
        for name, value in parameters.items():
            uri.setParam(name, value)
        return bytes(uri.encodedUri()).decode("utf-8")

    def _process_layer_definitions(
        self,
        name: str,
        url: str,
        service_type: str,
        definitions: list[LayerDefinition],
    ) -> bool:

        if self._definitions is not None:
            self._definitions.extend(definitions)
            return bool(definitions)
        ok = False
        for definition in definitions:
            layer, is_canceled = self._create_qgs_layer(
                service_uri=definition.uri,
                service_name=definition.display_name,
                service_type=definition.provider,
                layer_type=definition.layer_type,
            )

            if is_canceled:
                return False

            if layer.isValid():
                ok = True
                self.downloaded_layers.append(
                    {
                        "layer": layer,
                        "layer_id": definition.layer_id,
                        "url": url,
                    }
                )
        return ok

    @staticmethod
    def _open_service(
        factory: Callable[..., OGCServiceType],
        url: str,
        version: str,
        service_type: str,
    ) -> OGCServiceType:
        parts = urlsplit(url)
        query = [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() not in ("service", "request", "version")
        ]
        endpoint = urlunsplit(parts._replace(query=urlencode(query)))
        success, content = NetworkUtils().fetch_content(
            endpoint,
            params={
                "service": service_type,
                "request": "GetCapabilities",
                "version": version,
            },
            timeout_ms=SERVICES_REQUEST_TIMEOUT_SECONDS * 1000,
        )
        if not success:
            host = parts.hostname or service_type
            if "SSL" in str(content) or "certificate" in str(content).lower():
                raise CapabilitiesDownloadError(
                    f"Nie można zweryfikować certyfikatu serwera {host}. "
                    "Sprawdź certyfikat serwera i zaufane certyfikaty w QGIS."
                )
            raise CapabilitiesDownloadError(f"{host}: {content}")
        return factory(
            endpoint,
            version=version,
            timeout=SERVICES_REQUEST_TIMEOUT_SECONDS,
            xml=content.encode("utf-8"),
        )

    def _open_versioned_service(
        self,
        factory: Callable[..., OGCServiceType],
        url: str,
        versions: Sequence[str],
        service_type: str,
    ) -> OGCServiceType | None:
        for version in versions:
            if self._cancel_requested:
                return None
            try:
                service = self._open_service(
                    factory, url, version, service_type
                )
                self.last_error = None
                return service
            except CapabilitiesDownloadError as error:
                self.last_error = str(error)
                return None
            except (
                ServiceException,
                requests.exceptions.RequestException,
                ValueError,
                etree.XMLSyntaxError,
            ) as error:
                self.last_error = f"{service_type}, wersja {version}: {error}"
        return None

    def _process_wms_layer(self, name: str, url: str) -> bool:
        service = self._open_versioned_service(
            WebMapService, url, ("1.3.0", "1.1.1"), "WMS"
        )
        if service is None:
            return False

        definitions = []
        get_map = service.getOperationByName("GetMap")
        if not get_map.formatOptions:
            return False
        format_name = get_map.formatOptions[0]
        for layer_name, layer_info in service.contents.items():
            if layer_info.children:
                continue

            uri = self._provider_uri(
                url=service.url,
                layers=layer_name,
                styles=next(iter(layer_info.styles), ""),
                format=format_name,
            )
            title = layer_info.title or layer_name
            definitions.append(
                LayerDefinition(
                    uri=uri,
                    display_name=f"WMS - {title}",
                    provider="wms",
                    layer_type="raster",
                    layer_id=layer_name,
                    title=title,
                )
            )
        return self._process_layer_definitions(
            name=name,
            url=url,
            service_type="WMS",
            definitions=definitions,
        )

    def _process_wmts_layer(self, name: str, url: str) -> bool:
        service = self._open_service(WebMapTileService, url, "1.0.0", "WMTS")
        definitions = []
        for layer_name, layer_info in service.contents.items():
            tile_matrix_set_link = (
                next(iter(layer_info.tilematrixsetlinks), None)
                if layer_info.tilematrixsetlinks
                else None
            )
            tile_matrix_set = getattr(
                tile_matrix_set_link, "tilematrixset", tile_matrix_set_link
            )
            if not tile_matrix_set:
                continue
            if not layer_info.formats:
                continue
            format_name = layer_info.formats[0]
            style_name = next(iter(layer_info.styles), "")
            uri = self._provider_uri(
                url=url,
                layers=layer_name,
                styles=style_name,
                format=format_name,
                tileMatrixSet=tile_matrix_set,
            )
            title = getattr(layer_info, "title", None) or layer_name
            definitions.append(
                LayerDefinition(
                    uri=uri,
                    display_name=f"WMTS - {layer_name}",
                    provider="wms",
                    layer_type="raster",
                    layer_id=layer_name,
                    title=title,
                )
            )
        return self._process_layer_definitions(
            name=name,
            url=url,
            service_type="WMTS",
            definitions=definitions,
        )

    def _process_wfs_layer(self, name: str, url: str) -> bool:
        service = self._open_service(WebFeatureService, url, "2.0.0", "WFS")

        definitions = []
        for feature_name, feature_info in service.contents.items():
            title = feature_info.title or feature_name
            uri = QgsDataSourceUri()
            uri.setParam("url", url)
            uri.setParam("typename", feature_name)
            uri.setParam("pagingEnabled", "true")
            uri.setParam("version", "auto")

            definitions.append(
                LayerDefinition(
                    uri=uri.uri(False),
                    display_name=f"WFS - {title}",
                    provider="WFS",
                    layer_type="vector",
                    layer_id=feature_name,
                    title=title,
                )
            )
        return self._process_layer_definitions(
            name=name,
            url=url,
            service_type="WFS",
            definitions=definitions,
        )

    def _process_wcs_layer(self, name: str, url: str) -> bool:
        service = self._open_versioned_service(
            WebCoverageService, url, ("1.0.0", "1.1.1"), "WCS"
        )
        if service is None:
            if self._cancel_requested:
                return False
            service = LegacyWebCoverageService(url)

        definitions = []
        for coverage_id in service.contents:
            uri = self._provider_uri(url=url, identifier=coverage_id)
            definitions.append(
                LayerDefinition(
                    uri=uri,
                    display_name=f"WCS - {coverage_id}",
                    provider="wcs",
                    layer_type="raster",
                    layer_id=coverage_id,
                    title=coverage_id,
                )
            )
        return self._process_layer_definitions(
            name=name,
            url=url,
            service_type="WCS",
            definitions=definitions,
        )
