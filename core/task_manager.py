from __future__ import annotations

from collections.abc import Callable
from typing import Generic, TypeVar

from qgis.core import QgsApplication, QgsTask

from .messages import MessageUtils

TaskResult = TypeVar("TaskResult")


class SingleTaskManager(Generic[TaskResult]):
    def __init__(
        self,
        main_func: Callable[[], TaskResult] | None = None,
        on_finish_func: Callable[[], None] | None = None,
        task_name: str = "processing",
    ) -> None:
        self.task_name = task_name
        self.task_instance: QgsTask | None = None
        self.task_func = main_func
        self.on_finish_func = on_finish_func
        self.last_error: Exception | None = None
        self.result: TaskResult | bool | None = None
        self.was_canceled = False
        self._cancel_requested = False

    def _task_func(self, task: QgsTask) -> TaskResult | bool:
        if task.isCanceled():
            return False
        return self.task_func()

    def _on_finish_func(
        self,
        exception: Exception | None,
        value: TaskResult | bool | None = None,
    ) -> None:
        self.last_error = exception
        self.result = value
        self.was_canceled = self._cancel_requested or (
            self.task_instance is not None and self.task_instance.isCanceled()
        )
        self.task_instance = None
        if exception is not None:
            log = (
                MessageUtils.log_warning
                if isinstance(exception, ValueError)
                else MessageUtils.log_critical
            )
            log(f"Błąd zadania: {exception}")
        if self.on_finish_func is not None:
            self.on_finish_func()

    def run(self) -> bool:
        if self.is_running():
            return False
        if self.task_func is None:
            return False
        self.last_error = None
        self.result = None
        self.was_canceled = False
        self._cancel_requested = False
        self.task_instance = QgsTask.fromFunction(
            self.task_name, self._task_func, on_finished=self._on_finish_func
        )
        QgsApplication.taskManager().addTask(self.task_instance)
        return True

    def is_running(self) -> bool:
        return self.task_instance is not None

    def cancel(self) -> None:
        if self.task_instance is not None:
            self._cancel_requested = True
            self.task_instance.cancel()
