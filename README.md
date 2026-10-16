# Polskie dane

[Polski](#polski) · [English](#english)

## Polski

**Polskie dane** to wtyczka QGIS ułatwiająca wyszukiwanie polskich usług
danych przestrzennych i dodawanie ich warstw do projektu. Zapewnia dostęp
do **ewidencji zbiorów i usług danych przestrzennych (EZiUDP)**: pobiera
z jej API nazwy zbiorów, identyfikatory IIP, organy zgłaszające i adresy
usług **WMS, WMTS, WFS i WCS**. Usługi można wyszukiwać po nazwie zbioru
oraz filtrować według województwa, powiatu lub gminy.

### EZiUDP i źródła danych

EZiUDP prowadzi **Główny Geodeta Kraju** na podstawie art. 13
[ustawy z 4 marca 2010 r. o infrastrukturze informacji przestrzennej](https://eli.gov.pl/eli/DU/2010/489/ogl),
wdrażającej do polskiego prawa
[dyrektywę INSPIRE 2007/2/WE](https://eur-lex.europa.eu/legal-content/PL/TXT/?uri=CELEX:32007L0002).
Wtyczka korzysta z tej ewidencji przez
[API EZiUDP GUGiK](https://integracja.gugik.gov.pl/eziudp/api.php).
Nazwy i kody jednostek administracyjnych pobiera z
[ULDK GUGiK](https://uldk.gugik.gov.pl/).

Wyniki są pobierane na bieżąco i przechowywane w pamięci na czas pracy
wtyczki. Wtyczka nie zawiera kompletnej lokalnej kopii ewidencji.
Zakres wyników zależy od wpisów udostępnianych przez API, a dostępność
warstw od serwerów poszczególnych dostawców. Warstwy są dodawane
z adresu wybranej usługi; warunki korzystania z danych określa ich dostawca.
**Polskie dane jest niezależnym projektem i nie jest oficjalnym produktem
GUGiK.**

### Możliwości

- Przeglądanie usług WMS, WMTS, WFS i WCS z EZiUDP oraz wyszukiwanie
  po nazwie zbioru.
- Filtrowanie obszaru według kodu TERYT: cała Polska → województwo →
  powiat → gmina. Listy jednostek są pobierane z ULDK po wybraniu
  jednostki nadrzędnej, a filtrowanie zbiorów odbywa się w API EZiUDP.
- Tabela z nazwą zbioru, adresem usługi, identyfikatorem IIP i organem
  zgłaszającym, z możliwością sortowania, zawijaniem nazw zbiorów
  i zapamiętywaniem szerokości kolumn w profilu QGIS.
- Sprawdzanie dostępnych warstw w tle przez GetCapabilities,
  wyszukiwanie i wybór warstw w panelu bocznym oraz dodawanie ich do QGIS.
- Odświeżanie wyników dla wybranego obszaru, ponawianie nieudanych
  sprawdzeń i komunikaty o wyniku dodawania warstw.
- Dopasowanie wyglądu okna do jasnego lub ciemnego motywu aplikacji.

### Wymagania i instalacja

- QGIS **3.28 lub nowszy z serii 3.x albo QGIS 4.x** z obsługą wtyczek Python.
- Pakiety **requests**, **lxml** i **OWSLib** w środowisku Python używanym
  przez QGIS. Mogą być już dostarczone z instalacją QGIS; wtyczka nie instaluje
  ich automatycznie. Instalator wtyczek QGIS nie pobiera pakietów z PyPI.
- Połączenie internetowe z `integracja.gugik.gov.pl`, `uldk.gugik.gov.pl`
  oraz serwerem wybranej usługi. Wtyczka nie wymaga konta ani klucza API
  do pobierania ewidencji i list jednostek; usługi dostawców mogą mieć
  własne ograniczenia dostępu.

#### Sprawdzenie i instalacja zależności

Przed włączeniem wtyczki otwórz w QGIS **Wtyczki → Konsola Pythona**
i wykonaj kolejno:

```python
import requests
from lxml import etree
from owslib.wms import WebMapService
```

Jeżeli importy kończą się bez błędu, zależności są dostępne. Gdy pojawi się
`ModuleNotFoundError`, zainstaluj brakujący pakiet w **Pythonie QGIS**.
Pakiet instalowany jako `OWSLib` jest importowany pod nazwą `owslib`.
Zwykły Python systemowy, Anaconda lub osobna instalacja z python.org
mogą korzystać z innego środowiska.

- **Windows:** otwórz **OSGeo4W Shell** należący do tej samej instalacji
  QGIS i uruchom:

  ```bat
  python -m pip install --user requests lxml OWSLib
  ```

- **Linux, Debian/Ubuntu z QGIS z pakietów systemowych:** użyj pakietów
  dystrybucji:

  ```bash
  sudo apt install python3-requests python3-lxml python3-owslib
  ```

  Instalacje Flatpak, kontenerowe i inne izolowane dystrybucje mają własne
  środowiska; pakiety zainstalowane w systemie mogą być w nich niedostępne.
- **macOS:** użyj interpretera dołączonego do swojej dystrybucji QGIS,
  zgodnie z jej instrukcją instalowania pakietów Python. W nowszych pakietach
  może to być `QGIS.app/Contents/MacOS/python`; ścieżka i nazwa aplikacji
  zależą od instalacji. Wywołaj ten interpreter z argumentami
  `-m pip install --user requests lxml OWSLib`.

W razie wątpliwości porównaj `import sys; print(sys.prefix)` w konsoli QGIS
z wynikiem w terminalu wybranego Pythona. Nie zmieniaj bibliotek PyQt,
GDAL ani samego QGIS przy instalacji tych zależności. Po instalacji pakietów
uruchom ponownie QGIS i powtórz sprawdzenie importów.
Informacje o dystrybucjach: [oficjalna instrukcja instalacji QGIS](https://qgis.org/resources/installation-guide/).

#### Instalacja wtyczki z ZIP

1. Pobierz przygotowane archiwum `polskie_dane.zip` lub utwórz je
   z kodu źródłowego zgodnie z instrukcją poniżej.
2. W QGIS otwórz **Wtyczki → Zarządzanie wtyczkami → Zainstaluj z ZIP**
   i wskaż archiwum.
3. W zakładce **Zainstalowane** włącz **Polskie dane**.
4. Uruchom wtyczkę z menu **Wtyczki → Polskie dane** lub paska narzędzi.
   Po aktualizacji istniejącej instalacji uruchom ponownie QGIS.

Przy instalacji ręcznej otwórz **Ustawienia → Profile użytkownika →
Otwórz folder aktywnego profilu** i umieść katalog `polskie_dane`
w `python/plugins`. Archiwum wydania zawiera ten katalog na najwyższym
poziomie. Archiwum źródeł pobrane przyciskiem GitHub „Download ZIP”
nie zastępuje paczki instalacyjnej.

### Korzystanie

1. Wybierz typ usługi WMS, WMTS, WFS lub WCS. Opcjonalnie wpisz fragment nazwy
   zbioru w wyszukiwarce.
2. W sekcji **Obszar usług (TERYT)** wybierz województwo, a następnie
   opcjonalnie powiat i gminę. Zmiana jednostki nadrzędnej czyści wybory
   podrzędne. Wyniki dotyczą najdokładniej wybranego obszaru.
3. Kliknij rekord w tabeli. Wtyczka pobierze opis **GetCapabilities**
   i sprawdzi dostępne warstwy.
4. Przy jednej warstwie kliknij **Dodaj**. Przy kilku warstwach zaznacz
   potrzebne pozycje w panelu bocznym i kliknij **Dodaj**. Panel umożliwia
   wyszukiwanie i zaznaczanie widocznych warstw; jego szerokość zmienisz
   przez przeciągnięcie separatora.
5. Ponowne kliknięcie zaznaczonego rekordu lub **Esc** odznacza usługę
   i anuluje jej sprawdzanie. **Ponów** pozwala powtórzyć nieudane sprawdzenie.
6. **Odśwież** ponownie pobiera zbiory dla bieżącego obszaru.
   Przełączanie rodzaju usługi korzysta z wyników zapamiętanych w pamięci.

Szerokości kolumn są zapisywane przy zamknięciu okna wtyczki i odtwarzane
po ponownym uruchomieniu QGIS w tym samym profilu. Odświeżanie katalogu
ani wyświetlenie komunikatu nie nadpisują wybranego układu. Pełne wartości
komórek są dostępne w podpowiedziach po najechaniu kursorem.

### Rozwiązywanie problemów

| Objaw | Co zrobić |
| --- | --- |
| `ModuleNotFoundError` przy włączaniu wtyczki | Sprawdź zależności w konsoli QGIS i zainstaluj brakujący pakiet według instrukcji powyżej. |
| API GUGiK nie odpowiada lub zwraca błąd HTTP | Sprawdź połączenie internetowe i ustawienia proxy QGIS. Jeśli połączenie działa, spróbuj ponownie później. Listy jednostek ponawiaj przyciskiem ponowienia w sekcji TERYT, a katalog przyciskiem **Odśwież**. |
| Wybrana usługa nie udostępnia warstw | Sprawdź jej adres i komunikat dostawcy. Przycisk **Ponów** powtarza sprawdzenie GetCapabilities. |
| Błąd certyfikatu SSL/TLS | Sprawdź certyfikat serwera oraz konfigurację zaufanych certyfikatów w QGIS. Weryfikacja TLS pozostaje włączona. |
| Brak usług dla obszaru lub rodzaju usługi | Wybierz szerszy obszar lub inny typ usługi. Pusty wynik ewidencji nie musi oznaczać awarii. |

W razie dalszych problemów otwórz panel **Komunikaty dziennika** w QGIS
(**Widok → Panele**) i sprawdź wpisy w zakładce **Polskie dane**.

### Rozwój i przygotowanie paczki

```bash
git clone https://github.com/agluszek/polskie_dane.git polskie_dane
cd polskie_dane
python3 scripts/package_plugin.py
```

Gotowe archiwum: `dist/polskie_dane.zip`. Skrypt pakuje pliki potrzebne
do działania wtyczki, pomijając testy i narzędzia deweloperskie.

Kod jest podzielony na:

```text
__init__.py       punkt wejścia QGIS
plugin.py         cykl życia wtyczki i akcje menu
core/             sieć, zadania, komunikaty, stałe i zgodność Qt
services/         EZiUDP, jednostki administracyjne i usługi OGC
gui/              okno, tabela, wybór obszaru i panel warstw
resources/        formularze, style i ikony
test/             testy automatyczne
scripts/          narzędzia przygotowania paczki
```

Testy wymagają instalacji QGIS z jego modułami Python. Użyj interpretera
systemowego dostarczonego z QGIS; pakiet `qgis` nie jest instalowany przez
`pip`. Dla linuksowego środowiska z QGIS w `/usr` można przygotować
środowisko wirtualne obok katalogu repozytorium:

```bash
/usr/bin/python3 -m venv --system-site-packages ../.venv
../.venv/bin/python -m pip install requests lxml OWSLib ruff==0.16.10
QT_QPA_PLATFORM=offscreen QGIS_PREFIX_PATH=/usr PYTHONDONTWRITEBYTECODE=1 \
  ../.venv/bin/python -m unittest discover -s test -t .. -v
../.venv/bin/ruff check .
../.venv/bin/ruff format --check .
```

Testy automatyczne korzystają z odpowiedzi testowych; działanie usług
publicznych trzeba sprawdzić osobno w QGIS.

### Zgłoszenia i licencja

Problemy i propozycje zmian zgłaszaj w
[GitHub Issues](https://github.com/agluszek/polskie_dane/issues).
Podaj wersję QGIS, system operacyjny, rodzaj i adres usługi, komunikat
błędu oraz kroki potrzebne do odtworzenia problemu.

Autorka: **Aleksandra Głuszek**. Historia zmian: [CHANGELOG.md](CHANGELOG.md).

Licencja: [GPL-3.0](LICENSE). Informacje o autorach i pochodzeniu kodu:
[NOTICE.md](NOTICE.md).

## English

**Polskie dane** is a QGIS plugin for discovering Polish spatial data
services and adding their layers to a project. It provides access to
**EZiUDP, the Polish register of spatial datasets and services**, retrieving
dataset names, spatial information infrastructure identifiers, reporting
authorities and **WMS, WMTS, WFS and WCS** service URLs from its API.
Search by dataset name and filter by voivodeship, county or municipality.

### Registry and data sources

The **Surveyor General of Poland** maintains EZiUDP under Article 13 of the
[Polish Act of 4 March 2010 on Spatial Information Infrastructure](https://eli.gov.pl/eli/DU/2010/489/ogl),
which implements the
[INSPIRE Directive 2007/2/EC](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32007L0002).
The plugin queries the
[GUGiK EZiUDP API](https://integracja.gugik.gov.pl/eziudp/api.php).
Administrative unit names and TERYT codes come from
[GUGiK ULDK](https://uldk.gugik.gov.pl/).

Results are retrieved online and cached in memory while the plugin runs.
The plugin does not include a complete local copy of the register.
Search results depend on the API records, and layer availability depends
on each service provider. Layers connect to the selected service URL;
the provider's terms govern use of its data.
**Polskie dane is an independent project, not an official GUGiK product.**

### Features

- Browse WMS, WMTS, WFS and WCS services from EZiUDP and search by dataset name.
- Filter by TERYT administrative codes: Poland → voivodeship → county →
  municipality. Unit lists load from ULDK after their parent is selected;
  the EZiUDP API filters datasets by area.
- View dataset names, service URLs, dataset identifiers and reporting
  authorities in a sortable table with wrapped dataset names and column widths
  saved in the QGIS user profile.
- Check GetCapabilities in the background, search and select layers
  in a side panel, and add selected layers to QGIS.
- Refresh the current area, retry failed checks and view layer addition results.
- Use light and dark styling matched to the application theme.

### Requirements and installation

- QGIS **3.28 or later in the 3.x series, or QGIS 4.x**, with Python plugin support.
- **requests**, **lxml** and **OWSLib** installed in the Python environment
  used by QGIS. Some QGIS distributions already include them. The plugin
  does not install them automatically, and the QGIS plugin installer does
  not download Python packages from PyPI.
- Internet access to `integracja.gugik.gov.pl`, `uldk.gugik.gov.pl` and each
  selected service endpoint. Registry and administrative unit requests
  need no account or API key; individual providers may restrict their services.

#### Check and install dependencies

Before enabling the plugin, open **Plugins → Python Console** in QGIS
and run these imports one by one:

```python
import requests
from lxml import etree
from owslib.wms import WebMapService
```

Successful imports mean the dependencies are available. For a
`ModuleNotFoundError`, install the missing package into **QGIS's Python**.
The package installed as `OWSLib` is imported as `owslib`. System Python,
Anaconda and python.org installations may use a different environment.

- **Windows:** open the **OSGeo4W Shell** belonging to the same QGIS installation:

  ```bat
  python -m pip install --user requests lxml OWSLib
  ```

- **Linux, Debian/Ubuntu with a system-package QGIS installation:** use distribution packages:

  ```bash
  sudo apt install python3-requests python3-lxml python3-owslib
  ```

  Flatpak, containers and other isolated distributions have their own
  environments; host-system packages may not be available inside them.
- **macOS:** use the Python interpreter bundled with your QGIS distribution,
  following that distribution's package installation instructions. In newer
  bundles it may be `QGIS.app/Contents/MacOS/python`; the location and app name
  vary. Invoke that interpreter with the arguments
  `-m pip install --user requests lxml OWSLib`.

To check the environment, compare `import sys; print(sys.prefix)` in QGIS
with the output from your chosen terminal interpreter. Do not replace PyQt,
GDAL or QGIS itself when installing these dependencies. Restart QGIS after
installation and repeat the imports.
See the [official QGIS installation guide](https://qgis.org/resources/installation-guide/)
for distribution information.

#### Install the plugin from ZIP

1. Obtain a prepared `polskie_dane.zip` or build it from the source as shown below.
2. Open **Plugins → Manage and Install Plugins → Install from ZIP** in QGIS
   and select the archive.
3. Enable **Polskie dane** on the **Installed** tab.
4. Launch it through **Plugins → Polskie dane** or the toolbar.
   Restart QGIS after updating an existing installation.

For manual installation, use **Settings → User Profiles → Open Active
Profile Folder** and place `polskie_dane` in `python/plugins`.
A release ZIP contains this directory at its top level. The GitHub
“Download ZIP” source archive is not an installation package.

### Usage

1. Select service type WMS, WMTS, WFS or WCS and optionally search by dataset name.
2. Choose a voivodeship, then optionally a county and municipality in
   **Obszar usług (TERYT)**. Changing a parent clears its child selections.
   The most specific selected unit determines the area filter.
3. Click a table row to retrieve its **GetCapabilities** document
   and check available layers.
4. For a single layer, click **Dodaj** (Add). For multiple layers, select
   the required entries in the side panel and click **Dodaj**. Use the
   search field, select visible entries or drag the splitter to resize the panel.
5. Click the selected row again or press **Esc** to clear the selection
   and cancel the check. Use **Ponów** (Retry) after a failed check.
6. **Odśwież** (Refresh) reloads datasets for the current area.
   Switching service types reuses the results cached in memory.

Column widths are saved when the plugin window closes and restored after
restarting QGIS with the same user profile. Refreshing the catalog or showing
a status message preserves the chosen widths. Hover over cells to see their
full values in tooltips.

### Troubleshooting

| Symptom | Action |
| --- | --- |
| `ModuleNotFoundError` when enabling the plugin | Check the imports in the QGIS console and install the missing dependency as described above. |
| GUGiK API timeout or HTTP error | Check Internet connectivity and QGIS proxy settings. If connectivity works, retry later. Use the retry button in the TERYT section for unit lists, or **Odśwież** for the catalog. |
| A selected service returns no layers | Check its URL and the provider's error message. **Ponów** retries the GetCapabilities check. |
| SSL/TLS certificate error | Check the server certificate and QGIS trusted CA configuration. TLS verification stays enabled. |
| No services for the selected area or service type | Choose a broader area or a different service type. An empty registry result does not necessarily mean a failure. |

For further details, open the **Log Messages** panel (**View → Panels**)
and check the **Polskie dane** tab.

### Development and packaging

```bash
git clone https://github.com/agluszek/polskie_dane.git polskie_dane
cd polskie_dane
python3 scripts/package_plugin.py
```

The output is `dist/polskie_dane.zip`. The packaging script includes runtime
files and excludes tests and development tools. Source directories separate
shared helpers (`core/`), data services (`services/`), the interface (`gui/`)
and assets (`resources/`).

Tests require an installed QGIS Python environment. On Linux with QGIS
under `/usr`, create a virtual environment using `/usr/bin/python3` and
`--system-site-packages`, then run the commands in the Polish development
section. Do not install QGIS through `pip`.

### Issues and license

Report problems through
[GitHub Issues](https://github.com/agluszek/polskie_dane/issues),
including the QGIS version, operating system, service type and URL,
error message and steps to reproduce the issue.

Author: **Aleksandra Głuszek**. Version history: [CHANGELOG.md](CHANGELOG.md).

License: [GPL-3.0](LICENSE). Credits and source attribution:
[NOTICE.md](NOTICE.md).
