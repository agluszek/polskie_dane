from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from qgis.PyQt.QtCore import QObject, pyqtSignal

from ..core.task_manager import SingleTaskManager
from ..services.administrative_units import AdministrativeUnitsFetcher

if TYPE_CHECKING:
    from .dialog import PolskieDaneDialog


class TerritorialSelector(QObject):
    area_changed = pyqtSignal(str)

    def __init__(self, ui: PolskieDaneDialog) -> None:
        super().__init__(ui)
        self.view = ui.territorial_groupbox
        self._active = False
        self._cache: dict[tuple[int, str], list[dict[str, str]]] = {}
        self._wanted_request: tuple[int, str] | None = None
        self._running_request: tuple[int, str] | None = None
        self._failed_request: tuple[int, str] | None = None
        self.combos = [ui.province_combo, ui.county_combo, ui.commune_combo]
        self._placeholders = tuple(combo.itemText(0) for combo in self.combos)
        for level, combo in enumerate(self.combos):
            self._reset_combo(level)
            combo.currentIndexChanged.connect(
                partial(self._selection_changed, level)
            )
        self.retry_btn = ui.territorial_retry_btn
        self.retry_btn.clicked.connect(self.retry)
        self.retry_btn.hide()
        self.task = SingleTaskManager(
            self._fetch_units,
            self._finish_request,
            "Pobieranie jednostek TERYT",
        )

    def selected_teryt(self) -> str:
        return next(
            (
                combo.currentData()
                for combo in reversed(self.combos)
                if combo.currentData()
            ),
            "PL",
        )

    def start(self) -> None:
        self._active = True
        for level in range(len(self.combos)):
            parent_code = (
                "" if level == 0 else self.combos[level - 1].currentData()
            )
            if level and not parent_code:
                break
            if (level, parent_code) not in self._cache:
                self._request_units(level, parent_code)
                break

    def stop(self) -> None:
        self._active = False
        self._wanted_request = None
        self.task.cancel()

    def retry(self) -> None:
        if self._failed_request is not None:
            self._request_units(*self._failed_request)

    def _reset_combo(self, level: int) -> None:
        combo = self.combos[level]
        combo.blockSignals(True)
        try:
            combo.clear()
            combo.addItem(self._placeholders[level], None)
            combo.setEnabled(level == 0)
        finally:
            combo.blockSignals(False)

    def _selection_changed(self, level: int, index: int) -> None:
        self._wanted_request = None
        self._failed_request = None
        self.retry_btn.hide()
        self.task.cancel()
        for child in range(level + 1, 3):
            self._reset_combo(child)
        self.area_changed.emit(self.selected_teryt())
        code = self.combos[level].currentData()
        if level < 2 and code:
            self._request_units(level + 1, code)

    def _request_units(self, level: int, parent_code: str) -> None:
        self._wanted_request = (level, parent_code)
        self._failed_request = None
        self.retry_btn.hide()
        if self.task.is_running():
            self.task.cancel()
            return
        if self._wanted_request in self._cache:
            self._fill_combo(level, self._cache[self._wanted_request])
            return
        self._running_request = self._wanted_request
        if not self.task.run():
            self._show_error("Nie udało się rozpocząć pobierania jednostek.")

    def _fetch_units(self) -> list[dict[str, str]]:
        return AdministrativeUnitsFetcher().fetch_units(*self._running_request)

    def _finish_request(self) -> None:
        if not self._active:
            return
        if self._wanted_request != self._running_request:
            if self._wanted_request is not None:
                self._request_units(*self._wanted_request)
            return
        if self.task.was_canceled:
            self._request_units(*self._wanted_request)
            return
        if self.task.last_error is not None:
            self._show_error(str(self.task.last_error))
            return
        self._cache[self._running_request] = self.task.result
        self._fill_combo(self._running_request[0], self.task.result)

    def _fill_combo(self, level: int, units: list[dict[str, str]]) -> None:
        self._reset_combo(level)
        combo = self.combos[level]
        combo.blockSignals(True)
        try:
            for unit in units:
                combo.addItem(
                    f"{unit['name']} ({unit['teryt']})", unit["teryt"]
                )
            combo.setEnabled(True)
        finally:
            combo.blockSignals(False)

    def _show_error(self, message: str) -> None:
        self._failed_request = self._wanted_request
        self.retry_btn.setToolTip(f"Nie udało się pobrać jednostek: {message}")
        self.retry_btn.show()
