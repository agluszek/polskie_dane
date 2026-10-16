from __future__ import annotations

import re

from ..core.constants import SERVICES_REQUEST_TIMEOUT_SECONDS
from ..core.network import NetworkUtils

UNITS_API_URL = "https://uldk.gugik.gov.pl/service.php"
UNIT_ENDPOINTS = ("wojewodztwo", "powiat", "gmina")
UNIT_CODE_PATTERNS = (r"[0-9]{2}", r"[0-9]{4}", r"[0-9]{6}_[1-9]")


class AdministrativeUnitsFetcher:
    def __init__(self, network: NetworkUtils | None = None) -> None:
        self.network = network if network is not None else NetworkUtils()

    def fetch_units(
        self,
        level: int,
        parent_code: str = "",
    ) -> list[dict[str, str]]:
        if level not in range(3):
            raise ValueError("Niepoprawny poziom jednostki administracyjnej.")
        if level and not re.fullmatch(
            UNIT_CODE_PATTERNS[level - 1], parent_code
        ):
            raise ValueError("Niepoprawny kod TERYT jednostki nadrzędnej.")
        unit_type = UNIT_ENDPOINTS[level]
        params = {"obiekt": unit_type, "wynik": f"{unit_type},teryt"}
        if level:
            params["teryt"] = parent_code
        success, content = self.network.fetch_content(
            UNITS_API_URL,
            params=params,
            timeout_ms=SERVICES_REQUEST_TIMEOUT_SECONDS * 1000,
        )
        if not success:
            raise ValueError(
                "Nie udało się pobrać listy jednostek z API GUGiK (ULDK). "
                + (content or "Brak odpowiedzi serwera. Spróbuj ponownie.")
            )
        lines = content.lstrip("\ufeff").strip().splitlines()
        if not lines or lines[0].strip() != "0":
            raise ValueError("Niepoprawna odpowiedź listy jednostek ULDK.")
        units = {}
        for line in lines[1:]:
            if not line.strip():
                continue
            name, separator, code = line.strip().partition("|")
            if not separator:
                raise ValueError("Niepoprawny wpis na liście jednostek ULDK.")
            code = code.strip()
            if (
                not re.fullmatch(UNIT_CODE_PATTERNS[level], code)
                or not name.strip()
                or (level and not code.startswith(parent_code))
            ):
                raise ValueError("Niepoprawna nazwa lub kod TERYT jednostki.")
            units[code] = {"teryt": code, "name": name.strip()}
        return sorted(units.values(), key=lambda unit: unit["name"].casefold())
