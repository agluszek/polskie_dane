import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

import requests
from qgis.PyQt.QtCore import QEventLoop, QTimer

from ..core.constants import MAX_ATTEMPTS
from ..core.network import NetworkUtils, ServiceAPI
from ..core.task_manager import SingleTaskManager
from .utilities import get_qgis_app

QGIS_APP = get_qgis_app()


class NetworkTest(unittest.TestCase):
    def test_native_qgis_request_preserves_query(self):
        received = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                received.append(self.path)
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, format, *args):
                pass

        network = NetworkUtils()
        with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with patch.object(
                    network,
                    "_fetch_content_with_requests",
                    side_effect=AssertionError("Native QGIS request failed"),
                ):
                    result = network.fetch_content(
                        f"http://127.0.0.1:{server.server_port}/?existing=1",
                        params={"name": "Łódź", "count": 1},
                        timeout_ms=2000,
                    )
                self.assertEqual(result, (True, "ok"))
                self.assertEqual(len(received), 1)
                path = received[0]
                self.assertEqual(
                    parse_qs(urlsplit(path).query),
                    {
                        "existing": ["1"],
                        "name": ["Łódź"],
                        "count": ["1"],
                    },
                )
            finally:
                server.shutdown()
                thread.join(timeout=3)

    def test_tls_verification_and_resource_cleanup(self):
        network = NetworkUtils()
        session = MagicMock()
        session.__enter__.return_value = session
        response = session.get.return_value.__enter__.return_value
        response.content = b"ok"
        response.text = "ok"
        with patch.object(
            network, "_create_requests_session", return_value=session
        ):
            self.assertEqual(
                network._fetch_content_with_requests("https://example.com"),
                (True, "ok"),
            )
        self.assertIs(session.get.call_args.kwargs["verify"], True)
        session.__exit__.assert_called_once()
        session.get.return_value.__exit__.assert_called_once()

    def test_certificate_error_is_reported(self):
        network = NetworkUtils()
        with patch.object(
            network,
            "_requests_get",
            side_effect=requests.exceptions.SSLError("invalid"),
        ):
            success, message = network._fetch_content_with_requests(
                "https://example.com"
            )
        self.assertFalse(success)
        self.assertIn("SSL", message)

    def test_retries_are_bounded_and_do_not_sleep_after_last_attempt(self):
        api = ServiceAPI()
        with patch.object(
            api.network_utils,
            "fetch_content",
            return_value=(False, "unavailable"),
        ) as fetch:
            with patch("time.sleep") as sleep:
                self.assertFalse(api.get_request("https://example.com")[0])
        self.assertEqual(fetch.call_count, MAX_ATTEMPTS)
        self.assertEqual(sleep.call_count, MAX_ATTEMPTS - 1)

    def test_http_failure_preserves_status(self):
        response = MagicMock(status_code=503)
        error = requests.exceptions.HTTPError(response=response)
        network = NetworkUtils()
        with patch.object(network, "_requests_get", side_effect=error):
            success, message = network._fetch_content_with_requests(
                "https://example.com"
            )
        self.assertFalse(success)
        self.assertIn("503", message)


class TaskTest(unittest.TestCase):
    def test_real_task_failure_reaches_completion_callback(self):
        loop = QEventLoop()
        error = RuntimeError("worker failure")

        def fail():
            raise error

        completed = []

        def finish():
            completed.append(True)
            loop.quit()

        manager = SingleTaskManager(main_func=fail, on_finish_func=finish)
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        with patch(
            f"{SingleTaskManager.__module__}.MessageUtils.log_critical"
        ) as log:
            self.assertTrue(manager.run())
            self.assertFalse(manager.run())
            timer.start(5000)
            loop.exec()
            timer.stop()
        self.assertEqual(completed, [True])
        self.assertIs(manager.last_error, error)
        self.assertFalse(manager.is_running())
        log.assert_called_once()
