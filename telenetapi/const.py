"""The constants for telenetapi."""

from .models import TelenetEnvironment

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36"
TIMEOUT = 10
DEFAULT_LANGUAGE = "en"
LANGUAGES = ["en", "nl", "fr"]
DEFAULT_TELENET_ENVIRONMENT = TelenetEnvironment(
    ocapi="https://api.prd.telenet.be/ocapi",
    ocapi_public="https://api.prd.telenet.be/ocapi/public",
    ocapi_public_api="https://api.prd.telenet.be/ocapi/public/api",
    ocapi_oauth="https://api.prd.telenet.be/ocapi/oauth",
    openid="https://login.prd.telenet.be/openid",
    referer="https://www2.telenet.be/residential/nl/mijn-telenet",
    x_alt_referer="https://www2.telenet.be/",
)

BASE_HEADERS = {
    "User-Agent": USER_AGENT,
    "Referer": DEFAULT_TELENET_ENVIRONMENT.referer,
    "x-alt-referer": DEFAULT_TELENET_ENVIRONMENT.x_alt_referer,
}
