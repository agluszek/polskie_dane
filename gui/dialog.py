from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from qgis.core import QgsSettings
from qgis.PyQt import QtWidgets, uic
from qgis.PyQt.QtCore import QEvent, QObject, Qt, QTimer, pyqtSlot
from qgis.PyQt.QtGui import (
    QCloseEvent,
    QKeyEvent,
    QMouseEvent,
    QPalette,
    QShowEvent,
    QStandardItem,
    QStandardItemModel,
)
from qgis.PyQt.QtWidgets import QTableView

from ..core.constants import RADIOBUTTONS_SERVICES
from ..core.messages import MessageUtils
from ..core.qt_compat import QtCompat
from ..core.task_manager import SingleTaskManager
from ..services.content_manager import ContentManager
from .layer_panel import LayerSelectionPanel
from .table_model import (
    NumberedRowsProxyModel,
    WrappedNameDelegate,
    wrapped_name_height,
)
from .territorial_selector import TerritorialSelector

COLUMN_WIDTHS_KEY = "PolskieDane/catalogColumnWidths"

RESOURCE_DIR = Path(__file__).resolve().parents[1] / "resources"
FORM_CLASS, _ = uic.loadUiType(str(RESOURCE_DIR / "forms" / "polskie_dane.ui"))


class PolskieDaneDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setupUi(self)
        self._theme_is_dark = None
        self._apply_app_theme()
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.paletteChanged.connect(self._apply_app_theme)
        self.is_window_shown = False
        self._selected_service_type = "WMS"
        self._selected_teryt = "PL"
        self.content_manager = ContentManager(self)
        self.table_setup_task = SingleTaskManager(
            self._fetch_services, self._finish_table_setup, "Pobieranie usług"
        )
        self.model = QStandardItemModel(self)
        self.proxy_model = NumberedRowsProxyModel(self)
        self.configure_table()
        self.refresh_btn.clicked.connect(self.refresh_catalog)
        self.territorial_selector = TerritorialSelector(self)
        self.territorial_selector.area_changed.connect(self._area_changed)
        self.finished.connect(self._stop_tasks)
        self.layer_panel = LayerSelectionPanel(self)
        self.layer_state.hide()
        self.layer_panel.selection_changed.connect(self._update_layer_state)
        self.services_table.selectionModel().selectionChanged.connect(
            self._services_selected
        )
        self.proxy_model.modelAboutToBeReset.connect(
            self._clear_service_selection
        )
        self.setup_signals()

    @staticmethod
    def _system_dark_mode() -> bool | None:
        """Read macOS appearance when Qt's application palette remains light.

        Returns None on platforms where the system preference is unavailable.
        """
        if sys.platform != "darwin":
            return None
        try:
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True,
                text=True,
                timeout=1.5,
                check=False,
            )
            if result.returncode == 0:
                return result.stdout.strip().lower() == "dark"
            return False
        except (OSError, subprocess.TimeoutExpired):
            return None

    @pyqtSlot()
    def _apply_app_theme(self) -> None:
        """Apply explicit colors to every widget, including on macOS."""
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        color = app.palette().color(
            QtCompat.get_enum(QPalette, "ColorRole", "Window")
        )
        brightness = (
            0.2126 * color.red()
            + 0.7152 * color.green()
            + 0.0722 * color.blue()
        )
        dark = brightness < 128
        mac_dark = self._system_dark_mode()
        if mac_dark is not None:
            dark = mac_dark
        if dark == self._theme_is_dark:
            return
        self._theme_is_dark = dark
        filename = "dark.qss" if dark else "light.qss"
        stylesheet = (RESOURCE_DIR / "styles" / filename).read_text(
            encoding="utf-8"
        )
        arrow = "combo_arrow_light.svg" if dark else "combo_arrow_dark.svg"
        arrow_path = (RESOURCE_DIR / "icons" / arrow).as_posix()
        stylesheet = stylesheet.replace("__COMBO_ARROW__", arrow_path)
        self.setStyleSheet(stylesheet)
        self.update()

    def configure_table(self) -> None:
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setFilterKeyColumn(0)
        self.proxy_model.setFilterCaseSensitivity(
            QtCompat.get_enum(Qt, "CaseSensitivity", "CaseInsensitive")
        )
        self._header_drag_active = False
        self._row_resize_pending = False
        self._settings = QgsSettings()
        self._catalog_widths = [320, 360, 220, 220]
        saved_widths = self._settings.value(COLUMN_WIDTHS_KEY, [])
        try:
            widths = [int(width) for width in saved_widths]
            if len(widths) == 4 and all(
                60 <= width <= 10000 for width in widths
            ):
                self._catalog_widths = widths
        except (TypeError, ValueError):
            pass
        self.services_table.setModel(self.proxy_model)
        self.services_table.setWordWrap(False)
        self.services_table.setVerticalScrollMode(
            QtCompat.get_enum(QTableView, "ScrollMode", "ScrollPerPixel")
        )
        self.services_table.setHorizontalScrollMode(
            QtCompat.get_enum(QTableView, "ScrollMode", "ScrollPerPixel")
        )
        self.services_table.setItemDelegateForColumn(
            0, WrappedNameDelegate(self.services_table)
        )
        self.services_table.verticalHeader().setSectionResizeMode(
            QtCompat.get_enum(
                QtWidgets.QHeaderView, "ResizeMode", "Interactive"
            )
        )
        self._row_resize_timer = QTimer(self)
        self._row_resize_timer.setSingleShot(True)
        self._row_resize_timer.setInterval(0)
        self._row_resize_timer.timeout.connect(self._resize_table_rows)
        for signal in (
            self.proxy_model.modelReset,
            self.proxy_model.rowsInserted,
            self.proxy_model.rowsRemoved,
            self.proxy_model.dataChanged,
            self.proxy_model.layoutChanged,
        ):
            signal.connect(self._schedule_row_resize)
        self.services_table.viewport().installEventFilter(self)
        header = self.services_table.horizontalHeader()
        header.viewport().installEventFilter(self)
        header.setResizeContentsPrecision(0)
        header.setSectionResizeMode(
            QtCompat.get_enum(
                QtWidgets.QHeaderView, "ResizeMode", "Interactive"
            )
        )
        header.sectionResized.connect(self._column_resized)
        self.services_table.verticalScrollBar().valueChanged.connect(
            self._schedule_row_resize
        )
        header.setDefaultSectionSize(220)
        header.resizeSection(0, 320)
        header.setMinimumSectionSize(60)
        header.setStretchLastSection(False)
        header.setDefaultAlignment(
            QtCompat.get_enum(Qt, "AlignmentFlag", "AlignCenter")
        )
        self.services_table.setSelectionBehavior(
            QtCompat.get_enum(QTableView, "SelectionBehavior", "SelectRows")
        )
        self.services_table.setSelectionMode(
            QtCompat.get_enum(QTableView, "SelectionMode", "SingleSelection")
        )
        self.services_table.setSortingEnabled(True)
        self.services_table.sortByColumn(
            0, QtCompat.get_enum(Qt, "SortOrder", "AscendingOrder")
        )
        self.fill_services_table()

    def _schedule_row_resize(self, *args: object) -> None:
        self._row_resize_pending = True
        if not self._header_drag_active:
            self._row_resize_timer.start()

    def _column_resized(self, column: int, *args: object) -> None:
        if column == 0:
            self._schedule_row_resize()

    def _resize_table_rows(self) -> None:
        table = self.services_table
        if self._header_drag_active:
            return
        self._row_resize_pending = False
        count = self.proxy_model.rowCount()
        if not count or not table.isVisible():
            return
        row = max(0, table.rowAt(0))
        width = max(1, table.columnWidth(0) - 12)
        font = table.font().toString()
        minimum = table.verticalHeader().defaultSectionSize()
        while row < count and table.rowViewportPosition(row) < (
            table.viewport().height()
        ):
            text = self.proxy_model.index(row, 0).data() or ""
            height = max(minimum, wrapped_name_height(text, width, font))
            if table.rowHeight(row) != height:
                table.setRowHeight(row, height)
            row += 1

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.services_table.horizontalHeader().viewport():
            if event.type() == QtCompat.get_enum(
                QEvent, "Type", "MouseButtonPress"
            ):
                self._header_drag_active = True
                self._row_resize_timer.stop()
            elif event.type() in (
                QtCompat.get_enum(QEvent, "Type", "MouseButtonRelease"),
                QtCompat.get_enum(QEvent, "Type", "Hide"),
                QtCompat.get_enum(QEvent, "Type", "UngrabMouse"),
            ):
                self._header_drag_active = False
                if self._row_resize_pending:
                    self._row_resize_timer.start()
        if (
            watched is self.services_table.viewport()
            and event.type() == QtCompat.get_enum(QEvent, "Type", "Resize")
        ):
            self._schedule_row_resize()
        if (
            watched is self.services_table.viewport()
            and self.services_table.isEnabled()
            and event.type()
            in (
                QtCompat.get_enum(QEvent, "Type", "MouseButtonPress"),
                QtCompat.get_enum(QEvent, "Type", "MouseButtonDblClick"),
            )
            and isinstance(event, QMouseEvent)
            and event.button()
            == QtCompat.get_enum(Qt, "MouseButton", "LeftButton")
            and event.modifiers()
            == QtCompat.get_enum(Qt, "KeyboardModifier", "NoModifier")
        ):
            position = (
                event.position().toPoint()
                if hasattr(event, "position")
                else event.pos()
            )
            index = self.services_table.indexAt(position)
            selection = self.services_table.selectionModel()
            if index.isValid() and selection.isRowSelected(
                index.row(), index.parent()
            ):
                selection.clear()
                self.services_table.setFocus()
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if (
            event.key() == QtCompat.get_enum(Qt, "Key", "Key_Escape")
            and self.services_table.isEnabled()
            and self.services_table.selectionModel().hasSelection()
        ):
            self.services_table.selectionModel().clear()
            event.accept()
            return
        super().keyPressEvent(event)

    def setup_dialog(self, plugin_name: str, plugin_version: str) -> None:
        title = f"{plugin_name} {plugin_version}"
        self.setWindowTitle(title)

    def setup_signals(self) -> None:
        for name in RADIOBUTTONS_SERVICES:
            getattr(self, name).toggled.connect(self._service_type_changed)
        self.search_lineedit.textChanged.connect(self.apply_search_filter)
        self.add_btn.clicked.connect(self.add_service)

    def refresh_catalog(self) -> None:
        if self.table_setup_task.is_running():
            return
        self.content_manager.invalidate_services(
            self.territorial_selector.selected_teryt()
        )
        self.setup_table()

    def _area_changed(self, teryt: str) -> None:
        self.table_setup_task.cancel()
        self.setup_table()

    def _service_type_changed(self, checked: bool) -> None:
        if checked:
            self.setup_table()

    def setup_table(self) -> None:
        if not self.is_window_shown or self.table_setup_task.is_running():
            return
        self._selected_service_type = self.get_selected_service_type()
        self._selected_teryt = self.territorial_selector.selected_teryt()
        if self.content_manager.has_cached_services(
            self._selected_service_type, self._selected_teryt
        ):
            self.set_busy(False)
            self._display_services(
                self.content_manager.get_cached_services(
                    self._selected_service_type, self._selected_teryt
                )
            )
            return
        self.set_busy(True)
        self.push_message_over_table("Pobieranie usług...", "Pobieranie")
        if not self.table_setup_task.run():
            self.push_message_over_table(
                "Nie udało się uruchomić pobierania we wtyczce. "
                "Spróbuj ponownie lub otwórz ponownie okno wtyczki.",
                "Nie rozpoczęto pobierania",
            )
            self.set_busy(False)

    def _fetch_services(self) -> list[dict[str, str]]:
        return self.content_manager.fetch_services(
            self._selected_service_type, self._selected_teryt
        )

    def _finish_table_setup(self) -> None:
        self.set_busy(False)
        if not self.is_window_shown:
            return
        if self.table_setup_task.was_canceled:
            self.setup_table()
            return
        if self.table_setup_task.last_error is not None:
            self.push_message_over_table(
                str(self.table_setup_task.last_error), "Błąd katalogu"
            )
            return
        rows = self.table_setup_task.result
        self.content_manager.cache_services(
            self._selected_service_type, rows, self._selected_teryt
        )
        self._display_services(rows)

    def _display_services(self, rows: list[dict[str, str]]) -> None:
        if rows:
            self.fill_services_table(rows)
        else:
            self.push_message_over_table(
                "Brak usług tego typu dla wybranego obszaru.", "Pusty katalog"
            )

    def apply_search_filter(self, text: str) -> None:
        self.proxy_model.setFilterFixedString(text)

    def _clear_service_selection(self) -> None:
        self.services_table.clearSelection()
        self.layer_panel.set_services({}, self.get_selected_service_type())

    def _services_selected(self) -> None:
        services = {
            self.proxy_model.index(
                index.row(), 1
            ).data(): self.proxy_model.index(index.row(), 0).data()
            for index in self.services_table.selectionModel().selectedRows()
        }
        self.layer_panel.set_services(
            services, self.get_selected_service_type()
        )

    def _update_layer_state(self) -> None:
        self.layer_state.setVisible(self.layer_panel.has_service_selection())
        self._update_add_button()

    def _update_add_button(self) -> None:
        self.add_btn.setEnabled(
            not self.table_setup_task.is_running()
            and not self.layer_panel.task.is_running()
            and bool(self.layer_panel.selected_definitions())
        )

    def add_service(self) -> None:
        selected = self.layer_panel.selected_definitions()
        if not selected:
            return
        self.set_busy(True)
        self.territorial_selector.view.setEnabled(False)
        self.layer_panel.view.setEnabled(False)
        loader = self.content_manager.ogc_service
        loader.clear_cache()
        try:
            for url, (name, definitions) in selected.items():
                loader.create_layers(
                    name, url, self.get_selected_service_type(), definitions
                )
            results = loader.add_services(
                {
                    url: [definition.layer_id for definition in definitions]
                    for url, (_, definitions) in selected.items()
                }
            )
            added = sum(results.values())
            self.layer_panel.status.setText(
                f"Dodano warstwy: {added}. Nie dodano: {len(results) - added}."
            )
        except (RuntimeError, ValueError) as error:
            MessageUtils.push_message_box_warning(
                self, "Nie udało się dodać warstwy", str(error)
            )
        finally:
            loader.clear_cache()
            self.territorial_selector.view.setEnabled(True)
            self.layer_panel.view.setEnabled(True)
            self.set_busy(False)

    def fill_services_table(
        self, rows: Sequence[dict[str, str]] | None = None
    ) -> None:
        self._remember_catalog_widths()
        model = QStandardItemModel(self)
        model.setColumnCount(4)
        model.setRowCount(len(rows or ()))
        model.setHorizontalHeaderLabels(
            [
                "Nazwa zbioru",
                "Adres usługi",
                "Identyfikator zbioru danych",
                "Organ zgłaszający",
            ]
        )
        for row, service in enumerate(rows or ()):
            for column, key in enumerate(
                (
                    "dataset_name",
                    "url",
                    "dataset_identifier",
                    "reporting_authority",
                )
            ):
                text = service.get(key) or "—"
                item = QStandardItem(text)
                item.setEditable(False)
                note = service.get("metadata_status") if column >= 2 else ""
                item.setToolTip(f"{text}\n{note}" if note else text)
                model.setItem(row, column, item)
        previous = self.model
        self.model = model
        self.proxy_model.setSourceModel(model)
        previous.deleteLater()
        header = self.services_table.horizontalHeader()
        header.setSectionResizeMode(
            QtCompat.get_enum(
                QtWidgets.QHeaderView, "ResizeMode", "Interactive"
            )
        )
        for column, width in enumerate(self._catalog_widths):
            header.resizeSection(column, width)
        self.apply_search_filter(self.search_lineedit.text())

    def _remember_catalog_widths(self) -> None:
        if self.model.columnCount() == 4:
            self._catalog_widths = [
                self.services_table.columnWidth(column) for column in range(4)
            ]

    def push_message_over_table(self, message: str, status: str = "") -> None:
        self._remember_catalog_widths()
        self.proxy_model.setFilterFixedString("")
        self.model.removeRows(0, self.model.rowCount())
        self.model.setColumnCount(2)
        self.model.setHorizontalHeaderLabels(["Komunikat", "Status"])
        items = [QStandardItem(message), QStandardItem(status)]
        for item in items:
            item.setFlags(QtCompat.get_enum(Qt, "ItemFlag", "NoItemFlags"))
        self.model.appendRow(items)
        header = self.services_table.horizontalHeader()
        header.setSectionResizeMode(
            0,
            QtCompat.get_enum(
                QtWidgets.QHeaderView, "ResizeMode", "Interactive"
            ),
        )
        header.resizeSection(0, 360)
        header.setSectionResizeMode(
            1,
            QtCompat.get_enum(
                QtWidgets.QHeaderView, "ResizeMode", "ResizeToContents"
            ),
        )
        self.add_btn.setEnabled(False)

    def set_busy(self, busy: bool) -> None:
        for name in RADIOBUTTONS_SERVICES:
            getattr(self, name).setEnabled(not busy)
        self.refresh_btn.setEnabled(not busy)
        self.services_table.setEnabled(not busy)
        if busy or not hasattr(self, "layer_panel"):
            self.add_btn.setEnabled(False)
        else:
            self._update_add_button()

    def get_selected_service_type(self) -> str:
        for name in RADIOBUTTONS_SERVICES:
            if getattr(self, name).isChecked():
                return name.removesuffix("_rdbtn").upper()
        return "WMS"

    def changeEvent(self, event: QEvent) -> None:
        if event.type() in (
            QtCompat.get_enum(QEvent, "Type", "ActivationChange"),
            QtCompat.get_enum(QEvent, "Type", "PaletteChange"),
        ):
            self._apply_app_theme()
        super().changeEvent(event)

    def showEvent(self, event: QShowEvent) -> None:
        self._apply_app_theme()
        super().showEvent(event)
        self.is_window_shown = True
        self.layer_panel.start()
        self.territorial_selector.start()
        self.setup_table()
        self.wms_rdbtn.setFocus()

    def _stop_tasks(self) -> None:
        self._remember_catalog_widths()
        self._settings.setValue(COLUMN_WIDTHS_KEY, self._catalog_widths)
        self.is_window_shown = False
        self.table_setup_task.cancel()
        self.territorial_selector.stop()
        self.layer_panel.stop()
        self.content_manager.ogc_service.cancel_tasks()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._stop_tasks()
        super().closeEvent(event)
