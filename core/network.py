from __future__ import annotations

import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from urllib.parse import quote, urlsplit

import requests
from qgis.core import QgsBlockingNetworkRequest, QgsNetworkAccessManager
from qgis.PyQt.QtCore import QUrl, QUrlQuery
from qgis.PyQt.QtNetwork import QNetworkRequest

from .constants import (
    ENCODING_SYSTEM,
    MAX_ATTEMPTS,
    MSG_EMPTY_CONTENT,
    TIMEOUT_MS,
    USER_AGENT_HEADER,
)
from .qt_compat import QtCompat


class NetworkUtils:
    def fetch_content(
        self,
        url: str,
        params: Mapping[str, str | int] | None = None,
        timeout_ms: int = TIMEOUT_MS,
    ) -> tuple[bool, str]:
        request_url = QUrl(url)
        if params:
            query = QUrlQuery(request_url)
            for key, value in params.items():
                query.addQueryItem(str(key), str(value))
            request_url.setQuery(query)
        request = QNetworkRequest(request_url)
        request.setAttribute(
            QtCompat.get_enum(
                QNetworkRequest, "Attribute", "RedirectPolicyAttribute"
            ),
            QtCompat.get_enum(
                QNetworkRequest, "RedirectPolicy", "NoLessSafeRedirectPolicy"
            ),
        )
        if hasattr(request, "setTransferTimeout"):
            request.setTransferTimeout(timeout_ms)
        blocking_request = QgsBlockingNetworkRequest()
        error = blocking_request.get(request)
        no_error = QtCompat.get_enum(
            QgsBlockingNetworkRequest, "ErrorCode", "NoError"
        )
        if error != no_error:
            return self._fetch_content_with_requests(url, params, timeout_ms)
        content = bytes(blocking_request.reply().content())
        if not content:
            return False, MSG_EMPTY_CONTENT.format(url)
        try:
            return True, content.decode(ENCODING_SYSTEM)
        except UnicodeDecodeError:
            return False, f"Serwer zwrócił dane inne niż tekstowe: {url}"

    @staticmethod
    def _create_requests_session() -> requests.Session:
        session = requests.Session()
        session.headers["User-Agent"] = USER_AGENT_HEADER
        proxy = QgsNetworkAccessManager.instance().proxy()
        if proxy.hostName():
            credentials = ""
            if proxy.user():
                username = quote(proxy.user(), safe="")
                password = quote(proxy.password(), safe="")
                credentials = f"{username}:{password}@"
            proxy_url = (
                f"http://{credentials}{proxy.hostName()}:{proxy.port()}"
            )
            session.proxies = {"http": proxy_url, "https": proxy_url}
        return session

    def _fetch_content_with_requests(
        self,
        url: str,
        params: Mapping[str, str | int] | None = None,
        timeout_ms: int = TIMEOUT_MS,
    ) -> tuple[bool, str]:
        try:
            with self._requests_get(url, params, timeout_ms) as response:
                response.raise_for_status()
                if not response.content:
                    return False, MSG_EMPTY_CONTENT.format(url)
                return True, response.text
        except requests.exceptions.RequestException as error:
            return self._handle_requests_error(error, url)

    @contextmanager
    def _requests_get(
        self,
        url: str,
        params: Mapping[str, str | int] | None = None,
        timeout_ms: int = TIMEOUT_MS,
    ) -> Iterator[requests.Response]:
        with self._create_requests_session() as session:
            with session.get(
                url, params=params, timeout=timeout_ms / 1000, verify=True
            ) as response:
                yield response

    @staticmethod
    def _handle_requests_error(
        error: requests.exceptions.RequestException,
        url: str = "",
    ) -> tuple[bool, str]:
        host = urlsplit(url).hostname or "nieznany serwer"
        is_gugik = host == "gugik.gov.pl" or host.endswith(".gugik.gov.pl")
        server = (
            f"Serwer API GUGiK ({host})" if is_gugik else f"Serwer ({host})"
        )
        retry = "Spróbuj ponownie za chwilę."
        if isinstance(error, requests.exceptions.Timeout):
            message = f"{server} nie odpowiedział w wymaganym czasie.\n{retry}"
        elif isinstance(error, requests.exceptions.SSLError):
            message = (
                f"Nie udało się nawiązać bezpiecznego połączenia SSL "
                f"z serwerem {host}. Sprawdź certyfikat i ustawienia sieci."
            )
        elif isinstance(error, requests.exceptions.HTTPError):
            status = (
                error.response.status_code
                if error.response is not None
                else "nieznany"
            )
            message = f"{server} zwrócił błąd HTTP: {status}.\n{retry}"
        elif isinstance(error, requests.exceptions.ConnectionError):
            message = (
                f"Nie można połączyć się z serwerem {host}.\n"
                "Sprawdź połączenie internetowe.\n"
                f"Jeśli działa, serwer może być niedostępny.\n{retry}"
            )
        else:
            message = f"Nie udało się pobrać danych z serwera {host}. {retry}"
        return False, message


class ServiceAPI:
    def __init__(self, network: NetworkUtils | None = None) -> None:
        self.network_utils = network if network is not None else NetworkUtils()

    def get_request(
        self,
        url: str,
        params: Mapping[str, str | int] | None = None,
    ) -> tuple[bool, str]:
        for attempt in range(MAX_ATTEMPTS):
            result = self.network_utils.fetch_content(
                url, params=params, timeout_ms=TIMEOUT_MS * 2
            )
            if result[0]:
                return result
            if attempt < MAX_ATTEMPTS - 1:
                time.sleep(2)
        return result
