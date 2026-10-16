import unittest
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import patch

from qgis.PyQt.QtCore import (
    QEvent,
    QPoint,
    QSettings,
    Qt,
    QThread,
)
from qgis.PyQt.QtGui import QColor, QPalette
from qgis.PyQt.QtTest import QTest

from .. import PLUGIN_NAME, classFactory
from ..core.qt_compat import QtCompat
from ..gui.dialog import PolskieDaneDialog
from ..services.add_service import LayerDefinition
from .qgis_interface import QgisInterface
from .utilities import get_qgis_app, wait_until

QGIS_APP, CANVAS, PARENT, _ = get_qgis_app()
GUI_PACKAGE = PolskieDaneDialog.__module__.rsplit(".", 1)[0]


class PluginTest(unittest.TestCase):
    def setUp(self):
        self.settings_dir = TemporaryDirectory()
        self.addCleanup(self.settings_dir.cleanup)
        self.settings = QSettings(
            f"{self.settings_dir.name}/settings.ini",
            QtCompat.get_enum(QSettings, "Format", "IniFormat"),
        )
        settings_patch = patch(
            f"{GUI_PACKAGE}.dialog.QgsSettings", return_value=self.settings
        )
        settings_patch.start()
        self.addCleanup(settings_patch.stop)
        self.iface = QgisInterface(CANVAS)
        self.plugin = classFactory(self.iface)
        self.plugin.initGui()
        self.units_patch = patch(
            f"{GUI_PACKAGE}.territorial_selector."
            "AdministrativeUnitsFetcher.fetch_units",
            return_value=[],
        )
        self.units_patch.start()

    def tearDown(self):
        self.plugin.unload()
        self.plugin.dlg.close()
        wait_until(
            lambda: (
                not self.plugin.dlg.territorial_selector.task.is_running()
                and not self.plugin.dlg.layer_panel.task.is_running()
            )
        )
        self.units_patch.stop()
        self.iface.window.close()

    def test_refresh_invalidates_all_types_only_in_selected_area(self):
        dialog = self.plugin.dlg
        manager = dialog.content_manager
        manager.cache_services("WMS", [])
        manager.cache_services("WFS", [])
        manager.cache_services("WMS", [], "02")
        with patch.object(dialog, "setup_table") as setup:
            dialog.refresh_btn.click()
        self.assertFalse(manager.has_cached_services("WMS"))
        self.assertFalse(manager.has_cached_services("WFS"))
        self.assertTrue(manager.has_cached_services("WMS", "02"))
        setup.assert_called_once()

    def test_second_click_clears_row_and_next_click_selects_it(self):
        dialog = self.plugin.dlg
        definitions = [
            LayerDefinition("uri", "Mapa", "wms", "raster", "map", "Mapa")
        ]
        with (
            patch.object(dialog, "setup_table"),
            patch.object(dialog.territorial_selector, "start"),
            patch(
                f"{GUI_PACKAGE}.layer_panel.AddOGCService.fetch_definitions",
                return_value=definitions,
            ),
        ):
            dialog.show()
            dialog.fill_services_table(
                [
                    {"dataset_name": "Alpha", "url": "a"},
                    {"dataset_name": "Beta", "url": "b"},
                ]
            )
            QGIS_APP.processEvents()
            viewport = dialog.services_table.viewport()
            left = QtCompat.get_enum(Qt, "MouseButton", "LeftButton")
            first = dialog.services_table.visualRect(
                dialog.proxy_model.index(0, 0)
            ).center()
            other_column = dialog.services_table.visualRect(
                dialog.proxy_model.index(0, 1)
            ).center()
            QTest.mouseClick(viewport, left, pos=first)
            wait_until(lambda: bool(dialog.layer_panel._definitions))
            self.assertTrue(dialog.add_btn.isEnabled())
            self.assertTrue(dialog.layer_panel.view.isHidden())
            self.assertFalse(dialog.layer_state.isHidden())
            QTest.mouseClick(viewport, left, pos=other_column)
            self.assertFalse(
                dialog.services_table.selectionModel().hasSelection()
            )
            self.assertEqual(dialog.layer_panel.selected_definitions(), {})
            self.assertTrue(dialog.layer_panel.view.isHidden())
            self.assertTrue(dialog.layer_state.isHidden())
            self.assertFalse(dialog.add_btn.isEnabled())
            QTest.mouseClick(viewport, left, pos=first)
            self.assertEqual(
                len(dialog.services_table.selectionModel().selectedRows()), 1
            )
            second = dialog.services_table.visualRect(
                dialog.proxy_model.index(1, 0)
            ).center()
            QTest.mouseClick(viewport, left, pos=second)
            self.assertEqual(
                dialog.services_table.selectionModel().selectedRows()[0].row(),
                1,
            )
            QTest.mouseDClick(viewport, left, pos=second)
            self.assertFalse(
                dialog.services_table.selectionModel().hasSelection()
            )

    def test_escape_clears_selection_without_closing_dialog(self):
        dialog = self.plugin.dlg
        with (
            patch.object(dialog, "setup_table"),
            patch.object(dialog.territorial_selector, "start"),
        ):
            dialog.show()
            dialog.fill_services_table(
                [
                    {"dataset_name": "Alpha", "url": "a"},
                ]
            )
            dialog.services_table.selectRow(0)
            QTest.keyClick(
                dialog.services_table,
                QtCompat.get_enum(Qt, "Key", "Key_Escape"),
            )
            self.assertFalse(
                dialog.services_table.selectionModel().hasSelection()
            )
            self.assertTrue(dialog.isVisible())
            self.assertTrue(dialog.layer_state.isHidden())
            self.assertFalse(dialog.add_btn.isEnabled())

    def test_second_click_cancels_pending_layer_check(self):
        dialog = self.plugin.dlg
        started = Event()
        release = Event()

        def fetch(name, url, service_type):
            started.set()
            release.wait(2)
            return [LayerDefinition("uri", name, "wms", "raster", "map", name)]

        with (
            patch.object(dialog, "setup_table"),
            patch.object(dialog.territorial_selector, "start"),
            patch(
                f"{GUI_PACKAGE}.layer_panel.AddOGCService.fetch_definitions",
                side_effect=fetch,
            ),
        ):
            try:
                dialog.show()
                dialog.fill_services_table(
                    [
                        {"dataset_name": "Alpha", "url": "a"},
                    ]
                )
                QGIS_APP.processEvents()
                position = dialog.services_table.visualRect(
                    dialog.proxy_model.index(0, 0)
                ).center()
                viewport = dialog.services_table.viewport()
                left = QtCompat.get_enum(Qt, "MouseButton", "LeftButton")
                QTest.mouseClick(viewport, left, pos=position)
                wait_until(started.is_set)
                QTest.mouseClick(viewport, left, pos=position)
                self.assertTrue(
                    dialog.layer_panel.task.task_instance.isCanceled()
                )
                release.set()
                wait_until(lambda: not dialog.layer_panel.task.is_running())
                self.assertEqual(dialog.layer_panel.selected_definitions(), {})
                self.assertTrue(dialog.layer_panel.view.isHidden())
                self.assertFalse(dialog.add_btn.isEnabled())
            finally:
                release.set()

    def test_territorial_selection_filters_catalog_and_preserves_cache(self):
        dialog = self.plugin.dlg
        selector = dialog.territorial_selector
        provinces = [{"teryt": "02", "name": "dolnośląskie"}]
        counties = [{"teryt": "0201", "name": "powiat bolesławiecki"}]
        communes = [{"teryt": "020101_1", "name": "Bolesławiec"}]

        def units(level, parent):
            return (provinces, counties, communes)[level]

        def services(teryt, service_type):
            return [{"dataset_name": teryt, "url": "url"}]

        def wait_for_requests():
            wait_until(
                lambda: (
                    not selector.task.is_running()
                    and not dialog.table_setup_task.is_running()
                )
            )

        with (
            patch(
                f"{GUI_PACKAGE}.territorial_selector."
                "AdministrativeUnitsFetcher.fetch_units",
                side_effect=units,
            ),
            patch.object(
                dialog.content_manager.registry,
                "fetch_services",
                side_effect=services,
            ) as fetch,
        ):
            dialog.show()
            wait_for_requests()
            for level, teryt in enumerate(("02", "0201", "020101_1")):
                selector.combos[level].setCurrentIndex(1)
                wait_for_requests()
                self.assertEqual(dialog.model.index(0, 0).data(), teryt)
                self.assertEqual(fetch.call_args.args, (teryt, "WMS"))
            selector.combos[0].setCurrentIndex(0)
            self.assertEqual(dialog.model.index(0, 0).data(), "PL")
            self.assertEqual(fetch.call_count, 4)
            dialog.refresh_btn.click()
            wait_for_requests()
            self.assertEqual(fetch.call_count, 5)
            self.assertTrue(
                dialog.content_manager.has_cached_services("WMS", "020101_1")
            )

    def test_territory_change_discards_pending_catalog(self):
        dialog = self.plugin.dlg
        selector = dialog.territorial_selector
        started, release = Event(), Event()

        def services(service_type, teryt):
            if teryt == "PL":
                started.set()
                release.wait(2)
            return [{"dataset_name": teryt, "url": "url"}]

        with patch.object(
            dialog.content_manager, "fetch_services", side_effect=services
        ):
            try:
                dialog.show()
                wait_until(started.is_set)
                wait_until(lambda: not selector.task.is_running())
                selector.combos[0].addItem("dolnośląskie (02)", "02")
                selector.combos[0].setCurrentIndex(1)
                release.set()
                wait_until(lambda: not dialog.table_setup_task.is_running())
                self.assertEqual(dialog.model.index(0, 0).data(), "02")
                self.assertFalse(
                    dialog.content_manager.has_cached_services("WMS", "PL")
                )
            finally:
                release.set()

    def test_cached_empty_catalog_keeps_add_disabled(self):
        dialog = self.plugin.dlg
        dialog.is_window_shown = True
        dialog.content_manager.cache_services("WMS", [])
        with patch.object(dialog.content_manager, "fetch_services") as fetch:
            dialog.setup_table()
        fetch.assert_not_called()
        self.assertFalse(dialog.add_btn.isEnabled())
        self.assertEqual(dialog.model.index(0, 1).data(), "Pusty katalog")

    def test_catalog_loads_in_worker_and_reuses_cache_by_type(self):
        dialog = self.plugin.dlg
        worker_threads = []
        selected_service_type = dialog.get_selected_service_type

        def service_type_on_gui_thread():
            self.assertEqual(QThread.currentThread(), dialog.thread())
            return selected_service_type()

        def fetch(service_type, teryt):
            worker_threads.append(QThread.currentThread())
            return [
                {
                    "dataset_name": service_type,
                    "url": "url",
                    "service_type": service_type,
                }
            ]

        with (
            patch.object(
                dialog,
                "get_selected_service_type",
                side_effect=service_type_on_gui_thread,
            ),
            patch.object(
                dialog.content_manager, "fetch_services", side_effect=fetch
            ) as request,
        ):
            dialog.show()
            wait_until(lambda: not dialog.table_setup_task.is_running())
            self.assertEqual(dialog.model.index(0, 0).data(), "WMS")
            dialog.wfs_rdbtn.setChecked(True)
            wait_until(lambda: not dialog.table_setup_task.is_running())
            self.assertEqual(dialog.model.index(0, 0).data(), "WFS")
            dialog.wms_rdbtn.setChecked(True)
            self.assertEqual(dialog.model.index(0, 0).data(), "WMS")
        self.assertEqual(request.call_count, 2)
        self.assertTrue(
            all(thread != dialog.thread() for thread in worker_threads)
        )

    def test_closing_dialog_discards_pending_catalog_result(self):
        dialog = self.plugin.dlg
        started = Event()
        release = Event()
        rows = [{"dataset_name": "WMS", "url": "url", "service_type": "WMS"}]

        def fetch(service_type, teryt):
            started.set()
            release.wait(2)
            return rows

        with patch.object(
            dialog.content_manager, "fetch_services", side_effect=fetch
        ) as request:
            try:
                dialog.show()
                wait_until(started.is_set)
                dialog.close()
                release.set()
                wait_until(lambda: not dialog.table_setup_task.is_running())
                self.assertFalse(
                    dialog.content_manager.has_cached_services("WMS")
                )
                dialog.show()
                wait_until(lambda: not dialog.table_setup_task.is_running())
                self.assertEqual(dialog.model.index(0, 0).data(), "WMS")
            finally:
                release.set()
        self.assertEqual(request.call_count, 2)

    def test_status_rows_are_visible_with_active_search_and_cannot_be_selected(
        self,
    ):
        dialog = self.plugin.dlg
        dialog.search_lineedit.setText("roads")
        dialog.push_message_over_table("Pobieranie...", "Pobieranie")
        self.assertEqual(dialog.proxy_model.rowCount(), 1)
        dialog.services_table.selectAll()
        self.assertEqual(
            dialog.services_table.selectionModel().selectedRows(), []
        )
        self.assertFalse(dialog.add_btn.isEnabled())

    def test_metadata_columns_support_sorting_and_name_search(self):
        dialog = self.plugin.dlg
        dialog.fill_services_table(
            [
                {
                    "dataset_name": "Plan miasta",
                    "url": "a",
                    "dataset_identifier": "PL.PZGiK.12072",
                    "reporting_authority": "Starosta Powiatu Kazimierskiego",
                },
                {
                    "dataset_name": "Plan gminy",
                    "url": "b",
                    "reporting_authority": "Prezydent Miasta Gdańska",
                },
            ]
        )
        self.assertEqual(dialog.model.columnCount(), 4)
        self.assertEqual(dialog.model.index(0, 2).data(), "PL.PZGiK.12072")
        self.assertEqual(dialog.model.index(1, 2).data(), "—")
        for column in range(dialog.model.columnCount()):
            self.assertFalse(dialog.model.item(0, column).isEditable())
        dialog.services_table.sortByColumn(
            3, QtCompat.get_enum(Qt, "SortOrder", "AscendingOrder")
        )
        self.assertEqual(dialog.proxy_model.index(0, 1).data(), "b")
        dialog.search_lineedit.setText("MIASTA")
        self.assertEqual(dialog.proxy_model.rowCount(), 1)
        self.assertEqual(dialog.proxy_model.index(0, 1).data(), "a")
        dialog.push_message_over_table("Błąd", "Brak połączenia")
        self.assertEqual(dialog.proxy_model.rowCount(), 1)
        self.assertEqual(dialog.model.columnCount(), 2)
        dialog.fill_services_table([{"dataset_name": "Plan", "url": "d"}])
        self.assertEqual(dialog.model.columnCount(), 4)

    def test_column_drag_measures_only_visible_names(self):
        dialog = self.plugin.dlg
        table = dialog.services_table
        with (
            patch.object(dialog, "setup_table"),
            patch.object(dialog.territorial_selector, "start"),
        ):
            try:
                dialog.show()
                dialog.fill_services_table(
                    [{"dataset_name": "Długi opis zbioru " * 10}] * 2000
                )
                wait_until(lambda: not dialog._row_resize_timer.isActive())
                with (
                    patch.object(table, "resizeRowsToContents") as full_resize,
                    patch.object(
                        table, "setRowHeight", wraps=table.setRowHeight
                    ) as resize,
                ):
                    header = table.horizontalHeader()
                    handle = QPoint(header.sectionSize(0) - 1, 10)
                    left = QtCompat.get_enum(Qt, "MouseButton", "LeftButton")
                    QTest.mousePress(header.viewport(), left, pos=handle)
                    for width in range(200, 400, 5):
                        table.setColumnWidth(0, width)
                        QGIS_APP.processEvents()
                    QTest.qWait(200)
                    resize.assert_not_called()
                    QTest.mouseRelease(header.viewport(), left, pos=handle)
                    wait_until(lambda: not dialog._row_resize_timer.isActive())
                    full_resize.assert_not_called()
                    self.assertGreater(resize.call_count, 0)
                    self.assertLess(resize.call_count, 100)
                    resize.reset_mock()
                    table.setColumnWidth(1, 300)
                    table.setColumnWidth(2, 300)
                    QGIS_APP.processEvents()
                    self.assertFalse(dialog._row_resize_timer.isActive())
                    resize.assert_not_called()
            finally:
                dialog.close()

    def test_column_widths_survive_refresh_status_and_plugin_restart(self):
        dialog = self.plugin.dlg
        table = dialog.services_table
        widths = [345, 275, 265, 310]
        for column, width in enumerate(widths):
            table.setColumnWidth(column, width)
        dialog.fill_services_table([{"dataset_name": "Plan", "url": "url"}])
        self.assertEqual([table.columnWidth(c) for c in range(4)], widths)
        dialog.push_message_over_table("Błąd połączenia", "Błąd katalogu")
        dialog.push_message_over_table("Ponowna próba", "Pobieranie")
        dialog.fill_services_table([{"dataset_name": "Plan"}])
        self.assertEqual([table.columnWidth(c) for c in range(4)], widths)
        dialog.push_message_over_table("Brak odpowiedzi", "Błąd katalogu")
        dialog.close()
        self.settings.sync()
        fresh_settings = QSettings(
            self.settings.fileName(),
            QtCompat.get_enum(QSettings, "Format", "IniFormat"),
        )
        with patch(
            f"{GUI_PACKAGE}.dialog.QgsSettings", return_value=fresh_settings
        ):
            reopened = PolskieDaneDialog()
        try:
            self.assertEqual(
                [reopened.services_table.columnWidth(c) for c in range(4)],
                widths,
            )
        finally:
            reopened.close()
            reopened.deleteLater()

    def test_long_names_and_messages_wrap_when_column_is_narrowed(self):
        dialog = self.plugin.dlg
        with (
            patch.object(dialog, "setup_table"),
            patch.object(dialog.territorial_selector, "start"),
        ):
            try:
                dialog.show()
                dialog.fill_services_table(
                    [{"dataset_name": "Długi opis zbioru danych " * 12}]
                )
                table = dialog.services_table
                table.setColumnWidth(0, 600)
                wait_until(lambda: not dialog._row_resize_timer.isActive())
                wide_height = table.rowHeight(0)
                table.setColumnWidth(0, 180)
                wait_until(lambda: not dialog._row_resize_timer.isActive())
                self.assertGreater(table.rowHeight(0), wide_height)
                message = (
                    "Nie udało się pobrać ewidencji z API GUGiK.\n\n"
                    "Nie można połączyć się z serwerem.\n"
                    "Sprawdź połączenie internetowe."
                )
                dialog.push_message_over_table(message, "Błąd katalogu")
                wait_until(lambda: not dialog._row_resize_timer.isActive())
                self.assertEqual(dialog.model.item(0, 0).text(), message)
                self.assertGreater(
                    table.rowHeight(0), table.fontMetrics().height() * 3
                )
            finally:
                dialog.close()

    def test_row_numbers_follow_visible_order_after_sorting_and_filtering(
        self,
    ):
        dialog = self.plugin.dlg
        dialog.fill_services_table(
            [
                {"dataset_name": "Zebra", "url": "z"},
                {"dataset_name": "Alfa", "url": "a"},
                {"dataset_name": "Beta", "url": "b"},
            ]
        )
        vertical = QtCompat.get_enum(Qt, "Orientation", "Vertical")
        descending = QtCompat.get_enum(Qt, "SortOrder", "DescendingOrder")
        for column in range(4):
            dialog.services_table.sortByColumn(column, descending)
            self.assertEqual(
                [
                    dialog.proxy_model.headerData(row, vertical)
                    for row in range(dialog.proxy_model.rowCount())
                ],
                [1, 2, 3],
            )
        dialog.search_lineedit.setText("Alfa")
        self.assertEqual(dialog.proxy_model.headerData(0, vertical), 1)
        self.assertEqual(dialog.proxy_model.index(0, 1).data(), "a")

    def test_inline_panel_adds_only_checked_layers_without_modal_dialog(self):
        dialog = self.plugin.dlg
        loader = dialog.content_manager.ogc_service
        definitions = [
            LayerDefinition("uri", name, "wms", "raster", name, name)
            for name in ("Drogi", "Budynki")
        ]
        dialog.content_manager.cache_services(
            "WMS", [{"dataset_name": "Map", "url": "url"}]
        )
        with (
            patch(
                f"{GUI_PACKAGE}.layer_panel.AddOGCService.fetch_definitions",
                return_value=definitions,
            ),
            patch.object(loader, "create_layers") as create,
            patch.object(
                loader, "add_services", return_value={"Drogi": True}
            ) as add,
            patch("qgis.PyQt.QtWidgets.QDialog.exec") as modal,
        ):
            dialog.show()
            dialog.services_table.selectRow(0)
            wait_until(lambda: bool(dialog.layer_panel._definitions))
            self.assertFalse(dialog.add_btn.isEnabled())
            dialog.layer_panel.tree.topLevelItem(0).child(0).setCheckState(
                0, QtCompat.get_enum(Qt, "CheckState", "Checked")
            )
            self.assertTrue(dialog.add_btn.isEnabled())
            dialog.add_btn.click()
            create.assert_called_once_with(
                "Map", "url", "WMS", [definitions[0]]
            )
            add.assert_called_once_with({"url": ["Drogi"]})
            modal.assert_not_called()
            self.assertIn(
                "Dodano warstwy: 1", dialog.layer_panel.status.text()
            )

    def test_immediate_reload_does_not_reuse_toolbar_pending_deletion(self):
        self.plugin.initGui()
        self.assertEqual(len(self.iface.actions), 1)
        self.plugin.unload()
        replacement = classFactory(self.iface)
        replacement.initGui()
        try:
            deferred = QtCompat.get_enum(QEvent, "Type", "DeferredDelete")
            QGIS_APP.sendPostedEvents(None, deferred)
            self.assertEqual(replacement.toolbar.objectName(), PLUGIN_NAME)
            self.assertEqual(len(replacement.toolbar.actions()), 1)
        finally:
            replacement.unload()
            replacement.unload()
        self.assertEqual(self.iface.actions, [])

    def test_reopened_dialog_receives_application_palette_changes(self):
        dialog = self.plugin.dlg
        original_palette = QPalette(QGIS_APP.palette())
        window = QtCompat.get_enum(QPalette, "ColorRole", "Window")
        foreground = QtCompat.get_enum(QPalette, "ColorRole", "WindowText")
        with (
            patch.object(dialog, "setup_table"),
            patch.object(dialog.territorial_selector, "start"),
            patch.object(dialog, "_system_dark_mode", return_value=None),
        ):
            try:
                dialog.show()
                dialog.close()
                dialog.show()
                for background, dark, label_color, status_color, arrow in (
                    ("#202020", True, "#bdc4a5", "#d6d8ce", "light"),
                    ("#ffffff", False, "#626749", "#505447", "dark"),
                ):
                    palette = QPalette(original_palette)
                    palette.setColor(window, QColor(background))
                    QGIS_APP.setPalette(palette)
                    QGIS_APP.processEvents()
                    self.assertEqual(dialog._theme_is_dark, dark)
                    self.assertIn(
                        f"/icons/combo_arrow_{arrow}.svg", dialog.styleSheet()
                    )
                    for label in (
                        dialog.province_label,
                        dialog.county_label,
                        dialog.commune_label,
                    ):
                        self.assertEqual(
                            label.palette().color(foreground).name(),
                            label_color,
                        )
                    self.assertEqual(
                        dialog.layer_status.palette().color(foreground).name(),
                        status_color,
                    )
                for widget in (
                    dialog.province_label,
                    dialog.county_label,
                    dialog.commune_label,
                    dialog.layer_status,
                    dialog.province_combo,
                    dialog.county_combo,
                    dialog.commune_combo,
                ):
                    self.assertEqual(
                        widget.font().pointSizeF(),
                        QGIS_APP.font().pointSizeF(),
                    )
                for combo in (
                    dialog.province_combo,
                    dialog.county_combo,
                    dialog.commune_combo,
                ):
                    self.assertEqual(
                        combo.view().font().pointSizeF(),
                        combo.font().pointSizeF(),
                    )
            finally:
                QGIS_APP.setPalette(original_palette)
