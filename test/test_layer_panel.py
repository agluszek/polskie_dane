import unittest
from threading import Event
from unittest.mock import patch

from qgis.PyQt.QtCore import Qt, QThread

from ..core.qt_compat import QtCompat
from ..gui.dialog import (
    PolskieDaneDialog,
)
from ..services.add_service import LayerDefinition
from .utilities import get_qgis_app, wait_until

get_qgis_app()
FETCH_PATH = (
    f"{PolskieDaneDialog.__module__.rsplit('.', 1)[0]}.layer_panel."
    "AddOGCService.fetch_definitions"
)


def definitions(*titles):
    return [
        LayerDefinition("uri", title, "wms", "raster", title, title)
        for title in titles
    ]


class LayerPanelTest(unittest.TestCase):
    def setUp(self):
        self.dialog = PolskieDaneDialog()
        self.panel = self.dialog.layer_panel
        self.panel.start()

    def tearDown(self):
        self.panel.stop()
        wait_until(lambda: not self.panel.task.is_running())
        self.dialog.close()

    def wait(self):
        wait_until(
            lambda: (
                not self.panel.timer.isActive()
                and not self.panel.task.is_running()
            )
        )

    def test_inline_selection_groups_services_and_fetches_in_worker(self):
        threads = []

        def fetch(name, url, kind):
            threads.append(QThread.currentThread())
            return definitions("Drogi", "Budynki")

        with patch(FETCH_PATH, side_effect=fetch):
            self.panel.set_services({"a": "Mapa A", "b": "Mapa B"}, "WMS")
            self.wait()
        self.assertFalse(self.panel.view.isHidden())
        self.assertEqual(self.panel.tree.topLevelItemCount(), 2)
        self.assertEqual(self.panel.selected_definitions(), {})
        self.assertTrue(
            all(thread != self.panel.thread() for thread in threads)
        )
        self.panel.search.setText("drogi")
        self.panel.select_all.click()
        selected = self.panel.selected_definitions()
        self.assertEqual(set(selected), {"a", "b"})
        self.assertTrue(
            all(
                [item.layer_id for item in value[1]] == ["Drogi"]
                for value in selected.values()
            )
        )

    def test_service_change_discards_pending_layers(self):
        started, release = Event(), Event()

        def fetch(name, url, kind):
            if url == "a":
                started.set()
                release.wait(2)
            return definitions(url)

        with patch(FETCH_PATH, side_effect=fetch):
            try:
                self.panel.set_services({"a": "Mapa A"}, "WMS")
                wait_until(started.is_set)
                self.panel.set_services({"b": "Mapa B"}, "WMS")
                release.set()
                self.wait()
                self.assertEqual(set(self.panel.selected_definitions()), {"b"})
            finally:
                release.set()

    def test_cancel_discards_results_and_retry_does_not_duplicate_rows(self):
        started, release = Event(), Event()

        def fetch(*args):
            started.set()
            release.wait(2)
            return definitions("Drogi")

        with patch(FETCH_PATH, side_effect=fetch):
            try:
                self.panel.set_services({"a": "Mapa"}, "WMS")
                wait_until(started.is_set)
                self.panel.cancel_btn.click()
                release.set()
                self.wait()
                self.assertEqual(self.panel.selected_definitions(), {})
                self.assertIn("anulowane", self.panel.status.text())
                self.panel.retry_btn.click()
                self.wait()
                self.assertEqual(self.panel.tree.topLevelItemCount(), 1)
            finally:
                release.set()

    def test_metadata_error_is_visible_and_can_be_retried(self):
        with patch(FETCH_PATH, side_effect=ValueError("Błąd SSL usługi")):
            self.panel.set_services({"a": "Ortofotomapa"}, "WMS")
            self.wait()
        self.assertTrue(self.panel.view.isHidden())
        self.assertIn("Błąd SSL", self.panel.status.text())
        self.assertFalse(self.panel.retry_btn.isHidden())
        self.assertEqual(self.panel.selected_definitions(), {})
        with patch(FETCH_PATH, return_value=definitions("Raster")):
            self.panel.retry_btn.click()
            self.wait()
        self.assertEqual(
            self.panel.selected_definitions()["a"][1][0].layer_id, "Raster"
        )

    def test_close_discards_pending_results(self):
        started, release = Event(), Event()

        def fetch(*args):
            started.set()
            release.wait(2)
            return definitions("Drogi")

        with patch(FETCH_PATH, side_effect=fetch):
            try:
                self.panel.set_services({"a": "Mapa"}, "WMS")
                wait_until(started.is_set)
                self.panel.stop()
                release.set()
                self.wait()
                self.assertEqual(self.panel.selected_definitions(), {})
            finally:
                release.set()

    def test_hidden_selections_are_preserved_when_search_changes(self):
        with patch(FETCH_PATH, return_value=definitions("Drogi", "Budynki")):
            self.panel.set_services({"a": "Mapa"}, "WMS")
            self.wait()
        self.panel.tree.topLevelItem(0).child(1).setCheckState(
            0, QtCompat.get_enum(Qt, "CheckState", "Checked")
        )
        self.panel.search.setText("drogi")
        self.panel.select_all.click()
        self.assertEqual(len(self.panel.selected_definitions()["a"][1]), 2)
