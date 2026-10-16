from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING

from qgis.PyQt.QtCore import QObject, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import QTreeWidgetItem

from ..core.qt_compat import QtCompat
from ..core.task_manager import SingleTaskManager
from ..services.add_service import AddOGCService, LayerDefinition

if TYPE_CHECKING:
    from .dialog import PolskieDaneDialog


class LayerSelectionPanel(QObject):
    selection_changed = pyqtSignal()

    def __init__(self, ui: PolskieDaneDialog) -> None:
        super().__init__(ui)
        self.view = ui.layer_groupbox
        self._active = False
        self._wanted: tuple[str, tuple[tuple[str, str], ...]] | None = None
        self._running: tuple[str, tuple[tuple[str, str], ...]] | None = None
        self._definitions: dict[str, tuple[str, list[LayerDefinition]]] = {}
        self._user_canceled = False
        self.search = ui.layer_search
        self.select_all = ui.layer_select_all
        self.cancel_btn = ui.layer_cancel_btn
        self.retry_btn = ui.layer_retry_btn
        self.status = ui.layer_status
        self.tree = ui.layer_tree
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self._load)
        self.task = SingleTaskManager(
            self._fetch, self._finish, "Sprawdzanie dostępnych warstw"
        )
        self.search.textChanged.connect(self._filter)
        self.select_all.clicked.connect(self._select_visible)
        self.tree.itemChanged.connect(self._selection_changed)
        self.cancel_btn.clicked.connect(self._cancel)
        self.retry_btn.clicked.connect(self._load)
        self.view.hide()

    def start(self) -> None:
        self._active = True
        if self._wanted and not self._definitions:
            self.timer.start()

    def has_service_selection(self) -> bool:
        return self._wanted is not None

    def stop(self) -> None:
        self._active = False
        self.timer.stop()
        self.task.cancel()

    def set_services(
        self,
        services: Mapping[str, str],
        service_type: str,
    ) -> None:
        request = (
            (service_type, tuple(sorted(services.items())))
            if services
            else None
        )
        if request == self._wanted:
            return
        self._wanted = request
        self.task.cancel()
        self._definitions.clear()
        self.tree.clear()
        self.select_all.setChecked(False)
        self.search.clear()
        self.view.hide()
        self.cancel_btn.hide()
        self.retry_btn.hide()
        self.timer.stop()
        if request:
            self.status.setText("Sprawdzanie dostępnych warstw…")
            self.timer.start()
        self.selection_changed.emit()

    def _load(self) -> None:
        if not self._active or not self._wanted or self.task.is_running():
            return
        self._definitions.clear()
        self.tree.clear()
        self.view.hide()
        self.select_all.setChecked(False)
        self.selection_changed.emit()
        self._running = self._wanted
        self._user_canceled = False
        self.status.setText("Sprawdzanie dostępnych warstw…")
        self.retry_btn.hide()
        self.cancel_btn.show()
        if not self.task.run():
            self.status.setText("Nie udało się rozpocząć sprawdzania warstw.")
            self.retry_btn.show()

    def _fetch(self) -> list[tuple[str, str, list[LayerDefinition]]]:
        service_type, services = self._running
        result = []
        for url, name in services:
            if self.task.task_instance.isCanceled():
                break
            definitions = AddOGCService.fetch_definitions(
                name, url, service_type
            )
            result.append((url, name, definitions))
        return result

    def _finish(self) -> None:
        if not self._active:
            return
        if self._running != self._wanted:
            self._load()
            return
        self.cancel_btn.hide()
        if self.task.was_canceled or self.task.last_error:
            if not self._user_canceled and self.task.was_canceled:
                self._load()
                return
            self.status.setText(
                "Sprawdzanie anulowane."
                if self.task.was_canceled
                else f"Nie udało się sprawdzić warstw: {self.task.last_error}"
            )
            self.retry_btn.show()
            self.selection_changed.emit()
            return
        missing = []
        role = QtCompat.get_enum(Qt, "ItemDataRole", "UserRole")
        unchecked = QtCompat.get_enum(Qt, "CheckState", "Unchecked")
        checked = QtCompat.get_enum(Qt, "CheckState", "Checked")
        self.tree.blockSignals(True)
        try:
            for url, name, definitions in self.task.result:
                if not definitions:
                    missing.append(name)
                    continue
                self._definitions[url] = name, definitions
                group = QTreeWidgetItem(self.tree, [name])
                for definition in definitions:
                    item = QTreeWidgetItem(group, [definition.title])
                    item.setData(0, role, (url, definition.layer_id))
                    item.setCheckState(
                        0, checked if len(definitions) == 1 else unchecked
                    )
                group.setExpanded(True)
        finally:
            self.tree.blockSignals(False)
        self.status.setText(
            "Wybierz warstwy do dodania do projektu."
            if not missing
            else "Brak warstw lub błąd usługi: " + ", ".join(missing)
        )
        self.retry_btn.setVisible(bool(missing))
        count = sum(len(rows) for _, rows in self._definitions.values())
        self.view.setVisible(count > 1)
        if count == 1 and not missing:
            self.status.setText("Jedna warstwa — gotowa do dodania.")
        self._filter(self.search.text())

    def _items(self) -> Iterator[QTreeWidgetItem]:
        for position in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(position)
            for child in range(group.childCount()):
                yield group.child(child)

    def selected_definitions(
        self,
    ) -> dict[str, tuple[str, list[LayerDefinition]]]:
        role = QtCompat.get_enum(Qt, "ItemDataRole", "UserRole")
        checked = QtCompat.get_enum(Qt, "CheckState", "Checked")
        selected = {}
        for item in self._items():
            if item.checkState(0) == checked:
                url, layer_id = item.data(0, role)
                selected.setdefault(url, set()).add(layer_id)
        return {
            url: (
                name,
                [
                    definition
                    for definition in definitions
                    if definition.layer_id in selected.get(url, ())
                ],
            )
            for url, (name, definitions) in self._definitions.items()
            if selected.get(url)
        }

    def _filter(self, text: str) -> None:
        text = text.casefold()
        for item in self._items():
            item.setHidden(
                text not in item.text(0).casefold()
                and text not in item.parent().text(0).casefold()
            )
        for position in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(position)
            group.setHidden(
                all(
                    group.child(child).isHidden()
                    for child in range(group.childCount())
                )
            )
        self._selection_changed()

    def _select_visible(self, checked: bool) -> None:
        state = QtCompat.get_enum(
            Qt, "CheckState", "Checked" if checked else "Unchecked"
        )
        self.tree.blockSignals(True)
        try:
            for item in self._items():
                if not item.isHidden():
                    item.setCheckState(0, state)
        finally:
            self.tree.blockSignals(False)
        self._selection_changed()

    def _selection_changed(self) -> None:
        checked = QtCompat.get_enum(Qt, "CheckState", "Checked")
        visible = [item for item in self._items() if not item.isHidden()]
        self.select_all.setChecked(
            bool(visible)
            and all(item.checkState(0) == checked for item in visible)
        )
        self.selection_changed.emit()

    def _cancel(self) -> None:
        self._user_canceled = True
        self.task.cancel()
