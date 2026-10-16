import json
import unittest
from unittest.mock import MagicMock

from ..services.registry_metadata import (
    REGISTRY_API_URL,
    RegistryMetadataFetcher,
)


class RegistryMetadataTest(unittest.TestCase):
    def setUp(self):
        self.network = MagicMock()
        self.fetcher = RegistryMetadataFetcher(self.network)

    def respond(self, datasets):
        self.fetcher.invalidate("PL")
        self.fetcher.invalidate("0201")
        self.network.fetch_content.return_value = (
            True,
            json.dumps({"data": datasets}),
        )

    def dataset(self, identifier="PL.PZGiK.203", services=None):
        return {
            "idiip": identifier,
            "zbior": "Ortofotomapa",
            "organ": "Główny Geodeta Kraju",
            "uslugi": services
            or {"przegladania": ["WMS=https://example.com/wms"]},
        }

    def test_catalog_uses_registry_metadata_and_territory(self):
        self.respond([self.dataset()])
        rows = self.fetcher.fetch_services("0201", "wms")
        self.assertEqual(
            rows,
            [
                {
                    "dataset_name": "Ortofotomapa",
                    "service_type": "WMS",
                    "url": "https://example.com/wms",
                    "dataset_identifier": "PL.PZGiK.203",
                    "reporting_authority": "Główny Geodeta Kraju",
                }
            ],
        )
        call = self.network.fetch_content.call_args
        self.assertEqual(call.args[0], REGISTRY_API_URL)
        self.assertEqual(call.kwargs["params"]["teryt"], "0201")

    def test_duplicate_endpoints_keep_distinct_datasets(self):
        services = {
            "przegladania": [
                "WMS=https://example.com/wms",
                "WMS=https://example.com/wms?service=WMS",
            ],
            "pobierania": ["https://example.com/wms"],
        }
        self.respond(
            [
                self.dataset(services=services),
                self.dataset("PL.PZGiK.204", services),
            ]
        )
        rows = self.fetcher.fetch_services("PL", "WMS")
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            {row["dataset_identifier"] for row in rows},
            {"PL.PZGiK.203", "PL.PZGiK.204"},
        )

    def test_bare_urls_queries_and_unsupported_downloads(self):
        for address, category, expected in (
            ("https://example.com/wmse.php", "przegladania", "WMS"),
            ("https://example.com/wfs.php", "pobierania", "WFS"),
            (
                "https://example.com/maps?SERVICE=WCS&map=A",
                "pobierania",
                "WCS",
            ),
            ("https://example.com/maps", "przegladania", "WMS"),
            ("https://example.com/ATOM/feed", "pobierania", None),
            ("ATOM=https://example.com/feed", "pobierania", None),
            ("https://example.com/data.zip", "pobierania", None),
            ("https://example.com/feed", "pobierania", None),
            ("https://example.com/data.gml", "pobierania", None),
            ("https://example.com/atom.xml", "pobierania", None),
            ("https://example.com/ows", "pobierania", "WFS"),
            ("https://example.com/ows.php", "pobierania", "WFS"),
            ("ftp://example.com/wms", "przegladania", None),
            ("https://example.com/maps?service=ATOM", "przegladania", None),
        ):
            with self.subTest(address=address):
                parsed = self.fetcher.parse_service(address, category)
                if expected is None:
                    self.assertIsNone(parsed)
                else:
                    self.assertEqual(parsed, (expected, address))

    def test_siemiatycze_bare_endpoint_is_listed_for_both_protocols(self):
        url = "https://geoportal.siemiatycze.pl/siemiatycze-egib"
        dataset = {
            "idiip": "PL.PZGiK.360",
            "zbior": "Ewidencja Gruntów i Budynków (EGiB)",
            "organ": "Starosta Powiatu Siemiatyckiego",
            "uslugi": {"przegladania": [url], "pobierania": [url]},
        }
        self.respond([dataset])
        for protocol in ("WMS", "WFS"):
            with self.subTest(protocol=protocol):
                rows = self.fetcher.fetch_services("2010", protocol)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["url"], url)
                self.assertEqual(rows[0]["service_type"], protocol)
                self.assertEqual(rows[0]["dataset_identifier"], "PL.PZGiK.360")
        self.network.fetch_content.assert_called_once()

    def test_empty_catalog_is_success_and_failures_are_reported(self):
        self.respond([])
        self.assertEqual(self.fetcher.fetch_services("PL", "WMS"), [])
        self.fetcher.invalidate("PL")
        self.network.fetch_content.return_value = (False, "Błąd HTTP: 503")
        with self.assertRaisesRegex(ValueError, "503"):
            self.fetcher.fetch_services("PL", "WMS")
        for payload in ("<html>Error</html>", "[]", '{"data": {}}'):
            self.network.fetch_content.return_value = (True, payload)
            with self.assertRaises(ValueError):
                self.fetcher.fetch_services("PL", "WMS")

    def test_malformed_urls_do_not_hide_valid_services(self):
        for invalid_url in (
            "https://[broken/wms",
            "https://[not-an-ip]/wms",
        ):
            with self.subTest(url=invalid_url):
                self.assertIsNone(self.fetcher.service_key(invalid_url))
                self.respond(
                    [
                        self.dataset(
                            services={
                                "przegladania": [
                                    invalid_url,
                                    f"WMS={invalid_url}",
                                    "WMS=https://example.com/wms",
                                ]
                            }
                        )
                    ]
                )
                rows = self.fetcher.fetch_services("PL", "WMS")
                self.assertEqual(
                    [row["url"] for row in rows], ["https://example.com/wms"]
                )

    def test_invalid_addresses_and_protocol_are_reported(self):
        for addresses in ("url", [None]):
            self.respond([self.dataset(services={"przegladania": addresses})])
            with self.assertRaises(ValueError):
                self.fetcher.fetch_services("PL", "WMS")

    def test_whole_country_pagination_fetches_every_page(self):
        first = [self.dataset(f"PL.PZGiK.{index}") for index in range(1000)]
        self.network.fetch_content.side_effect = [
            (True, json.dumps({"data": first})),
            (True, json.dumps({"data": [self.dataset()]})),
        ]
        self.assertEqual(len(self.fetcher.fetch_datasets("PL")), 1001)
        calls = self.network.fetch_content.call_args_list
        self.assertEqual(calls[0].kwargs["params"]["teryt"], "")
        self.assertEqual(calls[1].kwargs["params"]["index"], 1000)

    def test_types_share_dataset_cache_and_refresh_invalidates_it(self):
        self.respond(
            [
                self.dataset(
                    services={
                        "przegladania": ["WMS=https://example.com/wms"],
                        "pobierania": ["https://example.com/wfs"],
                    }
                )
            ]
        )
        self.assertEqual(len(self.fetcher.fetch_services("PL", "WMS")), 1)
        self.assertEqual(len(self.fetcher.fetch_services("PL", "WFS")), 1)
        self.network.fetch_content.assert_called_once()
        self.fetcher.invalidate("PL")
        self.fetcher.fetch_services("PL", "WMS")
        self.assertEqual(self.network.fetch_content.call_count, 2)

    def test_failed_pages_do_not_cache_partial_catalog(self):
        first = [self.dataset(f"PL.PZGiK.{index}") for index in range(1000)]
        self.network.fetch_content.side_effect = [
            (True, json.dumps({"data": first})),
            (False, "HTTP 503"),
            (True, json.dumps({"data": [self.dataset()]})),
        ]
        with self.assertRaisesRegex(ValueError, "503"):
            self.fetcher.fetch_datasets("PL")
        self.assertEqual(len(self.fetcher.fetch_datasets("PL")), 1)
        self.assertEqual(
            self.network.fetch_content.call_args.kwargs["params"]["index"], 0
        )

    def test_repeated_page_is_reported(self):
        first = [self.dataset(f"PL.PZGiK.{index}") for index in range(1000)]
        self.respond(first)
        with self.assertRaisesRegex(ValueError, "powtórzoną"):
            self.fetcher.fetch_datasets("PL")
