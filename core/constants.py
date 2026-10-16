from .. import PLUGIN_VERSION

ENCODING_SYSTEM = "utf-8"

USER_AGENT_HEADER = f"PolskieDane/{PLUGIN_VERSION}"
TIMEOUT_MS = 5000
MAX_ATTEMPTS = 3
SERVICES_REQUEST_TIMEOUT_SECONDS = 10
MSG_EMPTY_CONTENT = "Serwer zwrócił pustą zawartość dla: {}"
RADIOBUTTONS_SERVICES = (
    "wms_rdbtn",
    "wmts_rdbtn",
    "wfs_rdbtn",
    "wcs_rdbtn",
)
WCS_NAMESPACES = {
    "wcs": "http://www.opengis.net/wcs/2.0",
    "ows": "http://www.opengis.net/ows/2.0",
}
