# Historia zmian / Changelog

## 1.0.0

### Polski

Pierwsza wersja wtyczki **Polskie dane** przygotowana do publikacji
w oficjalnym repozytorium wtyczek QGIS.

- Wyszukiwanie usług WMS, WMTS, WFS i WCS w ewidencji EZiUDP GUGiK.
- Kaskadowe filtrowanie według województwa, powiatu i gminy z listami ULDK.
- Nazwy zbiorów, adresy usług, identyfikatory IIP i organy zgłaszające w tabeli.
- Pobieranie katalogu i sprawdzanie GetCapabilities w tle.
- Wybór i dodawanie warstw z panelu bocznego, wyszukiwanie oraz ponawianie
  nieudanych sprawdzeń.
- Zawijanie nazw zbiorów, podpowiedzi z pełną treścią komórek i zapamiętywanie
  szerokości kolumn w profilu QGIS.
- Jasny i ciemny motyw oraz rozmiar czcionki zgodny z ustawieniami QGIS.
- Komunikaty wskazujące problemy połączenia i odpowiedzi API GUGiK.
- Obsługa QGIS 3.28+ z serii 3.x oraz QGIS 4.x.

### English

Initial **Polskie dane** version prepared for submission to the official
QGIS plugin repository.

- Discover WMS, WMTS, WFS and WCS services through the GUGiK EZiUDP registry.
- Filter by voivodeship, county and municipality using cascading ULDK lists.
- Display dataset names, service URLs, IIP identifiers and reporting authorities.
- Fetch catalogs and check GetCapabilities in background tasks.
- Search, select and add layers through the side panel, with retries after errors.
- Wrap dataset names, show full cell values in tooltips and persist column widths
  in the QGIS user profile.
- Light and dark themes with font sizes following QGIS settings.
- Report connection failures and GUGiK API response errors.
- Support QGIS 3.28+ in the 3.x series and QGIS 4.x.
