import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

from qgis.core import QgsApplication, QgsDataSourceUri, QgsProject
from qgis.PyQt.QtCore import QUrl

from ..services import add_service
from ..services.add_service import (
    AddOGCService,
    LayerDefinition,
    LegacyWebCoverageService,
)
from .utilities import get_qgis_app

QGIS_APP = get_qgis_app()


class OGCServicesTest(unittest.TestCase):
    def setUp(self):
        self.network_patch = patch.object(
            add_service.NetworkUtils,
            "fetch_content",
            return_value=(True, "<Capabilities/>"),
        )
        self.network = self.network_patch.start()
        self.addCleanup(self.network_patch.stop)

    def test_certificate_failure_stops_without_protocol_retry(self):
        with (
            patch.object(
                add_service.NetworkUtils,
                "fetch_content",
                return_value=(False, "Błąd SSL: certificate verify failed"),
            ) as network,
            patch.object(add_service, "WebMapService") as factory,
        ):
            with self.assertRaisesRegex(
                ValueError, "certyfikatu.*geo.stat.gov.pl"
            ):
                AddOGCService.fetch_definitions(
                    "Mapa",
                    "https://geo.stat.gov.pl/wss/wms_inspire/wms",
                    "WMS",
                )
        self.assertEqual(network.call_count, 1)
        factory.assert_not_called()

    def test_wms_retries_next_protocol_version(self):
        service = MagicMock()
        service.getOperationByName.return_value.formatOptions = []
        failure = add_service.ServiceException("Unsupported version")
        with patch.object(
            add_service, "WebMapService", side_effect=[failure, service]
        ) as factory:
            with patch.object(add_service.MessageUtils, "log_warning"):
                self.assertFalse(
                    AddOGCService().download_services(
                        "Map", "https://example.com", "WMS"
                    )
                )
        self.assertEqual(
            [call.kwargs["version"] for call in factory.call_args_list],
            ["1.3.0", "1.1.1"],
        )

    def test_canceled_download_does_not_restart_on_next_service(self):
        loader = AddOGCService()
        loader.cancel_tasks()
        with patch.object(loader, "_process_wms_layer") as handler:
            self.assertFalse(loader.download_services("Map", "url", "WMS"))
        handler.assert_not_called()
        loader.clear_cache()
        with patch.object(loader, "_process_wms_layer", return_value=True):
            self.assertTrue(loader.download_services("Map", "url", "WMS"))

    def test_canceled_layer_creation_does_not_construct_provider(self):
        loader = AddOGCService()
        loader.cancel_tasks()
        with patch.object(add_service, "QgsRasterLayer") as layer:
            self.assertEqual(
                loader._create_qgs_layer("uri", "Map", "wms"), (None, True)
            )
        layer.assert_not_called()

    def test_worker_cannot_construct_native_layers(self):
        def create_in_worker(layer_type):
            return AddOGCService()._create_qgs_layer(
                "uri", "Map", "provider", layer_type
            )

        with (
            patch.object(add_service, "QgsRasterLayer") as raster,
            patch.object(add_service, "QgsVectorLayer") as vector,
            ThreadPoolExecutor(max_workers=1) as executor,
        ):
            for layer_type in ("raster", "vector"):
                with (
                    self.subTest(layer_type=layer_type),
                    self.assertRaisesRegex(RuntimeError, "głównym wątku"),
                ):
                    executor.submit(create_in_worker, layer_type).result(
                        timeout=5
                    )
        raster.assert_not_called()
        vector.assert_not_called()

    def test_memory_layer_survives_cache_cleanup_after_adding_to_project(self):
        loader = AddOGCService()
        definition = LayerDefinition(
            "Point?crs=EPSG:4326",
            "Polskie dane test",
            "memory",
            "vector",
            "points",
            "Test points",
        )
        self.assertTrue(
            loader.create_layers("Test", "memory://test", "WFS", [definition])
        )
        layer = loader.downloaded_layers[0]["layer"]
        project = QgsProject.instance()
        layer_id = layer.id()
        self.addCleanup(project.removeMapLayer, layer_id)
        self.assertEqual(layer.thread(), QgsApplication.instance().thread())
        self.assertIsNone(project.mapLayer(layer_id))
        self.assertEqual(
            loader.add_services({"memory://test": ["points"]}),
            {("memory://test", "points"): True},
        )
        self.assertEqual(loader.downloaded_layers, [])
        self.assertIs(project.mapLayer(layer_id), layer)
        self.assertTrue(project.mapLayer(layer_id).isValid())

    def test_wfs_uri_preserves_typename_and_endpoint_in_qgis_format(self):
        endpoint = (
            "https://example.com/wfs?map=A&key=a'b%20c"
            "&SERVICE=WFS&request=GetCapabilities"
        )
        feature_name = "ns:roads"
        service = SimpleNamespace(
            contents={feature_name: SimpleNamespace(title="Drogi")}
        )
        with patch.object(
            add_service, "WebFeatureService", return_value=service
        ) as factory:
            definitions = AddOGCService.fetch_definitions(
                "Mapa", endpoint, "WFS"
            )
        self.assertEqual(len(definitions), 1)
        definition = definitions[0]
        self.assertEqual(definition.provider, "WFS")
        self.assertEqual(definition.layer_type, "vector")
        decoded = QgsDataSourceUri(definition.uri)
        self.assertEqual(decoded.param("typename"), feature_name)
        self.assertEqual(decoded.param("url"), endpoint)
        self.assertEqual(decoded.param("pagingEnabled"), "true")
        self.assertEqual(decoded.param("version"), "auto")
        request = self.network.call_args
        self.assertEqual(
            parse_qs(urlsplit(request.args[0]).query),
            {"map": ["A"], "key": ["a'b c"]},
        )
        self.assertEqual(
            request.kwargs["params"],
            {
                "service": "WFS",
                "request": "GetCapabilities",
                "version": "2.0.0",
            },
        )
        self.assertEqual(factory.call_args.kwargs["xml"], b"<Capabilities/>")

    def test_wmts_without_styles_uses_default_style(self):
        service = SimpleNamespace(
            contents={
                "roads": SimpleNamespace(
                    tilematrixsetlinks={"EPSG:3857": object()},
                    formats=["image/png"],
                    styles={},
                    title="Roads",
                )
            }
        )
        endpoint = "https://example.com/wmts?key=a&value=b%20c"
        with patch.object(
            add_service, "WebMapTileService", return_value=service
        ):
            definitions = AddOGCService.fetch_definitions(
                "Map", endpoint, "WMTS"
            )
        self.assertEqual(len(definitions), 1)
        decoded = QgsDataSourceUri()
        decoded.setEncodedUri(definitions[0].uri)
        self.assertEqual(QUrl(decoded.param("url")), QUrl(endpoint))
        self.assertEqual(decoded.param("layers"), "roads")
        self.assertEqual(decoded.param("styles"), "")

    def test_wmts_without_formats_is_skipped(self):
        service = SimpleNamespace(
            contents={
                "roads": SimpleNamespace(
                    tilematrixsetlinks={"EPSG:3857": object()},
                    formats=[],
                )
            }
        )
        loader = AddOGCService()
        with patch.object(
            add_service, "WebMapTileService", return_value=service
        ):
            self.assertFalse(
                loader.download_services("Map", "https://example.com", "WMTS")
            )
        self.assertEqual(loader.downloaded_layers, [])

    def test_invalid_layer_is_not_added_to_project(self):
        loader = AddOGCService()
        layer = MagicMock()
        layer.isValid.return_value = False
        loader.downloaded_layers = [
            {
                "url": "url",
                "layer_id": "roads",
                "layer": layer,
            }
        ]
        with patch.object(add_service, "QgsProject") as project:
            self.assertEqual(
                loader.add_services({"url": ["roads"]}),
                {("url", "roads"): False},
            )
        project.instance.assert_not_called()
        self.assertEqual(loader.downloaded_layers, [])

    def test_results_keep_distinct_layers_with_identical_titles(self):
        loader = AddOGCService()
        definitions = [
            LayerDefinition("uri", "WMS - Map", "wms", "raster", key, "Map")
            for key in ("roads", "buildings")
        ]
        layers = [MagicMock() for _ in range(3)]
        with patch.object(
            loader,
            "_create_qgs_layer",
            side_effect=[(layer, False) for layer in layers],
        ):
            loader.create_layers("Map", "first", "WMS", definitions)
            loader.create_layers("Map", "second", "WMS", definitions[:1])
        with patch.object(
            loader, "_add_map_layer", side_effect=[True, False, True]
        ) as add:
            results = loader.add_services(
                {"first": ["roads", "buildings"], "second": ["roads"]}
            )
        self.assertEqual(
            results,
            {
                ("first", "roads"): True,
                ("first", "buildings"): False,
                ("second", "roads"): True,
            },
        )
        self.assertEqual(add.call_count, 3)
        self.assertEqual(loader.downloaded_layers, [])

    def test_invalid_provider_counts_as_failed_selected_layer(self):
        loader = AddOGCService()
        definitions = [
            LayerDefinition("uri", key, "wms", "raster", key, key)
            for key in ("invalid", "valid")
        ]
        invalid, valid = MagicMock(), MagicMock()
        invalid.isValid.return_value = False
        valid.isValid.return_value = True
        with patch.object(
            loader,
            "_create_qgs_layer",
            side_effect=[(invalid, False), (valid, False)],
        ):
            self.assertTrue(
                loader.create_layers("Map", "url", "WMS", definitions)
            )
        with patch.object(add_service, "QgsProject") as project:
            results = loader.add_services({"url": ["invalid", "valid"]})
        self.assertEqual(
            results, {("url", "invalid"): False, ("url", "valid"): True}
        )
        project.instance.return_value.addMapLayer.assert_called_once_with(
            valid
        )

    def test_malformed_wcs_document_is_reported(self):
        with patch.object(
            add_service.ServiceAPI,
            "get_request",
            return_value=(True, "not xml"),
        ):
            with patch.object(add_service.MessageUtils, "log_warning") as log:
                service = LegacyWebCoverageService("https://example.com")
        self.assertEqual(service.contents, [])
        log.assert_called_once()
