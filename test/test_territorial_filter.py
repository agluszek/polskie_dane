import unittest
from threading import Event
from unittest.mock import MagicMock, patch

from qgis.PyQt.QtCore import QThread

from ..gui.dialog import (
    PolskieDaneDialog,
)
from ..services.administrative_units import AdministrativeUnitsFetcher
from .utilities import get_qgis_app, wait_until

QGIS_APP = get_qgis_app()
FETCH_PATH = (
    f"{PolskieDaneDialog.__module__.rsplit('.', 1)[0]}.territorial_selector."
    "AdministrativeUnitsFetcher.fetch_units"
)
UNIT_ROWS = {
    (0, ""): [
        {"teryt": "02", "name": "dolnośląskie"},
        {"teryt": "04", "name": "kujawsko-pomorskie"},
    ],
    (1, "02"): [{"teryt": "0201", "name": "powiat bolesławiecki"}],
    (1, "04"): [{"teryt": "0401", "name": "powiat aleksandrowski"}],
    (2, "0201"): [{"teryt": "020101_1", "name": "Bolesławiec (miasto)"}],
}


class AdministrativeUnitsTest(unittest.TestCase):
    def test_fetches_only_children_and_preserves_teryt(self):
        network = MagicMock()
        fetcher = AdministrativeUnitsFetcher(network)
        for request, rows in UNIT_ROWS.items():
            with self.subTest(request=request):
                network.fetch_content.return_value = (
                    True,
                    "0\n"
                    + "\n".join(
                        f"{row['name']}|{row['teryt']}" for row in rows
                    ),
                )
                self.assertEqual(fetcher.fetch_units(*request), rows)
                level, parent = request
                unit_type = ("wojewodztwo", "powiat", "gmina")[level]
                call = network.fetch_content.call_args
                self.assertEqual(
                    call.args[0], "https://uldk.gugik.gov.pl/service.php"
                )
                expected = {
                    "obiekt": unit_type,
                    "wynik": f"{unit_type},teryt",
                }
                if level:
                    expected["teryt"] = parent
                self.assertEqual(call.kwargs["params"], expected)

    def test_rejects_wrong_parent_before_network_request(self):
        network = MagicMock()
        fetcher = AdministrativeUnitsFetcher(network)
        for request in ((1, ""), (1, "0201"), (2, "02"), (3, "0201")):
            with self.subTest(request=request), self.assertRaises(ValueError):
                fetcher.fetch_units(*request)
        network.fetch_content.assert_not_called()

    def test_rejects_malformed_and_foreign_units(self):
        network = MagicMock()
        fetcher = AdministrativeUnitsFetcher(network)
        for payload in (
            "",
            "<html>Error</html>",
            "-1\nBrak wyników",
            "0\nCounty",
            "0\nOther county|0401",
            "0\nCounty|201",
            "0\n|0201",
            "0\nCounty|0201|extra",
        ):
            network.fetch_content.return_value = (True, payload)
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                fetcher.fetch_units(1, "02")

    def test_sorts_deduplicates_and_accepts_bom_and_crlf(self):
        network = MagicMock()
        network.fetch_content.return_value = (
            True,
            "\ufeff0\r\nZeta|0202\r\n\r\nAlfa|0201\r\nAlfa|0201\r\n",
        )
        self.assertEqual(
            AdministrativeUnitsFetcher(network).fetch_units(1, "02"),
            [
                {"teryt": "0201", "name": "Alfa"},
                {"teryt": "0202", "name": "Zeta"},
            ],
        )

    def test_transport_error_is_distinct_from_empty_list(self):
        network = MagicMock()
        fetcher = AdministrativeUnitsFetcher(network)
        network.fetch_content.return_value = (False, "Błąd HTTP: 503")
        with self.assertRaisesRegex(ValueError, "503"):
            fetcher.fetch_units(0)
        network.fetch_content.return_value = (True, "0\n")
        self.assertEqual(fetcher.fetch_units(0), [])


class TerritorialSelectorTest(unittest.TestCase):
    def setUp(self):
        self.dialog = PolskieDaneDialog()
        self.selector = self.dialog.territorial_selector
        self.worker_threads = []
        self.fetch_patch = patch(FETCH_PATH, side_effect=self.fetch)
        self.fetch_mock = self.fetch_patch.start()

    def tearDown(self):
        self.selector.stop()
        wait_until(lambda: not self.selector.task.is_running())
        self.fetch_patch.stop()
        self.dialog.close()

    def fetch(self, level, parent):
        self.worker_threads.append(QThread.currentThread())
        return UNIT_ROWS.get((level, parent), [])

    def wait(self):
        wait_until(lambda: not self.selector.task.is_running())

    def test_cascade_runs_in_worker_and_reuses_parent_cache(self):
        selector = self.selector
        changes = []
        selector.area_changed.connect(changes.append)
        selector.start()
        self.wait()
        self.fetch_mock.assert_called_once_with(0, "")
        self.assertFalse(selector.combos[1].isEnabled())
        selector.combos[0].setCurrentIndex(1)
        self.wait()
        self.assertEqual(selector.selected_teryt(), "02")
        selector.combos[1].setCurrentIndex(1)
        self.wait()
        selector.combos[2].setCurrentIndex(1)
        self.assertEqual(selector.selected_teryt(), "020101_1")
        self.assertEqual(changes, ["02", "0201", "020101_1"])
        selector.combos[0].setCurrentIndex(0)
        self.assertEqual(selector.selected_teryt(), "PL")
        self.assertEqual(selector.combos[1].count(), 1)
        self.assertEqual(selector.combos[2].count(), 1)
        self.assertFalse(selector.combos[2].isEnabled())
        selector.combos[0].setCurrentIndex(1)
        self.assertEqual(selector.combos[1].count(), 2)
        self.assertEqual(self.fetch_mock.call_count, 3)
        self.assertTrue(
            all(thread != selector.thread() for thread in self.worker_threads)
        )

    def test_parent_change_discards_stale_counties(self):
        selector = self.selector
        selector.start()
        self.wait()
        started, release = Event(), Event()

        def delayed(level, parent):
            if parent == "02":
                started.set()
                release.wait(2)
            return self.fetch(level, parent)

        with patch(FETCH_PATH, side_effect=delayed):
            try:
                selector.combos[0].setCurrentIndex(1)
                wait_until(started.is_set)
                selector.combos[0].setCurrentIndex(2)
                self.assertEqual(selector.combos[1].count(), 1)
                release.set()
                self.wait()
                self.assertEqual(selector.combos[1].itemData(1), "0401")
                self.assertEqual(selector.selected_teryt(), "04")
            finally:
                release.set()

    def test_failure_can_be_retried_without_changing_parent(self):
        selector = self.selector
        with patch(FETCH_PATH, side_effect=ValueError("Błąd HTTP: 503")):
            selector.start()
            self.wait()
        self.assertIn("503", selector.retry_btn.toolTip())
        self.assertFalse(selector.retry_btn.isHidden())
        selector.retry_btn.click()
        self.wait()
        self.assertEqual(selector.combos[0].count(), 3)
        self.assertTrue(selector.retry_btn.isHidden())

    def test_close_discards_pending_units_and_reopen_fetches_again(self):
        selector = self.selector
        started, release = Event(), Event()

        def delayed(level, parent):
            started.set()
            release.wait(2)
            return self.fetch(level, parent)

        with patch(FETCH_PATH, side_effect=delayed):
            try:
                selector.start()
                wait_until(started.is_set)
                selector.stop()
                release.set()
                self.wait()
                self.assertEqual(selector.combos[0].count(), 1)
                selector.start()
                self.wait()
                self.assertEqual(selector.combos[0].count(), 3)
            finally:
                release.set()
