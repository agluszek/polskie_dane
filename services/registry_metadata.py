from __future__ import annotations

import json
import re
from typing import TypedDict, cast
from urllib.parse import parse_qsl, urlsplit

from ..core.constants import SERVICES_REQUEST_TIMEOUT_SECONDS
from ..core.network import NetworkUtils

ServiceKey = tuple[str, str, tuple[tuple[str, str], ...]]


class RegistryDataset(TypedDict):
    idiip: str
    zbior: str
    organ: str
    uslugi: dict[str, list[str]]


REGISTRY_API_URL = "https://integracja.gugik.gov.pl/eziudp/api.php"


class RegistryMetadataFetcher:
    def __init__(self, network: NetworkUtils | None = None) -> None:
        self.network = network if network is not None else NetworkUtils()
        self._datasets_by_area: dict[str, list[RegistryDataset]] = {}

    def fetch_datasets(self, teryt: str) -> list[RegistryDataset]:
        if teryt in self._datasets_by_area:
            return self._datasets_by_area[teryt]
        datasets: list[RegistryDataset] = []
        seen_pages = set()
        page_size = 1000
        while True:
            success, content = self.network.fetch_content(
                REGISTRY_API_URL,
                params={
                    "teryt": "" if teryt == "PL" else teryt,
                    "result": "idiip,zbior,organ,uslugi",
                    "count": page_size,
                    "index": len(datasets),
                },
                timeout_ms=SERVICES_REQUEST_TIMEOUT_SECONDS * 1000,
            )
            if not success:
                raise ValueError(
                    f"Nie udało się pobrać ewidencji z API GUGiK.\n\n{content}"
                )
            try:
                payload = json.loads(content)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    "API GUGiK zwróciło niepoprawną odpowiedź ewidencji. "
                    "Spróbuj ponownie za chwilę."
                ) from error
            rows = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(rows, list):
                raise ValueError(
                    "API GUGiK zwróciło niepoprawną listę zbiorów w ewidencji."
                )
            for row in rows:
                if (
                    not isinstance(row, dict)
                    or not all(
                        isinstance(row.get(key), str) and row[key].strip()
                        for key in ("idiip", "zbior", "organ")
                    )
                    or not isinstance(row.get("uslugi"), dict)
                ):
                    raise ValueError(
                        "Niepoprawne metadane zbioru w ewidencji."
                    )
            signature = tuple(row["idiip"] for row in rows)
            if rows and signature in seen_pages:
                raise ValueError(
                    "Ewidencja zwróciła powtórzoną stronę wyników."
                )
            seen_pages.add(signature)
            datasets.extend(cast(list[RegistryDataset], rows))
            if len(rows) < page_size:
                self._datasets_by_area[teryt] = datasets
                return datasets

    def invalidate(self, teryt: str) -> None:
        self._datasets_by_area.pop(teryt, None)

    @staticmethod
    def service_key(url: str) -> ServiceKey | None:
        try:
            parts = urlsplit(url.strip())
        except ValueError:
            return None
        if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
            return None
        query = tuple(
            sorted(
                (key, value)
                for key, value in parse_qsl(
                    parts.query, keep_blank_values=True
                )
                if key.lower() not in ("service", "request", "version")
            )
        )
        return parts.netloc.lower(), parts.path, query

    @staticmethod
    def parse_service(address: str, category: str) -> tuple[str, str] | None:
        protocol, separator, url = address.strip().partition("=")
        supported = ("WMS", "WMTS", "WFS", "WCS")
        if separator and protocol.upper() in supported:
            service_type = protocol.upper()
            url = url.strip()
        else:
            url = address.strip()
            try:
                parts = urlsplit(url)
            except ValueError:
                return None
            declared = next(
                (
                    value.upper()
                    for key, value in parse_qsl(parts.query)
                    if key.lower() == "service"
                ),
                "",
            )
            match = re.search(
                r"(?:^|[/_.-])(wmts|wms|wfs|wcs)(?:$|[/_.-]|e\.php)",
                parts.path,
                re.IGNORECASE,
            )
            if declared:
                if declared not in supported:
                    return None
                service_type = declared
            elif match:
                service_type = match.group(1).upper()
            elif category == "przegladania":
                service_type = "WMS"
            elif category == "pobierania":
                path = parts.path.rstrip("/")
                if re.search(
                    r"(?:^|[/_.-])(?:atom|feed)(?:$|[/_.-])",
                    path,
                    re.IGNORECASE,
                ) or re.search(
                    r"\.(?!(?:php|cgi|asp|aspx|ashx)$)[^/.]+$",
                    path,
                    re.IGNORECASE,
                ):
                    return None
                service_type = "WFS"
            else:
                return None
        if RegistryMetadataFetcher.service_key(url) is None:
            return None
        return service_type, url

    def fetch_services(
        self, teryt: str, service_type: str
    ) -> list[dict[str, str]]:
        service_type = service_type.strip().upper()
        if service_type not in ("WMS", "WMTS", "WFS", "WCS"):
            raise ValueError("Nieobsługiwany rodzaj usługi.")
        rows = []
        seen = set()
        for dataset in self.fetch_datasets(teryt):
            for category in ("przegladania", "pobierania"):
                addresses = dataset["uslugi"].get(category, [])
                if not isinstance(addresses, list):
                    raise ValueError("Niepoprawna lista adresów w ewidencji.")
                for address in addresses:
                    if not isinstance(address, str):
                        raise ValueError(
                            "Niepoprawny adres usługi w ewidencji."
                        )
                    service = self.parse_service(address, category)
                    if service is None or service[0] != service_type:
                        continue
                    _, url = service
                    identity = dataset["idiip"], self.service_key(url)
                    if identity in seen:
                        continue
                    seen.add(identity)
                    rows.append(
                        {
                            "dataset_name": dataset["zbior"].strip(),
                            "service_type": service_type,
                            "url": url,
                            "dataset_identifier": dataset["idiip"].strip(),
                            "reporting_authority": dataset["organ"].strip(),
                        }
                    )
        return rows
